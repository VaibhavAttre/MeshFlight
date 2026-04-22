# tests/sim/test_routing.py

from services.sim_core.routing import compute_routes
from services.sim_core.state import LinkState, NodeState, SimState


def test_client_routes_directly_to_gateway():
    state = SimState(run_id="test-run")

    state.nodes["client-1"] = NodeState(
        id="client-1",
        kind="client",
        x=0,
        y=0,
    )

    state.nodes["gateway-1"] = NodeState(
        id="gateway-1",
        kind="gateway",
        x=100,
        y=0,
    )

    state.links = [
        LinkState(
            source_id="client-1",
            target_id="gateway-1",
            distance_m=100,
            quality=0.8,
        )
    ]

    routes = compute_routes(state)

    assert routes["client-1"].connected is True
    assert routes["client-1"].gateway_id == "gateway-1"
    assert routes["client-1"].path == ["client-1", "gateway-1"]


def test_client_routes_through_drone_to_gateway():
    state = SimState(run_id="test-run")

    state.nodes["client-1"] = NodeState(
        id="client-1",
        kind="client",
        x=0,
        y=0,
    )

    state.nodes["drone-1"] = NodeState(
        id="drone-1",
        kind="drone",
        x=100,
        y=0,
    )

    state.nodes["gateway-1"] = NodeState(
        id="gateway-1",
        kind="gateway",
        x=200,
        y=0,
    )

    state.links = [
        LinkState(
            source_id="client-1",
            target_id="drone-1",
            distance_m=100,
            quality=0.9,
        ),
        LinkState(
            source_id="drone-1",
            target_id="gateway-1",
            distance_m=100,
            quality=0.9,
        ),
    ]

    routes = compute_routes(state)

    assert routes["client-1"].connected is True
    assert routes["client-1"].gateway_id == "gateway-1"
    assert routes["client-1"].path == [
        "client-1",
        "drone-1",
        "gateway-1",
    ]


def test_client_disconnected_when_no_gateway_path_exists():
    state = SimState(run_id="test-run")

    state.nodes["client-1"] = NodeState(
        id="client-1",
        kind="client",
        x=0,
        y=0,
    )

    state.nodes["drone-1"] = NodeState(
        id="drone-1",
        kind="drone",
        x=100,
        y=0,
    )

    state.nodes["gateway-1"] = NodeState(
        id="gateway-1",
        kind="gateway",
        x=500,
        y=0,
    )

    state.links = [
        LinkState(
            source_id="client-1",
            target_id="drone-1",
            distance_m=100,
            quality=0.9,
        )
    ]

    routes = compute_routes(state)

    assert routes["client-1"].connected is False
    assert routes["client-1"].gateway_id is None
    assert routes["client-1"].path == []


def test_routing_chooses_better_quality_path():
    state = SimState(run_id="test-run")

    state.nodes["client-1"] = NodeState(
        id="client-1",
        kind="client",
        x=0,
        y=0,
    )

    state.nodes["drone-good"] = NodeState(
        id="drone-good",
        kind="drone",
        x=100,
        y=0,
    )

    state.nodes["drone-bad"] = NodeState(
        id="drone-bad",
        kind="drone",
        x=100,
        y=100,
    )

    state.nodes["gateway-1"] = NodeState(
        id="gateway-1",
        kind="gateway",
        x=200,
        y=0,
    )

    state.links = [
        LinkState(
            source_id="client-1",
            target_id="drone-good",
            distance_m=100,
            quality=0.9,
        ),
        LinkState(
            source_id="drone-good",
            target_id="gateway-1",
            distance_m=100,
            quality=0.9,
        ),
        LinkState(
            source_id="client-1",
            target_id="drone-bad",
            distance_m=100,
            quality=0.2,
        ),
        LinkState(
            source_id="drone-bad",
            target_id="gateway-1",
            distance_m=100,
            quality=0.2,
        ),
    ]

    routes = compute_routes(state)

    assert routes["client-1"].connected is True
    assert routes["client-1"].path == [
        "client-1",
        "drone-good",
        "gateway-1",
    ]


def test_state_set_routes_updates_client_connectivity():
    state = SimState(run_id="test-run")

    state.nodes["client-1"] = NodeState(
        id="client-1",
        kind="client",
        x=0,
        y=0,
    )

    state.nodes["gateway-1"] = NodeState(
        id="gateway-1",
        kind="gateway",
        x=100,
        y=0,
    )

    state.links = [
        LinkState(
            source_id="client-1",
            target_id="gateway-1",
            distance_m=100,
            quality=0.8,
        )
    ]

    routes = compute_routes(state)
    state.set_routes(routes)

    assert state.nodes["client-1"].connected is True
    assert state.nodes["client-1"].current_route == [
        "client-1",
        "gateway-1",
    ]