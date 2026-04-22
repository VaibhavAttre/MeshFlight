import { useEffect, useMemo, useRef, useState } from "react";

import { useEditorStore } from "../../app/editorStore";
import AIScenarioAssistantModal from "./AIScenarioAssistantModal";
import {
  editorDocumentToScenarioSource,
  scenarioSourceToEditorDocument,
  type ScenarioSource,
} from "../../lib/scenarioMapper";
import {
  compileScenarioOnBackend,
  listSavedScenarios,
  loadSavedScenario,
  saveScenarioToBackend,
  type ScenarioSummary,
} from "../../lib/scenarioApi";
import {
  downloadScenarioFile,
  readScenarioFile,
} from "../../lib/scenarioFileIO";

export default function TopBar() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const moreMenuRef = useRef<HTMLDivElement | null>(null);
  const [savedScenarios, setSavedScenarios] = useState<ScenarioSummary[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [isMoreMenuOpen, setIsMoreMenuOpen] = useState(false);
  const [isAIModalOpen, setIsAIModalOpen] = useState(false);

  const documentName = useEditorStore((s) => s.documentName);
  const currentScenarioId = useEditorStore((s) => s.currentScenarioId);
  const setCurrentScenarioId = useEditorStore((s) => s.setCurrentScenarioId);

  const showDroneRanges = useEditorStore((s) => s.showDroneRanges);
  const toggleDroneRanges = useEditorStore((s) => s.toggleDroneRanges);

  const showClientDroneLinks = useEditorStore((s) => s.showClientDroneLinks);
  const toggleClientDroneLinks = useEditorStore((s) => s.toggleClientDroneLinks);

  const resetDocument = useEditorStore((s) => s.resetDocument);
  const replaceFromDocument = useEditorStore((s) => s.replaceFromDocument);
  const exportToDocument = useEditorStore((s) => s.exportToDocument);
  const setDocumentName = useEditorStore((s) => s.setDocumentName);

  const selectedScenario = useMemo(
    () =>
      savedScenarios.find((scenario) => scenario.scenario_id === selectedScenarioId) ??
      null,
    [savedScenarios, selectedScenarioId]
  );

  async function refreshSavedScenarios(preferredScenarioId?: string) {
    const scenarios = await listSavedScenarios();
    setSavedScenarios(scenarios);

    if (preferredScenarioId) {
      setSelectedScenarioId(preferredScenarioId);
      return;
    }

    setSelectedScenarioId((current) => {
      if (current && scenarios.some((scenario) => scenario.scenario_id === current)) {
        return current;
      }

      return scenarios[0]?.scenario_id ?? "";
    });
  }

  useEffect(() => {
    refreshSavedScenarios().catch((error) => {
      console.error(error);
    });
  }, []);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (
        moreMenuRef.current &&
        event.target instanceof Node &&
        !moreMenuRef.current.contains(event.target)
      ) {
        setIsMoreMenuOpen(false);
      }
    }

    window.addEventListener("mousedown", handlePointerDown);
    return () => window.removeEventListener("mousedown", handlePointerDown);
  }, []);

  function handleNew() {
    resetDocument();
    setCurrentScenarioId(null);
  }

  function buildScenarioForBackend() {
    const doc = exportToDocument();
    const scenario = editorDocumentToScenarioSource(doc);

    if (currentScenarioId) {
      scenario.metadata.scenario_id = currentScenarioId;
    }

    return { doc, scenario };
  }

  async function handleSave() {
    const { scenario } = buildScenarioForBackend();

    try {
      setIsBusy(true);
      const result = await saveScenarioToBackend(scenario);
      setDocumentName(result.title);
      setCurrentScenarioId(result.scenario_id);
      await refreshSavedScenarios(result.scenario_id);
      window.alert(`Saved scenario to app storage as ${result.title}.`);
    } catch (error) {
      console.error(error);
      window.alert("Could not save that scenario to backend storage.");
    } finally {
      setIsBusy(false);
    }
  }

  function handleExport() {
    const doc = exportToDocument();
    const scenario = editorDocumentToScenarioSource(doc);
    downloadScenarioFile(doc.name, scenario);
    setIsMoreMenuOpen(false);
  }

  async function handleLoadSavedScenario() {
    if (!selectedScenarioId) {
      window.alert("Choose a saved scenario first.");
      return;
    }

    try {
      setIsBusy(true);
      const scenario = await loadSavedScenario(selectedScenarioId);
      const doc = scenarioSourceToEditorDocument(scenario);
      replaceFromDocument(doc);
      setCurrentScenarioId(scenario.metadata.scenario_id);
    } catch (error) {
      console.error(error);
      window.alert("Could not load that saved scenario.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSavedScenarioChange(
    event: React.ChangeEvent<HTMLSelectElement>
  ) {
    const scenarioId = event.target.value;
    setSelectedScenarioId(scenarioId);

    if (!scenarioId) {
      setCurrentScenarioId(null);
      return;
    }

    try {
      setIsBusy(true);
      const scenario = await loadSavedScenario(scenarioId);
      const doc = scenarioSourceToEditorDocument(scenario);
      replaceFromDocument(doc);
      setCurrentScenarioId(scenario.metadata.scenario_id);
    } catch (error) {
      console.error(error);
      window.alert("Could not load that saved scenario.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCompile() {
    const { scenario } = buildScenarioForBackend();

    try {
      setIsBusy(true);
      const saveResult = await saveScenarioToBackend(scenario);
      setDocumentName(saveResult.title);
      setCurrentScenarioId(saveResult.scenario_id);
      await refreshSavedScenarios(saveResult.scenario_id);
      const compileResult = await compileScenarioOnBackend(saveResult.scenario_id);
      window.alert(
        `Compiled ${compileResult.scenario_id} into ${compileResult.compiled_path}.`
      );
    } catch (error) {
      console.error(error);
      window.alert("Could not compile that scenario.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleFileChange(
    event: React.ChangeEvent<HTMLInputElement>
  ) {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const raw = await readScenarioFile(file);
      const doc = scenarioSourceToEditorDocument(raw as never);
      replaceFromDocument(doc);
      if (
        typeof raw === "object" &&
        raw !== null &&
        "metadata" in raw &&
        typeof (raw as { metadata?: { scenario_id?: unknown } }).metadata?.scenario_id === "string"
      ) {
        setCurrentScenarioId((raw as { metadata: { scenario_id: string } }).metadata.scenario_id);
      } else {
        setCurrentScenarioId(null);
      }
      setIsMoreMenuOpen(false);
    } catch (error) {
      console.error(error);
      window.alert("Could not load that scenario file.");
    } finally {
      event.target.value = "";
    }
  }

  function handleApplyAIScenario(
    scenario: ScenarioSource | null | undefined,
    mode: "generate" | "update",
    sourceScenarioId: string | null
  ) {
    if (!scenario) {
      return;
    }

    const doc = scenarioSourceToEditorDocument(scenario);
    replaceFromDocument(doc);
    setDocumentName(scenario.metadata.title);
    setCurrentScenarioId(mode === "update" ? (sourceScenarioId ?? scenario.metadata.scenario_id) : null);
    setSelectedScenarioId(mode === "update" ? (sourceScenarioId ?? scenario.metadata.scenario_id) : "");
    setIsAIModalOpen(false);
  }

  return (
    <>
      <header className="topbar">
        <div className="topbar-left">
          <h1>MeshFlight Editor</h1>
        </div>

        <div className="topbar-center">
          <input
            value={documentName}
            onChange={(e) => setDocumentName(e.target.value)}
            className="topbar-name-input"
            placeholder="Scenario name"
          />
        </div>

        <div className="topbar-right">
          <select
            className="topbar-name-input"
            value={selectedScenarioId}
            onChange={handleSavedScenarioChange}
            disabled={isBusy}
            aria-label="Open saved scenario"
          >
            <option value="">Open saved scenario...</option>
            {savedScenarios.map((scenario) => (
              <option key={scenario.scenario_id} value={scenario.scenario_id}>
                {scenario.title}
                {scenario.has_compiled ? " [compiled]" : ""}
              </option>
            ))}
          </select>

          <button
            type="button"
            className={`drone-radius-toggle ${showDroneRanges ? "is-on" : ""}`}
            onClick={toggleDroneRanges}
            aria-pressed={showDroneRanges}
          >
            <span className="drone-radius-toggle__track">
              <span className="drone-radius-toggle__thumb" />
            </span>
            <span className="drone-radius-toggle__label">
              Drone Radius {showDroneRanges ? "On" : "Off"}
            </span>
          </button>

          <button
            type="button"
            className={`drone-radius-toggle ${showClientDroneLinks ? "is-on" : ""}`}
            onClick={toggleClientDroneLinks}
            aria-pressed={showClientDroneLinks}
          >
            <span className="drone-radius-toggle__track">
              <span className="drone-radius-toggle__thumb" />
            </span>
            <span className="drone-radius-toggle__label">
              Link Flow {showClientDroneLinks ? "On" : "Off"}
            </span>
          </button>

          <button type="button" onClick={handleNew}>
            New
          </button>

          <button
            type="button"
            onClick={handleLoadSavedScenario}
            disabled={isBusy || !selectedScenario}
            title="Reload the currently selected saved scenario"
          >
            Load
          </button>

          <button type="button" onClick={handleSave} disabled={isBusy}>
            Save
          </button>

          <button type="button" onClick={handleCompile} disabled={isBusy}>
            Compile
          </button>

          <button type="button" onClick={() => setIsAIModalOpen(true)} disabled={isBusy}>
            AI Scenario
          </button>

          <div className="topbar-menu" ref={moreMenuRef}>
            <button
              type="button"
              onClick={() => setIsMoreMenuOpen((current) => !current)}
              disabled={isBusy}
              aria-expanded={isMoreMenuOpen}
            >
              More
            </button>

            {isMoreMenuOpen && (
              <div className="topbar-menu-panel">
                <button type="button" onClick={handleExport} disabled={isBusy}>
                  Export
                </button>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isBusy}
                >
                  Import
                </button>
              </div>
            )}
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept="application/json"
            style={{ display: "none" }}
            onChange={handleFileChange}
          />
        </div>
      </header>

      <AIScenarioAssistantModal
        isOpen={isAIModalOpen}
        savedScenarios={savedScenarios}
        currentScenarioId={currentScenarioId}
        onClose={() => setIsAIModalOpen(false)}
        onApply={handleApplyAIScenario}
      />
    </>
  );
}
