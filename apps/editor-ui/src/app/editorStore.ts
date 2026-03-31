import { create } from "zustand";

export type Tool =
  | "select"
  | "drone"
  | "gateway"
  | "client"
  | "building"
  | "wall"
  | "tree-zone"
  | "demand-zone";

export type BaseObject = {
  id: string;
  type: Exclude<Tool, "select">;
  x: number;
  y: number;
  label: string;
};

export type DroneObject = BaseObject & {
  type: "drone";
  radioRange: number;
  battery: number;
};

export type GatewayObject = BaseObject & {
  type: "gateway";
  uplink: string;
};

export type ClientObject = BaseObject & {
  type: "client";
  demandClass: string;
};

export type BuildingObject = BaseObject & {
  type: "building";
  width: number;
  height: number;
  attenuation: number;
};

export type WallObject = BaseObject & {
  type: "wall";
  length: number;
  attenuation: number;
};

export type TreeZoneObject = BaseObject & {
  type: "tree-zone";
  radius: number;
  attenuation: number;
};

export type DemandZoneObject = BaseObject & {
  type: "demand-zone";
  radius: number;
  intensity: number;
};

export type EditorObject =
  | DroneObject
  | GatewayObject
  | ClientObject
  | BuildingObject
  | WallObject
  | TreeZoneObject
  | DemandZoneObject;

type EditorStore = {
  activeTool: Tool;
  setActiveTool: (tool: Tool) => void;

  showDroneRanges: boolean;
  toggleDroneRanges: () => void;

  selectedObjectId: string | null;
  setSelectedObjectId: (id: string | null) => void;

  objects: EditorObject[];
  addObject: (object: EditorObject) => void;

  updateObject: (id: string, patch: Partial<EditorObject>) => void;
  removeObject: (id: string) => void;
};

export const useEditorStore = create<EditorStore>((set) => ({
  activeTool: "select",
  setActiveTool: (tool) => set({ activeTool: tool }),

  showDroneRanges: false,
  toggleDroneRanges: () =>
    set((state) => ({ showDroneRanges: !state.showDroneRanges })),

  selectedObjectId: null,
  setSelectedObjectId: (id) => set({ selectedObjectId: id }),

  objects: [],
  addObject: (object) =>
    set((state) => ({
      objects: [...state.objects, object],
    })),

  updateObject: (id, patch) =>
    set((state) => ({
      objects: state.objects.map((obj) =>
        obj.id === id ? ({ ...obj, ...patch } as EditorObject) : obj
      ),
    })),

  removeObject: (id) =>
    set((state) => ({
      objects: state.objects.filter((obj) => obj.id !== id),
      selectedObjectId:
        state.selectedObjectId === id ? null : state.selectedObjectId,
    })),
}));
