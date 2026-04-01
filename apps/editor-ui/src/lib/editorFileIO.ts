import type { EditorDocument } from "../app/editorDocument";
import { normalizeEditorDocument } from "./editorDocumentSchema";
import {
  editorDocumentToScenarioSource,
  isScenarioSource,
  scenarioSourceToEditorDocument,
} from "./scenarioMapper";

function makeDownloadName(name: string) {
  const base = name.trim() || "untitled-scenario";
  return `${base}.meshflight.editor.json`;
}

export function downloadEditorDocument(doc: EditorDocument) {
  const blob = new Blob([JSON.stringify(doc, null, 2)], {
    type: "application/json",
  });

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = makeDownloadName(doc.name);
  anchor.click();
  URL.revokeObjectURL(url);
}

export function downloadScenarioSource(doc: EditorDocument) {
  const scenario = editorDocumentToScenarioSource(doc);
  const blob = new Blob([JSON.stringify(scenario, null, 2)], {
    type: "application/json",
  });

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${(doc.name.trim() || "untitled-scenario")}.scenario.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function readEditorDocumentFromFile(
  file: File
): Promise<EditorDocument> {
  const text = await file.text();
  const raw = JSON.parse(text);

  if (isScenarioSource(raw)) {
    return scenarioSourceToEditorDocument(raw);
  }

  return normalizeEditorDocument(raw);
}
