import { create } from "zustand";

type Tool =
  | "select"
  | "drone"
  | "gateway"
  | "client"
  | "building"
  | "wall"
  | "tree-zone"
  | "demand-zone";

type EditorStore = {
  activeTool: Tool;
  setActiveTool: (tool: Tool) => void;
  selectedObjectId: string | null;
  setSelectedObjectId: (id: string | null) => void;
};

export const useEditorStore = create<EditorStore>((set) => ({
  activeTool: "select",
  setActiveTool: (tool) => set({ activeTool: tool }),
  selectedObjectId: null,
  setSelectedObjectId: (id) => set({ selectedObjectId: id }),
}));