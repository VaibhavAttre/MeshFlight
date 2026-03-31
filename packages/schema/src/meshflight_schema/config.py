from __future__ import annotations

from pydantic import Field

from .common import MeshFlightModel


class RunConfig(MeshFlightModel):
    run_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    seed: int = Field(ge=0)
    tick_interval_ms: int = Field(gt=0)
    snapshot_interval_ms: int = Field(gt=0)
    max_runtime_s: int = Field(gt=0)
    baseline_policy_name: str = Field(min_length=1)
