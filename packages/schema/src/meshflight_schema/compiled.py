from __future__ import annotations

from pydantic import Field

from .common import MeshFlightModel, Point2D, Size2D


class CompilationMetadata(MeshFlightModel):
    source_scenario_id: str = Field(min_length=1)
    source_hash: str = Field(min_length=1)
    compiler_version: str = Field(min_length=1)
    config_hash: str = Field(min_length=1)
    seed: int = Field(ge=0)
    generated_at: str = Field(min_length=1)


class NormalizedEntity(MeshFlightModel):
    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    properties: dict[str, str | int | float | bool] = Field(default_factory=dict)


class ObstacleIndexEntry(MeshFlightModel):
    obstacle_id: str = Field(min_length=1)
    cell_keys: list[str] = Field(default_factory=list)
    los_penalty: float = Field(ge=0)


class CandidateGraphEdge(MeshFlightModel):
    src: str = Field(min_length=1)
    dst: str = Field(min_length=1)
    distance_m: float = Field(ge=0)
    estimated_penalty: float = Field(ge=0)


class WaypointCandidate(MeshFlightModel):
    drone_id: str = Field(min_length=1)
    point: Point2D
    move_cost: float = Field(ge=0)


class MobilityConstraint(MeshFlightModel):
    drone_id: str = Field(min_length=1)
    max_speed_mps: float = Field(gt=0)
    movement_bounds: Size2D


class RuntimeScheduleEntry(MeshFlightModel):
    time_s: float = Field(ge=0)
    action: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    payload: dict[str, str | int | float | bool] = Field(default_factory=dict)


class CompiledScenario(MeshFlightModel):
    compilation_metadata: CompilationMetadata
    normalized_entities: list[NormalizedEntity] = Field(default_factory=list)
    obstacle_index: list[ObstacleIndexEntry] = Field(default_factory=list)
    candidate_graph_edges: list[CandidateGraphEdge] = Field(default_factory=list)
    waypoint_candidates: list[WaypointCandidate] = Field(default_factory=list)
    mobility_constraints: list[MobilityConstraint] = Field(default_factory=list)
    runtime_schedule: list[RuntimeScheduleEntry] = Field(default_factory=list)
