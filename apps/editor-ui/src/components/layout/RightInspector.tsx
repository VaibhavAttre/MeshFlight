import { useEditorStore } from "../../app/editorStore";

function NumberInput({
  label,
  value,
  onChange,
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: number;
}) {
  return (
    <label className="editor-field">
      <span>{label}</span>
      <input
        type="number"
        value={Number.isFinite(value) ? value : 0}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}

function TextInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="editor-field">
      <span>{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

export default function RightInspector() {
  const selectedObjectId = useEditorStore((s) => s.selectedObjectId);
  const objects = useEditorStore((s) => s.objects);
  const updateObject = useEditorStore((s) => s.updateObject);
  const removeObject = useEditorStore((s) => s.removeObject);

  const selectedObject = objects.find((obj) => obj.id === selectedObjectId);

  if (!selectedObject) {
    return (
      <aside className="right-inspector">
        <h2>Inspector</h2>
        <div className="inspector-empty">
          <p>No object selected</p>
          <p>Select something on the canvas to edit its properties.</p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="right-inspector">
      <h2>Inspector</h2>

      <div className="inspector-fields">
        <div className="field-row">
          <strong>ID</strong>
          <span>{selectedObject.id}</span>
        </div>

        <div className="field-row">
          <strong>Type</strong>
          <span>{selectedObject.type}</span>
        </div>

        <TextInput
          label="Label"
          value={selectedObject.label}
          onChange={(value) =>
            updateObject(selectedObject.id, { label: value })
          }
        />

        <NumberInput
          label="X"
          value={selectedObject.x}
          onChange={(value) => updateObject(selectedObject.id, { x: value })}
        />

        <NumberInput
          label="Y"
          value={selectedObject.y}
          onChange={(value) => updateObject(selectedObject.id, { y: value })}
        />

        {"radioRange" in selectedObject && (
          <NumberInput
            label="Radio Range"
            value={selectedObject.radioRange}
            onChange={(value) =>
              updateObject(selectedObject.id, { radioRange: value })
            }
          />
        )}

        {"battery" in selectedObject && (
          <NumberInput
            label="Battery"
            value={selectedObject.battery}
            onChange={(value) =>
              updateObject(selectedObject.id, { battery: value })
            }
          />
        )}

        {"uplink" in selectedObject && (
          <TextInput
            label="Uplink"
            value={selectedObject.uplink}
            onChange={(value) =>
              updateObject(selectedObject.id, { uplink: value })
            }
          />
        )}

        {"demandClass" in selectedObject && (
          <TextInput
            label="Demand Class"
            value={selectedObject.demandClass}
            onChange={(value) =>
              updateObject(selectedObject.id, { demandClass: value })
            }
          />
        )}

        {"width" in selectedObject && (
          <NumberInput
            label="Width"
            value={selectedObject.width}
            onChange={(value) =>
              updateObject(selectedObject.id, { width: value })
            }
          />
        )}

        {"height" in selectedObject && (
          <NumberInput
            label="Height"
            value={selectedObject.height}
            onChange={(value) =>
              updateObject(selectedObject.id, { height: value })
            }
          />
        )}

        {"length" in selectedObject && (
          <NumberInput
            label="Length"
            value={selectedObject.length}
            onChange={(value) =>
              updateObject(selectedObject.id, { length: value })
            }
          />
        )}

        {"radius" in selectedObject && (
          <NumberInput
            label="Radius"
            value={selectedObject.radius}
            onChange={(value) =>
              updateObject(selectedObject.id, { radius: value })
            }
          />
        )}

        {"attenuation" in selectedObject && (
          <NumberInput
            label="Attenuation"
            value={selectedObject.attenuation}
            step={0.05}
            onChange={(value) =>
              updateObject(selectedObject.id, { attenuation: value })
            }
          />
        )}

        {"intensity" in selectedObject && (
          <NumberInput
            label="Intensity"
            value={selectedObject.intensity}
            onChange={(value) =>
              updateObject(selectedObject.id, { intensity: value })
            }
          />
        )}

        <button
          className="danger-button"
          onClick={() => removeObject(selectedObject.id)}
        >
          Delete Object
        </button>
      </div>
    </aside>
  );
}