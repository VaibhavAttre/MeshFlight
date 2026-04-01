import type { EditorObject } from "./editorStore";

export type EditorDocument = {
  version: 1;
  name: string;
  savedAt: string | null;
  canvas: {
    width: number;
    height: number;
  };
  objects: EditorObject[];
  view: {
    showDroneRanges: boolean;
    showClientDroneLinks: boolean;
    densityCellSize: number;
    densityThreshold: number;
    autoZoneRadius: number;
    autoZoneIntensity: number;
    autoDemandZonesEnabled: boolean;
  };
};

export function createEmptyEditorDocument(): EditorDocument {
  return {
    version: 1,
    name: "untitled-scenario",
    savedAt: null,
    canvas: {
      width: 2000,
      height: 1200,
    },
    objects: [],
    view: {
      showDroneRanges: false,
      showClientDroneLinks: false,
      densityCellSize: 120,
      densityThreshold: 3,
      autoZoneRadius: 80,
      autoZoneIntensity: 10,
      autoDemandZonesEnabled: false,
    },
  };
}