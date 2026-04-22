# services/sim_core/movement.py

from __future__ import annotations

import math

from services.sim_core.state import NodeState, SimState


DEFAULT_DRONE_SPEED_MPS = 20.0
ARRIVAL_EPSILON_M = 1.0


def move_drones_toward_disconnected_clients(
    state: SimState,
    *,
    speed_mps: float = DEFAULT_DRONE_SPEED_MPS,
) -> None:
    """
    Move active drones toward disconnected clients.

    Stage 0E baseline behavior:
      - find disconnected clients
      - for each active drone, pick the nearest disconnected client
      - move one tick's worth of distance toward that client

    This is intentionally simple. Later can replace this with:
      - waypoint candidate scoring
      - reconnect-first baseline
      - congestion-aware movement
      - RL-selected movement actions
    """

    disconnected_clients = [
        client
        for client in state.clients()
        if client.is_active() and not client.connected
    ]

    if not disconnected_clients:
        return

    max_distance_this_tick = speed_mps * state.tick_duration_s

    for drone in state.drones():
        if not drone.is_active():
            continue

        target = nearest_node(drone, disconnected_clients)

        if target is None:
            continue

        move_node_toward(
            node=drone,
            target_x=target.x,
            target_y=target.y,
            max_distance_m=max_distance_this_tick,
        )

        drain_drone_battery(drone, distance_m=max_distance_this_tick)


def move_node_toward(
    *,
    node: NodeState,
    target_x: float,
    target_y: float,
    max_distance_m: float,
) -> float:
    """
    Move one node toward a target point.

    Returns the actual distance moved.

    If the target is closer than max_distance_m, the node moves exactly
    to the target instead of overshooting.
    """

    dx = target_x - node.x
    dy = target_y - node.y

    distance_to_target = math.sqrt(dx * dx + dy * dy)

    if distance_to_target <= ARRIVAL_EPSILON_M:
        return 0.0

    actual_distance = min(max_distance_m, distance_to_target)

    unit_x = dx / distance_to_target
    unit_y = dy / distance_to_target

    node.x += unit_x * actual_distance
    node.y += unit_y * actual_distance

    return actual_distance


def nearest_node(
    source: NodeState,
    candidates: list[NodeState],
) -> NodeState | None:
    """
    Return the candidate closest to source.
    """

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda candidate: distance_between(source, candidate),
    )


def distance_between(a: NodeState, b: NodeState) -> float:
    dx = a.x - b.x
    dy = a.y - b.y

    return math.sqrt(dx * dx + dy * dy)


def drain_drone_battery(
    drone: NodeState,
    *,
    distance_m: float,
    drain_per_meter: float = 0.002,
) -> None:
    """
    Very simple battery drain model.

    Example:
      distance_m = 20
      drain_per_meter = 0.002
      battery drain = 0.04%

    Later, this can become:
      - hover cost
      - movement cost
      - radio transmit cost
      - payload cost
    """

    if drone.battery_pct is None:
        return

    drone.battery_pct = max(
        0.0,
        drone.battery_pct - distance_m * drain_per_meter,
    )

    if drone.battery_pct <= 0.0:
        drone.mark_failed()