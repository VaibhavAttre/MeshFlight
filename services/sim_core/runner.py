# services/sim_core/runner.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.sim_core.events import AppliedEvent, apply_due_events, extract_runtime_schedule
from services.sim_core.links import compute_links
from services.sim_core.movement import move_drones_toward_disconnected_clients
from services.sim_core.routing import compute_routes
from services.sim_core.snapshots import build_snapshot
from services.sim_core.state import SimState, build_initial_state


@dataclass
class SimulationResult:
    """
    In-memory result of a simulation run.

    Later, io.py can write this into artifacts/runs/<run_id>/.
    """

    run_id: str
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    events: list[AppliedEvent] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


class SimulationRunner:
    """
    Stage 0E simulator runner.

    This is the first simple orchestrator:
      - load compiled scenario
      - initialize runtime state
      - run tick loop
      - collect snapshots and applied events
    """

    def __init__(
        self,
        *,
        compiled_scenario: Any,
        run_id: str,
        duration_s: float = 30.0,
        tick_duration_s: float = 1.0,
        drone_speed_mps: float = 20.0,
    ) -> None:
        self.compiled_scenario = compiled_scenario
        self.run_id = run_id
        self.duration_s = float(duration_s)
        self.tick_duration_s = float(tick_duration_s)
        self.drone_speed_mps = float(drone_speed_mps)

        self.schedule = extract_runtime_schedule(compiled_scenario)

        self.state: SimState = build_initial_state(
            run_id=run_id,
            compiled_scenario=compiled_scenario,
            tick_duration_s=tick_duration_s,
        )

        self.snapshots: list[dict[str, Any]] = []
        self.applied_events: list[AppliedEvent] = []

    def initialize(self) -> None:
        """
        Compute the initial network state and emit the initial snapshot.

        Important:
        The simulation should always have a tick 0 snapshot before any
        movement/time advancement happens.
        """

        self._recompute_network_state()

        initial_snapshot = build_snapshot(
            self.state,
            recent_events=[],
        )
        self.snapshots.append(initial_snapshot)

    def step(self) -> None:
        """
        Execute one simulation tick.

        Order for Stage 0E:
          1. advance simulation clock (events use time_s <= state.time_s)
          2. apply scheduled events due at the new time
          3. recompute links/routes after failures
          4. move drones toward disconnected clients
          5. recompute links/routes again after movement
          6. emit snapshot for this tick
        """

        self.state.advance_time()

        recent_events = apply_due_events(self.state, self.schedule)
        self.applied_events.extend(recent_events)

        self._recompute_network_state()

        move_drones_toward_disconnected_clients(
            self.state,
            speed_mps=self.drone_speed_mps,
        )

        self._recompute_network_state()

        snapshot = build_snapshot(
            self.state,
            recent_events=recent_events,
        )
        self.snapshots.append(snapshot)

    def run(self) -> SimulationResult:
        """
        Run the full simulation and return all in-memory outputs.
        """

        self.initialize()

        total_steps = self._compute_total_steps()

        for _ in range(total_steps):
            self.step()

        summary = self._build_summary()

        return SimulationResult(
            run_id=self.run_id,
            snapshots=self.snapshots,
            events=self.applied_events,
            summary=summary,
        )

    def _recompute_network_state(self) -> None:
        links = compute_links(self.state)
        self.state.set_links(links)

        routes = compute_routes(self.state)
        self.state.set_routes(routes)

    def _compute_total_steps(self) -> int:
        """
        Number of step() calls to make.

        Example:
          duration_s = 30
          tick_duration_s = 1
          total_steps = 30

        Since initialize() already emitted the t=0 snapshot,
        this produces 31 snapshots total:
          tick 0 through tick 30
        """

        if self.tick_duration_s <= 0:
            raise ValueError("tick_duration_s must be > 0")

        return int(self.duration_s / self.tick_duration_s)

    def _build_summary(self) -> dict[str, Any]:
        clients = self.state.clients()
        drones = self.state.drones()
        gateways = self.state.gateways()

        connected_clients = sum(1 for client in clients if client.connected)
        disconnected_clients = len(clients) - connected_clients
        failed_drones = sum(1 for drone in drones if drone.status == "failed")

        return {
            "run_id": self.run_id,
            "duration_s": self.duration_s,
            "tick_duration_s": self.tick_duration_s,
            "ticks_completed": self.state.tick,
            "snapshots_written": len(self.snapshots),
            "events_applied": len(self.applied_events),
            "total_nodes": len(self.state.nodes),
            "total_clients": len(clients),
            "total_drones": len(drones),
            "total_gateways": len(gateways),
            "final_connected_clients": connected_clients,
            "final_disconnected_clients": disconnected_clients,
            "final_failed_drones": failed_drones,
            "final_active_links": len(self.state.links),
        }