from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meshflight_api.main import app
from meshflight_api.ollama_client import OllamaClient, OllamaClientError
from meshflight_api.scenario_ai import GeminiScenarioProvider


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
    updated_payload = make_editor_safe_scenario(scenario_payload)
    updated_payload["metadata"]["title"] = "Bridge Reconnect Updated"
    updated_payload["demand_zones"].append(
        {
            "id": "demand-south",
            "label": "South Cluster",
            "center": {"x": 310, "y": 280},
            "radius_m": 90,
            "priority": 6,
        }
    )

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setattr(
        OllamaClient,
        "chat_json",
        lambda self, *, model, system_prompt, user_prompt: {
            "doable": True,
            "mode": "update",
            "scenario": updated_payload,
            "summary": "Added a new south-side demand zone.",
            "warnings": [],
            "reason": None,
            "suggested_prompt": None,
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scenarios/ai-assist",
            json={
                "provider": "ollama",
                "mode": "update",
                "prompt": "Add a new demand zone near the south side.",
                "existing_scenario_id": scenario_payload["metadata"]["scenario_id"],
                "existing_scenario": scenario_payload,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["doable"] is True
    assert payload["scenario"]["metadata"]["scenario_id"] == "bridge-reconnect"
    assert payload["scenario"]["metadata"]["title"] == "Bridge Reconnect Updated"
    assert payload["scenario"]["demand_zones"][-1]["id"] == "demand-south"


def test_ai_assist_invalid_model_payload_uses_repair_pass(monkeypatch) -> None:
    scenario_payload = make_editor_safe_scenario(load_fixture("bridge_reconnect.json"))
    calls = {"count": 0}

    def fake_chat_json(self, *, model, system_prompt, user_prompt):  # noqa: ANN001
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "doable": True,
                "mode": "generate",
                "scenario": {},
                "summary": "Generated something.",
                "warnings": [],
                "reason": None,
                "suggested_prompt": None,
            }

        return {
            "doable": True,
            "mode": "generate",
            "scenario": scenario_payload,
            "summary": "Generated a repaired scenario.",
            "warnings": [],
            "reason": None,
            "suggested_prompt": None,
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
    scenario_payload = make_editor_safe_scenario(load_fixture("bridge_reconnect.json"))
    calls = {"count": 0}

    def fake_chat_json(self, *, model, system_prompt, user_prompt):  # noqa: ANN001
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "doable": False,
                "mode": "generate",
                "scenario": None,
                "summary": None,
                "warnings": [],
                "reason": "The drones are too close to obstacles and spacing is unrealistic.",
                "suggested_prompt": "Please provide exact x/y metadata.",
            }

        return {
            "doable": True,
            "mode": "generate",
            "scenario": scenario_payload,
            "summary": "Adjusted spacing and generated defaults automatically.",
            "warnings": ["Adjusted spacing to avoid overlap."],
            "reason": None,
            "suggested_prompt": None,
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
    assert payload["warnings"] == ["Adjusted spacing to avoid overlap."]
    assert calls["count"] == 2


def test_ai_assist_runs_prompt_alignment_pass(monkeypatch) -> None:
    base_payload = make_editor_safe_scenario(load_fixture("bridge_reconnect.json"))
    aligned_payload = make_editor_safe_scenario(load_fixture("bridge_reconnect.json"))
    aligned_payload["metadata"]["title"] = "Bridge Reconnect Aligned"
    calls = {"count": 0}

    def fake_chat_json(self, *, model, system_prompt, user_prompt):  # noqa: ANN001
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "doable": True,
                "mode": "generate",
                "scenario": base_payload,
                "summary": "Generated base scenario.",
                "warnings": [],
                "reason": None,
                "suggested_prompt": None,
            }
        return {
            "doable": True,
            "mode": "generate",
            "scenario": aligned_payload,
            "summary": "Aligned scenario to user constraints.",
            "warnings": [],
            "reason": None,
            "suggested_prompt": None,
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
    assert payload["scenario"]["metadata"]["title"] == "Bridge Reconnect Aligned"
    assert calls["count"] == 2


def test_ai_assist_uses_multiple_repair_attempts_before_failing(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_chat_json(self, *, model, system_prompt, user_prompt):  # noqa: ANN001
        calls["count"] += 1
        return {
            "doable": True,
            "mode": "generate",
            "scenario": {"metadata": {"scenario_id": "bad"}},
            "summary": "broken",
            "warnings": [],
            "reason": None,
            "suggested_prompt": None,
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
    scenario_payload = make_editor_safe_scenario(load_fixture("bridge_reconnect.json"))

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        GeminiScenarioProvider,
        "complete_assist_response",
        lambda self, request: {
            "doable": True,
            "mode": "generate",
            "scenario": scenario_payload,
            "summary": "Generated from Gemini.",
            "warnings": [],
            "reason": None,
            "suggested_prompt": None,
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scenarios/ai-assist",
            json={
                "provider": "gemini",
                "mode": "generate",
                "prompt": "Create a small emergency response scenario.",
            },
        )

    assert response.status_code == 200
    assert response.json()["summary"] == "Generated from Gemini."
