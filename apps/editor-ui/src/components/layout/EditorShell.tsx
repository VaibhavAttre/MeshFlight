import { useEffect } from "react";

import { useEditorStore } from "../../app/editorStore";
import TopBar from "./TopBar";
import LeftToolbar from "./LeftToolbar";
import RightInspector from "./RightInspector";
import CanvasViewport from "./CanvasViewport";

export default function EditorShell() {
  const selectedObjectId = useEditorStore((s) => s.selectedObjectId);
  const removeObject = useEditorStore((s) => s.removeObject);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (!selectedObjectId) return;

      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable)
      ) {
        return;
      }

      if (event.key === "Backspace" || event.key === "Delete") {
        event.preventDefault();
        removeObject(selectedObjectId);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [removeObject, selectedObjectId]);

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
