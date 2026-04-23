# tests/sim/test_runner.py

from services.sim_core.runner import SimulationRunner


def test_runner_initializes_and_produces_snapshots():
    compiled = {
        "normalized_entities": [
            {
                "id": "gateway-1",
                "type": "gateway",
                "position": {"x": 0, "y": 0},
                "properties": {"comms_range_m": 500},
            },
            {
                "id": "drone-1",
                "type": "drone",
                "position": {"x": 100, "y": 0},
                "properties": {
                    "comms_range_m": 300,
                    "battery_pct": 100,
                },
            },
            {
                "id": "client-1",
                "type": "client",
                "position": {"x": 200, "y": 0},
                "properties": {},
            },
        ]
    }

    runner = SimulationRunner(
        compiled_scenario=compiled,
        run_id="run-test",
        duration_s=3.0,
        tick_duration_s=1.0,
        drone_speed_mps=20.0,
    )

    result = runner.run()

    assert result.run_id == "run-test"
    assert len(result.snapshots) == 4
    assert result.summary["snapshots_written"] == 4
    assert result.summary["ticks_completed"] == 3


def test_runner_applies_scheduled_failure_event():
    compiled = {
        "normalized_entities": [
            {
                "id": "gateway-1",
                "type": "gateway",
                "position": {"x": 0, "y": 0},
                "properties": {"comms_range_m": 500},
            },
            {
                "id": "drone-1",
                "type": "drone",
                "position": {"x": 100, "y": 0},
                "properties": {
                    "comms_range_m": 300,
                    "battery_pct": 100,
                },
            },
            {
                "id": "client-1",
                "type": "client",
                "position": {"x": 200, "y": 0},
                "properties": {},
            },
        ],
        "runtime_schedule": [
            {
                "id": "event-1",
                "kind": "drone_failure",
                "time_s": 1.0,
                "target_id": "drone-1",
            }
        ],
    }

    runner = SimulationRunner(
        compiled_scenario=compiled,
        run_id="run-failure",
        duration_s=3.0,
        tick_duration_s=1.0,
        drone_speed_mps=20.0,
    )

    result = runner.run()

    assert len(result.events) == 1
    assert result.events[0].target_id == "drone-1"
    assert result.summary["events_applied"] == 1
    assert runner.state.nodes["drone-1"].status == "failed"


def test_runner_moves_drone_toward_disconnected_client():
    compiled = {
        "normalized_entities": [
            {
                "id": "gateway-1",
                "type": "gateway",
                "position": {"x": 0, "y": 0},
                "properties": {"comms_range_m": 50},
            },
            {
                "id": "drone-1",
                "type": "drone",
                "position": {"x": 0, "y": 100},
                "properties": {
                    "comms_range_m": 80,
                    "battery_pct": 100,
                },
            },
            {
                "id": "client-1",
                "type": "client",
                "position": {"x": 300, "y": 100},
                "properties": {"comms_range_m": 80},
            },
        ]
    }

    runner = SimulationRunner(
        compiled_scenario=compiled,
        run_id="run-move",
        duration_s=1.0,
        tick_duration_s=1.0,
        drone_speed_mps=20.0,
    )

    start_x = runner.state.nodes["drone-1"].x
    start_y = runner.state.nodes["drone-1"].y

    result = runner.run()

    end_x = runner.state.nodes["drone-1"].x
    end_y = runner.state.nodes["drone-1"].y

    assert len(result.snapshots) == 2
    assert (end_x, end_y) != (start_x, start_y)


def test_runner_raises_on_invalid_tick_duration():
    compiled = {
        "normalized_entities": []
    }

    runner = SimulationRunner(
        compiled_scenario=compiled,
        run_id="bad-run",
        duration_s=10.0,
        tick_duration_s=0.0,
    )

    try:
        runner.run()
        assert False, "Expected ValueError for tick_duration_s <= 0"
    except ValueError:
        pass