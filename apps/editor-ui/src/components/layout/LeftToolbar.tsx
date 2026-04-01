import { useEffect, useState } from "react";

import { useEditorStore } from "../../app/editorStore";

const tools = [
  { label: "Select", value: "select" },
  { label: "Drone", value: "drone" },
  { label: "Gateway", value: "gateway" },
  { label: "Client", value: "client" },
  { label: "Building", value: "building" },
  { label: "Wall", value: "wall" },
  { label: "Tree Zone", value: "tree-zone" },
] as const;

function ToolbarNumberField({
  label,
  min,
  step,
  value,
  onCommit,
}: {
  label: string;
  min: number;
  step: number;
  value: number;
  onCommit: (value: number) => void;
}) {
  const [draftValue, setDraftValue] = useState(String(value));

  useEffect(() => {
    setDraftValue(String(value));
  }, [value]);

  function commit(nextRawValue: string) {
    if (nextRawValue.trim() === "") {
      setDraftValue(String(value));
      return;
    }

    const parsedValue = Number(nextRawValue);
    if (!Number.isFinite(parsedValue)) {
      setDraftValue(String(value));
      return;
    }

    const normalizedValue = Math.max(min, parsedValue);
    onCommit(normalizedValue);
    setDraftValue(String(normalizedValue));
  }

  return (
    <label className="toolbar-field">
      <span>{label}</span>
      <input
        type="number"
        min={min}
        step={step}
        value={draftValue}
        onChange={(event) => setDraftValue(event.target.value)}
        onBlur={(event) => commit(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            commit((event.target as HTMLInputElement).value);
          }
        }}
      />
    </label>
  );
}

export default function LeftToolbar() {
  const activeTool = useEditorStore((s) => s.activeTool);
  const setActiveTool = useEditorStore((s) => s.setActiveTool);
  const densityCellSize = useEditorStore((s) => s.densityCellSize);
  const setDensityCellSize = useEditorStore((s) => s.setDensityCellSize);
  const densityThreshold = useEditorStore((s) => s.densityThreshold);
  const setDensityThreshold = useEditorStore((s) => s.setDensityThreshold);
  const autoZoneRadius = useEditorStore((s) => s.autoZoneRadius);
  const setAutoZoneRadius = useEditorStore((s) => s.setAutoZoneRadius);
  const autoZoneIntensity = useEditorStore((s) => s.autoZoneIntensity);
  const setAutoZoneIntensity = useEditorStore((s) => s.setAutoZoneIntensity);
  const autoDemandZonesEnabled = useEditorStore((s) => s.autoDemandZonesEnabled);
  const toggleAutoDemandZones = useEditorStore((s) => s.toggleAutoDemandZones);

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

      <div className="toolbar-section">
        <h2>Auto Demand Zones</h2>

        <button
          type="button"
          className={`drone-radius-toggle ${autoDemandZonesEnabled ? "is-on" : ""}`}
          onClick={toggleAutoDemandZones}
          aria-pressed={autoDemandZonesEnabled}
        >
          <span className="drone-radius-toggle__track">
            <span className="drone-radius-toggle__thumb" />
          </span>
          <span className="drone-radius-toggle__label">
            Auto Zones {autoDemandZonesEnabled ? "On" : "Off"}
          </span>
        </button>

        <ToolbarNumberField
          label="Cell Size"
          min={1}
          step={1}
          value={densityCellSize}
          onCommit={setDensityCellSize}
        />

        <ToolbarNumberField
          label="Min Clients"
          min={2}
          step={1}
          value={densityThreshold}
          onCommit={setDensityThreshold}
        />

        <ToolbarNumberField
          label="Zone Radius"
          min={20}
          step={5}
          value={autoZoneRadius}
          onCommit={setAutoZoneRadius}
        />

        <ToolbarNumberField
          label="Base Intensity"
          min={1}
          step={1}
          value={autoZoneIntensity}
          onCommit={setAutoZoneIntensity}
        />
      </div>
    </aside>
  );
}
