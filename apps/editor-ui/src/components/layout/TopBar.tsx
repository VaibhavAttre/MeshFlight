import { useEditorStore } from "../../app/editorStore";

export default function TopBar() {
  const showDroneRanges = useEditorStore((s) => s.showDroneRanges);
  const toggleDroneRanges = useEditorStore((s) => s.toggleDroneRanges);

  return (
    <header className="topbar">
      <div className="topbar-left">
        <h1>MeshFlight Editor</h1>
      </div>

      <div className="topbar-center">
        <span className="status-pill">No scenario loaded</span>
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
        <button>New</button>
        <button>Load</button>
        <button>Save</button>
      </div>
    </header>
  );
}
