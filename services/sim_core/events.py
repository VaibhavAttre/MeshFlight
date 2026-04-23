# services/sim_core/events.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from services.sim_core.state import SimState


EventKind = Literal[
    "node_failure",
    "drone_failure",
    "fail_node",
    "failure",
]

_FAILURE_KINDS: frozenset[str] = frozenset(
    {"node_failure", "drone_failure", "fail_node", "failure"}
)


@dataclass
class AppliedEvent:
    event_id: str
    kind: str
    time_s: float
    target_id: str
    message: str
    payload: dict[str, Any]


def apply_due_events(state: SimState, schedule: list[dict[str, Any]]) -> list[AppliedEvent]:
    """Apply schedule entries whose time_s is <= current simulation time (once each)."""
    applied: list[AppliedEvent] = []

    for event in schedule:
        event_id = _event_id(event)

        if event_id in state.applied_event_ids:
            continue

        event_time_s = _event_time_s(event)
        if event_time_s > state.time_s:
            continue

        applied_event = apply_event(state, event)
        if applied_event is None:
            continue

        state.applied_event_ids.add(event_id)
        applied.append(applied_event)

    return applied


def apply_event(state: SimState, event: dict[str, Any]) -> AppliedEvent | None:
    action = _schedule_action(event)
    if action.endswith("_end"):
        return None

    if _is_failure_action(action):
        return _apply_node_failure(state, event)

    kind = _legacy_event_kind(event)
    if kind in _FAILURE_KINDS:
        return _apply_node_failure(state, event)

    return None


def _schedule_action(event: dict[str, Any]) -> str:
    raw = event.get("action")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower().replace("-", "_")
    return ""


def _is_failure_action(action: str) -> bool:
    if not action:
        return False
    if action.endswith("_end"):
        return False
    if "node_failure" in action:
        return True
    if action.startswith("chaos_") and action.endswith("_failure"):
        return True
    return action in {"drone_failure", "fail_node", "failure", "node_failure"}


def _legacy_event_kind(event: dict[str, Any]) -> str:
    raw = (
        event.get("kind")
        or event.get("type")
        or event.get("event_type")
    )

    if raw is None:
        return "unknown"

    return str(raw).lower().replace("-", "_")


def _apply_node_failure(
    state: SimState,
    event: dict[str, Any],
) -> AppliedEvent | None:
    target_id = _event_target_id(event)

    if target_id is None:
        return None

    if target_id not in state.nodes:
        return None

    node = state.nodes[target_id]
    if not node.is_active():
        return None

    state.fail_node(target_id)
    event_id = _event_id(event)

    return AppliedEvent(
        event_id=event_id,
        kind=_schedule_action(event) or _legacy_event_kind(event),
        time_s=state.time_s,
        target_id=target_id,
        message=f"Node {target_id} failed at t={state.time_s:.2f}s",
        payload=dict(event),
    )


def _event_id(event: dict[str, Any]) -> str:
    raw = (
        event.get("id")
        or event.get("event_id")
        or event.get("schedule_id")
    )

    if raw is not None:
        return str(raw)

    payload = event.get("payload")
    base: str | None = None
    if isinstance(payload, dict):
        nested = payload.get("event_id")
        if nested is not None:
            base = str(nested)

    action = _schedule_action(event)
    target_id = _event_target_id(event) or "unknown"
    time_s = _event_time_s(event)

    if base:
        return f"{base}|{action}|{time_s}"

    kind = _legacy_event_kind(event)
    return f"{kind}:{target_id}:{time_s}"


def _event_time_s(event: dict[str, Any]) -> float:
    raw = (
        event.get("time_s")
        or event.get("start_time_s")
        or event.get("at_s")
        or event.get("t")
        or 0.0
    )

    return float(raw)


def _event_target_id(event: dict[str, Any]) -> str | None:
    raw = (
        event.get("target_id")
        or event.get("node_id")
        or event.get("entity_id")
        or event.get("drone_id")
    )

    if raw is not None:
        return str(raw)

    payload = event.get("payload")

    if isinstance(payload, dict):
        nested = (
            payload.get("target_id")
            or payload.get("node_id")
            or payload.get("entity_id")
            or payload.get("drone_id")
        )

        if nested is not None:
            return str(nested)

    return None


def _entry_to_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="python")
    raise TypeError(f"Schedule entry must be dict or model, got {type(item)!r}")


def extract_runtime_schedule(compiled_scenario: Any) -> list[dict[str, Any]]:
    scenario = _to_dict(compiled_scenario)

    candidates = [
        scenario.get("runtime_schedule"),
        scenario.get("runtime_schedule_entries"),
        scenario.get("schedule"),
        scenario.get("events"),
    ]

    if "scenario" in scenario and isinstance(scenario["scenario"], dict):
        nested = scenario["scenario"]
        candidates.extend(
            [
                nested.get("runtime_schedule"),
                nested.get("runtime_schedule_entries"),
                nested.get("schedule"),
                nested.get("events"),
            ]
        )

    for candidate in candidates:
        if isinstance(candidate, list):
            return [_entry_to_dict(item) for item in candidate]

    return []


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")

    raise TypeError(f"Expected dict or Pydantic model, got {type(value)!r}")
