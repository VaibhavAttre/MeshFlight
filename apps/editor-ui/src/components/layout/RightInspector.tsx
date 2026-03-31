import { useEditorStore, type EditorObject } from "../../app/editorStore";

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

type SharedSelectionType = EditorObject["type"] | null;

function getSharedSelectionType(objects: EditorObject[]): SharedSelectionType {
  if (objects.length === 0) return null;
  const firstType = objects[0].type;
  return objects.every((object) => object.type === firstType) ? firstType : null;
}

export default function RightInspector() {
  const selectedObjectIds = useEditorStore((s) => s.selectedObjectIds);
  const objects = useEditorStore((s) => s.objects);
  const updateObject = useEditorStore((s) => s.updateObject);
  const updateObjectsById = useEditorStore((s) => s.updateObjectsById);
  const removeObject = useEditorStore((s) => s.removeObject);
  const removeSelectedObjects = useEditorStore((s) => s.removeSelectedObjects);

  const selectedObjects = objects.filter((obj) => selectedObjectIds.includes(obj.id));
  const sharedType = getSharedSelectionType(selectedObjects);
  const isMultiSelect = selectedObjects.length > 1;
  const singleSelectedObject = selectedObjects.length === 1 ? selectedObjects[0] : null;
  const sharedObjects = selectedObjects;

  if (selectedObjects.length === 0) {
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

  if (isMultiSelect) {
    const sharedDroneObjects =
      sharedType === "drone" ? (sharedObjects as Extract<EditorObject, { type: "drone" }>[]) : null;
    const sharedGatewayObjects =
      sharedType === "gateway"
        ? (sharedObjects as Extract<EditorObject, { type: "gateway" }>[])
        : null;
    const sharedClientObjects =
      sharedType === "client" ? (sharedObjects as Extract<EditorObject, { type: "client" }>[]) : null;
    const sharedBuildingObjects =
      sharedType === "building"
        ? (sharedObjects as Extract<EditorObject, { type: "building" }>[])
        : null;
    const sharedWallObjects =
      sharedType === "wall" ? (sharedObjects as Extract<EditorObject, { type: "wall" }>[]) : null;
    const sharedTreeZoneObjects =
      sharedType === "tree-zone"
        ? (sharedObjects as Extract<EditorObject, { type: "tree-zone" }>[])
        : null;
    const sharedDemandZoneObjects =
      sharedType === "demand-zone"
        ? (sharedObjects as Extract<EditorObject, { type: "demand-zone" }>[])
        : null;

    return (
      <aside className="right-inspector">
        <h2>Inspector</h2>

        <div className="inspector-fields">
          <div className="field-row">
            <strong>Selection</strong>
            <span>{selectedObjects.length} objects</span>
          </div>

          <div className="field-row">
            <strong>Type Mode</strong>
            <span>{sharedType ? `Shared: ${sharedType}` : "Mixed types"}</span>
          </div>

          {!sharedType && (
            <div className="field-row">
              <strong>Available Actions</strong>
              <span>Drag to move, Ctrl/Cmd+C to copy, Ctrl/Cmd+V to paste, Delete to remove.</span>
            </div>
          )}

          {sharedDroneObjects && (
            <>
              <NumberInput
                label="Radio Range"
                value={sharedDroneObjects[0].radioRange}
                onChange={(value) =>
                  updateObjectsById(selectedObjectIds, () => ({ radioRange: value }))
                }
              />
              <NumberInput
                label="Battery"
                value={sharedDroneObjects[0].battery}
                onChange={(value) =>
                  updateObjectsById(selectedObjectIds, () => ({ battery: value }))
                }
              />
            </>
          )}

          {sharedGatewayObjects && (
            <TextInput
              label="Uplink"
              value={sharedGatewayObjects[0].uplink}
              onChange={(value) =>
                updateObjectsById(selectedObjectIds, () => ({ uplink: value }))
              }
            />
          )}

          {sharedClientObjects && (
            <TextInput
              label="Demand Class"
              value={sharedClientObjects[0].demandClass}
              onChange={(value) =>
                updateObjectsById(selectedObjectIds, () => ({ demandClass: value }))
              }
            />
          )}

          {sharedBuildingObjects && (
            <>
              <NumberInput
                label="Width"
                value={sharedBuildingObjects[0].width}
                onChange={(value) =>
                  updateObjectsById(selectedObjectIds, () => ({ width: value }))
                }
              />
              <NumberInput
                label="Height"
                value={sharedBuildingObjects[0].height}
                onChange={(value) =>
                  updateObjectsById(selectedObjectIds, () => ({ height: value }))
                }
              />
              <NumberInput
                label="Attenuation"
                value={sharedBuildingObjects[0].attenuation}
                step={0.05}
                onChange={(value) =>
                  updateObjectsById(selectedObjectIds, () => ({ attenuation: value }))
                }
              />
            </>
          )}

          {sharedWallObjects && (
            <>
              <NumberInput
                label="Length"
                value={sharedWallObjects[0].length}
                onChange={(value) =>
                  updateObjectsById(selectedObjectIds, () => ({ length: value }))
                }
              />
              <NumberInput
                label="Attenuation"
                value={sharedWallObjects[0].attenuation}
                step={0.05}
                onChange={(value) =>
                  updateObjectsById(selectedObjectIds, () => ({ attenuation: value }))
                }
              />
            </>
          )}

          {(sharedTreeZoneObjects || sharedDemandZoneObjects) && (
            <NumberInput
              label="Radius"
              value={(sharedTreeZoneObjects ?? sharedDemandZoneObjects)![0].radius}
              onChange={(value) =>
                updateObjectsById(selectedObjectIds, () => ({ radius: value }))
              }
            />
          )}

          {sharedTreeZoneObjects && (
            <NumberInput
              label="Attenuation"
              value={sharedTreeZoneObjects[0].attenuation}
              step={0.05}
              onChange={(value) =>
                updateObjectsById(selectedObjectIds, () => ({ attenuation: value }))
              }
            />
          )}

          {sharedDemandZoneObjects && (
            <NumberInput
              label="Intensity"
              value={sharedDemandZoneObjects[0].intensity}
              onChange={(value) =>
                updateObjectsById(selectedObjectIds, () => ({ intensity: value }))
              }
            />
          )}

          <button className="danger-button" onClick={removeSelectedObjects}>
            Delete Selected
          </button>
        </div>
      </aside>
    );
  }

  if (!singleSelectedObject) {
    return null;
  }

  return (
    <aside className="right-inspector">
      <h2>Inspector</h2>

      <div className="inspector-fields">
        <div className="field-row">
          <strong>ID</strong>
          <span>{singleSelectedObject.id}</span>
        </div>

        <div className="field-row">
          <strong>Type</strong>
          <span>{singleSelectedObject.type}</span>
        </div>

        <TextInput
          label="Label"
          value={singleSelectedObject.label}
          onChange={(value) => updateObject(singleSelectedObject.id, { label: value })}
        />

        <NumberInput
          label="X"
          value={singleSelectedObject.x}
          onChange={(value) => updateObject(singleSelectedObject.id, { x: value })}
        />

        <NumberInput
          label="Y"
          value={singleSelectedObject.y}
          onChange={(value) => updateObject(singleSelectedObject.id, { y: value })}
        />

        {"radioRange" in singleSelectedObject && (
          <NumberInput
            label="Radio Range"
            value={singleSelectedObject.radioRange}
            onChange={(value) => updateObject(singleSelectedObject.id, { radioRange: value })}
          />
        )}

        {"battery" in singleSelectedObject && (
          <NumberInput
            label="Battery"
            value={singleSelectedObject.battery}
            onChange={(value) => updateObject(singleSelectedObject.id, { battery: value })}
          />
        )}

        {"uplink" in singleSelectedObject && (
          <TextInput
            label="Uplink"
            value={singleSelectedObject.uplink}
            onChange={(value) => updateObject(singleSelectedObject.id, { uplink: value })}
          />
        )}

        {"demandClass" in singleSelectedObject && (
          <TextInput
            label="Demand Class"
            value={singleSelectedObject.demandClass}
            onChange={(value) =>
              updateObject(singleSelectedObject.id, { demandClass: value })
            }
          />
        )}

        {"width" in singleSelectedObject && (
          <NumberInput
            label="Width"
            value={singleSelectedObject.width}
            onChange={(value) => updateObject(singleSelectedObject.id, { width: value })}
          />
        )}

        {"height" in singleSelectedObject && (
          <NumberInput
            label="Height"
            value={singleSelectedObject.height}
            onChange={(value) => updateObject(singleSelectedObject.id, { height: value })}
          />
        )}

        {"length" in singleSelectedObject && (
          <NumberInput
            label="Length"
            value={singleSelectedObject.length}
            onChange={(value) => updateObject(singleSelectedObject.id, { length: value })}
          />
        )}

        {"radius" in singleSelectedObject && (
          <NumberInput
            label="Radius"
            value={singleSelectedObject.radius}
            onChange={(value) => updateObject(singleSelectedObject.id, { radius: value })}
          />
        )}

        {"attenuation" in singleSelectedObject && (
          <NumberInput
            label="Attenuation"
            value={singleSelectedObject.attenuation}
            step={0.05}
            onChange={(value) =>
              updateObject(singleSelectedObject.id, { attenuation: value })
            }
          />
        )}

        {"intensity" in singleSelectedObject && (
          <NumberInput
            label="Intensity"
            value={singleSelectedObject.intensity}
            onChange={(value) => updateObject(singleSelectedObject.id, { intensity: value })}
          />
        )}

        <button
          className="danger-button"
          onClick={() => removeObject(singleSelectedObject.id)}
        >
          Delete Object
        </button>
      </div>
    </aside>
  );
}
