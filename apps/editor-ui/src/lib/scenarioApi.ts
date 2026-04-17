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
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
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
