from __future__ import annotations

import json
import math
import random
import re
import secrets
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from meshflight_schema import ScenarioSource
from meshflight_schema.scenario import ChaosEvent

from .scenario_event_builder import (
    build_contextual_chaos_events,
    infer_intent_axes_from_counts,
    merge_intent_axes,
)

SUPPORTED_ENTITY_TYPES = ("drone", "gateway", "client")
SUPPORTED_OBSTACLE_TYPES = ("building", "wall", "vegetation")


class ScenarioAIValidationError(ValueError):
    pass


class ScenarioCanvasRequest(BaseModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)


AIScenarioProviderName = Literal["ollama", "gemini", "openai"]


class ScenarioAIAssistRequest(BaseModel):
    provider: AIScenarioProviderName = "ollama"
    mode: Literal["generate", "update"]
    prompt: str = Field(min_length=1)
    existing_scenario: ScenarioSource | None = None
    existing_scenario_id: str | None = None
    canvas: ScenarioCanvasRequest | None = None
    conversation: list[str] = Field(default_factory=list)


class MeshFlightScenarioPlanV1(BaseModel):
    """
    Small, stable contract for the LLM. The server deterministically compiles
    this into a full `ScenarioSource`.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["meshflight_scenario_plan_v1"] = "meshflight_scenario_plan_v1"
    version: Literal[1] = 1
    request_mode: Literal["generate", "update"]

    feasible: bool
    summary: str | None = None
    reason: str | None = None
    suggested_user_prompt: str | None = None
    title: str | None = None
    warnings: list[str] = Field(default_factory=list)

    # Optional reproducibility: when null, the API assigns a fresh seed each generation.
    generation_seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    # Simulation horizon used for chaos timing (seconds).
    simulation_duration_s: float | None = Field(default=None, ge=60.0, le=7200.0)
    # Abstract axes in [0,1] from the LLM (optional); blended with structure-derived axes.
    intent_axes: dict[str, float] = Field(default_factory=dict)

    # High-level resource counts; the builder chooses coordinates deterministically.
    counts: dict[str, int] = Field(
        default_factory=dict,
        description="Keys: gateways, drones, clients, buildings, walls, vegetation, demand_zones",
    )

    # Layout intent for the deterministic placement algorithm.
    layout: Literal["gateway_left_drone_relay_clients_right", "compact_cluster", "corridor_blockage"] = (
        "gateway_left_drone_relay_clients_right"
    )

    notes: str | None = None

    @field_validator("counts")
    @classmethod
    def validate_non_negative_counts(cls, value: dict[str, int]) -> dict[str, int]:
        cleaned: dict[str, int] = {}
        for key, raw in value.items():
            if not isinstance(raw, int):
                raise ValueError(f"Count '{key}' must be an int")
            cleaned[key] = max(0, raw)
        return cleaned

    @field_validator("intent_axes")
    @classmethod
    def validate_intent_axes(cls, value: dict[str, float]) -> dict[str, float]:
        out: dict[str, float] = {}
        for key, raw in value.items():
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            out[str(key)] = max(0.0, min(1.0, v))
        return out


LayoutHint = Literal[
    "gateway_left_drone_relay_clients_right",
    "compact_cluster",
    "corridor_blockage",
]

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


def _extract_count_if_present(prompt: str, aliases: tuple[str, ...]) -> int | None:
    """Return a positive count only when the prompt states `<n> <alias>` (digit or spelled-out number)."""
    lowered = prompt.lower()
    for alias in aliases:
        pattern = re.compile(
            rf"(?:\b(\d+)\b|\b({'|'.join(_NUMBER_WORDS.keys())})\b)\s+{re.escape(alias)}\b"
        )
        match = pattern.search(lowered)
        if not match:
            continue
        digit, word = match.groups()
        if digit is not None:
            return int(digit)
        if word is not None and word in _NUMBER_WORDS:
            return int(_NUMBER_WORDS[word])
    return None


def _heuristic_counts_from_prompt(prompt: str) -> dict[str, int]:
    """
    Derive compile-time counts from the user's words. Small LLMs often echo the
    same `counts` JSON; the API therefore must not trust model counts for the
    final scenario — only the prompt text (plus a few conservative defaults).
    """
    p = (prompt or "").lower()

    gateways_raw = _extract_count_if_present(prompt, ("gateway", "gateways"))
    gateways = _clamp_count(gateways_raw if gateways_raw is not None else 1, 1, 4)

    drones_raw = _extract_count_if_present(prompt, ("drone", "drones"))
    drones = _clamp_count(drones_raw if drones_raw is not None else 1, 1, 24)

    clients_raw = _extract_count_if_present(prompt, ("client", "clients"))
    clients = _clamp_count(clients_raw if clients_raw is not None else 1, 1, 80)

    buildings_raw = _extract_count_if_present(prompt, ("building", "buildings"))
    if buildings_raw is not None:
        buildings = _clamp_count(buildings_raw, 0, 16)
    elif re.search(r"\b(no|without|zero)\s+buildings?\b", p):
        buildings = 0
    elif re.search(r"\b(building|buildings)\b", p):
        buildings = 1
    else:
        buildings = 0

    vegetation_raw = _extract_count_if_present(
        prompt,
        (
            "vegetation zone",
            "vegetation zones",
            "tree zone",
            "tree zones",
            "interference zone",
            "interference zones",
            "vegetation",
            "interference",
        ),
    )
    if vegetation_raw is not None:
        vegetation = _clamp_count(vegetation_raw, 0, 16)
    elif re.search(r"\b(no|without|zero)\s+(vegetation|interference)\b", p):
        vegetation = 0
    elif re.search(r"\b(no|without)\b[\w\s,]{0,48}\b(vegetation|interference)\b", p):
        # e.g. "no buildings or vegetation"
        vegetation = 0
    elif re.search(
        r"\b(vegetation zone|interference zone|tree zones?|foliage|canopy)\b",
        p,
    ):
        vegetation = 1
    elif re.search(r"\b(vegetation|interference)\b", p):
        vegetation = 1
    else:
        vegetation = 0

    walls_raw = _extract_count_if_present(prompt, ("wall", "walls"))
    walls = _clamp_count(walls_raw if walls_raw is not None else 0, 0, 24)

    demand_raw = _extract_count_if_present(prompt, ("demand zone", "demand zones"))
    demand_zones = _clamp_count(demand_raw if demand_raw is not None else 0, 0, 8)

    return {
        "gateways": gateways,
        "drones": drones,
        "clients": clients,
        "buildings": buildings,
        "vegetation": vegetation,
        "walls": walls,
        "demand_zones": demand_zones,
    }


def _infer_layout_from_prompt(prompt: str) -> LayoutHint | None:
    p = prompt.lower()
    if re.search(r"\b(wall|walls|corridor|alley|bottleneck|blocked|obstruction|narrow)\b", p):
        return "corridor_blockage"
    if re.search(r"\b(cluster|compact|dense|downtown|urban|city block)\b", p):
        return "compact_cluster"
    return None


def _default_title_from_prompt_line(prompt: str) -> str | None:
    line = (prompt or "").strip().split("\n", 1)[0].strip()
    if not line:
        return None
    if len(line) > 100:
        return line[:97].rstrip() + "…"
    return line


def merge_meshflight_plan_with_user_prompt(
    plan: MeshFlightScenarioPlanV1, user_prompt: str
) -> MeshFlightScenarioPlanV1:
    """
    Compile-time counts always come from the user's natural-language prompt.

    LLM `counts` are intentionally ignored here: local models frequently echo a
    stale template (same JSON for every request), which made unrelated prompts
    produce identical scenarios.
    """
    counts = _heuristic_counts_from_prompt(user_prompt)

    kw_layout = _infer_layout_from_prompt(user_prompt)
    new_layout: LayoutHint = kw_layout if kw_layout is not None else plan.layout  # type: ignore[assignment]

    explicit = (plan.title or "").strip()
    quoted_name = (_extract_scenario_name(user_prompt) or "").strip()
    first_line = (_default_title_from_prompt_line(user_prompt) or "").strip()
    new_title: str | None = explicit or quoted_name or first_line or None

    seed = plan.generation_seed
    if seed is None:
        seed = secrets.randbelow(2**31)

    base_updates: dict[str, object] = {
        "counts": counts,
        "layout": new_layout,
        "generation_seed": int(seed),
    }

    if new_title is None:
        return plan.model_copy(update=base_updates)
    return plan.model_copy(update={**base_updates, "title": new_title})


def validate_editor_supported_scenario(scenario: ScenarioSource) -> ScenarioSource:
    entity_types = {entity.type.value for entity in scenario.entities}
    unsupported_entities = sorted(entity_types - set(SUPPORTED_ENTITY_TYPES))
    if unsupported_entities:
        raise ScenarioAIValidationError(
            "The generated scenario uses unsupported editor entity types: " + ", ".join(unsupported_entities)
        )

    obstacle_types = {obstacle.type.value for obstacle in scenario.obstacles}
    unsupported_obstacles = sorted(obstacle_types - set(SUPPORTED_OBSTACLE_TYPES))
    if unsupported_obstacles:
        raise ScenarioAIValidationError(
            "The generated scenario uses unsupported editor obstacle types: " + ", ".join(unsupported_obstacles)
        )

    if scenario.traffic_classes:
        raise ScenarioAIValidationError("The editor does not yet support AI-authored traffic classes.")

    if scenario.scheduled_traffic:
        raise ScenarioAIValidationError("The editor does not yet support AI-authored scheduled traffic.")

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


def _extract_scenario_name(prompt: str) -> str | None:
    patterns = (
        r'scenario\s+name\s+"([^"]+)"',
        r'scenario\s+name\s+"([^"]+?)\s*(?:\n|$)',
        r'name\s+"([^"]+)"',
        r'name\s+"([^"]+?)\s*(?:\n|$)',
    )
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            name = match.group(1).strip()
            if name:
                return name
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


def _rng_spread(
    rng: random.Random,
    index: int,
    count: int,
    start: float,
    end: float,
    *,
    jitter_frac: float = 0.16,
) -> float:
    """Evenly spaced anchor with bounded jitter so repeated generations differ."""
    if count <= 1:
        mid = (start + end) / 2
        span = abs(end - start) * jitter_frac * 0.5
        return round(mid + rng.uniform(-span, span), 2)
    base = start + (end - start) * (index / (count - 1))
    span = abs(end - start) * jitter_frac
    return round(base + rng.uniform(-span, span), 2)


def build_plan_output_schema_summary() -> str:
    return json.dumps(
        MeshFlightScenarioPlanV1.model_json_schema(),
        indent=2,
    )


def build_scenario_plan_prompt(request: ScenarioAIAssistRequest) -> str:
    existing_scenario_json = (
        request.existing_scenario.model_dump_json(indent=2)
        if request.existing_scenario is not None
        else "null"
    )
    canvas_width, canvas_height = _canvas(request)
    conversation_history = (
        "\n".join(f"- {entry}" for entry in request.conversation if entry.strip())
        if request.conversation
        else "none"
    )

    return f"""
You are planning a 2D MeshFlight scenario. You MUST NOT output a full scenario document.
Return JSON only. No markdown. No code fences. No extra prose outside the JSON object.

The JSON must validate against this JSON Schema:
{build_plan_output_schema_summary()}

Planning rules:
- `request_mode` must be "{request.mode}".
- If the user's request is not representable with supported editor objects, set `feasible` to false and explain in `reason`.
- If the request is representable, set `feasible` to true. (The server derives final object counts from the user's words; you may still include `counts` for your own reasoning, but it will not override explicit numbers in the user text.)
- Supported object kinds you can represent via counts:
  - entities: gateways, drones, clients
  - obstacles: buildings (rect), walls (segments), vegetation (circular zones)
  - extra: demand_zones
- Chaos events are not authored in the plan: the server derives them from the placed scenario geometry plus optional `intent_axes`.
- Optional fields: `generation_seed` (integer for reproducible runs), `simulation_duration_s` (horizon for event timing), `intent_axes` (numeric stress axes in [0,1], e.g. disruption, congestion, gateway_dependency, coverage_pressure, sparsity).
- Do NOT try to include coordinates in this plan. Placement is handled server-side with controlled randomness unless `generation_seed` is set.
- `layout` is a hint for the deterministic layout algorithm. Pick the closest match to the user intent.
- Keep counts modest unless the user explicitly asks for more (avoid performance-hostile maps).

If `request_mode` is "update" and an existing scenario is provided, assume the user wants a refreshed scenario that reflects their new instructions, unless they explicitly request preserving specific objects. The server can preserve `scenario_id` and `created_at` automatically.

Editor canvas (preferred bounds):
- width={canvas_width}
- height={canvas_height}

Existing scenario JSON (update mode, may be null):
{existing_scenario_json}

Conversation history (oldest first):
{conversation_history}

User request:
{request.prompt}
""".strip()


def build_scenario_plan_repair_prompt(
    request: ScenarioAIAssistRequest,
    invalid_payload: dict[str, object],
    validation_error: str,
) -> str:
    canvas_width, canvas_height = _canvas(request)
    conversation_history = (
        "\n".join(f"- {entry}" for entry in request.conversation if entry.strip())
        if request.conversation
        else "none"
    )
    return f"""
Repair the invalid MeshFlight scenario plan JSON below.

Return JSON only. No markdown. No code fences. No extra prose.
The output must be a single JSON object validating against the JSON schema used for planning:
{build_plan_output_schema_summary()}

The repaired plan MUST keep:
- `kind` = "meshflight_scenario_plan_v1"
- `version` = 1
- `request_mode` = "{request.mode}"

Canvas (preferred bounds):
- width={canvas_width}
- height={canvas_height}

Conversation history (oldest first):
{conversation_history}

User request:
{request.prompt}

Validation error:
{validation_error}

Invalid payload:
{json.dumps(invalid_payload, indent=2)}
""".strip()


def scenario_plan_to_source(
    request: ScenarioAIAssistRequest, plan: MeshFlightScenarioPlanV1, *, now: datetime | None = None
) -> ScenarioSource:
    if plan.request_mode != request.mode:
        raise ScenarioAIValidationError(
            f"The plan's request_mode '{plan.request_mode}' does not match '{request.mode}'."
        )
    if not plan.feasible:
        raise ScenarioAIValidationError("The plan is marked not feasible; cannot build a scenario.")

    now_dt = now or datetime.now(UTC)
    now_iso = now_dt.isoformat().replace("+00:00", "Z")

    canvas_w, canvas_h = _canvas(request)
    c = _Counts.from_plan(plan)

    if plan.generation_seed is None:
        raise ScenarioAIValidationError(
            "Internal error: generation_seed missing; merge_meshflight_plan_with_user_prompt must run before build."
        )
    rng = random.Random(int(plan.generation_seed))

    title = (plan.title or "").strip() or _extract_scenario_name(request.prompt) or "ai-generated-scenario"
    scenario_id = _slugify_scenario_id(title)
    description = (plan.notes or request.prompt).strip()

    seed = int(plan.generation_seed)
    map_area = float(canvas_w * canvas_h)
    merged_axes = merge_intent_axes(
        infer_intent_axes_from_counts(plan.counts, map_area=map_area),
        plan.intent_axes,
    )
    rf_obstruction_labeling = merged_axes.get("disruption", 0.0) >= 0.52

    sim_duration = (
        float(plan.simulation_duration_s)
        if plan.simulation_duration_s is not None
        else float(rng.uniform(280.0, 780.0))
    )

    metadata = {
        "scenario_id": scenario_id,
        "schema_version": "0.1.0",
        "title": title,
        "description": description,
        "seed": seed,
        "created_at": now_iso,
        "authoring_version": "ai-plan-v1",
    }

    bx = rng.uniform(-0.07, 0.07) * canvas_w
    by = rng.uniform(-0.06, 0.06) * canvas_h
    center_y = canvas_h * 0.5 + by

    left_x = canvas_w * 0.18 + bx
    right_x = canvas_w * 0.72 + bx
    relay_start_x = canvas_w * 0.33 + bx * 0.35
    relay_end_x = canvas_w * 0.62 + bx * 0.35

    if plan.layout == "compact_cluster":
        left_x = canvas_w * (0.28 + rng.uniform(0, 0.06)) + bx
        right_x = canvas_w * (0.72 - rng.uniform(0, 0.06)) + bx
        relay_start_x = canvas_w * (0.4 + rng.uniform(0, 0.05)) + bx * 0.25
        relay_end_x = canvas_w * (0.6 - rng.uniform(0, 0.05)) + bx * 0.25
    if plan.layout == "corridor_blockage":
        left_x = canvas_w * (0.1 + rng.uniform(0, 0.04)) + bx
        right_x = canvas_w * (0.88 - rng.uniform(0, 0.04)) + bx
        relay_start_x = canvas_w * (0.26 + rng.uniform(0, 0.04)) + bx * 0.3
        relay_end_x = canvas_w * (0.74 - rng.uniform(0, 0.04)) + bx * 0.3

    cluster_variant = rng.randint(0, 2)

    entities: list[dict[str, object]] = []
    for index in range(c.gateways):
        gx = left_x + rng.uniform(-22, 22)
        y = _rng_spread(rng, index, c.gateways, center_y - 150, center_y + 150)
        entities.append(
            {
                "id": f"gateway-{index + 1}",
                "type": "gateway",
                "label": f"Gateway {index + 1}",
                "position": {"x": round(gx, 2), "y": y},
                "tags": ["editor:uplink=fiber"],
                "uplink_capacity_mbps": int(rng.uniform(240, 360)),
                "comms_range_m": int(rng.uniform(220, 300)),
            }
        )

    for index in range(c.drones):
        x = _rng_spread(rng, index, c.drones, relay_start_x, relay_end_x)
        y = _rng_spread(rng, index, c.drones, center_y - 110, center_y + 110)
        entities.append(
            {
                "id": f"drone-{index + 1}",
                "type": "drone",
                "label": f"Drone {index + 1}",
                "position": {"x": x, "y": y},
                "tags": ["editor:battery_pct=90"],
                "battery_capacity_mah": int(rng.uniform(95, 130)),
                "max_speed_mps": round(rng.uniform(12.0, 19.0), 2),
                "comms_range_m": int(rng.uniform(160, 220)),
                "waypoint_step_m": int(rng.uniform(18, 34)),
            }
        )

    demand_profiles = ["telemetry", "video", "telemetry", "control", "telemetry", "video"]
    for index in range(c.clients):
        if plan.layout == "compact_cluster":
            cx = canvas_w * rng.uniform(0.38, 0.62) + bx * 0.45
            cy = center_y + rng.uniform(-canvas_h * 0.1, canvas_h * 0.1)
            if cluster_variant == 0:
                ang = 2 * math.pi * ((index + rng.random()) / max(c.clients, 1))
                rad = rng.uniform(65.0, min(canvas_w, canvas_h) * 0.2) * rng.uniform(0.45, 1.0)
                x = cx + rad * math.cos(ang)
                y = cy + rad * math.sin(ang) * rng.uniform(0.62, 1.05)
            elif cluster_variant == 1:
                x = _rng_spread(rng, index, c.clients, cx - canvas_w * 0.24, cx + canvas_w * 0.24)
                y = _rng_spread(rng, index, c.clients, cy - canvas_h * 0.14, cy + canvas_h * 0.14, jitter_frac=0.24)
            else:
                x = rng.uniform(canvas_w * 0.2, canvas_w * 0.8)
                y = rng.uniform(canvas_h * 0.16, canvas_h * 0.84)
        elif plan.layout == "corridor_blockage":
            x = _rng_spread(rng, index, c.clients, right_x - 150, right_x + 150, jitter_frac=0.22)
            y = _rng_spread(rng, index, c.clients, center_y - 260, center_y + 260, jitter_frac=0.22)
        else:
            x = _rng_spread(rng, index, c.clients, right_x - 120, right_x + 120)
            y = _rng_spread(rng, index, c.clients, center_y - 220, center_y + 220)

        entities.append(
            {
                "id": f"client-{index + 1}",
                "type": "client",
                "label": f"Client {index + 1}",
                "position": {"x": round(x, 2), "y": round(y, 2)},
                "tags": [],
                "demand_profile": demand_profiles[index % len(demand_profiles)],
            }
        )

    obstacles: list[dict[str, object]] = []
    for index in range(c.buildings):
        bw = rng.uniform(95.0, 210.0)
        bh = rng.uniform(110.0, 260.0)
        obstacles.append(
            {
                "id": f"building-{index + 1}",
                "type": "building",
                "label": f"Building {index + 1}",
                "attenuation_db": int(rng.uniform(7, 14)),
                "blocks_flight": True,
                "shape": "rect",
                "position": {
                    "x": _rng_spread(rng, index, c.buildings, canvas_w * 0.42, canvas_w * 0.58),
                    "y": _rng_spread(rng, index, c.buildings, center_y - 150, center_y + 150),
                },
                "size": {"width": round(bw, 2), "height": round(bh, 2)},
            }
        )

    for index in range(c.walls):
        x0 = _rng_spread(rng, index, c.walls, canvas_w * 0.36, canvas_w * 0.64)
        y0 = _rng_spread(rng, index, c.walls, center_y - 220, center_y + 220)
        length = rng.uniform(110.0, 280.0)
        theta = rng.uniform(-0.45, 0.45)
        x1 = x0 + length * math.cos(theta)
        y1 = y0 + length * math.sin(theta)
        obstacles.append(
            {
                "id": f"wall-{index + 1}",
                "type": "wall",
                "label": f"Wall {index + 1}",
                "attenuation_db": int(rng.uniform(2, 6)),
                "blocks_flight": True,
                "shape": "segment",
                "start": {"x": round(x0, 2), "y": round(y0, 2)},
                "end": {"x": round(x1, 2), "y": round(y1, 2)},
            }
        )

    for index in range(c.vegetation):
        obstacles.append(
            {
                "id": f"vegetation-{index + 1}",
                "type": "vegetation",
                "label": (
                    f"RF Obstruction Zone {index + 1}"
                    if rf_obstruction_labeling
                    else f"Vegetation Zone {index + 1}"
                ),
                "attenuation_db": int(rng.uniform(5, 11)),
                "blocks_flight": False,
                "shape": "circle",
                "center": {
                    "x": _rng_spread(rng, index, c.vegetation, canvas_w * 0.54, canvas_w * 0.74),
                    "y": _rng_spread(rng, index, c.vegetation, center_y - 120, center_y + 120),
                },
                "radius": round(rng.uniform(55.0, 135.0), 2),
            }
        )

    demand_zones: list[dict[str, object]] = []
    for index in range(c.demand_zones):
        demand_zones.append(
            {
                "id": f"demand-zone-{index + 1}",
                "label": f"Demand {index + 1}",
                "center": {
                    "x": _rng_spread(rng, index, c.demand_zones, right_x - 55, right_x + 55),
                    "y": _rng_spread(rng, index, c.demand_zones, center_y - 90, center_y + 90),
                },
                "radius_m": round(rng.uniform(85.0, 165.0), 2),
                "priority": min(9, max(1, int(rng.uniform(4, 9)))),
            }
        )

    payload = {
        "metadata": metadata,
        "map": {
            "width": canvas_w,
            "height": canvas_h,
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

    scenario = ScenarioSource.model_validate(payload)
    _clamp_entities_to_map(scenario)

    chaos_dicts = build_contextual_chaos_events(
        scenario,
        intent_axes=merged_axes,
        simulation_duration_s=sim_duration,
        rng=rng,
    )
    chaos_events = [ChaosEvent.model_validate(ev) for ev in chaos_dicts]
    scenario = scenario.model_copy(update={"chaos_events": chaos_events})
    return validate_editor_supported_scenario(scenario)


def apply_update_metadata_preserve(
    request: ScenarioAIAssistRequest, generated: ScenarioSource
) -> ScenarioSource:
    if request.mode != "update" or request.existing_scenario is None:
        return generated

    existing = request.existing_scenario
    return generated.model_copy(
        update={
            "metadata": generated.metadata.model_copy(
                update={
                    "scenario_id": existing.metadata.scenario_id,
                    "created_at": existing.metadata.created_at,
                }
            )
        }
    )


class _Counts:
    def __init__(self, *, plan: MeshFlightScenarioPlanV1) -> None:
        counts = plan.counts
        self.gateways = _clamp_count(counts.get("gateways", 1), 1, 4)
        self.drones = _clamp_count(counts.get("drones", 1), 1, 24)
        self.clients = _clamp_count(counts.get("clients", 1), 1, 80)
        self.buildings = _clamp_count(counts.get("buildings", 0), 0, 16)
        self.vegetation = _clamp_count(counts.get("vegetation", 0), 0, 16)
        self.walls = _clamp_count(counts.get("walls", 0), 0, 24)
        self.demand_zones = _clamp_count(counts.get("demand_zones", 0), 0, 8)

    @classmethod
    def from_plan(cls, plan: MeshFlightScenarioPlanV1) -> "_Counts":
        return cls(plan=plan)


def _clamp_count(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _canvas(request: ScenarioAIAssistRequest) -> tuple[float, float]:
    if request.canvas is not None:
        return request.canvas.width, request.canvas.height
    if request.existing_scenario is not None:
        return request.existing_scenario.map.width, request.existing_scenario.map.height
    return 2000, 1200


def _clamp_entities_to_map(scenario: ScenarioSource) -> None:
    width = scenario.map.width
    height = scenario.map.height
    margin = 20.0

    def clamp_point(x: float, y: float) -> tuple[float, float]:
        return (min(max(margin, x), width - margin), min(max(margin, y), height - margin))

    for entity in scenario.entities:
        x, y = clamp_point(entity.position.x, entity.position.y)
        entity.position.x = x
        entity.position.y = y

    for obstacle in scenario.obstacles:
        if obstacle.shape == "rect":
            x, y = clamp_point(obstacle.position.x, obstacle.position.y)
            obstacle.position.x = x
            obstacle.position.y = y
        elif obstacle.shape == "segment":
            x0, y0 = clamp_point(obstacle.start.x, obstacle.start.y)
            x1, y1 = clamp_point(obstacle.end.x, obstacle.end.y)
            obstacle.start.x, obstacle.start.y = x0, y0
            obstacle.end.x, obstacle.end.y = x1, y1
        elif obstacle.shape == "circle":
            cx, cy = clamp_point(obstacle.center.x, obstacle.center.y)
            obstacle.center.x = cx
            obstacle.center.y = cy
            max_radius = min(cx, cy, width - cx, height - cy) - 5.0
            if max_radius < obstacle.radius:
                obstacle.radius = max(1.0, max_radius)

    for demand in scenario.demand_zones:
        cx, cy = clamp_point(demand.center.x, demand.center.y)
        demand.center.x = cx
        demand.center.y = cy
