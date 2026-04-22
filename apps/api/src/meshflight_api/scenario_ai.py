from __future__ import annotations

import json
import os
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


class ScenarioAIAssistResponse(BaseModel):
    doable: bool
    mode: Literal["generate", "update"]
    scenario: ScenarioSource | None = None
    summary: str | None = None
    warnings: list[str] = Field(default_factory=list)
    reason: str | None = None
    suggested_prompt: str | None = None


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
        )

    if request.mode == "update" and request.existing_scenario is None:
        raise ScenarioAIValidationError("Update mode requires an existing source scenario.")

    provider = create_ai_provider(request.provider)
    raw = provider.complete_assist_response(request)
    response = _coerce_valid_assist_response(provider, request, raw)

    if not response.doable:
        if _should_retry_for_inferred_defaults(response):
            repaired_raw = provider.repair_assist_response(
                request=request,
                invalid_payload=response.model_dump(mode="json"),
                validation_error=(
                    "The request is doable. Do not reject it just because some required fields "
                    "were omitted by the user. Infer reasonable defaults and return a complete scenario."
                ),
            )
            response = _coerce_valid_assist_response(provider, request, repaired_raw)

        if not response.doable:
            return response

    if response.scenario is None:
        raise ScenarioAIValidationError(
            "The selected LLM marked the request as doable but did not return a scenario."
        )

    validated_scenario = validate_editor_supported_scenario(response.scenario)

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

    return response.model_copy(update={"scenario": validated_scenario})


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
) -> ScenarioAIAssistResponse:
    try:
        response = ScenarioAIAssistResponse.model_validate(raw)
        return _validate_semantic_response(response, request)
    except (ValidationError, ScenarioAIValidationError) as error:
        repaired_raw = provider.repair_assist_response(
            request=request,
            invalid_payload=raw,
            validation_error=str(error),
        )
        try:
            repaired_response = ScenarioAIAssistResponse.model_validate(repaired_raw)
            return _validate_semantic_response(repaired_response, request)
        except (ValidationError, ScenarioAIValidationError) as repaired_error:
            raise ScenarioAIValidationError(
                f"{provider.display_name} returned an invalid scenario payload that does not match the MeshFlight schema."
            ) from repaired_error


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
- Keep every coordinate and geometry within the canvas bounds.
- Ensure ids are unique.
- Ensure required fields are present.
- Ensure numeric values are sane and positive where required.
- For update mode, preserve the existing scenario unless the user explicitly asks to change parts of it.
- For generate mode, create a complete new scenario with useful metadata.
- Use schema_version "0.1.0".
- Keep traffic_classes and scheduled_traffic as empty arrays for this editor workflow.

Preferred canvas bounds:
- width={canvas_width}
- height={canvas_height}

Existing scenario JSON for update mode:
{existing_scenario_json}

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
""".strip()


def _preferred_canvas(request: ScenarioAIAssistRequest) -> tuple[float, float]:
    if request.canvas is not None:
        return request.canvas.width, request.canvas.height
    if request.existing_scenario is not None:
        return request.existing_scenario.map.width, request.existing_scenario.map.height
    return 2000, 1200


def _should_retry_for_inferred_defaults(
    response: ScenarioAIAssistResponse,
) -> bool:
    if response.doable:
        return False

    reason = (response.reason or "").lower()
    missing_field_markers = (
        "missing required",
        "missing properties",
        "missing fields",
        "lack",
        "lacks",
        "omitted",
    )
    inferable_field_markers = (
        "battery",
        "range",
        "radio",
        "comms",
        "capacity",
        "demand",
        "attenuation",
        "speed",
        "metadata",
    )
    return any(marker in reason for marker in missing_field_markers) and any(
        marker in reason for marker in inferable_field_markers
    )


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
        timeout_s_raw = os.getenv("OLLAMA_TIMEOUT_S", "").strip() or "300"
        try:
            timeout_s = max(30.0, float(timeout_s_raw))
        except ValueError:
            timeout_s = 300.0
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
