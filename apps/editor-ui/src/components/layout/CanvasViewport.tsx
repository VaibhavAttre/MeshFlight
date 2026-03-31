import { useEditorStore } from "../../app/editorStore";

export default function CanvasViewport() {
  const activeTool = useEditorStore((s) => s.activeTool);

  return (
    <main className="canvas-viewport">
      <div className="canvas-header">
        <span>Canvas</span>
        <span>Active Tool: {activeTool}</span>
      </div>

      <div className="canvas-surface">
        <div className="grid-overlay" />
        <div className="canvas-placeholder">
          <p>2D Map Area</p>
          <p>Selected tool: {activeTool}</p>
        </div>
      </div>
    </main>
  );
}       