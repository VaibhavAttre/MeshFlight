from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Mapping

from meshflight_schema import ScenarioSource
from meshflight_schema.common import EventType


@dataclass(frozen=True)
class ScenarioStructureMetrics:
    """Numeric summaries of a placed scenario (no natural-language matching)."""

    map_area: float
    n_gateways: int
    n_drones: int
    n_clients: int
    n_obstacles: int
    obstacle_area_fraction: float
    clients_per_gateway: float
    clients_per_drone: float
    client_spread_normalized: float
    demand_zone_count: int
    # High when the map is large relative to placed entities (coverage / reach stress).
    sparsity: float


def infer_intent_axes_from_counts(
    counts: Mapping[str, int],
    *,
    map_area: float,
) -> dict[str, float]:
    """
    Derive abstract intent axes purely from counts and canvas scale.
    Values are in [0, 1] and feed the event selector (not phrase-matched themes).
    """
    gw = max(int(counts.get("gateways", 1)), 1)
    dr = max(int(counts.get("drones", 1)), 1)
    cl = max(int(counts.get("clients", 1)), 1)
    obs = int(counts.get("buildings", 0)) + int(counts.get("walls", 0)) + int(counts.get("vegetation", 0))

    # Obstacle / RF complexity proxy (more solid matter → more link-quality stress).
    disruption = min(1.0, obs / 10.0)
    # Client pressure relative to relay capacity.
    congestion = min(1.0, cl / (dr * 12.0 + 1.0))
    # Few uplinks serving many clients.
    gateway_dependency = min(1.0, cl / (gw * 22.0 + 1.0))
    # Coverage / mobility pressure when clients outnumber drones heavily.
    coverage_pressure = min(1.0, cl / (dr * 14.0 + 1.0))
    # Map scale vs entity count — very large maps with few actors feel “sparse”.
    sparsity = 1.0 - min(1.0, (cl + dr + gw) / max(map_area / 250_000.0, 1e-6))

    return {
        "disruption": disruption,
        "congestion": congestion,
        "gateway_dependency": gateway_dependency,
        "coverage_pressure": coverage_pressure,
        "sparsity": max(0.0, min(1.0, sparsity)),
    }


def merge_intent_axes(
    inferred: Mapping[str, float],
    llm_axes: Mapping[str, float] | None,
) -> dict[str, float]:
    """Blend LLM-provided axes (optional) with structure-derived defaults."""
    out = {k: float(v) for k, v in inferred.items()}
    if not llm_axes:
        return out
    for key, raw in llm_axes.items():
        try:
            v = max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            continue
        if key in out:
            out[key] = max(0.0, min(1.0, (out[key] + v) * 0.5))
        else:
            out[key] = v
    return out


def refine_intent_with_metrics(
    axes: Mapping[str, float],
    metrics: ScenarioStructureMetrics,
) -> dict[str, float]:
    """Nudge axes using post-placement geometry (still numeric / structural)."""
    out = dict(axes)
    out["disruption"] = max(
        out.get("disruption", 0.0),
        min(1.0, metrics.obstacle_area_fraction * 1.1),
    )
    out["congestion"] = max(
        out.get("congestion", 0.0),
        min(1.0, metrics.client_spread_normalized * 0.35 + metrics.clients_per_drone / 20.0),
    )
    out["gateway_dependency"] = max(
        out.get("gateway_dependency", 0.0),
        min(1.0, metrics.clients_per_gateway / 25.0),
    )
    out["coverage_pressure"] = max(
        out.get("coverage_pressure", 0.0),
        min(1.0, metrics.clients_per_drone / 18.0 + metrics.sparsity * 0.25),
    )
    for k, v in list(out.items()):
        out[k] = max(0.0, min(1.0, float(v)))
    return out


def compute_structure_metrics(scenario: ScenarioSource) -> ScenarioStructureMetrics:
    w = scenario.map.width
    h = scenario.map.height
    area = max(w * h, 1.0)

    n_gateways = sum(1 for e in scenario.entities if e.type.value == "gateway")
    n_drones = sum(1 for e in scenario.entities if e.type.value == "drone")
    n_clients = sum(1 for e in scenario.entities if e.type.value == "client")

    obs_area = 0.0
    for o in scenario.obstacles:
        if o.shape == "rect":
            obs_area += float(o.size.width) * float(o.size.height)
        elif o.shape == "circle":
            obs_area += math.pi * float(o.radius) ** 2
        elif o.shape == "segment":
            dx = float(o.end.x - o.start.x)
            dy = float(o.end.y - o.start.y)
            obs_area += math.hypot(dx, dy) * 12.0  # rough thickness proxy

    obstacle_area_fraction = min(1.0, obs_area / area)
    gw = max(n_gateways, 1)
    dr = max(n_drones, 1)

    client_positions = [(float(e.position.x), float(e.position.y)) for e in scenario.entities if e.type.value == "client"]
    spread_norm = 0.0
    if len(client_positions) >= 2:
        mx = sum(p[0] for p in client_positions) / len(client_positions)
        my = sum(p[1] for p in client_positions) / len(client_positions)
        var = sum((p[0] - mx) ** 2 + (p[1] - my) ** 2 for p in client_positions) / len(client_positions)
        spread_norm = min(1.0, math.sqrt(var) / max(math.hypot(w, h), 1.0))

    actors = n_gateways + n_drones + n_clients
    sparsity = max(0.0, min(1.0, 1.0 - min(1.0, actors / max(area / 250_000.0, 1e-6))))

    return ScenarioStructureMetrics(
        map_area=area,
        n_gateways=n_gateways,
        n_drones=n_drones,
        n_clients=n_clients,
        n_obstacles=len(scenario.obstacles),
        obstacle_area_fraction=obstacle_area_fraction,
        clients_per_gateway=n_clients / gw,
        clients_per_drone=n_clients / dr,
        client_spread_normalized=spread_norm,
        demand_zone_count=len(scenario.demand_zones),
        sparsity=sparsity,
    )


def _pick_weighted(rng: random.Random, choices: list[tuple[EventType, float]]) -> EventType | None:
    total = sum(w for _, w in choices if w > 0)
    if total <= 0:
        return None
    r = rng.random() * total
    acc = 0.0
    for kind, w in choices:
        if w <= 0:
            continue
        acc += w
        if r <= acc:
            return kind
    return choices[-1][0]


def build_contextual_chaos_events(
    scenario: ScenarioSource,
    *,
    intent_axes: Mapping[str, float],
    simulation_duration_s: float,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """
    Build 1–N chaos events from structural metrics + intent axes.
    Only uses schema-supported EventType values; semantics are approximated
    (e.g. interference_spike ~ link-quality stress, demand_burst ~ traffic pressure).
    """
    metrics = compute_structure_metrics(scenario)
    axes = refine_intent_with_metrics(intent_axes, metrics)

    drones = [e.id for e in scenario.entities if e.type.value == "drone"]
    clients = [e.id for e in scenario.entities if e.type.value == "client"]
    gateways = [e.id for e in scenario.entities if e.type.value == "gateway"]
    relay_nodes = drones + gateways
    any_nodes = relay_nodes + clients

    if not any_nodes:
        return []

    w_interference = 0.12 + 0.55 * metrics.obstacle_area_fraction + 0.35 * axes.get("disruption", 0.0)
    w_demand = 0.10 + 0.45 * axes.get("congestion", 0.0) + 0.20 * min(1.0, metrics.demand_zone_count / 3.0)
    w_failure = 0.10 + 0.50 * axes.get("gateway_dependency", 0.0) + 0.25 * axes.get("coverage_pressure", 0.0)
    w_obstacle = 0.08 + 0.40 * min(1.0, metrics.n_obstacles / 8.0) + 0.25 * axes.get("disruption", 0.0)

    # Sparse layouts: emphasize coverage/connectivity stress more than raw congestion.
    if axes.get("sparsity", 0.0) > 0.55:
        w_failure += 0.12
        w_interference += 0.08

    duration = max(120.0, float(simulation_duration_s))
    horizon = max(40.0, duration - 25.0)

    # Event count scales with complexity but stays bounded (never “always 1”).
    base_n = 1 + int(3.2 * (axes.get("disruption", 0) + axes.get("congestion", 0)))
    n_events = max(1, min(6, base_n + rng.randint(0, 2)))
    if metrics.n_clients + metrics.n_drones + metrics.n_gateways < 3:
        n_events = min(n_events, 2)

    used_types: list[EventType] = []
    events: list[dict[str, Any]] = []
    occupied: list[tuple[float, float]] = []

    def slot_time() -> tuple[float, float]:
        for _ in range(24):
            start = rng.uniform(18.0, horizon - 20.0)
            end = start + rng.uniform(5.0, min(45.0, duration - start - 5.0))
            if any(not (end < s0 or start > s1) for s0, s1 in occupied):
                continue
            occupied.append((start, end))
            return start, end - start
        start = rng.uniform(20.0, horizon - 15.0)
        dur = rng.uniform(6.0, 20.0)
        return start, dur

    for i in range(n_events):
        kind = _pick_weighted(
            rng,
            [
                (EventType.INTERFERENCE_SPIKE, w_interference),
                (EventType.DEMAND_BURST, w_demand),
                (EventType.NODE_FAILURE, w_failure),
                (EventType.OBSTACLE_APPEARANCE, w_obstacle),
            ],
        )
        if kind is None:
            kind = EventType.INTERFERENCE_SPIKE

        # Anti-repetition: if same type repeats too often, reshuffle lightly.
        if used_types.count(kind) >= 2 and len(set(used_types)) == 1:
            kind = rng.choice(
                [EventType.DEMAND_BURST, EventType.NODE_FAILURE, EventType.INTERFERENCE_SPIKE, EventType.OBSTACLE_APPEARANCE]
            )
        used_types.append(kind)

        t0, dur = slot_time()
        intensity = round(rng.uniform(0.22, 0.92), 3)

        if kind == EventType.DEMAND_BURST:
            target = rng.choice(clients) if clients else rng.choice(any_nodes)
        elif kind == EventType.NODE_FAILURE:
            target = rng.choice(relay_nodes) if relay_nodes else rng.choice(any_nodes)
        elif kind == EventType.INTERFERENCE_SPIKE:
            pool = clients + drones
            target = rng.choice(pool) if pool else rng.choice(any_nodes)
        else:  # obstacle appearance — compiler targets entity ids; pick a relay node as affected actor.
            target = rng.choice(drones) if drones else rng.choice(any_nodes)

        event_id = f"chaos-{i + 1}-{kind.value}-{int(t0)}"
        events.append(
            {
                "id": event_id,
                "event_type": kind.value,
                "target_entity_id": target,
                "trigger_time_s": round(t0, 2),
                "duration_s": round(dur, 2),
                "intensity": intensity,
            }
        )

    # De-duplicate identical (type,target,rounded start) entries.
    seen: set[tuple[str, str, float]] = set()
    deduped: list[dict[str, Any]] = []
    for ev in events:
        key = (str(ev["event_type"]), str(ev["target_entity_id"]), float(ev["trigger_time_s"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)
    return deduped
