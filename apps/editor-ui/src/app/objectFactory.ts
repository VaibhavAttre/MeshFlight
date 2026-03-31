import type {
  EditorObject,
  Tool,
  DroneObject,
  GatewayObject,
  ClientObject,
  BuildingObject,
  WallObject,
  TreeZoneObject,
  DemandZoneObject,
} from "./editorStore";

function makeId(prefix: string) {
  return `${prefix}-${crypto.randomUUID().slice(0, 8)}`;
}

export function createObjectFromTool(
  tool: Tool,
  x: number,
  y: number
): EditorObject | null {
  switch (tool) {
    case "drone": {
      const obj: DroneObject = {
        id: makeId("drone"),
        type: "drone",
        x,
        y,
        label: "Drone",
        radioRange: 120,
        battery: 100,
      };
      return obj;
    }

    case "gateway": {
      const obj: GatewayObject = {
        id: makeId("gateway"),
        type: "gateway",
        x,
        y,
        label: "Gateway",
        uplink: "fiber",
      };
      return obj;
    }

    case "client": {
      const obj: ClientObject = {
        id: makeId("client"),
        type: "client",
        x,
        y,
        label: "Client",
        demandClass: "standard",
      };
      return obj;
    }

    case "building": {
      const obj: BuildingObject = {
        id: makeId("building"),
        type: "building",
        x,
        y,
        label: "Building",
        width: 120,
        height: 80,
        attenuation: 0.8,
      };
      return obj;
    }

    case "wall": {
      const obj: WallObject = {
        id: makeId("wall"),
        type: "wall",
        x,
        y,
        label: "Wall",
        length: 140,
        attenuation: 0.9,
      };
      return obj;
    }

    case "tree-zone": {
      const obj: TreeZoneObject = {
        id: makeId("trees"),
        type: "tree-zone",
        x,
        y,
        label: "Tree Zone",
        radius: 60,
        attenuation: 0.35,
      };
      return obj;
    }

    case "demand-zone": {
      const obj: DemandZoneObject = {
        id: makeId("demand"),
        type: "demand-zone",
        x,
        y,
        label: "Demand Zone",
        radius: 70,
        intensity: 10,
      };
      return obj;
    }

    case "select":
    default:
      return null;
  }
}