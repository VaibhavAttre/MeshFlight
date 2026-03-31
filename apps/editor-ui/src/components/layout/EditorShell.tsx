import TopBar from "./TopBar";
import LeftToolbar from "./LeftToolbar";
import RightInspector from "./RightInspector";
import CanvasViewport from "./CanvasViewport";

export default function EditorShell() {
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