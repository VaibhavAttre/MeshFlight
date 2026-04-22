from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from meshflight_schema import ScenarioSource

from .env import load_repo_env
from .scenario_ai import (
    AIScenarioProviderName,
    ScenarioAIAssistRequest,
    ScenarioAIAssistResponse,
    ScenarioAIAssistHealthResponse,
    ScenarioAIProviderError,
    ScenarioAIValidationError,
    generate_ai_assisted_scenario,
    get_ai_assist_health,
)
from .storage import (
    compile_saved_scenario,
    ensure_storage_dirs,
    list_scenarios,
    load_scenario_source,
    save_scenario_source,
    scenario_source_path,
)


load_repo_env()


class ScenarioSummary(BaseModel):
    scenario_id: str
    title: str
    updated_at: str
    has_compiled: bool


class SaveScenarioResponse(BaseModel):
    scenario_id: str
    title: str
    path: str


class CompileScenarioResponse(BaseModel):
    scenario_id: str
    source_path: str
    output_dir: str
    compiled_path: str
    report_path: str


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
    saved_scenario, path = save_scenario_source(scenario)
    return SaveScenarioResponse(
        scenario_id=saved_scenario.metadata.scenario_id,
        title=saved_scenario.metadata.title,
        path=str(path),
    )


@app.post("/api/scenarios/ai-assist", response_model=ScenarioAIAssistResponse)
def post_ai_assist_scenario(
    request: ScenarioAIAssistRequest,
) -> ScenarioAIAssistResponse:
    try:
        return generate_ai_assisted_scenario(request)
    except ScenarioAIProviderError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ScenarioAIValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get(
    "/api/scenarios/ai-assist/health",
    response_model=ScenarioAIAssistHealthResponse,
)
def get_ai_assist_scenario_health(
    provider: AIScenarioProviderName | None = None,
) -> ScenarioAIAssistHealthResponse:
    return get_ai_assist_health(provider)


@app.post("/api/scenarios/{scenario_id}/compile", response_model=CompileScenarioResponse)
def post_compile_scenario(scenario_id: str) -> CompileScenarioResponse:
    source_path = scenario_source_path(scenario_id)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Scenario not found")

    result = compile_saved_scenario(scenario_id)
    return CompileScenarioResponse.model_validate(result)
