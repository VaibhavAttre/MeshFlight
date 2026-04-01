import type { EditorDocument } from "../app/editorDocument";
import type { EditorObject } from "../app/editorStore";

type AnyRecord = Record<string, unknown>;

function isRecord(value: unknown): value is AnyRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asString(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

function asBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function assertObjectType(
  type: string
): asserts type is EditorObject["type"] {
  const allowed = new Set([
    "drone",
    "gateway",
    "client",
    "building",
    "wall",
    "tree-zone",
    "demand-zone",
  ]);

  if (!allowed.has(type)) {
    throw new Error(`Unsupported object type: ${type}`);
  }
}

function normalizeObject(raw: unknown): EditorObject {
  if (!isRecord(raw)) {
    throw new Error("Each object must be an object.");
  }

  const type = asString(raw.type, "");
  assertObjectType(type);

  switch (type) {
    case "drone":
      return {
        id: asString(raw.id, crypto.randomUUID()),
        type: "drone",
        x: asNumber(raw.x, 0),
        y: asNumber(raw.y, 0),
        label: asString(raw.label, type),
        radioRange: asNumber(raw.radioRange, 150),
        battery: asNumber(raw.battery, 100),
      };

    case "gateway":
      return {
        id: asString(raw.id, crypto.randomUUID()),
        type: "gateway",
        x: asNumber(raw.x, 0),
        y: asNumber(raw.y, 0),
        label: asString(raw.label, type),
        uplink: asString(raw.uplink, "fiber"),
      };

    case "client":
      return {
        id: asString(raw.id, crypto.randomUUID()),
        type: "client",
        x: asNumber(raw.x, 0),
        y: asNumber(raw.y, 0),
        label: asString(raw.label, type),
        demandClass: asString(raw.demandClass, "standard"),
      };

    case "building":
      return {
        id: asString(raw.id, crypto.randomUUID()),
        type: "building",
        x: asNumber(raw.x, 0),
        y: asNumber(raw.y, 0),
        label: asString(raw.label, type),
        width: asNumber(raw.width, 120),
        height: asNumber(raw.height, 120),
        attenuation: asNumber(raw.attenuation, 0.8),
      };

    case "wall":
      return {
        id: asString(raw.id, crypto.randomUUID()),
        type: "wall",
        x: asNumber(raw.x, 0),
        y: asNumber(raw.y, 0),
        label: asString(raw.label, type),
        length: asNumber(raw.length, 140),
        attenuation: asNumber(raw.attenuation, 0.6),
      };

    case "tree-zone":
      return {
        id: asString(raw.id, crypto.randomUUID()),
        type: "tree-zone",
        x: asNumber(raw.x, 0),
        y: asNumber(raw.y, 0),
        label: asString(raw.label, type),
        radius: asNumber(raw.radius, 60),
        attenuation: asNumber(raw.attenuation, 0.35),
      };

    case "demand-zone":
      return {
        id: asString(raw.id, crypto.randomUUID()),
        type: "demand-zone",
        x: asNumber(raw.x, 0),
        y: asNumber(raw.y, 0),
        label: asString(raw.label, type),
        radius: asNumber(raw.radius, 80),
        intensity: asNumber(raw.intensity, 10),
      };
    default:
      throw new Error(`Unhandled object type: ${type}`);
  }
}

export function normalizeEditorDocument(raw: unknown): EditorDocument {
  if (!isRecord(raw)) {
    throw new Error("Document must be an object.");
  }

  const version = asNumber(raw.version, -1);
  if (version !== 1) {
    throw new Error(`Unsupported document version: ${version}`);
  }

  const canvasRaw = isRecord(raw.canvas) ? raw.canvas : {};
  const viewRaw = isRecord(raw.view) ? raw.view : {};
  const objectsRaw = Array.isArray(raw.objects) ? raw.objects : null;

  if (!objectsRaw) {
    throw new Error("Document is missing objects array.");
  }

  return {
    version: 1,
    name: asString(raw.name, "untitled-scenario"),
    savedAt: raw.savedAt === null ? null : asString(raw.savedAt, null as never),
    canvas: {
      width: asNumber(canvasRaw.width, 2000),
      height: asNumber(canvasRaw.height, 1200),
    },
    objects: objectsRaw.map(normalizeObject),
    view: {
      showDroneRanges: asBoolean(viewRaw.showDroneRanges, false),
      showClientDroneLinks: asBoolean(viewRaw.showClientDroneLinks, false),
      densityCellSize: asNumber(viewRaw.densityCellSize, 120),
      densityThreshold: asNumber(viewRaw.densityThreshold, 3),
      autoZoneRadius: asNumber(viewRaw.autoZoneRadius, 80),
      autoZoneIntensity: asNumber(viewRaw.autoZoneIntensity, 10),
      autoDemandZonesEnabled: asBoolean(viewRaw.autoDemandZonesEnabled, false),
    },
  };
}
