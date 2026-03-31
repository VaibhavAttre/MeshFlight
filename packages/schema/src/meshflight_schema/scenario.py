from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .common import (
    EntityType,
    EventType,
    FlowClass,
    MeshFlightModel,
    ObstacleType,
    Point2D,
    Size2D,
    TimeWindow,
)


class ScenarioMetadata(MeshFlightModel):
    scenario_id: str = Field(min_length=3)
    schema_version: str = Field(min_length=1)
    title: str = Field(min_length=3)
    description: str = ""
    seed: int = Field(ge=0)
    created_at: str = Field(min_length=1)
    authoring_version: str = Field(min_length=1)


class MapLayer(MeshFlightModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    visible: bool = True


class MapConfig(MeshFlightModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    grid_resolution: float = Field(gt=0)
    unit_scale_meters: float = Field(default=1.0, gt=0)
    origin: Point2D
    layers: list[MapLayer] = Field(default_factory=list)


class BaseEntity(MeshFlightModel):
    id: str = Field(min_length=1)
    type: EntityType
    label: str = Field(min_length=1)
    position: Point2D
    tags: list[str] = Field(default_factory=list)


class DroneEntity(BaseEntity):
    type: Literal[EntityType.DRONE] = EntityType.DRONE
    battery_capacity_mah: float = Field(gt=0)
    max_speed_mps: float = Field(gt=0)
    comms_range_m: float = Field(gt=0)
    waypoint_step_m: float = Field(gt=0)


class GatewayEntity(BaseEntity):
    type: Literal[EntityType.GATEWAY] = EntityType.GATEWAY
    uplink_capacity_mbps: float = Field(gt=0)
    comms_range_m: float = Field(gt=0)


class ClientEntity(BaseEntity):
    type: Literal[EntityType.CLIENT] = EntityType.CLIENT
    demand_profile: str = Field(min_length=1)


class InterferenceEmitterEntity(BaseEntity):
    type: Literal[EntityType.INTERFERENCE_EMITTER] = EntityType.INTERFERENCE_EMITTER
    radius_m: float = Field(gt=0)
    intensity: float = Field(ge=0)


ScenarioEntity = DroneEntity | GatewayEntity | ClientEntity | InterferenceEmitterEntity


class BaseObstacle(MeshFlightModel):
    id: str = Field(min_length=1)
    type: ObstacleType
    label: str = Field(min_length=1)
    attenuation_db: float = Field(ge=0)
    blocks_flight: bool = False


class RectObstacle(BaseObstacle):
    shape: Literal["rect"] = "rect"
    position: Point2D
    size: Size2D


class SegmentObstacle(BaseObstacle):
    shape: Literal["segment"] = "segment"
    start: Point2D
    end: Point2D


class CircleObstacle(BaseObstacle):
    shape: Literal["circle"] = "circle"
    center: Point2D
    radius: float = Field(gt=0)


ScenarioObstacle = RectObstacle | SegmentObstacle | CircleObstacle


class DemandZone(MeshFlightModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    center: Point2D
    radius_m: float = Field(gt=0)
    priority: int = Field(ge=1, le=10)


class TrafficClass(MeshFlightModel):
    id: str = Field(min_length=1)
    flow_class: FlowClass
    source_entity_ids: list[str] = Field(min_length=1)
    destination_entity_ids: list[str] = Field(min_length=1)
    rate_kbps: int = Field(gt=0)
    sla_latency_ms: int = Field(gt=0)


class ScheduledTrafficEvent(MeshFlightModel):
    id: str = Field(min_length=1)
    traffic_class_id: str = Field(min_length=1)
    time_window: TimeWindow


class ChaosEvent(MeshFlightModel):
    id: str = Field(min_length=1)
    event_type: EventType
    target_entity_id: str = Field(min_length=1)
    trigger_time_s: float = Field(ge=0)
    duration_s: float = Field(gt=0)
    intensity: float | None = Field(default=None, ge=0)


class ScenarioSource(MeshFlightModel):
    metadata: ScenarioMetadata
    map: MapConfig
    entities: list[ScenarioEntity] = Field(default_factory=list)
    obstacles: list[ScenarioObstacle] = Field(default_factory=list)
    demand_zones: list[DemandZone] = Field(default_factory=list)
    traffic_classes: list[TrafficClass] = Field(default_factory=list)
    scheduled_traffic: list[ScheduledTrafficEvent] = Field(default_factory=list)
    chaos_events: list[ChaosEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "ScenarioSource":
        entity_ids = {entity.id for entity in self.entities}
        traffic_class_ids = {traffic_class.id for traffic_class in self.traffic_classes}

        if len(entity_ids) != len(self.entities):
            raise ValueError("Entity ids must be unique")

        obstacle_ids = [obstacle.id for obstacle in self.obstacles]
        if len(obstacle_ids) != len(set(obstacle_ids)):
            raise ValueError("Obstacle ids must be unique")

        for entity in self.entities:
            if entity.position.x > self.map.width or entity.position.y > self.map.height:
                raise ValueError(f"Entity {entity.id} is outside map bounds")

        for traffic_class in self.traffic_classes:
            missing_sources = set(traffic_class.source_entity_ids) - entity_ids
            missing_destinations = set(traffic_class.destination_entity_ids) - entity_ids
            if missing_sources or missing_destinations:
                raise ValueError(
                    f"Traffic class {traffic_class.id} references unknown entities: "
                    f"{sorted(missing_sources | missing_destinations)}"
                )

        for scheduled_event in self.scheduled_traffic:
            if scheduled_event.traffic_class_id not in traffic_class_ids:
                raise ValueError(
                    f"Scheduled traffic event {scheduled_event.id} references unknown "
                    f"traffic class {scheduled_event.traffic_class_id}"
                )

        for chaos_event in self.chaos_events:
            if chaos_event.target_entity_id not in entity_ids:
                raise ValueError(
                    f"Chaos event {chaos_event.id} references unknown entity "
                    f"{chaos_event.target_entity_id}"
                )

        return self
