export default function TopBar() {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <h1>MeshFlight Editor</h1>
      </div>

      <div className="topbar-center">
        <span className="status-pill">No scenario loaded</span>
      </div>

      <div className="topbar-right">
        <button>New</button>
        <button>Load</button>
        <button>Save</button>
      </div>
    </header>
  );
}