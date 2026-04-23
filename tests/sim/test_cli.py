# tests/sim/test_cli.py

from pathlib import Path

from services.sim_core.cli import infer_scenario_name, load_json, make_run_id, sanitize_name


def test_sanitize_name():
    assert sanitize_name("Bridge Reconnect") == "bridge-reconnect"
    assert sanitize_name("urban_obstacle_course") == "urban-obstacle-course"


def test_infer_scenario_name_from_compiled_path():
    path = Path("artifacts/scenarios/bridge-reconnect/compiled/compiled.json")
    assert infer_scenario_name(path) == "bridge-reconnect"


def test_infer_scenario_name_falls_back_to_stem():
    path = Path("compiled.json")
    assert infer_scenario_name(path) == "compiled"


def test_make_run_id_contains_scenario_name():
    path = Path("artifacts/scenarios/bridge-reconnect/compiled/compiled.json")
    run_id = make_run_id(path)

    assert run_id.startswith("run-bridge-reconnect-")


def test_load_json(tmp_path: Path):
    file_path = tmp_path / "sample.json"
    file_path.write_text('{"hello": "world"}', encoding="utf-8")

    data = load_json(file_path)

    assert data["hello"] == "world"