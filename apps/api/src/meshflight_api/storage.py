from __future__ import annotations

from pathlib import Path

from meshflight_schema import ScenarioSource
from services.scenario_compiler.compiler import compile_scenario


ROOT_DIR = Path(__file__).resolve().parents[4]
ARTIFACTS_DIR = ROOT_DIR / "artifacts" / "scenarios"
SOURCE_DIR = ARTIFACTS_DIR / "source"


def ensure_storage_dirs() -> None:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)


def scenario_source_path(scenario_id: str) -> Path:
    return SOURCE_DIR / f"{scenario_id}.scenario.json"


def compiled_output_dir(scenario_id: str) -> Path:
    return ARTIFACTS_DIR / scenario_id


def compiled_scenario_bundle_path(scenario_id: str) -> Path:
    return compiled_output_dir(scenario_id) / "compiled.json"


def _model_to_json(model) -> str:
    return model.model_dump_json(indent=2)


def save_scenario_source(scenario: ScenarioSource) -> Path:
    ensure_storage_dirs()
    path = scenario_source_path(scenario.metadata.scenario_id)
    path.write_text(_model_to_json(scenario), encoding="utf-8")
    return path


def load_scenario_source(scenario_id: str) -> ScenarioSource:
    ensure_storage_dirs()
    path = scenario_source_path(scenario_id)
    return ScenarioSource.model_validate_json(path.read_text(encoding="utf-8"))


def list_scenarios() -> list[dict[str, str | bool]]:
    ensure_storage_dirs()
    scenarios: list[dict[str, str | bool]] = []

    for path in sorted(SOURCE_DIR.glob("*.scenario.json")):
        scenario = ScenarioSource.model_validate_json(path.read_text(encoding="utf-8"))
        scenarios.append(
            {
                "scenario_id": scenario.metadata.scenario_id,
                "title": scenario.metadata.title,
                "updated_at": scenario.metadata.created_at,
                "has_compiled": compiled_scenario_bundle_path(scenario.metadata.scenario_id).exists(),
            }
        )

    return scenarios


def compile_saved_scenario(scenario_id: str) -> dict[str, str]:
    ensure_storage_dirs()
    source_path = scenario_source_path(scenario_id)
    if not source_path.exists():
        raise FileNotFoundError(f"Scenario not found: {scenario_id}")

    _, report = compile_scenario(source_path, write_outputs=True)
    output_dir = Path(report["output_dir"])

    return {
        "scenario_id": scenario_id,
        "source_path": str(source_path),
        "output_dir": str(output_dir),
        "compiled_path": str(output_dir / "compiled.json"),
        "report_path": str(output_dir / "compile_report.json"),
    }
