from __future__ import annotations

from pydantic import Field

from .common import MeshFlightModel, NodeStatus, Point2D


class SnapshotNodeState(MeshFlightModel):
    node_id: str = Field(min_length=1)
    position: Point2D
    battery_pct: float = Field(ge=0, le=100)
    queue_depth: int = Field(ge=0)
    status: NodeStatus


class SnapshotLinkState(MeshFlightModel):
    src: str = Field(min_length=1)
    dst: str = Field(min_length=1)
    connected: bool
    cost: float = Field(ge=0)
    capacity_mbps: float = Field(ge=0)


class RunSnapshot(MeshFlightModel):
    snapshot_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    time_s: float = Field(ge=0)
    nodes: list[SnapshotNodeState] = Field(default_factory=list)
    links: list[SnapshotLinkState] = Field(default_factory=list)
    summary_metrics: dict[str, float | int] = Field(default_factory=dict)
