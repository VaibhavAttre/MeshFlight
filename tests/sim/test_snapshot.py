# tests/sim/test_snapshots.py

from services.sim_core.events import AppliedEvent
from services.sim_core.snapshots import build_snapshot
from services.sim_core.state import LinkState, NodeState, RouteState, SimState


def test_build_snapshot_contains_core_fields():
    state = SimState(
        run_id="run-1",
        tick=3,
        time_s=3.0,
        tick_duration_s=1.0,
    )

    state.nodes["client-1"] = NodeState(
        id="client-1",
        kind="client",
        x=0,
        y=0,
        connected=True,
        current_route=["client-1", "gateway-1"],
    )

    state.nodes["gateway-1"] = NodeState(
        id="gateway-1",
        kind="gateway",
        x=100,
        y=0,
        connected=True,
    )

    state.links = [
        LinkState(
            source_id="client-1",
            target_id="gateway-1",
            distance_m=100.0,
            quality=0.8,
        )
    ]

    state.routes = {
        "client-1": RouteState(
            client_id="client-1",
            gateway_id="gateway-1",
            path=["client-1", "gateway-1"],
            connected=True,
        )
    }

    snapshot = build_snapshot(state)

    assert snapshot["run_id"] == "run-1"
    assert snapshot["tick"] == 3
    assert snapshot["time_s"] == 3.0

    assert len(snapshot["nodes"]) == 2
    assert len(snapshot["links"]) == 1
    assert len(snapshot["routes"]) == 1

    assert snapshot["metrics"]["total_clients"] == 1
    assert snapshot["metrics"]["connected_clients"] == 1
    assert snapshot["metrics"]["disconnected_clients"] == 0


def test_build_snapshot_includes_recent_events():
    state = SimState(
        run_id="run-1",
        tick=10,
        time_s=10.0,
    )

    state.nodes["drone-1"] = NodeState(
        id="drone-1",
        kind="drone",
        x=0,
        y=0,
        status="failed",
    )

    recent_events = [
        AppliedEvent(
            event_id="event-1",
            kind="drone_failure",
            time_s=10.0,
            target_id="drone-1",
            message="Node drone-1 failed at t=10.00s",
            payload={"id": "event-1"},
        )
    ]

    snapshot = build_snapshot(
        state,
        recent_events=recent_events,
    )

    assert len(snapshot["events"]) == 1
    assert snapshot["events"][0]["event_id"] == "event-1"
    assert snapshot["events"][0]["target_id"] == "drone-1"


def test_snapshot_metrics_count_disconnected_clients():
    state = SimState(
        run_id="run-1",
        tick=0,
        time_s=0.0,
    )

    state.nodes["client-1"] = NodeState(
        id="client-1",
        kind="client",
        x=0,
        y=0,
        connected=False,
    )

    state.nodes["client-2"] = NodeState(
        id="client-2",
        kind="client",
        x=50,
        y=0,
        connected=True,
    )

    state.nodes["drone-1"] = NodeState(
        id="drone-1",
        kind="drone",
        x=20,
        y=0,
        status="failed",
    )

    snapshot = build_snapshot(state)

    assert snapshot["metrics"]["total_clients"] == 2
    assert snapshot["metrics"]["connected_clients"] == 1
    assert snapshot["metrics"]["disconnected_clients"] == 1
    assert snapshot["metrics"]["failed_drones"] == 1