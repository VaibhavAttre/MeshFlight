# tests/sim/test_stage0e_pipeline.py
"""Stage 0E integration: compiled scenario → runner → snapshots, events, summary artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.scenario_compiler.compiler import compile_scenario
from services.sim_core.io import read_json, read_jsonl, write_simulation_outputs
from services.sim_core.runner import SimulationRunner

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "scenarios" / "bridge_reconnect.json"


def _node_status(snapshot: dict, node_id: str) -> str:
    for node in snapshot["nodes"]:
        if node["id"] == node_id:
            return str(node["status"])
    raise AssertionError(f"missing node {node_id}")


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture scenario missing")
def test_compiled_bridge_reconnect_scheduled_failure_and_disk_artifacts(tmp_path: Path) -> None:
    compile_out = tmp_path / "compiled"
    compiled, report = compile_scenario(
        FIXTURE,
        output_dir=compile_out,
        write_outputs=True,
    )

    assert report["counts"]["chaos_events"] >= 1
    assert len(compiled.runtime_schedule) >= 1

    runner = SimulationRunner(
        compiled_scenario=compiled,
        run_id="stage0e-e2e",
        duration_s=75.0,
        tick_duration_s=1.0,
        drone_speed_mps=18.0,
    )
    result = runner.run()

    assert len(result.snapshots) == 76
    assert result.summary["ticks_completed"] == 75
    assert result.summary["snapshots_written"] == 76
    assert result.summary["events_applied"] >= 1
    assert result.summary["final_failed_nodes"] >= 1
    assert result.summary["final_failed_drones"] >= 1

    assert _node_status(result.snapshots[44], "dr-2") == "active"
    assert _node_status(result.snapshots[45], "dr-2") == "failed"

    snap45 = result.snapshots[45]
    dr2_edges = [
        lk
        for lk in snap45["links"]
        if lk["source_id"] == "dr-2" or lk["target_id"] == "dr-2"
    ]
    assert dr2_edges == []

    failure_events = [e for e in result.events if e.target_id == "dr-2"]
    assert len(failure_events) >= 1

    runs_root = tmp_path / "runs"
    paths = write_simulation_outputs(
        result=result,
        run_config={
            "scenario_id": "bridge-reconnect",
            "run_id": result.run_id,
            "compiled_path": str(compile_out / "compiled.json"),
            "duration_s": 75.0,
            "tick_duration_s": 1.0,
            "drone_speed_mps": 18.0,
        },
        runs_root=runs_root,
    )

    snapshot_rows = read_jsonl(paths.snapshots_path)
    assert len(snapshot_rows) == 76

    event_rows = read_jsonl(paths.events_path)
    assert len(event_rows) == len(result.events)
    assert any(row.get("target_id") == "dr-2" for row in event_rows)

    summary_disk = read_json(paths.summary_path)
    assert summary_disk["run_id"] == result.run_id
    assert summary_disk["events_applied"] == result.summary["events_applied"]
    assert summary_disk["snapshots_written"] == 76
    assert summary_disk["final_failed_nodes"] >= 1

    # JSON round-trip sanity (artifact is valid exports)
    json.dumps(summary_disk)
