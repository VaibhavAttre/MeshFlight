import type { ScenarioSource } from "./scenarioMapper";

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ||
  "http://127.0.0.1:8000";

export type ScenarioSummary = {
  scenario_id: string;
  title: string;
  updated_at: string;
  has_compiled: boolean;
};

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const raw = await response.text();
    let message = raw.trim() || `Request failed with status ${response.status}`;
    const trimmed = raw.trim();
    if (trimmed.startsWith("{")) {
      try {
        const parsed = JSON.parse(trimmed) as { detail?: unknown };
        if (typeof parsed.detail === "string") {
          message = parsed.detail;
        } else if (Array.isArray(parsed.detail)) {
          message = parsed.detail
            .map((entry) => (typeof entry === "object" && entry !== null ? JSON.stringify(entry) : String(entry)))
            .join("\n");
        }
      } catch {
        // keep message as raw body
      }
    }
    throw new Error(message.length > 800 ? `${message.slice(0, 800)}…` : message);
  }

  return (await response.json()) as T;
}

export async function listSavedScenarios(): Promise<ScenarioSummary[]> {
  const response = await fetch(`${API_BASE_URL}/api/scenarios`);
  return parseJsonResponse<ScenarioSummary[]>(response);
}

export async function loadSavedScenario(
  scenarioId: string
): Promise<ScenarioSource> {
  const response = await fetch(`${API_BASE_URL}/api/scenarios/${scenarioId}`);
  return parseJsonResponse<ScenarioSource>(response);
}

export async function saveScenarioToBackend(scenario: ScenarioSource) {
  const response = await fetch(`${API_BASE_URL}/api/scenarios`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(scenario),
  });

  return parseJsonResponse<{ scenario_id: string; title: string; path: string }>(response);
}

export async function compileScenarioOnBackend(scenarioId: string) {
  const response = await fetch(`${API_BASE_URL}/api/scenarios/${scenarioId}/compile`, {
    method: "POST",
  });

  return parseJsonResponse<{
    scenario_id: string;
    source_path: string;
    output_dir: string;
    compiled_path: string;
    report_path: string;
  }>(response);
}

export type SimulateScenarioResponse = {
  scenario_id: string;
  run_id: string;
  summary: Record<string, unknown>;
  run_dir: string;
  snapshots_path: string;
  events_path: string;
  summary_path: string;
  run_config_path: string;
};

export async function runSimulationOnBackend(
  scenarioId: string,
  options?: { duration_s?: number; tick_duration_s?: number; drone_speed_mps?: number }
): Promise<SimulateScenarioResponse> {
  const response = await fetch(`${API_BASE_URL}/api/scenarios/${scenarioId}/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      duration_s: options?.duration_s ?? 24,
      tick_duration_s: options?.tick_duration_s ?? 1,
      drone_speed_mps: options?.drone_speed_mps ?? 20,
    }),
  });

  return parseJsonResponse<SimulateScenarioResponse>(response);
}

export type SimulationSnapshot = {
  run_id?: string;
  tick?: number;
  time_s?: number;
  nodes?: Array<{
    id: string;
    kind: string;
    x: number;
    y: number;
    status?: string;
    battery_pct?: number | null;
  }>;
  metrics?: Record<string, unknown>;
};

export async function fetchSimulationSnapshots(
  scenarioId: string,
  runId: string
): Promise<SimulationSnapshot[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/scenarios/${encodeURIComponent(scenarioId)}/runs/${encodeURIComponent(runId)}/snapshots`
  );
  return parseJsonResponse<SimulationSnapshot[]>(response);
}
