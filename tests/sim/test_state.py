# tests/sim/test_state.py

from services.sim_core.state import build_initial_state


def test_build_initial_state_from_compiled_dict():
    compiled = {
        "normalized_entities": [
            {
                "id": "gateway-1",
                "type": "gateway",
                "position": {"x": 0, "y": 0},
                "properties": {
                    "comms_range_m": 500,
                },
            },
            {
                "id": "drone-1",
                "type": "drone",
                "position": {"x": 100, "y": 0},
                "properties": {
                    "comms_range_m": 300,
                    "battery_pct": 90,
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

    state = build_initial_state(
        run_id="test-run",
        compiled_scenario=compiled,
        tick_duration_s=1.0,
    )

    assert state.run_id == "test-run"
    assert state.tick == 0
    assert state.time_s == 0.0

    assert len(state.nodes) == 3

    assert state.nodes["gateway-1"].kind == "gateway"
    assert state.nodes["drone-1"].kind == "drone"
    assert state.nodes["client-1"].kind == "client"

    assert state.nodes["drone-1"].x == 100
    assert state.nodes["drone-1"].y == 0
    assert state.nodes["drone-1"].battery_pct == 90
    assert state.nodes["drone-1"].comms_range_m == 300


def test_fail_node_marks_node_failed_and_clears_connectivity():
    compiled = {
        "normalized_entities": [
            {
                "id": "drone-1",
                "type": "drone",
                "position": {"x": 100, "y": 0},
                "properties": {
                    "comms_range_m": 300,
                    "battery_pct": 90,
                },
            },
        ]
    }

    state = build_initial_state(
        run_id="test-run",
        compiled_scenario=compiled,
    )

    state.nodes["drone-1"].connected = True
    state.nodes["drone-1"].current_route = ["drone-1", "gateway-1"]

    state.fail_node("drone-1")

    assert state.nodes["drone-1"].status == "failed"
    assert state.nodes["drone-1"].connected is False
    assert state.nodes["drone-1"].current_route == []