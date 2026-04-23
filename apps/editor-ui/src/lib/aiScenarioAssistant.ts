import type { ScenarioSource } from "./scenarioMapper";

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ||
  "http://127.0.0.1:8000";

export type AIScenarioMode = "generate" | "update";
export type AIScenarioProvider = "ollama" | "gemini" | "openai";

export type AIScenarioAssistRequest = {
  provider: AIScenarioProvider;
  mode: AIScenarioMode;
  prompt: string;
  conversation?: string[];
  existingScenario?: ScenarioSource;
  existingScenarioId?: string;
  canvas?: {
    width: number;
    height: number;
  };
};

export type AIAssistEvent = {
  name: string;
  detail: string;
};

export type AIAssistDiagnostics = {
  provider: string;
  llm_used: boolean;
  model: string | null;
  base_url: string | null;
  events: AIAssistEvent[];
  schema_repair_passes: number;
  synthetic_fallback_used: boolean;
  alignment_pass_attempted: boolean;
  alignment_pass_succeeded: boolean;
};

export type AIScenarioAssistResponse = {
  doable: boolean;
  mode: AIScenarioMode;
  scenario?: ScenarioSource | null;
  summary?: string | null;
  warnings: string[];
  reason?: string | null;
  suggested_prompt?: string | null;
  ai_diagnostics?: AIAssistDiagnostics | null;
};

export type AIScenarioAssistHealthResponse = {
  provider: AIScenarioProvider;
  available: boolean;
  baseUrl?: string | null;
  model?: string | null;
  reason?: string | null;
};

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text();
    let detailMessage: string | null = null;

    try {
      const parsed = JSON.parse(message) as { detail?: unknown };
      if (typeof parsed.detail === "string" && parsed.detail.trim()) {
        detailMessage = parsed.detail;
      }
    } catch {
      // Fall back to the raw response body when it is not JSON.
    }

    throw new Error(
      detailMessage || message || `Request failed with status ${response.status}`
    );
  }

  return (await response.json()) as T;
}

export async function requestAIScenarioAssist(
  request: AIScenarioAssistRequest
): Promise<AIScenarioAssistResponse> {
  const response = await fetch(`${API_BASE_URL}/api/scenarios/ai-assist`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      provider: request.provider,
      mode: request.mode,
      prompt: request.prompt,
      conversation: request.conversation ?? [],
      existing_scenario: request.existingScenario,
      existing_scenario_id: request.existingScenarioId,
      canvas: request.canvas,
    }),
  });

  return parseJsonResponse<AIScenarioAssistResponse>(response);
}

export async function fetchAIScenarioAssistHealth(
  provider: AIScenarioProvider
): Promise<AIScenarioAssistHealthResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/scenarios/ai-assist/health?provider=${encodeURIComponent(provider)}`
  );
  return parseJsonResponse<AIScenarioAssistHealthResponse>(response);
}

export function validateScenarioSourceForEditor(
  scenario: ScenarioSource
): string[] {
  const issues: string[] = [];
  const allowedEntityTypes = new Set(["drone", "gateway", "client"]);
  const allowedObstacleTypes = new Set(["building", "wall", "vegetation"]);
  const width = scenario.map.width;
  const height = scenario.map.height;

  function checkPoint(label: string, x: number, y: number) {
    if (x < 0 || y < 0 || x > width || y > height) {
      issues.push(`${label} is outside the map bounds.`);
    }
  }

  for (const entity of scenario.entities) {
    if (!allowedEntityTypes.has(entity.type)) {
      issues.push(`Unsupported entity type "${entity.type}" cannot be applied in the editor.`);
      continue;
    }

    checkPoint(`Entity ${entity.id}`, entity.position.x, entity.position.y);

    if (entity.type === "drone") {
      if (entity.comms_range_m <= 0) {
        issues.push(`Drone ${entity.id} must have a positive comms range.`);
      }
      if (entity.battery_capacity_mah <= 0) {
        issues.push(`Drone ${entity.id} must have a positive battery value.`);
      }
    }

    if (entity.type === "gateway" && entity.comms_range_m <= 0) {
      issues.push(`Gateway ${entity.id} must have a positive comms range.`);
    }
  }

  for (const obstacle of scenario.obstacles) {
    if (!allowedObstacleTypes.has(obstacle.type)) {
      issues.push(`Unsupported obstacle type "${obstacle.type}" cannot be applied in the editor.`);
      continue;
    }

    if (obstacle.shape === "rect") {
      checkPoint(`Building ${obstacle.id}`, obstacle.position.x, obstacle.position.y);
      if (obstacle.size.width <= 0 || obstacle.size.height <= 0) {
        issues.push(`Building ${obstacle.id} must have a positive width and height.`);
      }
    } else if (obstacle.shape === "segment") {
      checkPoint(`Wall ${obstacle.id} start`, obstacle.start.x, obstacle.start.y);
      checkPoint(`Wall ${obstacle.id} end`, obstacle.end.x, obstacle.end.y);
    } else if (obstacle.shape === "circle") {
      checkPoint(`Vegetation zone ${obstacle.id}`, obstacle.center.x, obstacle.center.y);
      if (obstacle.radius <= 0) {
        issues.push(`Vegetation zone ${obstacle.id} must have a positive radius.`);
      }
    }
  }

  for (const zone of scenario.demand_zones) {
    checkPoint(`Demand zone ${zone.id}`, zone.center.x, zone.center.y);
    if (zone.radius_m <= 0) {
      issues.push(`Demand zone ${zone.id} must have a positive radius.`);
    }
  }

  if (scenario.traffic_classes.length > 0) {
    issues.push("AI-generated traffic classes are not yet editable in the current editor.");
  }

  if (scenario.scheduled_traffic.length > 0) {
    issues.push("AI-generated scheduled traffic is not yet editable in the current editor.");
  }

  return issues;
}
