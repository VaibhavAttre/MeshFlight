from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from services.scenario_compiler.compiler import compile_scenario


ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "scenarios"
TMP_ROOT = ROOT / "artifacts" / "reports" / "test-compiler-temp"

def _local_temp_dir(name: str) -> Path:
    path = TMP_ROOT / f"{name}-{uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_compile_scenario_builds_rich_compiled_output() -> None:
    source_path = FIXTURES_DIR / "urban_obstacle_course.json"
    output_dir = _local_temp_dir("urban-obstacle-course")

    compiled, report = compile_scenario(
        source_path,
        output_dir=output_dir,
        write_outputs=True,
    )

    compiled_path = output_dir / "compiled.json"
    report_path = output_dir / "compile_report.json"
    copied_source_path = output_dir / "source.json"

    assert compiled.compilation_metadata.source_scenario_id == "urban-obstacle-course"
    assert compiled.obstacle_index
    assert compiled.candidate_graph_edges
    assert compiled.waypoint_candidates
    assert compiled.mobility_constraints
    assert compiled.runtime_schedule

    assert compiled_path.exists()
    assert report_path.exists()
    assert copied_source_path.exists()

    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_payload["scenario_id"] == "urban-obstacle-course"
    assert report_payload["counts"] == {
        "entities": 5,
        "normalized_entities": 5,
        "obstacles": 3,
        "obstacle_index_entries": 3,
        "candidate_graph_edges": 3,
        "waypoint_candidates": 18,
        "mobility_constraints": 2,
        "runtime_schedule_entries": 4,
        "traffic_classes": 1,
        "scheduled_traffic_events": 1,
        "chaos_events": 1,
    }
    assert len(compiled.obstacle_index) == 3
    assert len(compiled.candidate_graph_edges) == 3
    assert len(compiled.waypoint_candidates) == 18
    assert len(compiled.mobility_constraints) == 2
    assert len(compiled.runtime_schedule) == 4

    returned_output_dir = Path(report["output_dir"]).resolve()
    assert returned_output_dir == output_dir.resolve()


def test_compile_scenario_is_deterministic_for_same_source() -> None:
    source_path = FIXTURES_DIR / "bridge_reconnect.json"
    output_dir_one = _local_temp_dir("bridge-reconnect-first")
    output_dir_two = _local_temp_dir("bridge-reconnect-second")

    compiled_one, report_one = compile_scenario(
        source_path,
        output_dir=output_dir_one,
        write_outputs=False,
    )
    compiled_two, report_two = compile_scenario(
        source_path,
        output_dir=output_dir_two,
        write_outputs=False,
    )

    assert compiled_one.model_dump(mode="json") == compiled_two.model_dump(mode="json")
    assert report_one["counts"] == {
        "entities": 4,
        "normalized_entities": 4,
        "obstacles": 1,
        "obstacle_index_entries": 1,
        "candidate_graph_edges": 3,
        "waypoint_candidates": 18,
        "mobility_constraints": 2,
        "runtime_schedule_entries": 4,
        "traffic_classes": 1,
        "scheduled_traffic_events": 1,
        "chaos_events": 1,
    }
    assert report_two["counts"] == report_one["counts"]
    assert report_one["source_hash"] == report_two["source_hash"]
    assert report_one["config_hash"] == report_two["config_hash"]
