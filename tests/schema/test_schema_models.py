from __future__ import annotations

import json
from pathlib import Path

import pytest
from meshflight_runtime.events import RuntimeEventEnvelope
from meshflight_schema import CompiledScenario, RunConfig, RunSnapshot, ScenarioSource
from pydantic import TypeAdapter, ValidationError


ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_DIR = ROOT / "artifacts" / "scenarios"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_example_scenarios_validate() -> None:
    scenario_paths = sorted(SCENARIOS_DIR.glob("*.json"))
    assert scenario_paths

    for path in scenario_paths:
        scenario = ScenarioSource.model_validate(load_json(path))
        assert scenario.metadata.schema_version == "0.1.0"


def test_invalid_scenario_missing_schema_version_fails() -> None:
    payload = load_json(SCENARIOS_DIR / "bridge_reconnect.json")
    del payload["metadata"]["schema_version"]

    with pytest.raises(ValidationError):
        ScenarioSource.model_validate(payload)


def test_invalid_scenario_unknown_entity_reference_fails() -> None:
    payload = load_json(SCENARIOS_DIR / "bridge_reconnect.json")
    payload["traffic_classes"][0]["destination_entity_ids"] = ["gw-missing"]

    with pytest.raises(ValidationError, match="unknown entities"):
        ScenarioSource.model_validate(payload)


def test_invalid_scenario_out_of_bounds_entity_fails() -> None:
    payload = load_json(SCENARIOS_DIR / "bridge_reconnect.json")
    payload["entities"][0]["position"]["x"] = 9999

    with pytest.raises(ValidationError, match="outside map bounds"):
        ScenarioSource.model_validate(payload)


def test_compiled_scenario_contract_accepts_minimum_payload() -> None:
    payload = {
        "compilation_metadata": {
            "source_scenario_id": "bridge-reconnect",
            "source_hash": "abc123",
            "compiler_version": "0.1.0",
            "config_hash": "cfg123",
            "seed": 7,
            "generated_at": "2026-03-30T20:20:00Z",
        }
    }
    model = CompiledScenario.model_validate(payload)
    assert model.compilation_metadata.compiler_version == "0.1.0"


def test_run_config_contract_accepts_minimum_payload() -> None:
    payload = {
        "run_id": "run-001",
        "scenario_id": "bridge-reconnect",
        "seed": 7,
        "tick_interval_ms": 500,
        "snapshot_interval_ms": 2000,
        "max_runtime_s": 180,
        "baseline_policy_name": "reconnect-first",
    }
    model = RunConfig.model_validate(payload)
    assert model.tick_interval_ms == 500


def test_snapshot_contract_accepts_minimum_payload() -> None:
    payload = {
        "snapshot_id": "snap-001",
        "run_id": "run-001",
        "time_s": 5,
        "nodes": [],
        "links": [],
        "summary_metrics": {"connected_clients": 3},
    }
    model = RunSnapshot.model_validate(payload)
    assert model.summary_metrics["connected_clients"] == 3


def test_runtime_event_union_accepts_known_event() -> None:
    payload = {
        "event_id": "evt-001",
        "event_type": "policy_action_chosen",
        "run_id": "run-001",
        "emitted_at": "2026-03-30T20:20:00Z",
        "time_s": 12,
        "policy_name": "reconnect-first",
        "action": "move_drone",
        "affected_nodes": ["dr-1"],
    }
    event = TypeAdapter(RuntimeEventEnvelope).validate_python(payload)
    assert event.event_type == "policy_action_chosen"
