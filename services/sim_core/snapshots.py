# services/sim_core/snapshots.py

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from services.sim_core.events import AppliedEvent
from services.sim_core.state import LinkState, NodeState, RouteState, SimState


def build_snapshot(
    state: SimState,
    *,
    recent_events: list[AppliedEvent] | None = None,
) -> dict[str, Any]:
    """
    Convert the current SimState into one serializable snapshot.

    Stage 0E version:
      - returns a plain dict
      - easy to write as JSON / JSONL
      - later can be upgraded to your RunSnapshot schema
    """

    return {
        "run_id": state.run_id,
        "tick": state.tick,
        "time_s": state.time_s,
        "tick_duration_s": state.tick_duration_s,
        "nodes": [serialize_node(node) for node in sorted_nodes(state.nodes)],
        "links": [serialize_link(link) for link in sorted_links(state.links)],
        "routes": [
            serialize_route(route)
            for route in sorted_routes(state.routes)
        ],
        "events": [
            serialize_applied_event(event)
            for event in (recent_events or [])
        ],
        "metrics": build_snapshot_metrics(state),
    }


def serialize_node(node: NodeState) -> dict[str, Any]:
    return {
        "id": node.id,
        "kind": node.kind,
        "label": node.label,
        "status": node.status,
        "x": node.x,
        "y": node.y,
        "battery_pct": node.battery_pct,
        "comms_range_m": node.comms_range_m,
        "connected": node.connected,
        "current_route": list(node.current_route),
        "properties": dict(node.properties),
    }


def serialize_link(link: LinkState) -> dict[str, Any]:
    return {
        "source_id": link.source_id,
        "target_id": link.target_id,
        "distance_m": link.distance_m,
        "quality": link.quality,
        "latency_ms": link.latency_ms,
        "bandwidth_mbps": link.bandwidth_mbps,
        "packet_loss": link.packet_loss,
    }


def serialize_route(route: RouteState) -> dict[str, Any]:
    return {
        "client_id": route.client_id,
        "gateway_id": route.gateway_id,
        "path": list(route.path),
        "connected": route.connected,
        "hop_count": route.hop_count,
    }


def serialize_applied_event(event: AppliedEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "kind": event.kind,
        "time_s": event.time_s,
        "target_id": event.target_id,
        "message": event.message,
        "payload": dict(event.payload),
    }


def build_snapshot_metrics(state: SimState) -> dict[str, Any]:
    clients = state.clients()
    drones = state.drones()
    gateways = state.gateways()

    connected_clients = sum(1 for client in clients if client.connected)
    disconnected_clients = len(clients) - connected_clients
    failed_drones = sum(1 for drone in drones if drone.status == "failed")
    active_links = len(state.links)

    return {
        "total_nodes": len(state.nodes),
        "total_clients": len(clients),
        "total_drones": len(drones),
        "total_gateways": len(gateways),
        "connected_clients": connected_clients,
        "disconnected_clients": disconnected_clients,
        "failed_drones": failed_drones,
        "active_links": active_links,
    }


def sorted_nodes(nodes: dict[str, NodeState]) -> list[NodeState]:
    return sorted(nodes.values(), key=lambda node: node.id)


def sorted_links(links: list[LinkState]) -> list[LinkState]:
    return sorted(
        links,
        key=lambda link: (
            min(link.source_id, link.target_id),
            max(link.source_id, link.target_id),
        ),
    )


def sorted_routes(routes: dict[str, RouteState]) -> list[RouteState]:
    return sorted(routes.values(), key=lambda route: route.client_id)


def to_jsonable(value: Any) -> Any:
    """
    Small helper in case you later want to recursively normalize objects.
    Right now not strictly required, but useful if you expand snapshot content.
    """

    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)

    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}

    if isinstance(value, list):
        return [to_jsonable(v) for v in value]

    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]

    if isinstance(value, set):
        return sorted(to_jsonable(v) for v in value)

    return value