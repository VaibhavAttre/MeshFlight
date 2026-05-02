# tests/sim/test_links.py

from services.sim_core.links import (
    apply_compiler_penalty_to_quality,
    compute_links,
    compute_link_between,
    link_quality_from_distance,
)
from services.sim_core.routing import compute_routes
from services.sim_core.state import NodeState, SimState, build_initial_state


def test_compute_link_between_nodes_inside_range():
    state = SimState(run_id="test-run")

    a = NodeState(
        id="drone-1",
        kind="drone",
        x=0,
        y=0,
        comms_range_m=300,
    )

    b = NodeState(
        id="gateway-1",
        kind="gateway",
        x=100,
        y=0,
        comms_range_m=300,
    )

    link = compute_link_between(state, a, b)

    assert link is not None
    assert link.source_id == "drone-1"
    assert link.target_id == "gateway-1"
    assert link.distance_m == 100
    assert 0.0 < link.quality < 1.0


def test_compute_link_between_nodes_outside_range():
    state = SimState(run_id="test-run")

    a = NodeState(
        id="drone-1",
        kind="drone",
        x=0,
        y=0,
        comms_range_m=300,
    )

    b = NodeState(
        id="gateway-1",
        kind="gateway",
        x=400,
        y=0,
        comms_range_m=300,
    )

    link = compute_link_between(state, a, b)

    assert link is None


def test_compiler_penalty_reduces_quality_vs_distance_only():
    base = link_quality_from_distance(80.0, 200.0)
    penalized = apply_compiler_penalty_to_quality(base, 50.0)
    assert penalized < base
    assert penalized >= 0.001


def test_route_prefers_relay_when_direct_edge_heavily_penalized():
    """
    Three collinear nodes: gateway — drone — client.

    Without penalty the single-hop gateway–client path can beat two hops.
    With a large penalty only on the gateway–client candidate edge, routing
    should prefer gateway–drone–client.
    """

    scenario = {
        "normalized_entities": [
            {
                "id": "gw-1",
                "type": "gateway",
                "x": 0,
                "y": 0,
                "properties": {"comms_range_m": 300.0},
            },
            {
                "id": "dr-1",
                "type": "drone",
                "x": 80,
                "y": 0,
                "properties": {"comms_range_m": 200.0},
            },
            {
                "id": "client-1",
                "type": "client",
                "x": 160,
                "y": 0,
                "properties": {},
            },
        ],
        "candidate_graph_edges": [
            {"src": "gw-1", "dst": "dr-1", "distance_m": 80.0, "estimated_penalty": 0.0},
            {"src": "dr-1", "dst": "client-1", "distance_m": 80.0, "estimated_penalty": 0.0},
            {"src": "gw-1", "dst": "client-1", "distance_m": 160.0, "estimated_penalty": 80.0},
        ],
    }

    state = build_initial_state(run_id="route-test", compiled_scenario=scenario, tick_duration_s=1.0)

    links = compute_links(state)
    state.set_links(links)
    routes = compute_routes(state)
    state.set_routes(routes)

    route = routes["client-1"]
    assert route.connected is True
    assert route.gateway_id == "gw-1"
    assert "dr-1" in route.path
    assert route.path == ["client-1", "dr-1", "gw-1"]


def test_compute_links_ignores_failed_nodes():
    state = SimState(run_id="test-run")

    state.nodes["drone-1"] = NodeState(
        id="drone-1",
        kind="drone",
        x=0,
        y=0,
        status="failed",
        comms_range_m=300,
    )

    state.nodes["gateway-1"] = NodeState(
        id="gateway-1",
        kind="gateway",
        x=100,
        y=0,
        comms_range_m=300,
    )

    links = compute_links(state)

    assert links == []


def test_compute_links_disallows_client_to_client_links():
    state = SimState(run_id="test-run")

    state.nodes["client-1"] = NodeState(
        id="client-1",
        kind="client",
        x=0,
        y=0,
        comms_range_m=300,
    )

    state.nodes["client-2"] = NodeState(
        id="client-2",
        kind="client",
        x=100,
        y=0,
        comms_range_m=300,
    )

    links = compute_links(state)

    assert links == []


def test_compute_links_finds_multiple_valid_links():
    state = SimState(run_id="test-run")

    state.nodes["gateway-1"] = NodeState(
        id="gateway-1",
        kind="gateway",
        x=0,
        y=0,
        comms_range_m=500,
    )

    state.nodes["drone-1"] = NodeState(
        id="drone-1",
        kind="drone",
        x=100,
        y=0,
        comms_range_m=300,
    )

    state.nodes["client-1"] = NodeState(
        id="client-1",
        kind="client",
        x=200,
        y=0,
        comms_range_m=250,
    )

    links = compute_links(state)

    edge_keys = {link.edge_key() for link in links}

    assert ("drone-1", "gateway-1") in edge_keys
    assert ("client-1", "drone-1") in edge_keys
    assert ("client-1", "gateway-1") in edge_keys
