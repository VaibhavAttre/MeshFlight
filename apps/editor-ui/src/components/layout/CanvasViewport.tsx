import { useRef, useState } from "react";
import { useEditorStore, type EditorObject } from "../../app/editorStore";
import { createObjectFromTool } from "../../app/objectFactory";

type DragState = {
  objectId: string;
  offsetX: number;
  offsetY: number;
} | null;

type ResizeState =
  | {
      objectId: string;
      mode: "building-size" | "drone-range" | "zone-radius" | "wall-length";
    }
  | null;

function ObjectLabel({ text }: { text: string }) {
  return <div className="canvas-object-label">{text}</div>;
}

function Handle({
  x,
  y,
  onMouseDown,
}: {
  x: number;
  y: number;
  onMouseDown: (e: React.MouseEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      className="resize-handle"
      style={{
        position: "absolute",
        left: x,
        top: y,
        transform: "translate(-50%, -50%)",
      }}
      onMouseDown={onMouseDown}
    />
  );
}

export default function CanvasViewport() {
  const canvasRef = useRef<HTMLDivElement | null>(null);

  const activeTool = useEditorStore((s) => s.activeTool);
  const objects = useEditorStore((s) => s.objects);
  const addObject = useEditorStore((s) => s.addObject);
  const setActiveTool = useEditorStore((s) => s.setActiveTool);
  const updateObject = useEditorStore((s) => s.updateObject);
  const showDroneRanges = useEditorStore((s) => s.showDroneRanges);
  const selectedObjectId = useEditorStore((s) => s.selectedObjectId);
  const setSelectedObjectId = useEditorStore((s) => s.setSelectedObjectId);

  const [dragState, setDragState] = useState<DragState>(null);
  const [resizeState, setResizeState] = useState<ResizeState>(null);

  function getCanvasCoordinates(clientX: number, clientY: number) {
    if (!canvasRef.current) return null;
    const rect = canvasRef.current.getBoundingClientRect();

    return {
      x: clientX - rect.left,
      y: clientY - rect.top,
    };
  }

  function distance(ax: number, ay: number, bx: number, by: number) {
    return Math.sqrt((ax - bx) ** 2 + (ay - by) ** 2);
  }

  function handleCanvasClick(event: React.MouseEvent<HTMLDivElement>) {
    if (dragState || resizeState) return;

    const coords = getCanvasCoordinates(event.clientX, event.clientY);
    if (!coords) return;

    if (activeTool === "select") {
      setSelectedObjectId(null);
      return;
    }

    const newObject = createObjectFromTool(activeTool, coords.x, coords.y);
    if (!newObject) return;

    addObject(newObject);
    setSelectedObjectId(newObject.id);
    setActiveTool("select");
  }

  function handleMouseDownObject(
    event: React.MouseEvent<HTMLDivElement>,
    object: EditorObject
  ) {
    event.stopPropagation();
    setSelectedObjectId(object.id);

    if (activeTool !== "select") return;

    const coords = getCanvasCoordinates(event.clientX, event.clientY);
    if (!coords) return;

    setDragState({
      objectId: object.id,
      offsetX: coords.x - object.x,
      offsetY: coords.y - object.y,
    });
  }

  function startResize(
    event: React.MouseEvent<HTMLDivElement>,
    objectId: string,
    mode: "building-size" | "drone-range" | "zone-radius" | "wall-length"
  ) {
    event.stopPropagation();
    event.preventDefault();
    setResizeState({ objectId, mode });
  }

  function handleMouseMove(event: React.MouseEvent<HTMLDivElement>) {
    const coords = getCanvasCoordinates(event.clientX, event.clientY);
    if (!coords) return;

    if (dragState) {
      const nextX = coords.x - dragState.offsetX;
      const nextY = coords.y - dragState.offsetY;

      updateObject(dragState.objectId, {
        x: nextX,
        y: nextY,
      });
      return;
    }

    if (resizeState) {
      const object = objects.find((obj) => obj.id === resizeState.objectId);
      if (!object) return;

      if (resizeState.mode === "building-size" && object.type === "building") {
        const nextWidth = Math.max(30, Math.abs(coords.x - object.x) * 2);
        const nextHeight = Math.max(30, Math.abs(coords.y - object.y) * 2);
        updateObject(object.id, {
          width: Math.round(nextWidth),
          height: Math.round(nextHeight),
        });
        return;
      }

      if (resizeState.mode === "drone-range" && object.type === "drone") {
        const nextRange = Math.max(20, distance(object.x, object.y, coords.x, coords.y));
        updateObject(object.id, { radioRange: Math.round(nextRange) });
        return;
      }

      if (
        resizeState.mode === "zone-radius" &&
        (object.type === "tree-zone" || object.type === "demand-zone")
      ) {
        const nextRadius = Math.max(10, distance(object.x, object.y, coords.x, coords.y));
        updateObject(object.id, { radius: Math.round(nextRadius) });
        return;
      }

      if (resizeState.mode === "wall-length" && object.type === "wall") {
        const nextLength = Math.max(20, coords.x - object.x + object.length / 2);
        updateObject(object.id, { length: Math.round(nextLength) });
      }
    }
  }

  function endInteractions() {
    if (dragState) setDragState(null);
    if (resizeState) setResizeState(null);
  }

  const selectedObject = objects.find((obj) => obj.id === selectedObjectId);

  return (
    <main className="canvas-viewport">
      <div className="canvas-header">
        <span>Canvas</span>
        <span>
          Active Tool: <strong>{activeTool}</strong>
        </span>
      </div>

      <div
        ref={canvasRef}
        className="canvas-surface"
        onClick={handleCanvasClick}
        onMouseMove={handleMouseMove}
        onMouseUp={endInteractions}
        onMouseLeave={endInteractions}
      >
        <div className="grid-overlay" />

        {objects.map((object) => {
          const isSelected = object.id === selectedObjectId;

          const commonStyle: React.CSSProperties = {
            position: "absolute",
            left: object.x,
            top: object.y,
            transform: "translate(-50%, -50%)",
            border: isSelected ? "2px solid #60a5fa" : "1px solid #0f172a",
            cursor: activeTool === "select" ? "grab" : "pointer",
            userSelect: "none",
          };

          const sharedProps = {
            key: object.id,
            title: `${object.label} (${object.id})`,
            onClick: (e: React.MouseEvent<HTMLDivElement>) => {
              e.stopPropagation();
              setSelectedObjectId(object.id);
            },
            onMouseDown: (e: React.MouseEvent<HTMLDivElement>) =>
              handleMouseDownObject(e, object),
          };

          switch (object.type) {
            case "drone":
              return (
                <div key={object.id}>
                  {showDroneRanges && (
                    <div
                      className="range-visual"
                      style={{
                        left: object.x,
                        top: object.y,
                        width: object.radioRange * 2,
                        height: object.radioRange * 2,
                      }}
                    />
                  )}

                  {isSelected && showDroneRanges && (
                    <>
                      <Handle
                        x={object.x + object.radioRange}
                        y={object.y}
                        onMouseDown={(e) =>
                          startResize(e, object.id, "drone-range")
                        }
                      />
                    </>
                  )}

                  <div
                    {...sharedProps}
                    style={{
                      ...commonStyle,
                      width: 22,
                      height: 22,
                      borderRadius: "50%",
                      background: "#38bdf8",
                    }}
                  >
                    <ObjectLabel text={object.label} />
                  </div>
                </div>
              );

            case "gateway":
              return (
                <div
                  {...sharedProps}
                  style={{
                    ...commonStyle,
                    width: 26,
                    height: 26,
                    borderRadius: 6,
                    background: "#f59e0b",
                  }}
                >
                  <ObjectLabel text={object.label} />
                </div>
              );

            case "client":
              return (
                <div
                  {...sharedProps}
                  style={{
                    ...commonStyle,
                    width: 16,
                    height: 16,
                    borderRadius: "50%",
                    background: "#a78bfa",
                  }}
                >
                  <ObjectLabel text={object.label} />
                </div>
              );

            case "building":
              return (
                <div key={object.id}>
                  <div
                    {...sharedProps}
                    style={{
                      ...commonStyle,
                      width: object.width,
                      height: object.height,
                      borderRadius: 8,
                      background: "#c4a484",
                    }}
                  >
                    <ObjectLabel text={object.label} />
                  </div>

                  {isSelected && (
                    <Handle
                      x={object.x + object.width / 2}
                      y={object.y + object.height / 2}
                      onMouseDown={(e) =>
                        startResize(e, object.id, "building-size")
                      }
                    />
                  )}
                </div>
              );

            case "wall":
              return (
                <div key={object.id}>
                  <div
                    {...sharedProps}
                    style={{
                      ...commonStyle,
                      width: object.length,
                      height: 10,
                      borderRadius: 6,
                      background: "#6b7280",
                    }}
                  >
                    <ObjectLabel text={object.label} />
                  </div>

                  {isSelected && (
                    <Handle
                      x={object.x + object.length / 2}
                      y={object.y}
                      onMouseDown={(e) => startResize(e, object.id, "wall-length")}
                    />
                  )}
                </div>
              );

            case "tree-zone":
              return (
                <div key={object.id}>
                  <div
                    {...sharedProps}
                    style={{
                      ...commonStyle,
                      width: object.radius * 2,
                      height: object.radius * 2,
                      borderRadius: "50%",
                      background: "rgba(34, 197, 94, 0.45)",
                    }}
                  >
                    <ObjectLabel text={object.label} />
                  </div>

                  {isSelected && (
                    <Handle
                      x={object.x + object.radius}
                      y={object.y}
                      onMouseDown={(e) => startResize(e, object.id, "zone-radius")}
                    />
                  )}
                </div>
              );

            case "demand-zone":
              return (
                <div key={object.id}>
                  <div
                    {...sharedProps}
                    style={{
                      ...commonStyle,
                      width: object.radius * 2,
                      height: object.radius * 2,
                      borderRadius: "50%",
                      background: "rgba(239, 68, 68, 0.25)",
                      outline: "2px dashed rgba(239, 68, 68, 0.8)",
                    }}
                  >
                    <ObjectLabel text={object.label} />
                  </div>

                  {isSelected && (
                    <Handle
                      x={object.x + object.radius}
                      y={object.y}
                      onMouseDown={(e) => startResize(e, object.id, "zone-radius")}
                    />
                  )}
                </div>
              );

            default:
              return null;
          }
        })}

        {objects.length === 0 && (
          <div className="canvas-placeholder">
            <p>2D Map Area</p>
            <p>Pick a tool and click to place objects.</p>
          </div>
        )}

        {selectedObject && (
          <div className="selection-readout">
            Selected: {selectedObject.label} ({selectedObject.type})
          </div>
        )}
      </div>
    </main>
  );
}
