# services/sim_core/routing.py

from __future__ import annotations

import networkx as nx

from services.sim_core.state import LinkState, RouteState, SimState

def compute_routes(state: SimState) -> dict[str, RouteState]:

    """
    
    Compute one route per client

    for each client:
        find any reachable gateway
        choose best path
        return route

    Stage 0E:
        uses current links 
        ignores traffic load
        uses link quality as weight
        lower total cost > better route


    """

    graph = build_connectivity_graph(state)

    routes: dict[str, RouteState] = {}

    gateways = [n for n in state.gateways() if n.is_active()]
    clients = [n for n in state.clients() if n.is_active()]

    for client in clients:
        best_gateway_id: str | None = None
        best_path: list[str] = []
        best_cost: float | None = None

        for gateway in gateways:
            try:
                path = nx.shortest_path(
                    graph,
                    source=client.id,
                    target=gateway.id,
                    weight="cost",
                )

                cost = nx.path_weight(graph, path, weight="cost")

            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue

            if best_cost is None or cost < best_cost:
                best_cost = cost
                best_path = list(path)
                best_gateway_id = gateway.id

        if best_gateway_id is None:
            routes[client.id] = RouteState(
                client_id=client.id,
                gateway_id=None,
                path=[],
                connected=False,
            )
        else:
            routes[client.id] = RouteState(
                client_id=client.id,
                gateway_id=best_gateway_id,
                path=best_path,
                connected=True,
            )

    return routes

def build_connectivity_graph(state: SimState) -> nx.Graph:

    graph = nx.Graph()

    for node in state.active_nodes():
        graph.add_node(node.id, kind=node.kind, x=node.x, y=node.y)

    for link in state.links:
        
        if link.source_id not in state.nodes:
            continue

        if link.target_id not in state.nodes:
            continue

        source = state.nodes[link.source_id]
        target = state.nodes[link.target_id]

        if not source.is_active() or not target.is_active():
            continue

        graph.add_edge(
            link.source_id,
            link.target_id,
            quality=link.quality,
            distance_m=link.distance_m,
            cost=link_cost(link),
        )

    return graph

def link_cost(link: LinkState) -> float:

    """
    Convert link quality to cost
    quality = 1 is cheap
    quality = 0.1 is expensive
    """

    quality_floor = 0.001
    qual = max(quality_floor, link.quality)

    return 1.0 / qual
