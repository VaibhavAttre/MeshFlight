from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from meshflight_schema import ScenarioSource

from .storage import (
    compile_scenario_source,
    ensure_storage_dirs,
    list_scenarios,
    load_scenario_source,
    save_compiled_scenario,
    save_scenario_source,
    scenario_source_path,
)


class ScenarioSummary(BaseModel):
    scenario_id: str
    title: str
    updated_at: str
    has_compiled: bool


class SaveScenarioResponse(BaseModel):
    scenario_id: str
    path: str


class CompileScenarioResponse(BaseModel):
    scenario_id: str
    source_path: str
    compiled_path: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_storage_dirs()
    yield


app = FastAPI(title="MeshFlight API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/scenarios", response_model=list[ScenarioSummary])
def get_scenarios() -> list[ScenarioSummary]:
    return [ScenarioSummary.model_validate(item) for item in list_scenarios()]


@app.get("/api/scenarios/{scenario_id}", response_model=ScenarioSource)
def get_scenario(scenario_id: str) -> ScenarioSource:
    path = scenario_source_path(scenario_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Scenario not found")

    return load_scenario_source(scenario_id)


@app.post("/api/scenarios", response_model=SaveScenarioResponse)
def post_scenario(scenario: ScenarioSource) -> SaveScenarioResponse:
    path = save_scenario_source(scenario)
    return SaveScenarioResponse(
        scenario_id=scenario.metadata.scenario_id,
        path=str(path),
    )


@app.post("/api/scenarios/{scenario_id}/compile", response_model=CompileScenarioResponse)
def post_compile_scenario(scenario_id: str) -> CompileScenarioResponse:
    source_path = scenario_source_path(scenario_id)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Scenario not found")

    scenario = load_scenario_source(scenario_id)
    compiled = compile_scenario_source(scenario)
    compiled_path = save_compiled_scenario(compiled)

    return CompileScenarioResponse(
        scenario_id=scenario_id,
        source_path=str(source_path),
        compiled_path=str(compiled_path),
    )
