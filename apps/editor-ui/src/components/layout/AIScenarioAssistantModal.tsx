import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import { useEditorStore } from "../../app/editorStore";
import {
  fetchAIScenarioAssistHealth,
  requestAIScenarioAssist,
  type AIScenarioAssistResponse,
  type AIScenarioAssistHealthResponse,
  type AIAssistDiagnostics,
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
  const hasInitializedSessionRef = useRef(false);
  const chatThreadRef = useRef<HTMLDivElement | null>(null);

  const [provider, setProvider] = useState<AIScenarioProvider>("ollama");
  const [mode, setMode] = useState<AIScenarioMode>("generate");
  const [selectedScenarioId, setSelectedScenarioId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState<AIScenarioAssistResponse | null>(null);
  const [health, setHealth] = useState<AIScenarioAssistHealthResponse | null>(null);
  const [conversationTurns, setConversationTurns] = useState<string[]>([]);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPreviewVisible, setIsPreviewVisible] = useState(true);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    if (!hasInitializedSessionRef.current) {
      setProvider("ollama");
      setMode("generate");
      setPrompt("");
      setResult(null);
      setHealth(null);
      setConversationTurns([]);
      setErrorMessage(null);
      setIsSubmitting(false);
      setIsPreviewVisible(true);
      setSelectedScenarioId(currentScenarioId ?? savedScenarios[0]?.scenario_id ?? "");
      hasInitializedSessionRef.current = true;
      return;
    }

    if (
      mode === "update" &&
      !selectedScenarioId &&
      (currentScenarioId || savedScenarios[0]?.scenario_id)
    ) {
      setSelectedScenarioId(currentScenarioId ?? savedScenarios[0]?.scenario_id ?? "");
    }
  }, [currentScenarioId, isOpen, mode, savedScenarios, selectedScenarioId]);

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
  const conversationMessages = useMemo(
    () =>
      conversationTurns.map((entry, index) => {
        const isUser = entry.startsWith("User: ");
        return {
          id: `${entry}-${index}`,
          role: isUser ? "user" : "assistant",
          text: entry.replace(/^(User|Assistant):\s*/, ""),
        };
      }),
    [conversationTurns]
  );

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const node = chatThreadRef.current;
    if (!node) {
      return;
    }

    node.scrollTop = node.scrollHeight;
  }, [conversationMessages, isOpen, isSubmitting]);

  if (!isOpen) {
    return null;
  }

  function renderDiagnostics(diagnostics: AIAssistDiagnostics) {
    return (
      <div className="ai-assistant-diagnostics">
        <h4>How this was generated</h4>
        <p className="ai-assistant-diagnostics__summary">
          Provider: <strong>{diagnostics.provider}</strong>
          {diagnostics.model ? (
            <>
              {" "}
              using <strong>{diagnostics.model}</strong>
            </>
          ) : null}
          {diagnostics.base_url ? (
            <>
              {" "}
              at <strong>{diagnostics.base_url}</strong>
            </>
          ) : null}
          {". "}
          LLM used: <strong>{diagnostics.llm_used ? "yes" : "no"}</strong>. LLM calls:{" "}
          <strong>{diagnostics.llm_invocations}</strong>. Plan repair passes:{" "}
          <strong>{diagnostics.plan_repair_passes}</strong>. Deterministic build:{" "}
          <strong>{diagnostics.deterministic_plan_builder_used ? "yes" : "no"}</strong>. Heuristic prompt
          fallback: <strong>{diagnostics.heuristic_prompt_fallback_used ? "yes" : "no"}</strong>. Raw model JSON
          logged to console: <strong>{diagnostics.raw_llm_logged ? "yes" : "no"}</strong> (set{" "}
          <code>AI_DEBUG_LLM=true</code> in the API process).
        </p>
        {diagnostics.events.length > 0 && (
          <ul className="ai-assistant-list">
            {diagnostics.events.map((event) => (
              <li key={`${event.name}-${event.detail}`}>
                <strong>{event.name}</strong>
                {event.detail ? ` — ${event.detail}` : ""}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
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
      setPrompt("");

      const userLine = `User: ${trimmedPrompt}`;
      const conversationForRequest = [...conversationTurns, userLine];
      setConversationTurns((current) => [...current, userLine].slice(-10));

      const existingScenario =
        mode === "update" ? await loadSavedScenario(selectedScenarioId) : undefined;

      const response = await requestAIScenarioAssist({
        provider,
        mode,
        prompt: trimmedPrompt,
        conversation: conversationForRequest,
        existingScenario,
        existingScenarioId: mode === "update" ? selectedScenarioId : undefined,
        canvas: {
          width: canvasWidth,
          height: canvasHeight,
        },
      });

      setResult(response);
      setIsPreviewVisible(true);
      setConversationTurns((current) => {
        const next = [...current];
        if (response.doable) {
          const assistantText = response.summary?.trim()
            ? response.summary.trim()
            : "Prepared a scenario preview with inferred values.";
          next.push(`Assistant: ${assistantText}`);
        } else {
          const assistantText = response.reason?.trim()
            ? response.reason.trim()
            : "That request cannot be represented with current editor features.";
          next.push(`Assistant: ${assistantText}`);
        }
        return next.slice(-10);
      });
    } catch (error) {
      console.error(error);
      const message =
        error instanceof Error
          ? error.message
          : "The AI assistant could not complete that request.";
      setErrorMessage(message);
      setConversationTurns((current) => [...current, `Assistant: ${message}`].slice(-10));
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter") {
      return;
    }

    if (event.shiftKey) {
      return;
    }

    event.preventDefault();
    void handleGenerateOrUpdate();
  }

  function handleStartNewConversation() {
    if (isSubmitting) {
      return;
    }

    setMode("generate");
    setPrompt("");
    setResult(null);
    setConversationTurns([]);
    setErrorMessage(null);
    setIsPreviewVisible(true);
    setSelectedScenarioId(currentScenarioId ?? savedScenarios[0]?.scenario_id ?? "");
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
                  setConversationTurns([]);
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
                  setConversationTurns([]);
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

          {mode === "update" && savedScenarios.length === 0 && (
            <div className="ai-assistant-note">
              No saved scenarios are available yet. Save one first or switch to generate mode.
            </div>
          )}

          {(conversationMessages.length > 0 || isSubmitting) && (
            <div className="ai-chat-thread" ref={chatThreadRef} aria-live="polite">
              {(() => {
                const messages = conversationMessages;
                if (messages.length === 0) {
                  return null;
                }

                return messages.map((message, index) => {
                  const isLast = index === messages.length - 1;
                  const showTypingUnderUser = isSubmitting && isLast && message.role === "user";

                  return (
                    <div
                      key={message.id}
                      className={`ai-chat-block ${
                        message.role === "user" ? "ai-chat-block--user" : "ai-chat-block--assistant"
                      }`}
                    >
                      <div
                        className={`ai-chat-message ${
                          message.role === "user"
                            ? "ai-chat-message--user"
                            : "ai-chat-message--assistant"
                        }`}
                      >
                        {message.text}
                      </div>
                      {showTypingUnderUser && (
                        <div className="ai-chat-typing-below">
                          <div className="ai-chat-message ai-chat-message--assistant ai-chat-typing">
                            <span className="ai-chat-typing-dot" />
                            <span className="ai-chat-typing-dot" />
                            <span className="ai-chat-typing-dot" />
                          </div>
                        </div>
                      )}
                    </div>
                  );
                });
              })()}
            </div>
          )}

          {selectedScenario && mode === "update" && (
            <div className="ai-assistant-note">
              Updating <strong>{selectedScenario.title}</strong>. The assistant will return a
              full updated source scenario, but it will not save automatically.
            </div>
          )}

          {errorMessage && <div className="ai-assistant-error">{errorMessage}</div>}

          {result && isPreviewVisible && (
            <div className="ai-assistant-preview">
              <div className="ai-assistant-preview__header">
                <h3>Preview</h3>
                <button
                  type="button"
                  className="ai-assistant-preview__toggle"
                  onClick={() => setIsPreviewVisible(false)}
                >
                  Hide
                </button>
              </div>
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
                  {result.ai_diagnostics && renderDiagnostics(result.ai_diagnostics)}
                </>
              ) : (
                <>
                  <p>{result.reason ?? "That request cannot be represented in the current editor."}</p>
                  {result.suggested_prompt && (
                    <p className="ai-assistant-suggestion">
                      Try instead: {result.suggested_prompt}
                    </p>
                  )}
                  {result.ai_diagnostics && renderDiagnostics(result.ai_diagnostics)}
                </>
              )}
            </div>
          )}
        </div>

        <div className="ai-assistant-modal__footer">
          <div className="ai-chat-composer">
            <textarea
              className="ai-chat-composer__input"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder={
                mode === "generate"
                  ? "Describe the scenario you want to generate... (Enter to send, Shift+Enter for a new line)"
                  : "Describe the changes you want to apply... (Enter to send, Shift+Enter for a new line)"
              }
            />
          </div>
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="button" onClick={handleStartNewConversation} disabled={isSubmitting}>
            Start New Conversation
          </button>
          {result && !isPreviewVisible && (
            <button type="button" onClick={() => setIsPreviewVisible(true)}>
              Show Preview
            </button>
          )}
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
            {mode === "generate" ? "Generate Preview" : "Update Preview"}
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
