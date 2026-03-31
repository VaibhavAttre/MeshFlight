import { useEditorStore } from "../../app/editorStore";

const tools = [
  { label: "Select", value: "select" },
  { label: "Drone", value: "drone" },
  { label: "Gateway", value: "gateway" },
  { label: "Client", value: "client" },
  { label: "Building", value: "building" },
  { label: "Wall", value: "wall" },
  { label: "Tree Zone", value: "tree-zone" },
  { label: "Demand Zone", value: "demand-zone" },
] as const;

export default function LeftToolbar() {
  const activeTool = useEditorStore((s) => s.activeTool);
  const setActiveTool = useEditorStore((s) => s.setActiveTool);

  return (
    <aside className="left-toolbar">
      <h2>Tools</h2>

      <div className="tool-list">
        {tools.map((tool) => {
          const isActive = activeTool === tool.value;

          return (
            <button
              key={tool.value}
              className="tool-button"
              onClick={() => setActiveTool(tool.value)}
              style={{
                outline: isActive ? "2px solid #60a5fa" : "none",
                background: isActive ? "#1d4ed8" : undefined,
              }}
            >
              {tool.label}
            </button>
          );
        })}
      </div>
    </aside>
  );
}