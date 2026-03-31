from __future__ import annotations

from typing import Literal

from pydantic import Field

from meshflight_schema.common import MeshFlightModel


class EventBase(MeshFlightModel):
    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    emitted_at: str = Field(min_length=1)
    time_s: float = Field(ge=0)


class NodeStateChanged(EventBase):
    event_type: Literal["node_state_changed"] = "node_state_changed"
    node_id: str = Field(min_length=1)
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    battery_pct: float = Field(ge=0, le=100)
    queue_depth: int = Field(ge=0)
    status: str = Field(min_length=1)


class LinkStateChanged(EventBase):
    event_type: Literal["link_state_changed"] = "link_state_changed"
    src: str = Field(min_length=1)
    dst: str = Field(min_length=1)
    connected: bool
    snr_db: float
    cost: float = Field(ge=0)
    capacity_mbps: float = Field(ge=0)


class FlowLifecycleEvent(EventBase):
    event_type: Literal["flow_started", "flow_ended"]
    flow_id: str = Field(min_length=1)
    flow_class: str = Field(min_length=1)
    src: str = Field(min_length=1)
    dst: str = Field(min_length=1)
    rate_kbps: int = Field(gt=0)
    sla_latency_ms: int = Field(gt=0)


class FlowRerouted(EventBase):
    event_type: Literal["flow_rerouted"] = "flow_rerouted"
    flow_id: str = Field(min_length=1)
    old_path: list[str] = Field(default_factory=list)
    new_path: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class FailureInjected(EventBase):
    event_type: Literal["failure_injected"] = "failure_injected"
    failure_type: str = Field(min_length=1)
    target: str = Field(min_length=1)
    start_time_s: float = Field(ge=0)


class PolicyActionChosen(EventBase):
    event_type: Literal["policy_action_chosen"] = "policy_action_chosen"
    policy_name: str = Field(min_length=1)
    action: str = Field(min_length=1)
    affected_nodes: list[str] = Field(default_factory=list)


class SnapshotEmitted(EventBase):
    event_type: Literal["snapshot_emitted"] = "snapshot_emitted"
    snapshot_id: str = Field(min_length=1)
    summary_metrics: dict[str, float | int] = Field(default_factory=dict)


RuntimeEventEnvelope = (
    NodeStateChanged
    | LinkStateChanged
    | FlowLifecycleEvent
    | FlowRerouted
    | FailureInjected
    | PolicyActionChosen
    | SnapshotEmitted
)
