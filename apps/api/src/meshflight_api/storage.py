from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeGuard

from meshflight_schema import CompiledScenario, ScenarioSource
from meshflight_schema.common import Size2D
from meshflight_schema.compiled import (
    CandidateGraphEdge,
    CompilationMetadata,
    MobilityConstraint,
    NormalizedEntity,
    RuntimeScheduleEntry,
)
from meshflight_schema.scenario import DroneEntity, ScenarioEntity


ROOT_DIR = Path(__file__).resolve().parents[4]
ARTIFACTS_DIR = ROOT_DIR / "artifacts" / "scenarios"
SOURCE_DIR = ARTIFACTS_DIR / "source"
COMPILED_DIR = ARTIFACTS_DIR / "compiled"


def ensure_storage_dirs() -> None:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    COMPILED_DIR.mkdir(parents=True, exist_ok=True)


def scenario_source_path(scenario_id: str) -> Path:
    return SOURCE_DIR / f"{scenario_id}.scenario.json"


def compiled_scenario_path(scenario_id: str) -> Path:
    return COMPILED_DIR / f"{scenario_id}.compiled.json"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _model_to_json(model) -> str:
    return model.model_dump_json(indent=2)


def _is_drone_entity(entity: ScenarioEntity) -> TypeGuard[DroneEntity]:
    return isinstance(entity, DroneEntity)


def save_scenario_source(scenario: ScenarioSource) -> Path:
    ensure_storage_dirs()
    path = scenario_source_path(scenario.metadata.scenario_id)
    path.write_text(_model_to_json(scenario), encoding="utf-8")
    return path


def load_scenario_source(scenario_id: str) -> ScenarioSource:
    ensure_storage_dirs()
    path = scenario_source_path(scenario_id)
    return ScenarioSource.model_validate_json(path.read_text(encoding="utf-8"))


def list_scenarios() -> list[dict[str, str | bool]]:
    ensure_storage_dirs()
    scenarios: list[dict[str, str | bool]] = []

    for path in sorted(SOURCE_DIR.glob("*.scenario.json")):
        scenario = ScenarioSource.model_validate_json(path.read_text(encoding="utf-8"))
        scenarios.append(
            {
                "scenario_id": scenario.metadata.scenario_id,
                "title": scenario.metadata.title,
                "updated_at": scenario.metadata.created_at,
                "has_compiled": compiled_scenario_path(scenario.metadata.scenario_id).exists(),
            }
        )

    return scenarios


def compile_scenario_source(scenario: ScenarioSource) -> CompiledScenario:
    source_json = scenario.model_dump_json()
    source_hash = hashlib.sha256(source_json.encode("utf-8")).hexdigest()

    normalized_entities = [
        NormalizedEntity(
            id=entity.id,
            type=entity.type.value if hasattr(entity.type, "value") else str(entity.type),
            x=entity.position.x,
            y=entity.position.y,
            properties={
                "label": entity.label,
                "tag_count": len(entity.tags),
            },
        )
        for entity in scenario.entities
    ]

    candidate_graph_edges: list[CandidateGraphEdge] = []
    for src_index, source in enumerate(scenario.entities):
        for target in scenario.entities[src_index + 1 :]:
            dx = source.position.x - target.position.x
            dy = source.position.y - target.position.y
            distance_m = round((dx * dx + dy * dy) ** 0.5, 3)
            candidate_graph_edges.append(
                CandidateGraphEdge(
                    src=source.id,
                    dst=target.id,
                    distance_m=distance_m,
                    estimated_penalty=0,
                )
            )

    drone_entities = [entity for entity in scenario.entities if _is_drone_entity(entity)]

    mobility_constraints = [
        MobilityConstraint(
            drone_id=entity.id,
            max_speed_mps=float(entity.max_speed_mps),
            movement_bounds=Size2D(
                width=scenario.map.width,
                height=scenario.map.height,
            ),
        )
        for entity in drone_entities
    ]

    runtime_schedule: list[RuntimeScheduleEntry] = [
        RuntimeScheduleEntry(
            time_s=event.trigger_time_s,
            action=event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
            target_id=event.target_entity_id,
            payload={"duration_s": event.duration_s, "intensity": event.intensity or 0},
        )
        for event in scenario.chaos_events
    ]

    runtime_schedule.extend(
        RuntimeScheduleEntry(
            time_s=event.time_window.start_time_s,
            action="scheduled_traffic_start",
            target_id=event.traffic_class_id,
            payload={"end_time_s": event.time_window.end_time_s},
        )
        for event in scenario.scheduled_traffic
    )

    return CompiledScenario(
        compilation_metadata=CompilationMetadata(
            source_scenario_id=scenario.metadata.scenario_id,
            source_hash=source_hash,
            compiler_version="phase0-ui-bridge",
            config_hash=hashlib.sha256(
                json.dumps(
                    {
                        "map_width": scenario.map.width,
                        "map_height": scenario.map.height,
                        "seed": scenario.metadata.seed,
                    },
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
            seed=scenario.metadata.seed,
            generated_at=_utc_now(),
        ),
        normalized_entities=normalized_entities,
        candidate_graph_edges=candidate_graph_edges,
        mobility_constraints=mobility_constraints,
        runtime_schedule=runtime_schedule,
    )


def save_compiled_scenario(compiled: CompiledScenario) -> Path:
    ensure_storage_dirs()
    path = compiled_scenario_path(compiled.compilation_metadata.source_scenario_id)
    path.write_text(_model_to_json(compiled), encoding="utf-8")
    return path
