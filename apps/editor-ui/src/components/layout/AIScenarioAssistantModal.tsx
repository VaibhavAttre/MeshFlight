import { useEffect, useMemo, useRef, useState } from "react";

import { useEditorStore } from "../../app/editorStore";
import {
  fetchAIScenarioAssistHealth,
  requestAIScenarioAssist,
  type AIScenarioAssistResponse,
  type AIScenarioAssistHealthResponse,
  type AIScenarioMode,
  type AIScenarioProvider,
  validateScenarioSourceForEditor,
} from "../../lib/aiScenarioAssistant";
import { loadSavedScenario, type ScenarioSummary } from "../../lib/scenarioApi";

type Props = {
  isOpen: boolean;
  savedScenarios: ScenarioSummary[];
  currentScenarioId: string | null;
  onClose: () => void;
  onApply: (
    scenario: AIScenarioAssistResponse["scenario"],
    mode: AIScenarioMode,
    sourceScenarioId: string | null
  ) => void;
};

export default function AIScenarioAssistantModal({
  isOpen,
  savedScenarios,
  currentScenarioId,
  onClose,
  onApply,
}: Props) {
  const canvasWidth = useEditorStore((state) => state.canvasWidth);
  const canvasHeight = useEditorStore((state) => state.canvasHeight);
  const healthRequestIdRef = useRef(0);

  const [provider, setProvider] = useState<AIScenarioProvider>("ollama");
  const [mode, setMode] = useState<AIScenarioMode>("generate");
  const [selectedScenarioId, setSelectedScenarioId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState<AIScenarioAssistResponse | null>(null);
  const [health, setHealth] = useState<AIScenarioAssistHealthResponse | null>(null);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    setProvider("ollama");
    setMode("generate");
    setPrompt("");
    setResult(null);
    setHealth(null);
    setErrorMessage(null);
    setIsSubmitting(false);
    setSelectedScenarioId(currentScenarioId ?? savedScenarios[0]?.scenario_id ?? "");
  }, [currentScenarioId, isOpen, savedScenarios]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const requestId = healthRequestIdRef.current + 1;
    healthRequestIdRef.current = requestId;
    setIsCheckingHealth(true);
    setHealth(null);

    fetchAIScenarioAssistHealth(provider)
      .then((response) => {
        if (healthRequestIdRef.current !== requestId) {
          return;
        }
        setHealth(response);
      })
      .catch((error) => {
        console.error(error);
        if (healthRequestIdRef.current !== requestId) {
          return;
        }
        setHealth({
          provider,
          available: false,
          reason:
            error instanceof Error
              ? error.message
              : "Could not reach the AI provider health endpoint.",
        });
      })
      .finally(() => {
        if (healthRequestIdRef.current !== requestId) {
          return;
        }
        setIsCheckingHealth(false);
      });
  }, [isOpen, provider]);

  const selectedScenario = useMemo(
    () =>
      savedScenarios.find((scenario) => scenario.scenario_id === selectedScenarioId) ?? null,
    [savedScenarios, selectedScenarioId]
  );

  if (!isOpen) {
    return null;
  }

  async function handleGenerateOrUpdate() {
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) {
      setErrorMessage("Enter a scenario description first.");
      return;
    }

    if (mode === "update" && !selectedScenarioId) {
      setErrorMessage("Choose an existing scenario to update.");
      return;
    }

    try {
      setIsSubmitting(true);
      setErrorMessage(null);
      setResult(null);

      const existingScenario =
        mode === "update" ? await loadSavedScenario(selectedScenarioId) : undefined;

      const response = await requestAIScenarioAssist({
        provider,
        mode,
        prompt: trimmedPrompt,
        existingScenario,
        existingScenarioId: mode === "update" ? selectedScenarioId : undefined,
        canvas: {
          width: canvasWidth,
          height: canvasHeight,
        },
      });

      setResult(response);
    } catch (error) {
      console.error(error);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "The AI assistant could not complete that request."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleApply() {
    if (!result?.doable || !result.scenario) {
      return;
    }

    const issues = validateScenarioSourceForEditor(result.scenario);
    if (issues.length > 0) {
      setErrorMessage(issues.join(" "));
      return;
    }

    onApply(result.scenario, mode, mode === "update" ? selectedScenarioId : null);
  }

  return (
    <div className="ai-assistant-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="ai-assistant-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ai-assistant-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="ai-assistant-modal__header">
          <div>
            <h2 id="ai-assistant-title">AI Scenario</h2>
            <p>
              Generate a new scenario or update an existing saved scenario with a
              natural-language prompt.
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close AI scenario assistant">
            Close
          </button>
        </div>

        <div className="ai-assistant-modal__body">
          <div className="ai-assistant-grid">
            <label className="editor-field">
              <span>Provider</span>
              <select
                value={provider}
                onChange={(event) => {
                  setProvider(event.target.value as AIScenarioProvider);
                  setResult(null);
                  setErrorMessage(null);
                }}
              >
                <option value="ollama">Ollama</option>
                <option value="gemini">Gemini</option>
                <option value="openai">OpenAI</option>
              </select>
            </label>

            <label className="editor-field">
              <span>Mode</span>
              <select
                value={mode}
                onChange={(event) => {
                  setMode(event.target.value as AIScenarioMode);
                  setResult(null);
                  setErrorMessage(null);
                }}
              >
                <option value="generate">Generate new scenario</option>
                <option value="update">Update existing scenario</option>
              </select>
            </label>

            {mode === "update" && (
              <label className="editor-field">
                <span>Existing scenario</span>
                <select
                  value={selectedScenarioId}
                  onChange={(event) => {
                    setSelectedScenarioId(event.target.value);
                    setResult(null);
                    setErrorMessage(null);
                  }}
                  disabled={savedScenarios.length === 0}
                >
                  <option value="">Choose a saved scenario...</option>
                  {savedScenarios.map((scenario) => (
                    <option key={scenario.scenario_id} value={scenario.scenario_id}>
                      {scenario.title}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          <div className="ai-assistant-note">
            <strong>Provider Status:</strong>{" "}
            {isCheckingHealth
              ? `Checking ${provider} status...`
              : health?.available
                ? `${health.provider} is available at ${health.baseUrl} using ${health.model}.`
                : health?.provider === provider
                  ? health.reason ?? `${provider} is not configured yet.`
                  : `${provider} is not configured yet.`}
          </div>

          {provider === "openai" && (
            <div className="ai-assistant-note">
              OpenAI API usage is paid, not free. This option stays blocked unless the backend
              explicitly enables it and sets a positive daily cap.
            </div>
          )}

          {mode === "update" && savedScenarios.length === 0 && (
            <div className="ai-assistant-note">
              No saved scenarios are available yet. Save one first or switch to generate mode.
            </div>
          )}

          <label className="editor-field">
            <span>Prompt</span>
            <textarea
              className="ai-assistant-textarea"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={
                mode === "generate"
                  ? "Create a downtown outage scenario with two gateways, six drones, several blocked corridors, and clustered clients near the south side."
                  : "Add more clients near the south edge and reduce drone battery values to make recovery harder."
              }
            />
          </label>

          {selectedScenario && mode === "update" && (
            <div className="ai-assistant-note">
              Updating <strong>{selectedScenario.title}</strong>. The assistant will return a
              full updated source scenario, but it will not save automatically.
            </div>
          )}

          {errorMessage && <div className="ai-assistant-error">{errorMessage}</div>}

          {result && (
            <div className="ai-assistant-preview">
              <h3>Preview</h3>
              {result.doable ? (
                <>
                  <p>{result.summary ?? "Ready to apply the generated scenario."}</p>
                  {result.warnings.length > 0 && (
                    <ul className="ai-assistant-list">
                      {result.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  )}
                </>
              ) : (
                <>
                  <p>{result.reason ?? "That request cannot be represented in the current editor."}</p>
                  {result.suggested_prompt && (
                    <p className="ai-assistant-suggestion">
                      Try instead: {result.suggested_prompt}
                    </p>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        <div className="ai-assistant-modal__footer">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            onClick={handleGenerateOrUpdate}
            disabled={
              isSubmitting ||
              isCheckingHealth ||
              health?.available === false ||
              (mode === "update" && savedScenarios.length === 0)
            }
          >
            {isSubmitting ? "Working..." : mode === "generate" ? "Generate Preview" : "Update Preview"}
          </button>
          <button
            type="button"
            onClick={handleApply}
            disabled={!result?.doable || !result.scenario || isSubmitting}
          >
            Apply to Editor
          </button>
        </div>
      </div>
    </div>
  );
}
