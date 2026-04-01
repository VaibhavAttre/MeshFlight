import { useEffect, useState } from "react";

import { useEditorStore } from "../../app/editorStore";
import {
  CHAOS_EVENT_TYPE_OPTIONS,
  normalizeChaosEventType,
} from "../../lib/editorOptions";

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

function ToolbarSelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly { label: string; value: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="toolbar-field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function LeftToolbar() {
  const activeTool = useEditorStore((s) => s.activeTool);
  const setActiveTool = useEditorStore((s) => s.setActiveTool);
  const objects = useEditorStore((s) => s.objects);
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
  const snapToGrid = useEditorStore((s) => s.snapToGrid);
  const toggleSnapToGrid = useEditorStore((s) => s.toggleSnapToGrid);
  const gridSize = useEditorStore((s) => s.gridSize);
  const setGridSize = useEditorStore((s) => s.setGridSize);
  const events = useEditorStore((s) => s.events);
  const addEvent = useEditorStore((s) => s.addEvent);
  const updateEvent = useEditorStore((s) => s.updateEvent);
  const removeEvent = useEditorStore((s) => s.removeEvent);

  const entityOptions = [
    { label: "Choose target", value: "" },
    ...objects
      .filter(
        (object) =>
          object.type === "drone" ||
          object.type === "gateway" ||
          object.type === "client"
      )
      .map((object) => ({
        label: `${object.label} (${object.type})`,
        value: object.id,
      })),
  ];

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
        <h2>Canvas Controls</h2>

        <button
          type="button"
          className={`drone-radius-toggle ${snapToGrid ? "is-on" : ""}`}
          onClick={toggleSnapToGrid}
          aria-pressed={snapToGrid}
        >
          <span className="drone-radius-toggle__track">
            <span className="drone-radius-toggle__thumb" />
          </span>
          <span className="drone-radius-toggle__label">
            Grid Snap {snapToGrid ? "On" : "Off"}
          </span>
        </button>

        <ToolbarNumberField
          label="Grid Size"
          min={4}
          step={4}
          value={gridSize}
          onCommit={setGridSize}
        />
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

      <div className="toolbar-section">
        <div className="toolbar-section-header">
          <h2>Events</h2>
          <button type="button" onClick={() => addEvent()}>
            Add Event
          </button>
        </div>

        {events.length === 0 && (
          <p className="toolbar-help">
            Add failures or spikes here so they save into the scenario schema.
          </p>
        )}

        {events.map((event, index) => (
          <div key={event.id} className="event-card">
            <div className="event-card__header">
              <strong>Event {index + 1}</strong>
              <button type="button" className="danger-button" onClick={() => removeEvent(event.id)}>
                Remove
              </button>
            </div>

            <ToolbarSelectField
              label="Type"
              value={normalizeChaosEventType(event.eventType)}
              options={CHAOS_EVENT_TYPE_OPTIONS.map((value) => ({
                label: value,
                value,
              }))}
              onChange={(value) =>
                updateEvent(event.id, {
                  eventType: normalizeChaosEventType(value),
                })
              }
            />

            <ToolbarSelectField
              label="Target"
              value={event.targetEntityId}
              options={entityOptions}
              onChange={(value) =>
                updateEvent(event.id, {
                  targetEntityId: value,
                })
              }
            />

            <ToolbarNumberField
              label="Trigger Time (s)"
              min={0}
              step={1}
              value={event.triggerTimeS}
              onCommit={(value) =>
                updateEvent(event.id, {
                  triggerTimeS: value,
                })
              }
            />

            <ToolbarNumberField
              label="Duration (s)"
              min={1}
              step={1}
              value={event.durationS}
              onCommit={(value) =>
                updateEvent(event.id, {
                  durationS: value,
                })
              }
            />

            <ToolbarNumberField
              label="Intensity"
              min={0}
              step={0.1}
              value={event.intensity}
              onCommit={(value) =>
                updateEvent(event.id, {
                  intensity: value,
                })
              }
            />
          </div>
        ))}
      </div>
    </aside>
  );
}
