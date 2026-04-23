# tests/sim/test_smoke_compiled_fixture.py

from __future__ import annotations

from pathlib import Path

import pytest

from services.scenario_compiler.compiler import compile_scenario
from services.sim_core.runner import SimulationRunner


FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "scenarios" / "bridge_reconnect.json"
)


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture scenario missing")
def test_simulation_smoke_on_compiled_bridge_reconnect(tmp_path) -> None:
    compiled, report = compile_scenario(
        FIXTURE,
        output_dir=tmp_path / "compiled-out",
        write_outputs=True,
    )

    assert report["counts"]["normalized_entities"] >= 1

    runner = SimulationRunner(
        compiled_scenario=compiled,
        run_id="smoke-run",
        duration_s=6.0,
        tick_duration_s=1.0,
        drone_speed_mps=18.0,
    )
    result = runner.run()

    assert len(result.snapshots) == 7
    assert result.summary["ticks_completed"] == 6
    assert result.summary["snapshots_written"] == 7

    first = result.snapshots[0]
    assert first["tick"] == 0
    assert "nodes" in first and len(first["nodes"]) >= 1

    if compiled.runtime_schedule:
        assert result.summary["events_applied"] >= 0


def test_events_apply_compiler_chaos_node_failure_action() -> None:
    from services.sim_core.events import apply_due_events
    from services.sim_core.state import SimState, build_initial_state

    compiled = {
        "normalized_entities": [
            {
                "id": "gateway-1",
                "type": "gateway",
                "x": 0,
                "y": 0,
                "properties": {"comms_range_m": 500},
            },
            {
                "id": "drone-1",
                "type": "drone",
                "x": 50,
                "y": 0,
                "properties": {"comms_range_m": 200, "battery_pct": 100},
            },
        ],
        "runtime_schedule": [
            {
                "time_s": 1.0,
                "action": "chaos_node_failure",
                "target_id": "drone-1",
                "payload": {"event_id": "ev-1", "event_type": "node_failure"},
            },
            {
                "time_s": 5.0,
                "action": "chaos_node_failure_end",
                "target_id": "drone-1",
                "payload": {"event_id": "ev-1", "event_type": "node_failure"},
            },
        ],
    }

    state = build_initial_state(run_id="t", compiled_scenario=compiled, tick_duration_s=1.0)
    state.advance_time()
    applied = apply_due_events(state, compiled["runtime_schedule"])
    assert len(applied) == 1
    assert state.nodes["drone-1"].status == "failed"
