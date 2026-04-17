from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, Point, box
from shapely.geometry.base import BaseGeometry

from meshflight_schema.common import EntityType, ObstacleType, Point2D, Size2D
from meshflight_schema.compiled import (
    CandidateGraphEdge,
    CompilationMetadata,
    CompiledScenario,
    MobilityConstraint,
    NormalizedEntity,
    ObstacleIndexEntry,
    RuntimeScheduleEntry,
    WaypointCandidate,
)

from meshflight_schema.scenario import (
    ClientEntity,
    CircleObstacle,
    DroneEntity,
    GatewayEntity,
    InterferenceEmitterEntity,
    RectObstacle,
    ScenarioEntity,
    ScenarioObstacle,
    ScenarioSource,
    SegmentObstacle,
)

COMPILER_VERSION = "0.1.0"
DEFAULT_CONFIG: dict[str, Any] = {
    "grid_cell_size_m": 50.0,
    "waypoint_directions": 8,
    "los_block_penalty_multiplier": 1.0,
    "blocks_flight_penalty_bonus": 5.0,
    "interference_penalty_scale": 10.0,
    "include_client_client_edges": False,
}


@dataclass(slots=True)
class CompileArtifacts:
    source_path: Path
    output_dir: Path
    compiled_path: Path
    report_path: Path


def _stable_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _sha256_hex(value: Any) -> str:
    return hashlib.sha256(_stable_json_bytes(value)).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_source_scenario(path: Path) -> ScenarioSource:
    raw = path.read_text(encoding="utf-8")
    return ScenarioSource.model_validate_json(raw)


def _scenario_output_dir(source: ScenarioSource, output: Path | None) -> Path:
    if output is not None:
        return output
    return Path("artifacts/scenarios") / source.metadata.scenario_id


def _build_compile_artifact_paths(
    source_path: Path,
    source: ScenarioSource,
    output_dir: Path | None,
) -> CompileArtifacts:
    output_dir = _scenario_output_dir(source, output_dir)
    return CompileArtifacts(
        source_path=source_path,
        output_dir=output_dir,
        compiled_path=output_dir / "compiled.json",
        report_path=output_dir / "compile_report.json",
    )


def _entity_properties(entity: ScenarioEntity) -> dict[str, str | int | float | bool]:
    props: dict[str, str | int | float | bool] = {
        "label": entity.label,
    }

    if entity.tags:
        props["tags_csv"] = ",".join(entity.tags)

    if isinstance(entity, DroneEntity):
        props.update(
            {
                "battery_capacity_mah": entity.battery_capacity_mah,
                "max_speed_mps": entity.max_speed_mps,
                "comms_range_m": entity.comms_range_m,
                "waypoint_step_m": entity.waypoint_step_m,
            }
        )
    elif isinstance(entity, GatewayEntity):
        props.update(
            {
                "uplink_capacity_mbps": entity.uplink_capacity_mbps,
                "comms_range_m": entity.comms_range_m,
            }
        )
    elif isinstance(entity, ClientEntity):
        props["demand_profile"] = entity.demand_profile
    elif isinstance(entity, InterferenceEmitterEntity):
        props.update(
            {
                "radius_m": entity.radius_m,
                "intensity": entity.intensity,
            }
        )

    return props


def _normalize_entities(source: ScenarioSource) -> list[NormalizedEntity]:
    normalized: list[NormalizedEntity] = []

    for entity in source.entities:
        normalized.append(
            NormalizedEntity(
                id=entity.id,
                type=entity.type.value,
                x=entity.position.x,
                y=entity.position.y,
                properties=_entity_properties(entity),
            )
        )

    normalized.sort(key=lambda entity: entity.id)
    return normalized


def _obstacle_geometry(obstacle: ScenarioObstacle) -> BaseGeometry:
    if isinstance(obstacle, RectObstacle):
        return box(
            obstacle.position.x,
            obstacle.position.y,
            obstacle.position.x + obstacle.size.width,
            obstacle.position.y + obstacle.size.height,
        )

    if isinstance(obstacle, SegmentObstacle):
        return LineString(
            [
                (obstacle.start.x, obstacle.start.y),
                (obstacle.end.x, obstacle.end.y),
            ]
        )

    if isinstance(obstacle, CircleObstacle):
        return Point(obstacle.center.x, obstacle.center.y).buffer(obstacle.radius)

    raise TypeError(f"Unsupported obstacle type: {type(obstacle)}")


def _obstacle_bounds_cell_keys(
    geometry: BaseGeometry,
    grid_cell_size_m: float,
    map_width: float,
    map_height: float,
) -> list[str]:
    min_x, min_y, max_x, max_y = geometry.bounds

    min_col = max(0, int(min_x // grid_cell_size_m))
    max_col = max(0, int(min(max_x, map_width) // grid_cell_size_m))
    min_row = max(0, int(min_y // grid_cell_size_m))
    max_row = max(0, int(min(max_y, map_height) // grid_cell_size_m))

    cell_keys: list[str] = []
    for row in range(min_row, max_row + 1):
        for col in range(min_col, max_col + 1):
            cell_keys.append(f"{row}:{col}")

    return sorted(set(cell_keys))


def _obstacle_los_penalty(obstacle: ScenarioObstacle, config: dict[str, Any]) -> float:
    penalty = float(obstacle.attenuation_db) * float(config["los_block_penalty_multiplier"])

    if obstacle.blocks_flight:
        penalty += float(config["blocks_flight_penalty_bonus"])

    if obstacle.type == ObstacleType.NO_FLY_ZONE:
        penalty += float(config["blocks_flight_penalty_bonus"])

    return penalty


def _build_obstacle_index(
    source: ScenarioSource,
    config: dict[str, Any],
) -> tuple[list[ObstacleIndexEntry], dict[str, BaseGeometry]]:
    geometries: dict[str, BaseGeometry] = {}
    entries: list[ObstacleIndexEntry] = []

    grid_cell_size_m = float(config["grid_cell_size_m"])

    for obstacle in source.obstacles:
        geometry = _obstacle_geometry(obstacle)
        geometries[obstacle.id] = geometry

        entries.append(
            ObstacleIndexEntry(
                obstacle_id=obstacle.id,
                cell_keys=_obstacle_bounds_cell_keys(
                    geometry=geometry,
                    grid_cell_size_m=grid_cell_size_m,
                    map_width=source.map.width,
                    map_height=source.map.height,
                ),
                los_penalty=_obstacle_los_penalty(obstacle, config),
            )
        )

    entries.sort(key=lambda entry: entry.obstacle_id)
    return entries, geometries


def _distance_m(a: ScenarioEntity, b: ScenarioEntity) -> float:
    return math.hypot(a.position.x - b.position.x, a.position.y - b.position.y)


def _entity_comms_range(entity: ScenarioEntity) -> float | None:
    if isinstance(entity, (DroneEntity, GatewayEntity)):
        return entity.comms_range_m
    return None


def _is_connectivity_entity(entity: ScenarioEntity) -> bool:
    return entity.type in {EntityType.DRONE, EntityType.GATEWAY, EntityType.CLIENT}


def _line_between_entities(a: ScenarioEntity, b: ScenarioEntity) -> LineString:
    return LineString([(a.position.x, a.position.y), (b.position.x, b.position.y)])


def _segment_obstacle_penalty(
    line: LineString,
    source: ScenarioSource,
    obstacle_geometries: dict[str, BaseGeometry],
    config: dict[str, Any],
) -> float:
    total_penalty = 0.0

    for obstacle in source.obstacles:
        geometry = obstacle_geometries[obstacle.id]
        if line.intersects(geometry):
            total_penalty += _obstacle_los_penalty(obstacle, config)

    return total_penalty


def _segment_interference_penalty(
    line: LineString,
    source: ScenarioSource,
    config: dict[str, Any],
) -> float:
    scale = float(config["interference_penalty_scale"])
    penalty = 0.0

    for entity in source.entities:
        if not isinstance(entity, InterferenceEmitterEntity):
            continue

        emitter_point = Point(entity.position.x, entity.position.y)
        distance = line.distance(emitter_point)
        if distance <= entity.radius_m:
            closeness = 1.0 - (distance / entity.radius_m)
            penalty += closeness * float(entity.intensity) * scale

    return penalty


def _build_candidate_graph_edges(
    source: ScenarioSource,
    obstacle_geometries: dict[str, BaseGeometry],
    config: dict[str, Any],
) -> list[CandidateGraphEdge]:
    eligible_entities = [entity for entity in source.entities if _is_connectivity_entity(entity)]
    include_client_client_edges = bool(config["include_client_client_edges"])

    edges: list[CandidateGraphEdge] = []

    for i, entity_a in enumerate(eligible_entities):
        for entity_b in eligible_entities[i + 1 :]:
            if (
                not include_client_client_edges
                and entity_a.type == EntityType.CLIENT
                and entity_b.type == EntityType.CLIENT
            ):
                continue

            range_a = _entity_comms_range(entity_a)
            range_b = _entity_comms_range(entity_b)

            if range_a is None and range_b is None:
                continue

            # For clients in Phase 0, allow them to connect to any radio-bearing node
            # if they are within the other node's range.
            effective_range = None
            if range_a is not None and range_b is not None:
                effective_range = min(range_a, range_b)
            elif range_a is not None:
                effective_range = range_a
            elif range_b is not None:
                effective_range = range_b

            if effective_range is None:
                continue

            distance = _distance_m(entity_a, entity_b)
            if distance > effective_range:
                continue

            line = _line_between_entities(entity_a, entity_b)
            obstacle_penalty = _segment_obstacle_penalty(
                line=line,
                source=source,
                obstacle_geometries=obstacle_geometries,
                config=config,
            )
            interference_penalty = _segment_interference_penalty(
                line=line,
                source=source,
                config=config,
            )

            estimated_penalty = obstacle_penalty + interference_penalty

            edges.append(
                CandidateGraphEdge(
                    src=entity_a.id,
                    dst=entity_b.id,
                    distance_m=round(distance, 3),
                    estimated_penalty=round(estimated_penalty, 3),
                )
            )

    edges.sort(key=lambda edge: (edge.src, edge.dst))
    return edges


def _point_inside_blocking_obstacle(point: Point, source: ScenarioSource) -> bool:
    for obstacle in source.obstacles:
        if not obstacle.blocks_flight:
            continue
        geometry = _obstacle_geometry(obstacle)
        if geometry.contains(point):
            return True
    return False


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _generate_waypoint_candidates_for_drone(
    drone: DroneEntity,
    source: ScenarioSource,
    directions: int,
) -> list[WaypointCandidate]:
    candidates: list[WaypointCandidate] = []

    step = drone.waypoint_step_m

    for index in range(directions):
        theta = (2.0 * math.pi * index) / directions
        x = drone.position.x + (step * math.cos(theta))
        y = drone.position.y + (step * math.sin(theta))

        x = _clamp(x, 0.0, source.map.width)
        y = _clamp(y, 0.0, source.map.height)

        point = Point(x, y)
        if _point_inside_blocking_obstacle(point, source):
            continue

        move_cost = math.hypot(x - drone.position.x, y - drone.position.y)
        candidates.append(
            WaypointCandidate(
                drone_id=drone.id,
                point=Point2D(x=round(x, 3), y=round(y, 3)),
                move_cost=round(move_cost, 3),
            )
        )

    # Include current position as a valid "hold" candidate so the movement policy
    # later has an explicit no-op option.
    candidates.append(
        WaypointCandidate(
            drone_id=drone.id,
            point=Point2D(x=drone.position.x, y=drone.position.y),
            move_cost=0.0,
        )
    )

    candidates.sort(key=lambda candidate: (candidate.drone_id, candidate.move_cost, candidate.point.x))
    return candidates


def _build_waypoint_candidates(
    source: ScenarioSource,
    config: dict[str, Any],
) -> list[WaypointCandidate]:
    directions = int(config["waypoint_directions"])
    all_candidates: list[WaypointCandidate] = []

    for entity in source.entities:
        if isinstance(entity, DroneEntity):
            all_candidates.extend(
                _generate_waypoint_candidates_for_drone(
                    drone=entity,
                    source=source,
                    directions=directions,
                )
            )

    return all_candidates


def _build_mobility_constraints(source: ScenarioSource) -> list[MobilityConstraint]:
    constraints: list[MobilityConstraint] = []

    for entity in source.entities:
        if not isinstance(entity, DroneEntity):
            continue

        constraints.append(
            MobilityConstraint(
                drone_id=entity.id,
                max_speed_mps=entity.max_speed_mps,
                movement_bounds=Size2D(
                    width=source.map.width,
                    height=source.map.height,
                ),
            )
        )

    constraints.sort(key=lambda item: item.drone_id)
    return constraints


def _expand_runtime_schedule(source: ScenarioSource) -> list[RuntimeScheduleEntry]:
    entries: list[RuntimeScheduleEntry] = []

    traffic_classes_by_id = {traffic_class.id: traffic_class for traffic_class in source.traffic_classes}

    for scheduled in source.scheduled_traffic:
        traffic_class = traffic_classes_by_id[scheduled.traffic_class_id]

        entries.append(
            RuntimeScheduleEntry(
                time_s=scheduled.time_window.start_time_s,
                action="traffic_start",
                target_id=scheduled.traffic_class_id,
                payload={
                    "event_id": scheduled.id,
                    "flow_class": traffic_class.flow_class.value,
                    "rate_kbps": traffic_class.rate_kbps,
                    "sla_latency_ms": traffic_class.sla_latency_ms,
                },
            )
        )
        entries.append(
            RuntimeScheduleEntry(
                time_s=scheduled.time_window.end_time_s,
                action="traffic_stop",
                target_id=scheduled.traffic_class_id,
                payload={
                    "event_id": scheduled.id,
                },
            )
        )

    for chaos in source.chaos_events:
        payload: dict[str, str | int | float | bool] = {
            "event_id": chaos.id,
            "event_type": chaos.event_type.value,
            "duration_s": chaos.duration_s,
        }
        if chaos.intensity is not None:
            payload["intensity"] = chaos.intensity

        entries.append(
            RuntimeScheduleEntry(
                time_s=chaos.trigger_time_s,
                action=f"chaos_{chaos.event_type.value}",
                target_id=chaos.target_entity_id,
                payload=payload,
            )
        )

        entries.append(
            RuntimeScheduleEntry(
                time_s=chaos.trigger_time_s + chaos.duration_s,
                action=f"chaos_{chaos.event_type.value}_end",
                target_id=chaos.target_entity_id,
                payload={
                    "event_id": chaos.id,
                    "event_type": chaos.event_type.value,
                },
            )
        )

    entries.sort(key=lambda entry: (entry.time_s, entry.action, entry.target_id))
    return entries


def _build_compilation_metadata(
    source: ScenarioSource,
    config: dict[str, Any],
) -> CompilationMetadata:
    source_json_obj = source.model_dump(mode="json")
    return CompilationMetadata(
        source_scenario_id=source.metadata.scenario_id,
        source_hash=_sha256_hex(source_json_obj),
        compiler_version=COMPILER_VERSION,
        config_hash=_sha256_hex(config),
        seed=source.metadata.seed,
        generated_at=_now_iso(),
    )


def compile_scenario(
    source_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    write_outputs: bool = True,
    config_overrides: dict[str, Any] | None = None,
) -> tuple[CompiledScenario, dict[str, Any]]:
    """
    Compile an authored scenario JSON file into a CompiledScenario plus a small report.

    Returns:
        (compiled_scenario, compile_report)
    """
    source_path = Path(source_path)
    source = _load_source_scenario(source_path)

    config = dict(DEFAULT_CONFIG)
    if config_overrides:
        config.update(config_overrides)

    artifacts = _build_compile_artifact_paths(
        source_path=source_path,
        source=source,
        output_dir=Path(output_dir) if output_dir is not None else None,
    )

    normalized_entities = _normalize_entities(source)
    obstacle_index, obstacle_geometries = _build_obstacle_index(source, config)
    candidate_graph_edges = _build_candidate_graph_edges(source, obstacle_geometries, config)
    waypoint_candidates = _build_waypoint_candidates(source, config)
    mobility_constraints = _build_mobility_constraints(source)
    runtime_schedule = _expand_runtime_schedule(source)
    compilation_metadata = _build_compilation_metadata(source, config)

    compiled = CompiledScenario(
        compilation_metadata=compilation_metadata,
        normalized_entities=normalized_entities,
        obstacle_index=obstacle_index,
        candidate_graph_edges=candidate_graph_edges,
        waypoint_candidates=waypoint_candidates,
        mobility_constraints=mobility_constraints,
        runtime_schedule=runtime_schedule,
    )

    compile_report: dict[str, Any] = {
        "scenario_id": source.metadata.scenario_id,
        "source_path": str(source_path),
        "output_dir": str(artifacts.output_dir),
        "compiler_version": COMPILER_VERSION,
        "generated_at": compilation_metadata.generated_at,
        "counts": {
            "entities": len(source.entities),
            "normalized_entities": len(normalized_entities),
            "obstacles": len(source.obstacles),
            "obstacle_index_entries": len(obstacle_index),
            "candidate_graph_edges": len(candidate_graph_edges),
            "waypoint_candidates": len(waypoint_candidates),
            "mobility_constraints": len(mobility_constraints),
            "runtime_schedule_entries": len(runtime_schedule),
            "traffic_classes": len(source.traffic_classes),
            "scheduled_traffic_events": len(source.scheduled_traffic),
            "chaos_events": len(source.chaos_events),
        },
        "config": config,
        "source_hash": compilation_metadata.source_hash,
        "config_hash": compilation_metadata.config_hash,
    }

    if write_outputs:
        artifacts.output_dir.mkdir(parents=True, exist_ok=True)

        # Keep a source copy beside the compiled artifact for easy replay/debugging.
        source_copy_path = artifacts.output_dir / "source.json"
        source_copy_path.write_text(
            json.dumps(source.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

        artifacts.compiled_path.write_text(
            json.dumps(compiled.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        artifacts.report_path.write_text(
            json.dumps(compile_report, indent=2),
            encoding="utf-8",
        )

    return compiled, compile_report


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile a MeshFlight scenario.")
    parser.add_argument("source", help="Path to a scenario source JSON file.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional explicit output directory. Defaults to artifacts/scenarios/<scenario_id>/",
    )
    parser.add_argument(
        "--grid-cell-size-m",
        type=float,
        default=None,
        help="Override obstacle index cell size in meters.",
    )
    parser.add_argument(
        "--waypoint-directions",
        type=int,
        default=None,
        help="Override number of radial waypoint directions per drone.",
    )
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    config_overrides: dict[str, Any] = {}
    if args.grid_cell_size_m is not None:
        config_overrides["grid_cell_size_m"] = args.grid_cell_size_m
    if args.waypoint_directions is not None:
        config_overrides["waypoint_directions"] = args.waypoint_directions

    _, report = compile_scenario(
        args.source,
        output_dir=args.output_dir,
        write_outputs=True,
        config_overrides=config_overrides or None,
    )

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
