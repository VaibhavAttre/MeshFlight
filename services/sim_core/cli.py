# services/sim_core/cli.py

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

from services.sim_core.io import write_simulation_outputs
from services.sim_core.runner import SimulationRunner


def main() -> None:
    args = parse_args()

    compiled_path = Path(args.compiled_path)
    compiled_scenario = load_json(compiled_path)

    run_id = args.run_id or make_run_id(compiled_path)

    runner = SimulationRunner(
        compiled_scenario=compiled_scenario,
        run_id=run_id,
        duration_s=args.duration,
        tick_duration_s=args.tick,
        drone_speed_mps=args.drone_speed,
    )

    result = runner.run()

    run_config = {
        "run_id": run_id,
        "compiled_path": str(compiled_path),
        "duration_s": args.duration,
        "tick_duration_s": args.tick,
        "drone_speed_mps": args.drone_speed,
    }

    output_paths = write_simulation_outputs(
        result=result,
        run_config=run_config,
        runs_root=args.runs_root,
    )

    print(f"Run complete: {run_id}")
    print(f"Run directory: {output_paths.run_dir}")
    print(f"Snapshots: {output_paths.snapshots_path}")
    print(f"Events: {output_paths.events_path}")
    print(f"Summary: {output_paths.summary_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the MeshFlight Stage 0E simulator on a compiled scenario.",
    )

    parser.add_argument(
        "compiled_path",
        help="Path to compiled scenario JSON.",
    )

    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional run id. If omitted, one is auto-generated.",
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="Simulation duration in seconds.",
    )

    parser.add_argument(
        "--tick",
        type=float,
        default=1.0,
        help="Tick duration in seconds.",
    )

    parser.add_argument(
        "--drone-speed",
        type=float,
        default=20.0,
        help="Drone speed in meters per second.",
    )

    parser.add_argument(
        "--runs-root",
        default="artifacts/runs",
        help="Directory where run artifacts should be written.",
    )

    return parser.parse_args()


def load_json(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))


def make_run_id(compiled_path: Path) -> str:
    """
    Generate a readable run id based on the compiled scenario path.

    Example:
      compiled file under bridge-reconnect/compiled/compiled.json
      -> run-bridge-reconnect-a1b2c3d4
    """

    scenario_name = infer_scenario_name(compiled_path)
    suffix = uuid.uuid4().hex[:8]

    return f"run-{scenario_name}-{suffix}"


def infer_scenario_name(compiled_path: Path) -> str:
    """
    Try to infer a scenario name from the compiled artifact path.

    Example:
      artifacts/scenarios/bridge-reconnect/compiled/compiled.json
      -> bridge-reconnect
    """

    parts = compiled_path.parts

    if "compiled" in parts:
        idx = parts.index("compiled")
        if idx >= 1:
            return sanitize_name(parts[idx - 1])

    return sanitize_name(compiled_path.stem)


def sanitize_name(value: str) -> str:
    cleaned = value.strip().lower().replace(" ", "-").replace("_", "-")
    return cleaned or "scenario"


if __name__ == "__main__":
    main()