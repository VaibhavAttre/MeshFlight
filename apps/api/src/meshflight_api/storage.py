from __future__ import annotations

import re
from pathlib import Path

from meshflight_schema import ScenarioSource
from services.scenario_compiler.compiler import compile_scenario


ROOT_DIR = Path(__file__).resolve().parents[4]
ARTIFACTS_DIR = ROOT_DIR / "artifacts" / "scenarios"


def ensure_storage_dirs() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def _slugify_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "untitled-scenario"


def scenario_dir(scenario_id: str) -> Path:
    return ARTIFACTS_DIR / scenario_id


def scenario_source_dir(scenario_id: str) -> Path:
    return scenario_dir(scenario_id) / "source"


def scenario_compiled_dir(scenario_id: str) -> Path:
    return scenario_dir(scenario_id) / "compiled"


def scenario_source_path(scenario_id: str) -> Path:
    return scenario_source_dir(scenario_id) / "scenario.json"


def compiled_scenario_bundle_path(scenario_id: str) -> Path:
    return scenario_compiled_dir(scenario_id) / "compiled.json"


def _model_to_json(model) -> str:
    return model.model_dump_json(indent=2)


def _existing_scenario_ids() -> set[str]:
    ensure_storage_dirs()
    ids: set[str] = set()

    for path in ARTIFACTS_DIR.iterdir():
        if not path.is_dir():
            continue
        if (path / "source" / "scenario.json").exists():
            ids.add(path.name)

    return ids


def _allocate_unique_identity(title: str) -> tuple[str, str]:
    base_title = title.strip() or "untitled-scenario"
    base_id = _slugify_name(base_title)
    existing_ids = _existing_scenario_ids()

    if base_id not in existing_ids:
        return base_id, base_title

    suffix = 2
    while True:
        scenario_id = f"{base_id}-{suffix}"
        scenario_title = f"{base_title} {suffix}"
        if scenario_id not in existing_ids:
            return scenario_id, scenario_title
        suffix += 1


def save_scenario_source(scenario: ScenarioSource) -> tuple[ScenarioSource, Path]:
    ensure_storage_dirs()

    existing_source_path = scenario_source_path(scenario.metadata.scenario_id)
    if existing_source_path.exists():
        scenario_id = scenario.metadata.scenario_id
        scenario_title = scenario.metadata.title.strip() or "untitled-scenario"
    else:
        scenario_id, scenario_title = _allocate_unique_identity(scenario.metadata.title)

    saved_scenario = scenario.model_copy(
        update={
            "metadata": scenario.metadata.model_copy(
                update={
                    "scenario_id": scenario_id,
                    "title": scenario_title,
                }
            )
        }
    )

    source_dir = scenario_source_dir(scenario_id)
    source_dir.mkdir(parents=True, exist_ok=True)
    path = scenario_source_path(scenario_id)
    path.write_text(_model_to_json(saved_scenario), encoding="utf-8")
    return saved_scenario, path


def load_scenario_source(scenario_id: str) -> ScenarioSource:
    ensure_storage_dirs()
    path = scenario_source_path(scenario_id)
    return ScenarioSource.model_validate_json(path.read_text(encoding="utf-8"))


def list_scenarios() -> list[dict[str, str | bool]]:
    ensure_storage_dirs()
    scenarios: list[dict[str, str | bool]] = []

    for scenario_path in sorted(ARTIFACTS_DIR.iterdir(), key=lambda item: item.name):
        if not scenario_path.is_dir():
            continue

        source_path = scenario_path / "source" / "scenario.json"
        if not source_path.exists():
            continue

        scenario = ScenarioSource.model_validate_json(source_path.read_text(encoding="utf-8"))
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

    compiled_dir = scenario_compiled_dir(scenario_id)
    _, report = compile_scenario(
        source_path,
        output_dir=compiled_dir,
        write_outputs=True,
    )
    output_dir = Path(report["output_dir"])

    return {
        "scenario_id": scenario_id,
        "source_path": str(source_path),
        "output_dir": str(output_dir),
        "compiled_path": str(output_dir / "compiled.json"),
        "report_path": str(output_dir / "compile_report.json"),
    }
