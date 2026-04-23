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
from .scenario_plan import (
    AIScenarioProviderName,
    MeshFlightScenarioPlanV1,
    ScenarioAIAssistRequest,
    ScenarioAIValidationError,
    ScenarioCanvasRequest,
    _infer_layout_from_prompt,
    apply_update_metadata_preserve,
    build_scenario_plan_prompt,
    build_scenario_plan_repair_prompt,
    merge_meshflight_plan_with_user_prompt,
    scenario_plan_to_source,
    validate_editor_supported_scenario,
)
ROOT_DIR = Path(__file__).resolve().parents[4]
AI_USAGE_DIR = ROOT_DIR / "artifacts" / "reports" / "ai_usage"


class ScenarioAIProviderError(RuntimeError):
    pass


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
    plan_repair_passes: int = 0
    deterministic_plan_builder_used: bool = False
    llm_invocations: int = 0
    heuristic_prompt_fallback_used: bool = False
    raw_llm_logged: bool = False
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

    plan_request = request
    provider = create_ai_provider(request.provider)
    base_url, model = _provider_display_config(request.provider)
    run_events: list[AIAssistEvent] = [AIAssistEvent(name="llm_start", detail=f"{request.provider} plan")]

    raw = provider.complete_scenario_plan(plan_request)
    raw_logged = _maybe_log_raw_llm_output("llm_plan_raw", raw)
    run_events.append(AIAssistEvent(name="llm_plan_received", detail="Received JSON plan from model."))

    llm_invocations = 1
    try:
        plan, plan_repairs = _coerce_valid_scenario_plan(
            provider,
            plan_request,
            raw,
        )
    except ScenarioAIValidationError as error:
        if _allow_synthetic_fallback():
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
                                detail="The model could not return a valid scenario plan after repair attempts.",
                            ),
                            AIAssistEvent(name="heuristic_prompt_fallback", detail=str(error)),
                        ],
                        plan_repair_passes=0,
                        deterministic_plan_builder_used=False,
                        llm_invocations=llm_invocations,
                        heuristic_prompt_fallback_used=True,
                        raw_llm_logged=raw_logged,
                        schema_repair_passes=0,
                        synthetic_fallback_used=True,
                        alignment_pass_attempted=False,
                        alignment_pass_succeeded=False,
                    )
                }
            )
        return ScenarioAIAssistResponse(
            doable=False,
            mode=request.mode,
            reason=(
                "The model could not return a valid scenario plan JSON. "
                "Enable AI_ASSIST_ALLOW_SYNTHETIC_FALLBACK=true to allow a local prompt-based fallback, or try a different model."
            ),
            warnings=[],
            ai_diagnostics=AIAssistDiagnostics(
                provider=request.provider,
                llm_used=True,
                model=model,
                base_url=base_url,
                events=run_events
                + [
                    AIAssistEvent(name="llm_error", detail="Invalid scenario plan JSON from model."),
                    AIAssistEvent(name="validation_failure", detail=str(error)),
                ],
                plan_repair_passes=0,
                deterministic_plan_builder_used=False,
                llm_invocations=llm_invocations,
                heuristic_prompt_fallback_used=False,
                raw_llm_logged=raw_logged,
                schema_repair_passes=0,
                synthetic_fallback_used=False,
                alignment_pass_attempted=False,
                alignment_pass_succeeded=False,
            ),
        )

    if not plan.feasible:
        return ScenarioAIAssistResponse(
            doable=False,
            mode=request.mode,
            reason=plan.reason or "The model could not map this request onto supported objects.",
            suggested_prompt=plan.suggested_user_prompt,
            summary=plan.summary,
            warnings=[],
            ai_diagnostics=AIAssistDiagnostics(
                provider=request.provider,
                llm_used=True,
                model=model,
                base_url=base_url,
                events=run_events
                + [AIAssistEvent(name="llm_plan_rejected", detail=plan.reason or "Model marked the plan as infeasible.")],
                plan_repair_passes=plan_repairs,
                deterministic_plan_builder_used=False,
                llm_invocations=llm_invocations,
                heuristic_prompt_fallback_used=False,
                raw_llm_logged=raw_logged,
                schema_repair_passes=plan_repairs,
                synthetic_fallback_used=False,
                alignment_pass_attempted=False,
                alignment_pass_succeeded=False,
            ),
        )

    plan = merge_meshflight_plan_with_user_prompt(plan, request.prompt.strip())
    run_events.append(
        AIAssistEvent(
            name="plan_enriched",
            detail="Compiled object counts from the user prompt (model `counts` are ignored to avoid stale templates).",
        )
    )

    try:
        built = scenario_plan_to_source(plan_request, plan)
        built = apply_update_metadata_preserve(plan_request, built)
    except ScenarioAIValidationError as error:
        if _allow_synthetic_fallback():
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
                                name="build_error",
                                detail="Deterministic build failed; used prompt heuristics instead.",
                            ),
                            AIAssistEvent(name="heuristic_prompt_fallback", detail=str(error)),
                        ],
                        plan_repair_passes=plan_repairs,
                        deterministic_plan_builder_used=True,
                        llm_invocations=llm_invocations,
                        heuristic_prompt_fallback_used=True,
                        raw_llm_logged=raw_logged,
                        schema_repair_passes=plan_repairs,
                        synthetic_fallback_used=True,
                        alignment_pass_attempted=False,
                        alignment_pass_succeeded=False,
                    )
                }
            )
        return ScenarioAIAssistResponse(
            doable=False,
            mode=request.mode,
            reason="A valid plan was returned, but compiling it into a scenario failed, and heuristics are disabled.",
            warnings=[],
            ai_diagnostics=AIAssistDiagnostics(
                provider=request.provider,
                llm_used=True,
                model=model,
                base_url=base_url,
                events=run_events + [AIAssistEvent(name="build_error", detail=str(error))],
                plan_repair_passes=plan_repairs,
                deterministic_plan_builder_used=True,
                llm_invocations=llm_invocations,
                heuristic_prompt_fallback_used=False,
                raw_llm_logged=raw_logged,
                schema_repair_passes=plan_repairs,
                synthetic_fallback_used=False,
                alignment_pass_attempted=False,
                alignment_pass_succeeded=False,
            ),
        )

    summary = (plan.summary or "").strip() or "Compiled a valid scenario from the model’s structured plan on the server."
    warnings: list[str] = [
        "The model produced a small JSON plan; MeshFlight built coordinates and schema details deterministically in the API."
    ]

    return ScenarioAIAssistResponse(
        doable=True,
        mode=request.mode,
        scenario=built,
        summary=summary,
        warnings=warnings,
        ai_diagnostics=AIAssistDiagnostics(
            provider=request.provider,
            llm_used=True,
            model=model,
            base_url=base_url,
            events=run_events
            + [
                AIAssistEvent(
                    name="plan_compiled",
                    detail=f"Deterministic build succeeded after {plan_repairs} plan repair pass(es).",
                )
            ],
            plan_repair_passes=plan_repairs,
            deterministic_plan_builder_used=True,
            llm_invocations=llm_invocations,
            heuristic_prompt_fallback_used=False,
            raw_llm_logged=raw_logged,
            schema_repair_passes=plan_repairs,
            synthetic_fallback_used=False,
            alignment_pass_attempted=False,
            alignment_pass_succeeded=False,
        ),
    )


def _allow_synthetic_fallback() -> bool:
    raw = os.getenv("AI_ASSIST_ALLOW_SYNTHETIC_FALLBACK")
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _maybe_log_raw_llm_output(label: str, payload: object) -> bool:
    raw = os.getenv("AI_DEBUG_LLM", "").strip() or os.getenv("MESHFLIGHT_AI_DEBUG_LLM", "").strip()
    if raw.lower() not in {"1", "true", "yes", "on"}:
        return False
    if isinstance(payload, dict):
        text = json.dumps(payload, indent=2, ensure_ascii=True)
    else:
        text = str(payload)
    # Keep to one line in normal logs, but this is an explicit local-dev escape hatch.
    print(f"[meshflight-ai] {label}:\n{text}")
    return True


def _coerce_valid_scenario_plan(
    provider: "ScenarioProviderProtocol",
    request: ScenarioAIAssistRequest,
    raw: dict[str, object],
    *,
    starting_repair_count: int = 0,
) -> tuple[MeshFlightScenarioPlanV1, int]:
    candidate_payload: dict[str, object] = raw
    last_error: Exception | None = None
    repair_count = starting_repair_count

    for attempt in range(4):
        try:
            plan = MeshFlightScenarioPlanV1.model_validate(candidate_payload)
            return plan, repair_count
        except (ValidationError, ValueError) as error:
            last_error = error
            if attempt >= 3:
                break
            repair_count += 1
            candidate_payload = provider.repair_scenario_plan(
                request=request,
                invalid_payload=candidate_payload,
                validation_error=(
                    f"Attempt {attempt + 1} failed validation.\n{error}\n"
                    "Return a complete JSON object matching the MeshFlight scenario plan schema."
                ),
            )

    raise ScenarioAIValidationError(
        f"{provider.display_name} returned an invalid scenario plan JSON."
    ) from last_error


def _build_prompt_driven_generate_response(
    request: ScenarioAIAssistRequest,
) -> ScenarioAIAssistResponse:
    prompt = request.prompt.strip()
    layout = _infer_layout_from_prompt(prompt) or "gateway_left_drone_relay_clients_right"
    plan = MeshFlightScenarioPlanV1(
        request_mode=request.mode,
        feasible=True,
        summary="Heuristic fallback plan (no LLM JSON).",
        title=_extract_scenario_name(prompt),
        layout=layout,  # type: ignore[arg-type]
        notes="Prompt-driven scenario generated by backend synthesis after schema validation failure.",
    )
    plan = merge_meshflight_plan_with_user_prompt(plan, prompt)
    scenario = scenario_plan_to_source(request, plan)
    scenario = validate_editor_supported_scenario(scenario)
    scenario = apply_update_metadata_preserve(request, scenario)

    c = plan.counts
    gw = int(c.get("gateways", 1))
    dr = int(c.get("drones", 1))
    cl = int(c.get("clients", 1))
    bd = int(c.get("buildings", 0))
    veg = int(c.get("vegetation", 0))
    dz = int(c.get("demand_zones", 0))
    title = scenario.metadata.title

    return ScenarioAIAssistResponse(
        doable=True,
        mode=request.mode,
        scenario=scenario,
        summary=(
            f"Created {title} with {gw} gateway(s), {dr} drone(s), {cl} client(s), "
            f"{bd} building obstacle(s), {veg} vegetation zone(s), {dz} demand zone(s), "
            f"and {len(scenario.chaos_events)} chaos event(s)."
        ),
        warnings=[
            "No usable JSON plan was produced, so the API fell back to prompt-derived counts plus the same "
            "deterministic scenario builder used for valid plans (including contextual chaos events)."
        ],
        ai_diagnostics=AIAssistDiagnostics(
            provider=request.provider,
            llm_used=False,
            model=os.getenv("OLLAMA_MODEL", "").strip() or None,
            base_url=os.getenv("OLLAMA_BASE_URL", "").strip() or None,
            events=[
                AIAssistEvent(
                    name="heuristic_prompt_generator",
                    detail="Built via merge_meshflight_plan_with_user_prompt + scenario_plan_to_source (no LLM scenario JSON).",
                )
            ],
            plan_repair_passes=0,
            deterministic_plan_builder_used=True,
            llm_invocations=0,
            heuristic_prompt_fallback_used=True,
            raw_llm_logged=False,
            schema_repair_passes=0,
            synthetic_fallback_used=True,
            alignment_pass_attempted=False,
            alignment_pass_succeeded=False,
        ),
    )


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
            baseUrl=base_url,
            model=model,
            reason=str(error),
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

    def complete_scenario_plan(
        self, request: ScenarioAIAssistRequest
    ) -> dict[str, object]:
        raise NotImplementedError

    def repair_scenario_plan(
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
                baseUrl=self.base_url,
                model=self.model,
                reason=f"{error} {_ollama_setup_hint(self.base_url, self.model)}",
            )

        if self.model not in models:
            return ScenarioAIAssistHealthResponse(
                provider="ollama",
                available=False,
                baseUrl=self.base_url,
                model=self.model,
                reason=(
                    f"Ollama is reachable at {self.base_url}, but the model '{self.model}' is not installed. "
                    f"Run: ollama pull {self.model}"
                ),
            )

        return ScenarioAIAssistHealthResponse(
            provider="ollama",
            available=True,
            baseUrl=self.base_url,
            model=self.model,
            reason=None,
        )

    def complete_scenario_plan(
        self, request: ScenarioAIAssistRequest
    ) -> dict[str, object]:
        return self._request_json(build_scenario_plan_prompt(request))

    def repair_scenario_plan(
        self,
        request: ScenarioAIAssistRequest,
        invalid_payload: dict[str, object],
        validation_error: str,
    ) -> dict[str, object]:
        return self._request_json(
            build_scenario_plan_repair_prompt(
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
                    "You generate structured JSON only for a MeshFlight scenario *plan* (not a full scenario). "
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
            baseUrl=self.base_url,
            model=self.model,
            reason=None,
        )

    def complete_scenario_plan(
        self, request: ScenarioAIAssistRequest
    ) -> dict[str, object]:
        return self._request_json(build_scenario_plan_prompt(request))

    def repair_scenario_plan(
        self,
        request: ScenarioAIAssistRequest,
        invalid_payload: dict[str, object],
        validation_error: str,
    ) -> dict[str, object]:
        return self._request_json(
            build_scenario_plan_repair_prompt(
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
                            "You generate structured JSON only for a MeshFlight scenario *plan* (not a full scenario). "
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
            baseUrl=self.base_url,
            model=self.model,
            reason=None,
        )

    def complete_scenario_plan(
        self, request: ScenarioAIAssistRequest
    ) -> dict[str, object]:
        return self._request_json(build_scenario_plan_prompt(request))

    def repair_scenario_plan(
        self,
        request: ScenarioAIAssistRequest,
        invalid_payload: dict[str, object],
        validation_error: str,
    ) -> dict[str, object]:
        return self._request_json(
            build_scenario_plan_repair_prompt(
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
                "You generate structured JSON only for a MeshFlight scenario *plan* (not a full scenario). "
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


def _ollama_setup_hint(base_url: str, model: str) -> str:
    return (
        f"Start Ollama, run 'ollama pull {model}', and verify the local API at {base_url}/api/tags."
    )
