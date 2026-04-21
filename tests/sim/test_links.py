# tests/sim/test_links.py

from services.sim_core.links import compute_links, compute_link_between
from services.sim_core.state import NodeState, SimState


def test_compute_link_between_nodes_inside_range():
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

    link = compute_link_between(a, b)

    assert link is not None
    assert link.source_id == "drone-1"
    assert link.target_id == "gateway-1"
    assert link.distance_m == 100
    assert 0.0 < link.quality < 1.0


def test_compute_link_between_nodes_outside_range():
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

    link = compute_link_between(a, b)

    assert link is None


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