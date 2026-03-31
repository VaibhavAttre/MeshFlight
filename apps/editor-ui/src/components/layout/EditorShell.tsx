import { useEffect } from "react";

import { useEditorStore } from "../../app/editorStore";
import CanvasViewport from "./CanvasViewport";
import LeftToolbar from "./LeftToolbar";
import RightInspector from "./RightInspector";
import TopBar from "./TopBar";

export default function EditorShell() {
  const selectedObjectIds = useEditorStore((s) => s.selectedObjectIds);
  const removeSelectedObjects = useEditorStore((s) => s.removeSelectedObjects);
  const copySelectedObjects = useEditorStore((s) => s.copySelectedObjects);
  const pasteClipboard = useEditorStore((s) => s.pasteClipboard);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (selectedObjectIds.length === 0 && !(event.metaKey || event.ctrlKey)) return;

      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable)
      ) {
        return;
      }

      const isModifierPressed = event.metaKey || event.ctrlKey;
      const key = event.key.toLowerCase();

      if (event.key === "Backspace" || event.key === "Delete") {
        event.preventDefault();
        removeSelectedObjects();
        return;
      }

      if (isModifierPressed && key === "c") {
        event.preventDefault();
        copySelectedObjects();
        return;
      }

      if (isModifierPressed && key === "v") {
        event.preventDefault();
        pasteClipboard();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [copySelectedObjects, pasteClipboard, removeSelectedObjects, selectedObjectIds.length]);

  return (
    <div className="app-shell">
      <TopBar />

      <div className="main-layout">
        <LeftToolbar />
        <CanvasViewport />
        <RightInspector />
      </div>
    </div>
  );
}
