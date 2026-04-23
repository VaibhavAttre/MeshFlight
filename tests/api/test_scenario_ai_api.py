from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meshflight_api.main import app
from meshflight_api.ollama_client import OllamaClient, OllamaClientError
from meshflight_api.scenario_ai import GeminiScenarioProvider
from meshflight_api.scenario_plan import (
    MeshFlightScenarioPlanV1,
    ScenarioAIAssistRequest,
    merge_meshflight_plan_with_user_prompt,
    scenario_plan_to_source,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "scenarios"


def load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def make_editor_safe_scenario(payload: dict) -> dict:
    scenario = copy.deepcopy(payload)
    scenario["traffic_classes"] = []
    scenario["scheduled_traffic"] = []
    return scenario


def test_ai_assist_rejects_unsupported_prompt_without_provider(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    with TestClient(app) as client:
        response = client.post(
            "/api/scenarios/ai-assist",
            json={
                "mode": "generate",
                "prompt": "Create a 3D weather physics scenario with altitude-aware drones.",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["doable"] is False
    assert "2D scenarios" in payload["reason"]
    assert payload["scenario"] is None


def test_ai_assist_health_reports_available(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setattr(
        OllamaClient,
        "list_models",
        lambda self: ["qwen2.5-coder:7b"],
    )

    with TestClient(app) as client:
        response = client.get("/api/scenarios/ai-assist/health?provider=ollama")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["provider"] == "ollama"
    assert payload["baseUrl"] == "http://localhost:11434"
    assert payload["model"] == "qwen2.5-coder:7b"


def test_ai_assist_health_reports_missing_model(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setattr(
        OllamaClient,
        "list_models",
        lambda self: ["llama3.2:latest"],
    )

    with TestClient(app) as client:
        response = client.get("/api/scenarios/ai-assist/health?provider=ollama")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert "ollama pull qwen2.5-coder:7b" in payload["reason"]


def test_ai_assist_health_reports_missing_gemini_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with TestClient(app) as client:
        response = client.get("/api/scenarios/ai-assist/health?provider=gemini")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert "GEMINI_API_KEY" in payload["reason"]


def test_ai_assist_openai_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_AI_ASSIST_ENABLED", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with TestClient(app) as client:
        response = client.post(
            "/api/scenarios/ai-assist",
            json={
                "provider": "openai",
                "mode": "generate",
                "prompt": "Create a small emergency response scenario.",
            },
        )

    assert response.status_code == 503
    assert "disabled by default" in response.text


def test_ai_assist_update_returns_validated_existing_scenario_id(monkeypatch) -> None:
    scenario_payload = load_fixture("bridge_reconnect.json")

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setattr(
        OllamaClient,
        "chat_json",
        lambda self, *, model, system_prompt, user_prompt: {
            "kind": "meshflight_scenario_plan_v1",
            "version": 1,
            "request_mode": "update",
            "feasible": True,
            "summary": "Refresh the south-side demand pressure.",
            "title": "Bridge Reconnect Updated",
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scenarios/ai-assist",
            json={
                "provider": "ollama",
                "mode": "update",
                "prompt": "Add two demand zones near the south side.",
                "existing_scenario_id": scenario_payload["metadata"]["scenario_id"],
                "existing_scenario": scenario_payload,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["doable"] is True
    assert payload["scenario"]["metadata"]["scenario_id"] == "bridge-reconnect"
    assert payload["scenario"]["metadata"]["title"] == "Bridge Reconnect Updated"
    assert len(payload["scenario"]["demand_zones"]) == 2
    assert payload["scenario"]["demand_zones"][-1]["id"] == "demand-zone-2"


def test_ai_assist_invalid_model_payload_uses_repair_pass(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_chat_json(self, *, model, system_prompt, user_prompt):  # noqa: ANN001
        calls["count"] += 1
        if calls["count"] == 1:
            return {"not": "a plan"}

        return {
            "kind": "meshflight_scenario_plan_v1",
            "version": 1,
            "request_mode": "generate",
            "feasible": True,
            "summary": "Repaired after invalid JSON.",
            "counts": {
                "gateways": 1,
                "drones": 1,
                "clients": 1,
                "buildings": 0,
                "vegetation": 0,
                "demand_zones": 0,
            },
        }

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setattr(OllamaClient, "chat_json", fake_chat_json)

    with TestClient(app) as client:
        response = client.post(
            "/api/scenarios/ai-assist",
            json={
                "provider": "ollama",
                "mode": "generate",
                "prompt": "Create a small emergency response scenario.",
            },
        )

    assert response.status_code == 200
    assert response.json()["doable"] is True
    assert calls["count"] == 2


def test_ai_assist_retries_when_model_rejects_fixable_quality_issue(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_chat_json(self, *, model, system_prompt, user_prompt):  # noqa: ANN001
        calls["count"] += 1
        if calls["count"] == 1:
            return {"invalid": "plan"}

        return {
            "kind": "meshflight_scenario_plan_v1",
            "version": 1,
            "request_mode": "generate",
            "feasible": True,
            "summary": "Adjusted counts after repair pass.",
            "warnings": ["Adjusted spacing to avoid overlap."],
            "counts": {
                "gateways": 1,
                "drones": 2,
                "clients": 2,
            },
        }

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setattr(OllamaClient, "chat_json", fake_chat_json)

    with TestClient(app) as client:
        response = client.post(
            "/api/scenarios/ai-assist",
            json={
                "provider": "ollama",
                "mode": "generate",
                "prompt": "Create a small emergency response scenario.",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["doable"] is True
    assert "Adjusted counts after repair pass." in (payload.get("summary") or "")
    assert calls["count"] == 2


def test_ai_assist_runs_plan_repair_and_compiles_scenario(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_chat_json(self, *, model, system_prompt, user_prompt):  # noqa: ANN001
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "kind": "meshflight_scenario_plan_v1",
                "version": "1",
                "request_mode": "generate",
                "feasible": True,
            }
        return {
            "kind": "meshflight_scenario_plan_v1",
            "version": 1,
            "request_mode": "generate",
            "feasible": True,
            "summary": "Second attempt supplies counts.",
            "counts": {
                "gateways": 1,
                "drones": 1,
                "clients": 1,
            },
        }

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:3b")
    monkeypatch.setattr(OllamaClient, "chat_json", fake_chat_json)

    with TestClient(app) as client:
        response = client.post(
            "/api/scenarios/ai-assist",
            json={
                "provider": "ollama",
                "mode": "generate",
                "prompt": "Create a scenario and ensure it matches explicit constraints.",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["doable"] is True
    assert payload["ai_diagnostics"]["plan_repair_passes"] == 1
    assert calls["count"] == 2


def test_ai_assist_uses_multiple_repair_attempts_before_failing(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_chat_json(self, *, model, system_prompt, user_prompt):  # noqa: ANN001
        calls["count"] += 1
        return {
            "kind": "meshflight_scenario_plan_v1",
            "version": 1,
            "request_mode": "generate",
            "feasible": True,
            "counts": {"gateways": "not-a-number"},
        }

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:3b")
    monkeypatch.setenv("AI_ASSIST_ALLOW_SYNTHETIC_FALLBACK", "true")
    monkeypatch.setattr(OllamaClient, "chat_json", fake_chat_json)

    with TestClient(app) as client:
        response = client.post(
            "/api/scenarios/ai-assist",
            json={
                "provider": "ollama",
                "mode": "generate",
                "prompt": "Create a small emergency response scenario.",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["doable"] is True
    assert payload["scenario"]["metadata"]["schema_version"] == "0.1.0"
    assert calls["count"] == 4
    assert payload["ai_diagnostics"]["heuristic_prompt_fallback_used"] is True


def test_ai_assist_reports_provider_connectivity_issue(monkeypatch) -> None:
    def fake_chat_json(self, *, model, system_prompt, user_prompt):  # noqa: ANN001
        raise OllamaClientError("blocked")

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setattr(OllamaClient, "chat_json", fake_chat_json)

    with TestClient(app) as client:
        response = client.post(
            "/api/scenarios/ai-assist",
            json={
                "provider": "ollama",
                "mode": "generate",
                "prompt": "Create a small emergency response scenario.",
            },
        )

    assert response.status_code == 503
    assert "ollama pull qwen2.5-coder:7b" in response.text


def test_ai_assist_can_route_to_gemini(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        GeminiScenarioProvider,
        "complete_scenario_plan",
        lambda self, request: {
            "kind": "meshflight_scenario_plan_v1",
            "version": 1,
            "request_mode": "generate",
            "feasible": True,
            "summary": "Generated from Gemini.",
            "counts": {
                "gateways": 1,
                "drones": 1,
                "clients": 1,
            },
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scenarios/ai-assist",
            json={
                "provider": "gemini",
                "mode": "generate",
                "prompt": "Create a small emergency response scenario with 1 gateway, 1 drone, and 1 client.",
            },
        )

    assert response.status_code == 200
    assert response.json()["summary"] == "Generated from Gemini."


def test_ai_assist_ignores_stale_llm_counts_in_favor_of_user_prompt(monkeypatch) -> None:
    """LLM `counts` must not override explicit numbers in the user's text."""

    def fake_chat_json(self, *, model, system_prompt, user_prompt):  # noqa: ANN001
        return {
            "kind": "meshflight_scenario_plan_v1",
            "version": 1,
            "request_mode": "generate",
            "feasible": True,
            "summary": "Stale template.",
            "counts": {
                "gateways": 3,
                "drones": 9,
                "clients": 12,
                "buildings": 4,
                "vegetation": 4,
            },
        }

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setattr(OllamaClient, "chat_json", fake_chat_json)

    with TestClient(app) as client:
        response = client.post(
            "/api/scenarios/ai-assist",
            json={
                "provider": "ollama",
                "mode": "generate",
                "prompt": "make 1 drone, 1 client, and 1 gateway. 0 buildings and 0 vegetation.",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["doable"] is True
    scenario = payload["scenario"]
    assert len([e for e in scenario["entities"] if e["type"] == "gateway"]) == 1
    assert len([e for e in scenario["entities"] if e["type"] == "drone"]) == 1
    assert len([e for e in scenario["entities"] if e["type"] == "client"]) == 1
    assert len(scenario["obstacles"]) == 0


def test_scenario_plan_builder_emits_chaos_events() -> None:
    req = ScenarioAIAssistRequest(mode="generate", prompt="2 drones 4 clients 1 gateway")
    plan = MeshFlightScenarioPlanV1(
        request_mode="generate",
        feasible=True,
        summary="test",
        layout="gateway_left_drone_relay_clients_right",
    )
    plan = merge_meshflight_plan_with_user_prompt(plan, req.prompt)
    built = scenario_plan_to_source(req, plan)
    assert len(built.chaos_events) >= 1
    for ev in built.chaos_events:
        assert ev.target_entity_id in {e.id for e in built.entities}


def test_scenario_plan_builder_reproducible_with_fixed_seed() -> None:
    req = ScenarioAIAssistRequest(mode="generate", prompt="3 drones 6 clients 1 gateway")
    plan = MeshFlightScenarioPlanV1(
        request_mode="generate",
        feasible=True,
        summary="test",
        layout="compact_cluster",
        generation_seed=9_001_355,
    )
    plan = merge_meshflight_plan_with_user_prompt(plan, req.prompt)
    fixed_now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    a = scenario_plan_to_source(req, plan, now=fixed_now).model_dump(mode="json")
    b = scenario_plan_to_source(req, plan, now=fixed_now).model_dump(mode="json")
    assert a == b
