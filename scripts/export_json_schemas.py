from __future__ import annotations

import json
from pathlib import Path

from meshflight_runtime.events import RuntimeEventEnvelope
from meshflight_schema import CompiledScenario, RunConfig, RunSnapshot, ScenarioSource
from pydantic import TypeAdapter


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "api" / "schemas"


def write_schema(name: str, payload: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{name}.schema.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    write_schema("scenario_source", ScenarioSource.model_json_schema())
    write_schema("compiled_scenario", CompiledScenario.model_json_schema())
    write_schema("run_config", RunConfig.model_json_schema())
    write_schema("run_snapshot", RunSnapshot.model_json_schema())
    write_schema("runtime_event", TypeAdapter(RuntimeEventEnvelope).json_schema())


if __name__ == "__main__":
    main()
