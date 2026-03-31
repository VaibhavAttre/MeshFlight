from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "0.1.0"


class MeshFlightModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class EntityType(str, Enum):
    DRONE = "drone"
    GATEWAY = "gateway"
    CLIENT = "client"
    INTERFERENCE_EMITTER = "interference_emitter"


class ObstacleType(str, Enum):
    BUILDING = "building"
    WALL = "wall"
    VEGETATION = "vegetation"
    NO_FLY_ZONE = "no_fly_zone"


class EventType(str, Enum):
    NODE_FAILURE = "node_failure"
    OBSTACLE_APPEARANCE = "obstacle_appearance"
    INTERFERENCE_SPIKE = "interference_spike"
    DEMAND_BURST = "demand_burst"


class FlowClass(str, Enum):
    TELEMETRY = "telemetry"
    VIDEO = "video"
    COMMAND = "command"
    BACKGROUND = "background"


class NodeStatus(str, Enum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


class RunStatus(str, Enum):
    PENDING = "pending"
    COMPILING = "compiling"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Point2D(MeshFlightModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)


class Size2D(MeshFlightModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class TimeWindow(MeshFlightModel):
    start_time_s: float = Field(ge=0)
    end_time_s: float = Field(ge=0)

    @field_validator("end_time_s")
    @classmethod
    def validate_end(cls, value: float, info) -> float:
        start = info.data.get("start_time_s", 0)
        if value < start:
            raise ValueError("end_time_s must be greater than or equal to start_time_s")
        return value
