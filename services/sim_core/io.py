# services/sim_core/io.py

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.sim_core.events import AppliedEvent
from services.sim_core.runner import SimulationResult


DEFAULT_RUNS_ROOT = Path("artifacts/runs")


@dataclass
class RunOutputPaths:
    run_dir: Path
    run_config_path: Path
    snapshots_path: Path
    events_path: Path
    summary_path: Path


def make_run_output_paths(
    *,
    run_id: str,
    runs_root: Path | str = DEFAULT_RUNS_ROOT,
) -> RunOutputPaths:
    runs_root = Path(runs_root)
    run_dir = runs_root / run_id

    return RunOutputPaths(
        run_dir=run_dir,
        run_config_path=run_dir / "run_config.json",
        snapshots_path=run_dir / "snapshots.jsonl",
        events_path=run_dir / "events.jsonl",
        summary_path=run_dir / "summary.json",
    )


def ensure_run_directory(paths: RunOutputPaths) -> None:
    paths.run_dir.mkdir(parents=True, exist_ok=True)


def write_simulation_outputs(
    *,
    result: SimulationResult,
    run_config: dict[str, Any],
    runs_root: Path | str = DEFAULT_RUNS_ROOT,
) -> RunOutputPaths:
    """
    Write a completed simulation result to disk.

    Files written:
      - run_config.json
      - snapshots.jsonl
      - events.jsonl
      - summary.json
    """

    paths = make_run_output_paths(
        run_id=result.run_id,
        runs_root=runs_root,
    )

    ensure_run_directory(paths)

    write_json(paths.run_config_path, run_config)
    write_jsonl(paths.snapshots_path, result.snapshots)
    write_events_jsonl(paths.events_path, result.events)
    write_json(paths.summary_path, result.summary)

    return paths


def write_json(path: Path | str, payload: Any) -> None:
    path = Path(path)
    path.write_text(
        json.dumps(to_jsonable(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_jsonl(path: Path | str, rows: list[Any]) -> None:
    path = Path(path)

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(to_jsonable(row), sort_keys=True))
            f.write("\n")


def write_events_jsonl(path: Path | str, events: list[AppliedEvent]) -> None:
    write_jsonl(path, [serialize_applied_event(event) for event in events])


def serialize_applied_event(event: AppliedEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "kind": event.kind,
        "time_s": event.time_s,
        "target_id": event.target_id,
        "message": event.message,
        "payload": dict(event.payload),
    }


def read_json(path: Path | str) -> Any:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path | str) -> list[Any]:
    path = Path(path)

    rows: list[Any] = []

    if not path.exists():
        return rows

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            rows.append(json.loads(line))

    return rows


def to_jsonable(value: Any) -> Any:
    """
    Recursively convert values into JSON-serializable structures.
    """

    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}

    if isinstance(value, list):
        return [to_jsonable(v) for v in value]

    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]

    if isinstance(value, set):
        return [to_jsonable(v) for v in sorted(value)]

    if hasattr(value, "__dict__"):
        return {
            str(k): to_jsonable(v)
            for k, v in vars(value).items()
        }

    return value