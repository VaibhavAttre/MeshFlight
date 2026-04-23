# tests/sim/test_io.py

from pathlib import Path

from services.sim_core.events import AppliedEvent
from services.sim_core.io import (
    make_run_output_paths,
    read_json,
    read_jsonl,
    write_simulation_outputs,
)
from services.sim_core.runner import SimulationResult


def test_make_run_output_paths():
    paths = make_run_output_paths(
        run_id="run-123",
        runs_root=Path("artifacts/runs"),
    )

    assert paths.run_dir == Path("artifacts/runs/run-123")
    assert paths.run_config_path == Path("artifacts/runs/run-123/run_config.json")
    assert paths.snapshots_path == Path("artifacts/runs/run-123/snapshots.jsonl")
    assert paths.events_path == Path("artifacts/runs/run-123/events.jsonl")
    assert paths.summary_path == Path("artifacts/runs/run-123/summary.json")


def test_write_simulation_outputs(tmp_path: Path):
    result = SimulationResult(
        run_id="run-test",
        snapshots=[
            {
                "run_id": "run-test",
                "tick": 0,
                "time_s": 0.0,
                "nodes": [],
                "links": [],
                "routes": [],
                "events": [],
                "metrics": {"connected_clients": 0},
            },
            {
                "run_id": "run-test",
                "tick": 1,
                "time_s": 1.0,
                "nodes": [],
                "links": [],
                "routes": [],
                "events": [],
                "metrics": {"connected_clients": 1},
            },
        ],
        events=[
            AppliedEvent(
                event_id="event-1",
                kind="drone_failure",
                time_s=1.0,
                target_id="drone-1",
                message="Node drone-1 failed at t=1.00s",
                payload={"id": "event-1"},
            )
        ],
        summary={
            "run_id": "run-test",
            "snapshots_written": 2,
            "events_applied": 1,
        },
    )

    run_config = {
        "run_id": "run-test",
        "duration_s": 1.0,
        "tick_duration_s": 1.0,
    }

    paths = write_simulation_outputs(
        result=result,
        run_config=run_config,
        runs_root=tmp_path,
    )

    assert paths.run_dir.exists()
    assert paths.run_config_path.exists()
    assert paths.snapshots_path.exists()
    assert paths.events_path.exists()
    assert paths.summary_path.exists()

    saved_config = read_json(paths.run_config_path)
    saved_summary = read_json(paths.summary_path)
    saved_snapshots = read_jsonl(paths.snapshots_path)
    saved_events = read_jsonl(paths.events_path)

    assert saved_config["run_id"] == "run-test"
    assert saved_summary["events_applied"] == 1
    assert len(saved_snapshots) == 2
    assert saved_snapshots[1]["tick"] == 1
    assert len(saved_events) == 1
    assert saved_events[0]["target_id"] == "drone-1"