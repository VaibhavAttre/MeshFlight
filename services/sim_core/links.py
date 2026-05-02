# services/sim_core/links.py

from __future__ import annotations

import math

from services.sim_core.state import LinkState, NodeState, SimState


DEFAULT_COMMS_RANGE_M = 300.0


def compute_links(state: SimState) -> list[LinkState]:
    links: list[LinkState] = []
    nodes = state.active_nodes()

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            a = nodes[i]
            b = nodes[j]
            if not _can_attempt_link(a, b):
                continue

            link = compute_link_between(state, a, b)
            if link is not None:
                links.append(link)

    return links


def compute_link_between(state: SimState, a: NodeState, b: NodeState) -> LinkState | None:
    distance_m = distance_between(a, b)
    range_m = effective_range_m(a, b)

    if distance_m > range_m:
        return None

    base_qual = link_quality_from_distance(distance_m, range_m)
    key = tuple(sorted((a.id, b.id)))
    penalty = state.edge_penalties.get(key, 0.0)
    qual = apply_compiler_penalty_to_quality(base_qual, penalty)

    return LinkState(
        source_id=a.id,
        target_id=b.id,
        distance_m=distance_m,
        quality=qual,
        latency_ms=latency_from_quality(qual),
        bandwidth_mbps=bandwidth_from_quality(qual),
        packet_loss=packet_loss_from_quality(qual),
    )


def apply_compiler_penalty_to_quality(base_quality: float, penalty: float) -> float:
    """
    Combine distance-based quality with compiler ``estimated_penalty``.

    Penalty is non-negative (obstacle LOS / interference). Higher penalty lowers
    quality and increases routing cost (via ``link_cost``), without replacing the
    distance model when penalty is zero.
    """

    if penalty <= 0.0:
        return max(0.0, min(1.0, base_quality))

    adjusted = base_quality / (1.0 + penalty)
    return max(0.001, min(1.0, adjusted))


def distance_between(a: NodeState, b: NodeState) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    return math.sqrt(dx * dx + dy * dy)


def effective_range_m(a: NodeState, b: NodeState) -> float:
    """
    Decide max comm range between two nodes.
    """

    arange = a.comms_range_m or DEFAULT_COMMS_RANGE_M
    brange = b.comms_range_m or DEFAULT_COMMS_RANGE_M
    return min(arange, brange)


def link_quality_from_distance(distance_m: float, range_m: float) -> float:
    """
    Calculate link quality based on distance and range between 1.0 and 0.0

    nodes close: qual = 1

    nodes far : qual = 0
    """

    if range_m <= 0:
        return 0.0

    raw = 1.0 - (distance_m / range_m)
    return max(0.0, min(1.0, raw))


def latency_from_quality(qual: float) -> float:
    """
    simple placeholder latency model
    better qual = lower latency
    Enough for stage 0E
    WILL BE CHANGED
    """

    min_latency_ms = 2.0
    max_latency_ms = 50.0

    return max_latency_ms - qual * (max_latency_ms - min_latency_ms)


def bandwidth_from_quality(qual: float) -> float:
    """
    simple placeholder bandwidth model
    better qual = more bandwidth
    """

    max_bandwidth_mbps = 100.0
    return qual * max_bandwidth_mbps


def packet_loss_from_quality(quality: float) -> float:
    """
    Simple placeholder packet loss model.

    quality = 1.0 means packet_loss = 0.0
    quality = 0.0 means packet_loss = 1.0
    """

    return 1.0 - quality


def _can_attempt_link(a: NodeState, b: NodeState) -> bool:
    """
    Decide whether this pair of node types is allowed to link.

    For Stage 0E, allow:
      - client <-> drone
      - client <-> gateway
      - drone <-> drone
      - drone <-> gateway
      - gateway <-> gateway

    Disallow:
      - client <-> client


    """

    if not a.is_active() or not b.is_active():
        return False

    if a.kind == "client" and b.kind == "client":
        return False

    return True
