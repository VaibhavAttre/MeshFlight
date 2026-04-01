import { useRef } from "react";

import { useEditorStore } from "../../app/editorStore";
import {
  editorDocumentToScenarioSource,
  scenarioSourceToEditorDocument,
} from "../../lib/scenarioMapper";
import {
  downloadScenarioFile,
  readScenarioFile,
} from "../../lib/scenarioFileIO";

export default function TopBar() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const documentName = useEditorStore((s) => s.documentName);

  const showDroneRanges = useEditorStore((s) => s.showDroneRanges);
  const toggleDroneRanges = useEditorStore((s) => s.toggleDroneRanges);

  const showClientDroneLinks = useEditorStore((s) => s.showClientDroneLinks);
  const toggleClientDroneLinks = useEditorStore((s) => s.toggleClientDroneLinks);

  const resetDocument = useEditorStore((s) => s.resetDocument);
  const replaceFromDocument = useEditorStore((s) => s.replaceFromDocument);
  const exportToDocument = useEditorStore((s) => s.exportToDocument);
  const setDocumentName = useEditorStore((s) => s.setDocumentName);

  function handleNew() {
    resetDocument();
  }

  function handleSave() {
    const doc = exportToDocument();
    const scenario = editorDocumentToScenarioSource(doc);
    downloadScenarioFile(doc.name, scenario);
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
    } catch (error) {
      console.error(error);
      window.alert("Could not load that scenario file.");
    } finally {
      event.target.value = "";
    }
  }

  return (
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
          onClick={() => fileInputRef.current?.click()}
        >
          Load
        </button>

        <button type="button" onClick={handleSave}>
          Save
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept="application/json"
          style={{ display: "none" }}
          onChange={handleFileChange}
        />
      </div>
    </header>
  );
}
