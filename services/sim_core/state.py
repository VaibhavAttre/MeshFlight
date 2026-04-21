# services/sim_core/state.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal

NodeKind = Literal["drone", "gateway", "client", "unknown"]
NodeStatus = Literal["active", "failed", "offline"]

@dataclass
class NodeState:

    """
    Runtime state for one network node

    Node state says:
        At given tick, this drone is at x,y with battery level and active
    
    compiled only says drone is at x,y
    """

    id:str
    kind: NodeKind
    x : float
    y : float

    label: str | None = None
    status: NodeStatus = "active"

    battery_pct : float | None = None

    comms_range_m : float | None = None

    connected : bool = False
    current_route: list[str] = field(default_factory=list)

    properties : dict[str, Any] = field(default_factory=dict)

    def is_active(self): 
        return self.status == "active"
    
    def position(self) : 
        return self.x, self.y
    
    def move_to(self, x: float, y: float) -> None:
        self.x = x
        self.y = y

    def mark_failed(self) -> None:
        self.status = "failed"
        self.connected = False
        self.current_route = []

@dataclass
class LinkState:

    """
    Runtime state for one link
    Link means two nodes can communicate


    """

    source_id: str
    target_id: str
    distance_m: float
    quality: float

    latency_ms: float = 1.0
    bandwidth_mbps: float | None = None
    packet_loss : float = 0.0

    def edge_key(self):

        return tuple(sorted((self.source_id, self.target_id)))
    
@dataclass
class RouteState:

    """

    Runtime route from client to gateway
    
    """

    client_id: str
    gateway_id: str | None
    path: list[str]
    connected: bool

    @property
    def hop_count(self):

        if not self.connected:
            return None
        
        return max(0, len(self.path) - 1)
    
@dataclass
class SimState:

    run_id: str

    tick: int = 0
    time_s: float = 0.0
    tick_duration_s: float = 1.0

    nodes: dict[str, NodeState] = field(default_factory=dict)
    links: list[LinkState] = field(default_factory=list)
    routes: dict[str, RouteState] = field(default_factory=dict)

    # IDs of events already applied, so scheduled events do not apply twice.
    applied_event_ids: set[str] = field(default_factory=set)

    def advance_time(self) -> None:
        self.tick += 1
        self.time_s = self.tick * self.tick_duration_s

    def active_nodes(self) -> list[NodeState]:
        return [node for node in self.nodes.values() if node.is_active()]

    def drones(self) -> list[NodeState]:
        return [node for node in self.nodes.values() if node.kind == "drone"]

    def gateways(self) -> list[NodeState]:
        return [node for node in self.nodes.values() if node.kind == "gateway"]

    def clients(self) -> list[NodeState]:
        return [node for node in self.nodes.values() if node.kind == "client"]

    def failed_nodes(self) -> list[NodeState]:
        return [node for node in self.nodes.values() if node.status == "failed"]

    def get_node(self, node_id: str) -> NodeState:
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise KeyError(f"Unknown node id: {node_id}") from exc
        

    def reset_connectivity(self) -> None:
        """
        Clear connectivity info before recomputing routes.

        The routing step will set connected=True again for clients
        that can reach a gateway.
        """

        for node in self.nodes.values():
            node.connected = False
            node.current_route = []

    def set_links(self, links: list[LinkState]) -> None:
        self.links = links

    def set_routes(self, routes: dict[str, RouteState]) -> None:
        self.routes = routes

        self.reset_connectivity()

        for route in routes.values():
            client = self.nodes.get(route.client_id)

            if client is None:
                continue

            client.connected = route.connected
            client.current_route = route.path if route.connected else []

            if route.connected:
                for node_id in route.path:
                    node = self.nodes.get(node_id)
                    if node is not None:
                        node.connected = True

    def fail_node(self, node_id: str) -> None:
        node = self.get_node(node_id)
        node.mark_failed()

        # Remove links that involve this failed node.
        self.links = [
            link
            for link in self.links
            if link.source_id != node_id and link.target_id != node_id
        ]

        # Remove routes that use this failed node.
        for route in self.routes.values():
            if node_id in route.path:
                route.connected = False
                route.path = []


def infer_node_kind(raw_kind: str | None) -> NodeKind:
    """
    Convert whatever the compiled scenario calls an entity into a simulator kind.

    This makes the simulator tolerant of names like:
        "drone"
        "gateway"
        "client"
        "ground_client"
    """

    if raw_kind is None:
        return "unknown"

    normalized = raw_kind.lower().replace("-", "_")

    if "drone" in normalized:
        return "drone"

    if "gateway" in normalized:
        return "gateway"

    if "client" in normalized:
        return "client"

    return "unknown"


def build_initial_state(
    *,
    run_id: str,
    compiled_scenario: Any,
    tick_duration_s: float = 1.0,
) -> SimState:
    """
    Build the first SimState from a compiled scenario.

    This function intentionally accepts Any because your compiled scenario may be:
        - a Pydantic model
        - a dict loaded from compiled.json

    Later, once you know the exact schema imports, you can type this more strictly.
    """

    scenario_dict = _to_dict(compiled_scenario)

    state = SimState(
        run_id=run_id,
        tick=0,
        time_s=0.0,
        tick_duration_s=tick_duration_s,
    )

    entities = _extract_entities(scenario_dict)

    for entity in entities:
        node = _entity_to_node_state(entity)
        state.nodes[node.id] = node

    return state


def _to_dict(value: Any) -> dict[str, Any]:
    """
    Convert a Pydantic model or plain dict into a dict.
    """

    if isinstance(value, dict):
        return value

    if hasattr(value, "model_dump"):
        return value.model_dump()

    raise TypeError(f"Expected dict or Pydantic model, got {type(value)!r}")


def _extract_entities(compiled: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract normalized entities from the compiled scenario.

    Your compiler may call this field one of a few names depending on
    where you are in the implementation.

    This tries the most likely ones.
    """

    if "normalized_entities" in compiled:
        return list(compiled["normalized_entities"])

    if "entities" in compiled:
        return list(compiled["entities"])

    if "scenario" in compiled and isinstance(compiled["scenario"], dict):
        scenario = compiled["scenario"]

        if "normalized_entities" in scenario:
            return list(scenario["normalized_entities"])

        if "entities" in scenario:
            return list(scenario["entities"])

    raise KeyError(
        "Could not find entities in compiled scenario. "
        "Expected one of: normalized_entities, entities, scenario.normalized_entities, scenario.entities."
    )


def _entity_to_node_state(entity: dict[str, Any]) -> NodeState:
    entity_id = str(entity.get("id"))

    raw_kind = (
        entity.get("kind")
        or entity.get("type")
        or entity.get("entity_type")
        or entity.get("role")
    )

    kind = infer_node_kind(str(raw_kind) if raw_kind is not None else None)

    x, y = _extract_position(entity)

    properties = dict(entity.get("properties") or {})

    label = entity.get("label") or properties.get("label")

    battery_pct = _extract_optional_float(
        entity,
        properties,
        keys=("battery_pct", "battery_percent", "initial_battery_pct"),
    )

    if battery_pct is None and kind == "drone":
        battery_pct = 100.0

    comms_range_m = _extract_optional_float(
        entity,
        properties,
        keys=("comms_range_m", "radio_range_m", "range_m"),
    )

    return NodeState(
        id=entity_id,
        kind=kind,
        x=x,
        y=y,
        label=label,
        status="active",
        battery_pct=battery_pct,
        comms_range_m=comms_range_m,
        properties=properties,
    )


def _extract_position(entity: dict[str, Any]) -> tuple[float, float]:
    """
    Extract x/y position from several possible compiled formats.

    Supported shapes:
        {"x": 10, "y": 20}
        {"position": {"x": 10, "y": 20}}
        {"position_m": {"x": 10, "y": 20}}
        {"position": [10, 20]}
    """

    if "x" in entity and "y" in entity:
        return float(entity["x"]), float(entity["y"])

    for key in ("position", "position_m", "pos"):
        value = entity.get(key)

        if isinstance(value, dict):
            return float(value["x"]), float(value["y"])

        if isinstance(value, list | tuple) and len(value) >= 2:
            return float(value[0]), float(value[1])

    raise KeyError(f"Entity {entity.get('id')} is missing a usable position")


def _extract_optional_float(
    entity: dict[str, Any],
    properties: dict[str, Any],
    *,
    keys: tuple[str, ...],
) -> float | None:
    for key in keys:
        if key in entity and entity[key] is not None:
            return float(entity[key])

        if key in properties and properties[key] is not None:
            return float(properties[key])

    return None