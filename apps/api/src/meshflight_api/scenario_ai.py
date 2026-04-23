from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from meshflight_schema import ScenarioSource

from .ollama_client import OllamaClient, OllamaClientError


AIScenarioProviderName = Literal["ollama", "gemini", "openai"]

SUPPORTED_ENTITY_TYPES = ("drone", "gateway", "client")
SUPPORTED_OBSTACLE_TYPES = ("building", "wall", "vegetation")
ROOT_DIR = Path(__file__).resolve().parents[4]
AI_USAGE_DIR = ROOT_DIR / "artifacts" / "reports" / "ai_usage"


class ScenarioAIProviderError(RuntimeError):
    pass


class ScenarioAIValidationError(ValueError):
    pass


class ScenarioCanvasRequest(BaseModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class ScenarioAIAssistRequest(BaseModel):
    provider: AIScenarioProviderName = "ollama"
    mode: Literal["generate", "update"]
    prompt: str = Field(min_length=1)
    existing_scenario: ScenarioSource | None = None
    existing_scenario_id: str | None = None
    canvas: ScenarioCanvasRequest | None = None
    conversation: list[str] = Field(default_factory=list)


class AIAssistEvent(BaseModel):
    name: str
    detail: str = ""


class AIAssistDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    llm_used: bool
    model: str | None = None
    base_url: str | None = None
    events: list[AIAssistEvent] = Field(default_factory=list)
    schema_repair_passes: int = 0
    synthetic_fallback_used: bool = False
    alignment_pass_attempted: bool = False
    alignment_pass_succeeded: bool = False


class ScenarioAIAssistResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doable: bool
    mode: Literal["generate", "update"]
    scenario: ScenarioSource | None = None
    summary: str | None = None
    warnings: list[str] = Field(default_factory=list)
    reason: str | None = None
    suggested_prompt: str | None = None
    ai_diagnostics: AIAssistDiagnostics | None = None


class ScenarioAIAssistHealthResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    provider: AIScenarioProviderName
    available: bool
    base_url: str | None = Field(default=None, alias="baseUrl")
    model: str | None = None
    reason: str | None = None


SCENARIO_RESPONSE_EXAMPLE = {
    "doable": True,
    "mode": "generate",
    "scenario": {
        "metadata": {
            "scenario_id": "small-emergency-response-test",
            "schema_version": "0.1.0",
            "title": "small-emergency-response-test",
            "description": "Small emergency response scenario with a relay chain around a blocked corridor.",
            "seed": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "authoring_version": "ai-assistant",
        },
        "map": {
            "width": 2000,
            "height": 1200,
            "grid_resolution": 20,
            "unit_scale_meters": 1,
            "origin": {"x": 0, "y": 0},
            "layers": [{"id": "base", "name": "Base", "visible": True}],
        },
        "entities": [
            {
                "id": "gateway-1",
                "type": "gateway",
                "label": "Gateway 1",
                "position": {"x": 200, "y": 600},
                "tags": ["editor:uplink=fiber"],
                "uplink_capacity_mbps": 250,
                "comms_range_m": 260,
            }
        ],
        "obstacles": [],
        "demand_zones": [],
        "traffic_classes": [],
        "scheduled_traffic": [],
        "chaos_events": [],
    },
    "summary": "Created a valid MeshFlight source scenario.",
    "warnings": [],
}


def check_prompt_doability(prompt: str) -> tuple[bool, str | None, str | None]:
    lowered = prompt.lower()

    unsupported_requests = [
        (
            ("3d", "altitude", "elevation", "terrain", "topography"),
            "The current editor only supports 2D scenarios and does not model altitude or terrain.",
            "Create a 2D emergency response scenario with drones, gateways, clients, buildings, and interference pressure.",
        ),
        (
            ("weather physics", "wind model", "rain fade", "storm simulation"),
            "The current editor does not support weather physics or environmental simulation models.",
            "Represent storm-affected areas with vegetation zones or interference-spike chaos events instead.",
        ),
        (
            ("map import", "real city map", "openstreetmap", "satellite imagery"),
            "The current editor does not support real map imports or satellite basemaps.",
            "Describe the layout in terms of buildings, walls, vegetation zones, gateways, clients, and drones on the 2D canvas.",
        ),
        (
            ("ray tracing", "rf propagation", "path loss model", "spectrum model"),
            "The current editor only supports simplified connectivity metadata such as range, attenuation, and interference pressure approximations.",
            "Ask for buildings, vegetation zones, and interference-spike events that approximate the radio environment.",
        ),
    ]

    for keywords, reason, suggestion in unsupported_requests:
        if any(keyword in lowered for keyword in keywords):
            return False, reason, suggestion

    return True, None, None


def generate_ai_assisted_scenario(
    request: ScenarioAIAssistRequest,
) -> ScenarioAIAssistResponse:
    doable, reason, suggested_prompt = check_prompt_doability(request.prompt)
    if not doable:
        return ScenarioAIAssistResponse(
            doable=False,
            mode=request.mode,
            reason=reason,
            suggested_prompt=suggested_prompt,
            warnings=[],
            ai_diagnostics=AIAssistDiagnostics(
                provider=request.provider,
                llm_used=False,
                model=None,
                base_url=None,
                events=[AIAssistEvent(name="pre_check", detail="Rejected prompt as not representable with current tools.")],
            ),
        )

    if request.mode == "update" and request.existing_scenario is None:
        raise ScenarioAIValidationError("Update mode requires an existing source scenario.")

    provider = create_ai_provider(request.provider)
    base_url, model = _provider_display_config(request.provider)
    run_events: list[AIAssistEvent] = [AIAssistEvent(name="llm_start", detail=f"{request.provider} generate")]
    raw = provider.complete_assist_response(request)
    repair_count = 0
    try:
        response, repair_count = _coerce_valid_assist_response(provider, request, raw)
    except ScenarioAIValidationError as error:
        if request.mode == "generate" and _allow_synthetic_fallback():
            fallback = _build_prompt_driven_generate_response(request)
            return fallback.model_copy(
                update={
                    "ai_diagnostics": AIAssistDiagnostics(
                        provider=request.provider,
                        llm_used=True,
                        model=model,
                        base_url=base_url,
                        events=run_events
                        + [
                            AIAssistEvent(
                                name="llm_error",
                                detail="Primary model output failed schema validation after repair attempts.",
                            ),
                            AIAssistEvent(name="synthetic_fallback", detail=str(error)),
                        ],
                        schema_repair_passes=repair_count,
                        synthetic_fallback_used=True,
                    )
                }
            )

        return ScenarioAIAssistResponse(
            doable=False,
            mode=request.mode,
            reason=(
                "The model returned invalid scenario JSON repeatedly and synthetic fallback is disabled. "
                "Enable AI_ASSIST_ALLOW_SYNTHETIC_FALLBACK=true or try a different model."
            ),
            warnings=[],
            ai_diagnostics=AIAssistDiagnostics(
                provider=request.provider,
                llm_used=True,
                model=model,
                base_url=base_url,
                events=run_events
                + [
                    AIAssistEvent(
                        name="llm_error",
                        detail="Primary model output failed schema validation after repair attempts.",
                    ),
                    AIAssistEvent(name="validation_failure", detail=str(error)),
                ],
                schema_repair_passes=repair_count,
                synthetic_fallback_used=False,
            ),
        )

    if not response.doable:
        repaired_raw = provider.repair_assist_response(
            request=request,
            invalid_payload=response.model_dump(mode="json"),
            validation_error=(
                "The request is representable in the current editor. Do not ask the user to rewrite it. "
                "Infer missing defaults, separate overlapping objects, fix unrealistic spacing, and return a complete valid scenario "
                "unless the prompt is truly unsupported by the editor feature set."
            ),
        )
        run_events.append(
            AIAssistEvent(
                name="soft_rejection_repair",
                detail="Retried a model rejection by forcing the provider to infer defaults and fix layout issues.",
            )
        )
        response, extra_repairs = _coerce_valid_assist_response(
            provider, request, repaired_raw, starting_repair_count=repair_count
        )
        repair_count = extra_repairs

        if not response.doable:
            return response.model_copy(
                update={
                    "ai_diagnostics": AIAssistDiagnostics(
                        provider=request.provider,
                        llm_used=True,
                        model=model,
                        base_url=base_url,
                        events=run_events
                        + [AIAssistEvent(name="llm_rejected", detail="Model marked prompt as not doable.")],
                        schema_repair_passes=repair_count,
                        synthetic_fallback_used=False,
                    )
                }
            )

    if response.scenario is None:
        raise ScenarioAIValidationError(
            "The selected LLM marked the request as doable but did not return a scenario."
        )

    try:
        validated_scenario = validate_editor_supported_scenario(response.scenario)
        alignment_attempted = True
        aligned_response = _attempt_prompt_alignment(provider, request, response, validated_scenario)
        alignment_succeeded = aligned_response is not None
        if aligned_response is not None:
            response = aligned_response
            validated_scenario = validate_editor_supported_scenario(aligned_response.scenario)
            run_events.append(AIAssistEvent(name="alignment_pass", detail="Prompt-alignment pass succeeded."))
        else:
            run_events.append(
                AIAssistEvent(
                    name="alignment_pass",
                    detail="Prompt-alignment pass ran but the model did not return a valid aligned payload, so the pre-alignment scenario is kept.",
                )
            )
    except ScenarioAIValidationError as error:
        if request.mode == "generate" and _allow_synthetic_fallback():
            fallback = _build_prompt_driven_generate_response(request)
            return fallback.model_copy(
                update={
                    "ai_diagnostics": AIAssistDiagnostics(
                        provider=request.provider,
                        llm_used=True,
                        model=model,
                        base_url=base_url,
                        events=run_events
                        + [
                            AIAssistEvent(name="post_validation_failure", detail=str(error)),
                            AIAssistEvent(name="synthetic_fallback", detail="Fallback used after validation failure."),
                        ],
                        schema_repair_passes=repair_count,
                        synthetic_fallback_used=True,
                    )
                }
            )
        return ScenarioAIAssistResponse(
            doable=False,
            mode=request.mode,
            reason="Generated scenario failed editor validation and fallback is disabled.",
            warnings=[],
            ai_diagnostics=AIAssistDiagnostics(
                provider=request.provider,
                llm_used=True,
                model=model,
                base_url=base_url,
                events=run_events + [AIAssistEvent(name="post_validation_failure", detail=str(error))],
                schema_repair_passes=repair_count,
                synthetic_fallback_used=False,
            ),
        )

    if request.mode == "update" and request.existing_scenario is not None:
        existing_metadata = request.existing_scenario.metadata
        validated_scenario = validated_scenario.model_copy(
            update={
                "metadata": validated_scenario.metadata.model_copy(
                    update={
                        "scenario_id": existing_metadata.scenario_id,
                        "created_at": existing_metadata.created_at,
                    }
                )
            }
        )

    return response.model_copy(
        update={
            "scenario": validated_scenario,
            "ai_diagnostics": AIAssistDiagnostics(
                provider=request.provider,
                llm_used=True,
                model=model,
                base_url=base_url,
                events=run_events,
                schema_repair_passes=repair_count,
                synthetic_fallback_used=False,
                alignment_pass_attempted=alignment_attempted,
                alignment_pass_succeeded=alignment_succeeded,
            ),
        }
    )


def _allow_synthetic_fallback() -> bool:
    raw = os.getenv("AI_ASSIST_ALLOW_SYNTHETIC_FALLBACK")
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _attempt_prompt_alignment(
    provider: "ScenarioProviderProtocol",
    request: ScenarioAIAssistRequest,
    response: ScenarioAIAssistResponse,
    scenario: ScenarioSource,
) -> ScenarioAIAssistResponse | None:
    """
    Ask the provider for a generic prompt-alignment pass so we don't hardcode
    one-off constraints in Python. If the returned payload is invalid, keep the
    already validated scenario.
    """
    try:
        aligned_raw = provider.repair_assist_response(
            request=request,
            invalid_payload=response.model_dump(mode="json"),
            validation_error=(
                "Perform one prompt-alignment pass: keep schema-valid structure, but adjust "
                "positions/metadata so the scenario better satisfies the user's natural-language request. "
                "Handle all explicit constraints in the prompt. Return full JSON payload."
            ),
        )
        aligned_response, _ = _coerce_valid_assist_response(provider, request, aligned_raw)
        if not aligned_response.doable or aligned_response.scenario is None:
            return None
        return aligned_response
    except ScenarioAIValidationError:
        return None


def _build_prompt_driven_generate_response(
    request: ScenarioAIAssistRequest,
) -> ScenarioAIAssistResponse:
    canvas_width, canvas_height = _preferred_canvas(request)
    prompt = request.prompt

    gateway_count = _extract_count(prompt, ("gateway", "gateways"), default=1, minimum=1, maximum=4)
    drone_count = _extract_count(prompt, ("drone", "drones"), default=3, minimum=1, maximum=24)
    client_count = _extract_count(prompt, ("client", "clients"), default=6, minimum=1, maximum=80)
    building_count = _extract_count(prompt, ("building", "buildings"), default=1, minimum=0, maximum=16)
    vegetation_count = _extract_count(
        prompt,
        ("vegetation zone", "vegetation zones", "tree zone", "tree zones", "interference zone", "interference zones"),
        default=1,
        minimum=0,
        maximum=16,
    )
    scenario_name = _extract_scenario_name(prompt) or "ai-generated-scenario"
    scenario_id = _slugify_scenario_id(scenario_name)
    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    left_x = canvas_width * 0.18
    right_x = canvas_width * 0.72
    center_y = canvas_height * 0.5
    relay_start_x = canvas_width * 0.33
    relay_end_x = canvas_width * 0.62

    entities: list[dict[str, object]] = []
    for index in range(gateway_count):
        y = _spread_value(index, gateway_count, center_y - 120, center_y + 120)
        entities.append(
            {
                "id": f"gateway-{index + 1}",
                "type": "gateway",
                "label": f"Gateway {index + 1}",
                "position": {"x": left_x, "y": y},
                "tags": ["editor:uplink=fiber"],
                "uplink_capacity_mbps": 300,
                "comms_range_m": 260,
            }
        )

    for index in range(drone_count):
        x = _spread_value(index, drone_count, relay_start_x, relay_end_x)
        y = _spread_value(index, drone_count, center_y - 80, center_y + 80)
        entities.append(
            {
                "id": f"drone-{index + 1}",
                "type": "drone",
                "label": f"Drone {index + 1}",
                "position": {"x": x, "y": y},
                "tags": ["editor:battery_pct=90"],
                "battery_capacity_mah": 110,
                "max_speed_mps": 15,
                "comms_range_m": 190,
                "waypoint_step_m": 25,
            }
        )

    demand_profiles = ["telemetry", "video", "telemetry", "control", "telemetry", "video"]
    for index in range(client_count):
        x = _spread_value(index, client_count, right_x - 80, right_x + 80)
        y = _spread_value(index, client_count, center_y - 180, center_y + 180)
        entities.append(
            {
                "id": f"client-{index + 1}",
                "type": "client",
                "label": f"Client {index + 1}",
                "position": {"x": x, "y": y},
                "tags": [],
                "demand_profile": demand_profiles[index % len(demand_profiles)],
            }
        )

    obstacles: list[dict[str, object]] = []
    for index in range(building_count):
        obstacles.append(
            {
                "id": f"building-{index + 1}",
                "type": "building",
                "label": f"Building {index + 1}",
                "attenuation_db": 10,
                "blocks_flight": True,
                "shape": "rect",
                "position": {
                    "x": _spread_value(index, building_count, canvas_width * 0.44, canvas_width * 0.54),
                    "y": _spread_value(index, building_count, center_y - 120, center_y + 120),
                },
                "size": {"width": 140, "height": 190},
            }
        )

    for index in range(vegetation_count):
        obstacles.append(
            {
                "id": f"vegetation-{index + 1}",
                "type": "vegetation",
                "label": (
                    f"Interference Zone {index + 1}"
                    if "interference" in prompt.lower()
                    else f"Vegetation Zone {index + 1}"
                ),
                "attenuation_db": 7,
                "blocks_flight": False,
                "shape": "circle",
                "center": {
                    "x": _spread_value(index, vegetation_count, canvas_width * 0.58, canvas_width * 0.7),
                    "y": _spread_value(index, vegetation_count, center_y - 90, center_y + 90),
                },
                "radius": 90,
            }
        )

    demand_zones = [
        {
            "id": "demand-zone-1",
            "label": "Primary Demand",
            "center": {"x": right_x, "y": center_y},
            "radius_m": 120,
            "priority": 7,
        }
    ]

    scenario_payload = {
        "metadata": {
            "scenario_id": scenario_id,
            "schema_version": "0.1.0",
            "title": scenario_name,
            "description": "Prompt-driven scenario generated by backend synthesis after schema validation failure.",
            "seed": 1,
            "created_at": now_iso,
            "authoring_version": "ai-assistant",
        },
        "map": {
            "width": canvas_width,
            "height": canvas_height,
            "grid_resolution": 20,
            "unit_scale_meters": 1,
            "origin": {"x": 0, "y": 0},
            "layers": [{"id": "base", "name": "Base", "visible": True}],
        },
        "entities": entities,
        "obstacles": obstacles,
        "demand_zones": demand_zones,
        "traffic_classes": [],
        "scheduled_traffic": [],
        "chaos_events": [],
    }

    scenario = ScenarioSource.model_validate(scenario_payload)
    scenario = validate_editor_supported_scenario(scenario)
    return ScenarioAIAssistResponse(
        doable=True,
        mode="generate",
        scenario=scenario,
        summary=(
            f"Created {scenario_name} with {gateway_count} gateway(s), {drone_count} drone(s), "
            f"{client_count} client(s), {building_count} building obstacle(s), and {vegetation_count} vegetation zone(s)."
        ),
        warnings=[
            "Model output did not pass schema validation, so the backend generated a schema-valid scenario directly from your prompt constraints."
        ],
        ai_diagnostics=AIAssistDiagnostics(
            provider=request.provider,
            llm_used=False,
            model=os.getenv("OLLAMA_MODEL", "").strip() or None,
            base_url=os.getenv("OLLAMA_BASE_URL", "").strip() or None,
            events=[AIAssistEvent(name="synthetic_generator", detail="Schema-safe synthesis from prompt counts.")],
            schema_repair_passes=0,
            synthetic_fallback_used=True,
        ),
    )


_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def _extract_count(
    prompt: str,
    aliases: tuple[str, ...],
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    lowered = prompt.lower()
    for alias in aliases:
        pattern = re.compile(
            rf"(?:\b(\d+)\b|\b({'|'.join(_NUMBER_WORDS.keys())})\b)\s+{re.escape(alias)}\b"
        )
        match = pattern.search(lowered)
        if match:
            digit, word = match.groups()
            value = int(digit) if digit else _NUMBER_WORDS.get(word, default)
            return max(minimum, min(maximum, value))
    return max(minimum, min(maximum, default))


def _extract_scenario_name(prompt: str) -> str | None:
    quoted = re.search(r'name\s+"([^"]+)"', prompt, flags=re.IGNORECASE)
    if quoted:
        return quoted.group(1).strip()
    single_quoted = re.search(r"name\s+'([^']+)'", prompt, flags=re.IGNORECASE)
    if single_quoted:
        return single_quoted.group(1).strip()
    return None


def _slugify_scenario_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "ai-generated-scenario"


def _spread_value(index: int, count: int, start: float, end: float) -> float:
    if count <= 1:
        return round((start + end) / 2, 2)
    fraction = index / (count - 1)
    return round(start + (end - start) * fraction, 2)


def get_ai_assist_health(
    provider_name: AIScenarioProviderName | None = None,
) -> ScenarioAIAssistHealthResponse:
    selected_provider = provider_name or _default_provider_name()

    try:
        provider = create_ai_provider(selected_provider)
        return provider.health()
    except ScenarioAIProviderError as error:
        base_url, model = _provider_display_config(selected_provider)
        return ScenarioAIAssistHealthResponse(
            provider=selected_provider,
            available=False,
            base_url=base_url,
            model=model,
            reason=str(error),
        )


def _coerce_valid_assist_response(
    provider: "ScenarioProviderProtocol",
    request: ScenarioAIAssistRequest,
    raw: dict[str, object],
    *,
    starting_repair_count: int = 0,
) -> tuple[ScenarioAIAssistResponse, int]:
    candidate_payload = raw
    last_error: Exception | None = None
    repair_count = starting_repair_count

    for attempt in range(4):
        try:
            response = ScenarioAIAssistResponse.model_validate(candidate_payload)
            return _validate_semantic_response(response, request), repair_count
        except (ValidationError, ScenarioAIValidationError) as error:
            last_error = error
            if attempt >= 3:
                break
            repair_count += 1
            candidate_payload = provider.repair_assist_response(
                request=request,
                invalid_payload=candidate_payload,
                validation_error=(
                    f"Attempt {attempt + 1} failed validation.\n"
                    f"{error}\n"
                    "Return a complete valid payload matching the required schema exactly."
                ),
            )

    raise ScenarioAIValidationError(
        f"{provider.display_name} returned an invalid scenario payload that does not match the MeshFlight schema."
    ) from last_error


def _validate_semantic_response(
    response: ScenarioAIAssistResponse,
    request: ScenarioAIAssistRequest,
) -> ScenarioAIAssistResponse:
    if response.mode != request.mode:
        raise ScenarioAIValidationError(
            f"The selected LLM returned mode '{response.mode}' for a '{request.mode}' request."
        )

    if response.doable and response.scenario is None:
        raise ScenarioAIValidationError(
            "The selected LLM marked the request as doable but omitted the scenario."
        )

    if not response.doable and not (response.reason and response.reason.strip()):
        raise ScenarioAIValidationError(
            "The selected LLM marked the request as not doable but did not include a reason."
        )

    return response


def build_ai_output_schema_summary() -> str:
    return json.dumps(
        {
            "type": "object",
            "required": ["doable", "mode"],
            "properties": {
                "doable": "boolean",
                "mode": '"generate" | "update"',
                "scenario": {
                    "type": "ScenarioSource or null",
                    "requiredWhenDoable": [
                        "metadata",
                        "map",
                        "entities",
                        "obstacles",
                        "demand_zones",
                        "traffic_classes",
                        "scheduled_traffic",
                        "chaos_events",
                    ],
                },
                "summary": "string or null",
                "warnings": "string[]",
                "reason": "string or null",
                "suggested_prompt": "string or null",
            },
        },
        indent=2,
    )


def build_ai_prompt(request: ScenarioAIAssistRequest) -> str:
    existing_scenario_json = (
        request.existing_scenario.model_dump_json(indent=2)
        if request.existing_scenario is not None
        else "null"
    )
    canvas_width, canvas_height = _preferred_canvas(request)
    conversation_history = (
        "\n".join(f"- {entry}" for entry in request.conversation if entry.strip())
        if request.conversation
        else "none"
    )

    return f"""
You generate MeshFlight scenario JSON for a React/TypeScript editor.

Return JSON only.
Do not include markdown.
Do not include explanations outside the JSON object.
The JSON must match the output schema summary below.

Important MeshFlight editor support constraints:
- Supported entity types: drone, gateway, client
- Supported obstacle types: building, wall, vegetation
- Supported extra sections: demand_zones, chaos_events
- Unsupported in the current editor AI path: interference_emitter entities, traffic_classes, scheduled_traffic, 3D altitude, weather physics, real map import
- If the user asks for an interference zone, represent it with a vegetation obstacle labeled as interference pressure, or with an interference_spike chaos event if that better matches the request.

Scenario rules:
- Respect exact coordinates and explicit values when the user provides them.
- If the user is vague, infer reasonable defaults.
- If the user does not explicitly provide a required field, you must generate a reasonable value for it yourself.
- Do not reject a request just because the user omitted metadata like battery, radio range, client demand profile, gateway capacity, map metadata, or obstacle attenuation. Fill those in.
- Do not return doable=false for fixable layout quality issues like overlapping objects, unrealistic spacing, or weak metadata defaults. Auto-adjust and return doable=true with warnings if needed.
- If any entities or obstacles share the same position by mistake, spread them to nearby valid positions and keep going.
- Keep every coordinate and geometry within the canvas bounds.
- Ensure ids are unique.
- Ensure required fields are present.
- Ensure numeric values are sane and positive where required.
- If the user asks for a constraint that is representable in the current schema, satisfy it in the returned scenario instead of only describing it in summary text.
- For update mode, preserve the existing scenario unless the user explicitly asks to change parts of it.
- For generate mode, create a complete new scenario with useful metadata.
- Use schema_version "0.1.0".
- Keep traffic_classes and scheduled_traffic as empty arrays for this editor workflow.

Preferred canvas bounds:
- width={canvas_width}
- height={canvas_height}

Existing scenario JSON for update mode:
{existing_scenario_json}

Conversation history for this assistant session (oldest first):
{conversation_history}

Output schema summary:
{build_ai_output_schema_summary()}

Example of the exact root structure when doable=true:
{json.dumps(SCENARIO_RESPONSE_EXAMPLE, indent=2)}

User request:
{request.prompt}
""".strip()


def build_ai_repair_prompt(
    request: ScenarioAIAssistRequest,
    invalid_payload: dict[str, object],
    validation_error: str,
) -> str:
    canvas_width, canvas_height = _preferred_canvas(request)
    conversation_history = (
        "\n".join(f"- {entry}" for entry in request.conversation if entry.strip())
        if request.conversation
        else "none"
    )
    return f"""
Repair the invalid MeshFlight scenario JSON below.
Return JSON only.
Do not include markdown.
Do not add commentary.

Original mode:
{request.mode}

Preferred canvas bounds:
- width={canvas_width}
- height={canvas_height}

Original user request:
{request.prompt}

Conversation history for this assistant session (oldest first):
{conversation_history}

Validation error:
{validation_error}

Invalid payload:
{json.dumps(invalid_payload, indent=2)}

You must:
- keep the top-level keys doable, mode, scenario, summary, warnings, reason, suggested_prompt
- return mode="{request.mode}"
- if doable=true, return a complete valid ScenarioSource in scenario
- if doable=false, return a clear reason and optional suggested_prompt
- if the request is otherwise representable, do not reject it because fields were omitted; infer those values and return a complete scenario instead
- use only the editor-supported types: drone, gateway, client, building, wall, vegetation, demand_zones, chaos_events
- keep traffic_classes and scheduled_traffic empty arrays
- keep all coordinates within bounds
- represent interference pressure with vegetation or interference_spike, not interference_emitter
- if two or more objects share the same position, move them to nearby unique positions and keep doable=true
- copy the ScenarioSource structure exactly from this template and replace values, do not rename keys:
{json.dumps(SCENARIO_RESPONSE_EXAMPLE["scenario"], indent=2)}
""".strip()


def _preferred_canvas(request: ScenarioAIAssistRequest) -> tuple[float, float]:
    if request.canvas is not None:
        return request.canvas.width, request.canvas.height
    if request.existing_scenario is not None:
        return request.existing_scenario.map.width, request.existing_scenario.map.height
    return 2000, 1200


def _default_provider_name() -> AIScenarioProviderName:
    candidate = (os.getenv("LLM_PROVIDER", "").strip().lower() or "ollama")
    if candidate in {"ollama", "gemini", "openai"}:
        return candidate  # type: ignore[return-value]
    return "ollama"


def _provider_display_config(provider_name: AIScenarioProviderName) -> tuple[str | None, str | None]:
    if provider_name == "gemini":
        return (
            os.getenv("GEMINI_BASE_URL", "").strip() or "https://generativelanguage.googleapis.com/v1beta",
            os.getenv("GEMINI_MODEL", "").strip() or "gemini-2.5-flash-lite",
        )
    if provider_name == "openai":
        return (
            os.getenv("OPENAI_BASE_URL", "").strip() or "https://api.openai.com/v1",
            os.getenv("OPENAI_MODEL", "").strip() or "gpt-5-nano",
        )
    return (
        os.getenv("OLLAMA_BASE_URL", "").strip() or "http://localhost:11434",
        os.getenv("OLLAMA_MODEL", "").strip() or "qwen2.5-coder:7b",
    )


def _parse_non_negative_int(value: str) -> int:
    try:
        return max(0, int(value.strip()))
    except (AttributeError, ValueError):
        return 0


def _usage_counter_path(provider_name: str) -> Path:
    AI_USAGE_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(UTC).date().isoformat()
    return AI_USAGE_DIR / f"{provider_name}-{day}.json"


def _enforce_daily_request_limit(provider_name: str, max_requests_per_day: int) -> None:
    if max_requests_per_day <= 0:
        raise ScenarioAIProviderError(
            f"{provider_name.capitalize()} scenario assistance is blocked because its daily request limit is set to 0."
        )

    path = _usage_counter_path(provider_name)
    if not path.exists():
        return

    payload = json.loads(path.read_text(encoding="utf-8"))
    used = int(payload.get("requests", 0))
    if used >= max_requests_per_day:
        raise ScenarioAIProviderError(
            f"{provider_name.capitalize()} scenario assistance hit its daily request cap of {max_requests_per_day}. "
            "Increase the limit only if you intentionally want to allow more billed requests."
        )


def _record_daily_request(provider_name: str) -> None:
    path = _usage_counter_path(provider_name)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {"requests": 0}

    payload["requests"] = int(payload.get("requests", 0)) + 1
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class ScenarioProviderProtocol:
    display_name: str

    def complete_assist_response(
        self, request: ScenarioAIAssistRequest
    ) -> dict[str, object]:
        raise NotImplementedError

    def repair_assist_response(
        self,
        request: ScenarioAIAssistRequest,
        invalid_payload: dict[str, object],
        validation_error: str,
    ) -> dict[str, object]:
        raise NotImplementedError

    def health(self) -> ScenarioAIAssistHealthResponse:
        raise NotImplementedError


class OllamaScenarioProvider(ScenarioProviderProtocol):
    display_name = "Ollama"

    def __init__(self, base_url: str, model: str, timeout_s: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.client = OllamaClient(self.base_url, timeout_s=self.timeout_s)

    @classmethod
    def from_environment(cls) -> "OllamaScenarioProvider":
        base_url, model = _provider_display_config("ollama")
        timeout_s_raw = os.getenv("OLLAMA_TIMEOUT_S", "").strip() or "600"
        try:
            timeout_s = max(60.0, float(timeout_s_raw))
        except ValueError:
            timeout_s = 600.0
        return cls(
            base_url=base_url or "http://localhost:11434",
            model=model or "qwen2.5-coder:7b",
            timeout_s=timeout_s,
        )

    def health(self) -> ScenarioAIAssistHealthResponse:
        try:
            models = self.client.list_models()
        except OllamaClientError as error:
            return ScenarioAIAssistHealthResponse(
                provider="ollama",
                available=False,
                base_url=self.base_url,
                model=self.model,
                reason=f"{error} {_ollama_setup_hint(self.base_url, self.model)}",
            )

        if self.model not in models:
            return ScenarioAIAssistHealthResponse(
                provider="ollama",
                available=False,
                base_url=self.base_url,
                model=self.model,
                reason=(
                    f"Ollama is reachable at {self.base_url}, but the model '{self.model}' is not installed. "
                    f"Run: ollama pull {self.model}"
                ),
            )

        return ScenarioAIAssistHealthResponse(
            provider="ollama",
            available=True,
            base_url=self.base_url,
            model=self.model,
            reason=None,
        )

    def complete_assist_response(
        self, request: ScenarioAIAssistRequest
    ) -> dict[str, object]:
        return self._request_json(build_ai_prompt(request))

    def repair_assist_response(
        self,
        request: ScenarioAIAssistRequest,
        invalid_payload: dict[str, object],
        validation_error: str,
    ) -> dict[str, object]:
        return self._request_json(
            build_ai_repair_prompt(
                request=request,
                invalid_payload=invalid_payload,
                validation_error=validation_error,
            )
        )

    def _request_json(self, user_prompt: str) -> dict[str, object]:
        try:
            return self.client.chat_json(
                model=self.model,
                system_prompt=(
                    "You generate structured MeshFlight scenario JSON only. "
                    "Return a single JSON object and no extra prose."
                ),
                user_prompt=user_prompt,
            )
        except OllamaClientError as error:
            raise ScenarioAIProviderError(
                f"{error} {_ollama_setup_hint(self.base_url, self.model)}"
            ) from error


class GeminiScenarioProvider(ScenarioProviderProtocol):
    display_name = "Gemini"

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    @classmethod
    def from_environment(cls) -> "GeminiScenarioProvider":
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key or api_key == "PASTE_YOUR_GEMINI_API_KEY_HERE":
            raise ScenarioAIProviderError(
                "GEMINI_API_KEY is not configured for Gemini scenario assistance."
            )

        base_url, model = _provider_display_config("gemini")
        return cls(
            api_key=api_key,
            model=model or "gemini-2.5-flash-lite",
            base_url=base_url or "https://generativelanguage.googleapis.com/v1beta",
        )

    def health(self) -> ScenarioAIAssistHealthResponse:
        return ScenarioAIAssistHealthResponse(
            provider="gemini",
            available=True,
            base_url=self.base_url,
            model=self.model,
            reason=None,
        )

    def complete_assist_response(
        self, request: ScenarioAIAssistRequest
    ) -> dict[str, object]:
        return self._request_json(build_ai_prompt(request))

    def repair_assist_response(
        self,
        request: ScenarioAIAssistRequest,
        invalid_payload: dict[str, object],
        validation_error: str,
    ) -> dict[str, object]:
        return self._request_json(
            build_ai_repair_prompt(
                request=request,
                invalid_payload=invalid_payload,
                validation_error=validation_error,
            )
        )

    def _request_json(self, prompt: str) -> dict[str, object]:
        payload = {
            "system_instruction": {
                "parts": [
                    {
                        "text": (
                            "You generate structured MeshFlight scenario assistance JSON only. "
                            "Return no prose outside the JSON object."
                        )
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
            },
        }

        with httpx.Client(timeout=60.0) as client:
            try:
                response = client.post(
                    f"{self.base_url}/models/{self.model}:generateContent",
                    headers={
                        "x-goog-api-key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            except httpx.HTTPError as error:
                raise ScenarioAIProviderError(
                    "The backend could not reach the Gemini API. Check your network/firewall settings and Gemini API access."
                ) from error

        if response.status_code >= 400:
            raise ScenarioAIProviderError(
                f"Gemini request failed with status {response.status_code}: {response.text}"
            )

        return self._extract_json_payload(response.json())

    def _extract_json_payload(self, payload: dict[str, object]) -> dict[str, object]:
        candidates = payload.get("candidates")
        if isinstance(candidates, list):
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                content = candidate.get("content")
                if not isinstance(content, dict):
                    continue
                parts = content.get("parts")
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        return json.loads(text)

        raise ScenarioAIProviderError("Gemini response did not contain structured JSON output.")


class OpenAIScenarioProvider(ScenarioProviderProtocol):
    display_name = "OpenAI"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        max_requests_per_day: int,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_requests_per_day = max_requests_per_day

    @classmethod
    def from_environment(cls) -> "OpenAIScenarioProvider":
        enabled = os.getenv("OPENAI_AI_ASSIST_ENABLED", "").strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            raise ScenarioAIProviderError(
                "OpenAI scenario assistance is disabled by default to avoid billing. "
                "Set OPENAI_AI_ASSIST_ENABLED=true and a positive OPENAI_MAX_AI_ASSIST_REQUESTS_PER_DAY to use it."
            )

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key or api_key == "PASTE_YOUR_OPENAI_API_KEY_HERE":
            raise ScenarioAIProviderError(
                "OPENAI_API_KEY is not configured for OpenAI scenario assistance."
            )

        max_requests_per_day = _parse_non_negative_int(
            os.getenv("OPENAI_MAX_AI_ASSIST_REQUESTS_PER_DAY", "0")
        )
        if max_requests_per_day <= 0:
            raise ScenarioAIProviderError(
                "OPENAI_MAX_AI_ASSIST_REQUESTS_PER_DAY must be greater than 0 to allow paid OpenAI requests."
            )

        base_url, model = _provider_display_config("openai")
        return cls(
            api_key=api_key,
            model=model or "gpt-5-nano",
            base_url=base_url or "https://api.openai.com/v1",
            max_requests_per_day=max_requests_per_day,
        )

    def health(self) -> ScenarioAIAssistHealthResponse:
        return ScenarioAIAssistHealthResponse(
            provider="openai",
            available=True,
            base_url=self.base_url,
            model=self.model,
            reason=None,
        )

    def complete_assist_response(
        self, request: ScenarioAIAssistRequest
    ) -> dict[str, object]:
        return self._request_json(build_ai_prompt(request))

    def repair_assist_response(
        self,
        request: ScenarioAIAssistRequest,
        invalid_payload: dict[str, object],
        validation_error: str,
    ) -> dict[str, object]:
        return self._request_json(
            build_ai_repair_prompt(
                request=request,
                invalid_payload=invalid_payload,
                validation_error=validation_error,
            )
        )

    def _request_json(self, prompt: str) -> dict[str, object]:
        _enforce_daily_request_limit("openai", self.max_requests_per_day)
        payload = {
            "model": self.model,
            "instructions": (
                "You generate structured MeshFlight scenario assistance JSON only. "
                "Return no prose outside the JSON object."
            ),
            "input": prompt,
            "text": {"format": {"type": "json_object"}},
        }

        with httpx.Client(timeout=60.0) as client:
            try:
                response = client.post(
                    f"{self.base_url}/responses",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            except httpx.HTTPError as error:
                raise ScenarioAIProviderError(
                    "The backend could not reach the OpenAI API. Check your network settings and OpenAI API access."
                ) from error

        if response.status_code >= 400:
            raise ScenarioAIProviderError(
                f"OpenAI request failed with status {response.status_code}: {response.text}"
            )

        try:
            response_payload = response.json()
        except json.JSONDecodeError as error:
            raise ScenarioAIProviderError(
                "OpenAI returned a non-JSON response for scenario assistance."
            ) from error

        _record_daily_request("openai")
        return self._extract_json_payload(response_payload)

    def _extract_json_payload(self, payload: dict[str, object]) -> dict[str, object]:
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return json.loads(output_text)

        output = payload.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for content_item in content:
                    if not isinstance(content_item, dict):
                        continue
                    text = content_item.get("text")
                    if isinstance(text, str) and text.strip():
                        return json.loads(text)

        raise ScenarioAIProviderError(
            "OpenAI response did not contain structured JSON output."
        )


def create_ai_provider(provider_name: AIScenarioProviderName) -> ScenarioProviderProtocol:
    if provider_name == "gemini":
        return GeminiScenarioProvider.from_environment()
    if provider_name == "openai":
        return OpenAIScenarioProvider.from_environment()
    return OllamaScenarioProvider.from_environment()


def validate_editor_supported_scenario(scenario: ScenarioSource) -> ScenarioSource:
    entity_types = {entity.type.value for entity in scenario.entities}
    unsupported_entities = sorted(entity_types - set(SUPPORTED_ENTITY_TYPES))
    if unsupported_entities:
        raise ScenarioAIValidationError(
            "The generated scenario uses unsupported editor entity types: "
            + ", ".join(unsupported_entities)
        )

    obstacle_types = {obstacle.type.value for obstacle in scenario.obstacles}
    unsupported_obstacles = sorted(obstacle_types - set(SUPPORTED_OBSTACLE_TYPES))
    if unsupported_obstacles:
        raise ScenarioAIValidationError(
            "The generated scenario uses unsupported editor obstacle types: "
            + ", ".join(unsupported_obstacles)
        )

    if scenario.traffic_classes:
        raise ScenarioAIValidationError(
            "The editor does not yet support AI-authored traffic classes."
        )

    if scenario.scheduled_traffic:
        raise ScenarioAIValidationError(
            "The editor does not yet support AI-authored scheduled traffic."
        )

    width = scenario.map.width
    height = scenario.map.height

    def check_point(name: str, x: float, y: float) -> None:
        if x < 0 or y < 0 or x > width or y > height:
            raise ScenarioAIValidationError(
                f"{name} is outside the canvas bounds ({width} x {height})."
            )

    for entity in scenario.entities:
        check_point(f"Entity {entity.id}", entity.position.x, entity.position.y)

    for obstacle in scenario.obstacles:
        if obstacle.shape == "rect":
            check_point(
                f"Building {obstacle.id}",
                obstacle.position.x,
                obstacle.position.y,
            )
        elif obstacle.shape == "segment":
            check_point(f"Wall {obstacle.id} start", obstacle.start.x, obstacle.start.y)
            check_point(f"Wall {obstacle.id} end", obstacle.end.x, obstacle.end.y)
        elif obstacle.shape == "circle":
            check_point(
                f"Vegetation zone {obstacle.id}",
                obstacle.center.x,
                obstacle.center.y,
            )

    for demand_zone in scenario.demand_zones:
        check_point(
            f"Demand zone {demand_zone.id}",
            demand_zone.center.x,
            demand_zone.center.y,
        )

    return scenario


def _ollama_setup_hint(base_url: str, model: str) -> str:
    return (
        f"Start Ollama, run 'ollama pull {model}', and verify the local API at {base_url}/api/tags."
    )
