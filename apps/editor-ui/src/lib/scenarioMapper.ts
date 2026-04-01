import type { EditorDocument } from "../app/editorDocument";
import { createEmptyEditorDocument } from "../app/editorDocument";

type Point2D = {
  x: number;
  y: number;
};

type ScenarioMetadata = {
  scenario_id: string;
  schema_version: string;
  title: string;
  description: string;
  seed: number;
  created_at: string;
  authoring_version: string;
};

type MapLayer = {
  id: string;
  name: string;
  visible: boolean;
};

type MapConfig = {
  width: number;
  height: number;
  grid_resolution: number;
  unit_scale_meters: number;
  origin: Point2D;
  layers: MapLayer[];
};

type DroneEntity = {
  id: string;
  type: "drone";
  label: string;
  position: Point2D;
  tags: string[];
  battery_capacity_mah: number;
  max_speed_mps: number;
  comms_range_m: number;
  waypoint_step_m: number;
};

type GatewayEntity = {
  id: string;
  type: "gateway";
  label: string;
  position: Point2D;
  tags: string[];
  uplink_capacity_mbps: number;
  comms_range_m: number;
};

type ClientEntity = {
  id: string;
  type: "client";
  label: string;
  position: Point2D;
  tags: string[];
  demand_profile: string;
};

type ScenarioEntity = DroneEntity | GatewayEntity | ClientEntity;

type BuildingObstacle = {
  id: string;
  type: "building";
  label: string;
  attenuation_db: number;
  blocks_flight: true;
  shape: "rect";
  position: Point2D;
  size: {
    width: number;
    height: number;
  };
};

type WallObstacle = {
  id: string;
  type: "wall";
  label: string;
  attenuation_db: number;
  blocks_flight: false;
  shape: "segment";
  start: Point2D;
  end: Point2D;
};

type VegetationObstacle = {
  id: string;
  type: "vegetation";
  label: string;
  attenuation_db: number;
  blocks_flight: false;
  shape: "circle";
  center: Point2D;
  radius: number;
};

type ScenarioObstacle = BuildingObstacle | WallObstacle | VegetationObstacle;

type DemandZone = {
  id: string;
  label: string;
  center: Point2D;
  radius_m: number;
  priority: number;
};

export type ScenarioSource = {
  metadata: ScenarioMetadata;
  map: MapConfig;
  entities: ScenarioEntity[];
  obstacles: ScenarioObstacle[];
  demand_zones: DemandZone[];
  traffic_classes: unknown[];
  scheduled_traffic: unknown[];
  chaos_events: unknown[];
};

function slugifyScenarioId(name: string) {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

  return slug || "untitled-scenario";
}

function makeTimestamp(value: string | null | undefined) {
  return value ?? new Date().toISOString();
}

function clampPriority(value: number) {
  return Math.max(1, Math.min(10, Math.round(value || 1)));
}

function makeGatewayCapacity(uplink: string) {
  switch (uplink.trim().toLowerCase()) {
    case "satellite":
      return 75;
    case "cellular":
      return 120;
    case "microwave":
      return 180;
    case "fiber":
    default:
      return 250;
  }
}

function findTagValue(tags: string[] | undefined, prefix: string) {
  return tags?.find((tag) => tag.startsWith(prefix))?.slice(prefix.length);
}

export function isScenarioSource(value: unknown): value is ScenarioSource {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const record = value as Record<string, unknown>;
  const metadata = record.metadata;
  const map = record.map;

  return (
    typeof metadata === "object" &&
    metadata !== null &&
    !Array.isArray(metadata) &&
    typeof map === "object" &&
    map !== null &&
    !Array.isArray(map) &&
    Array.isArray(record.entities) &&
    Array.isArray(record.obstacles) &&
    Array.isArray(record.demand_zones)
  );
}

export function editorDocumentToScenarioSource(
  doc: EditorDocument
): ScenarioSource {
  const entities: ScenarioEntity[] = [];
  const obstacles: ScenarioObstacle[] = [];
  const demand_zones: DemandZone[] = [];

  for (const obj of doc.objects) {
    switch (obj.type) {
      case "drone":
        entities.push({
          id: obj.id,
          type: "drone",
          label: obj.label,
          position: { x: obj.x, y: obj.y },
          tags: [`editor:battery_pct=${obj.battery}`],
          battery_capacity_mah: Math.max(1, obj.battery),
          max_speed_mps: 15,
          comms_range_m: obj.radioRange,
          waypoint_step_m: 25,
        });
        break;

      case "gateway":
        entities.push({
          id: obj.id,
          type: "gateway",
          label: obj.label,
          position: { x: obj.x, y: obj.y },
          tags: [`editor:uplink=${obj.uplink}`],
          uplink_capacity_mbps: makeGatewayCapacity(obj.uplink),
          comms_range_m: 240,
        });
        break;

      case "client":
        entities.push({
          id: obj.id,
          type: "client",
          label: obj.label,
          position: { x: obj.x, y: obj.y },
          tags: [],
          demand_profile: obj.demandClass,
        });
        break;

      case "building":
        obstacles.push({
          id: obj.id,
          type: "building",
          label: obj.label,
          attenuation_db: obj.attenuation,
          blocks_flight: true,
          shape: "rect",
          position: { x: obj.x, y: obj.y },
          size: {
            width: obj.width,
            height: obj.height,
          },
        });
        break;

      case "wall":
        obstacles.push({
          id: obj.id,
          type: "wall",
          label: obj.label,
          attenuation_db: obj.attenuation,
          blocks_flight: false,
          shape: "segment",
          start: { x: obj.x - obj.length / 2, y: obj.y },
          end: { x: obj.x + obj.length / 2, y: obj.y },
        });
        break;

      case "tree-zone":
        obstacles.push({
          id: obj.id,
          type: "vegetation",
          label: obj.label,
          attenuation_db: obj.attenuation,
          blocks_flight: false,
          shape: "circle",
          center: { x: obj.x, y: obj.y },
          radius: obj.radius,
        });
        break;

      case "demand-zone":
        demand_zones.push({
          id: obj.id,
          label: obj.label,
          center: { x: obj.x, y: obj.y },
          radius_m: obj.radius,
          priority: clampPriority(obj.intensity),
        });
        break;

      default: {
        const _never: never = obj;
        throw new Error(`Unsupported object type: ${JSON.stringify(_never)}`);
      }
    }
  }

  return {
    metadata: {
      scenario_id: slugifyScenarioId(doc.name),
      schema_version: "0.1.0",
      title: doc.name.trim() || "untitled-scenario",
      description: "",
      seed: 0,
      created_at: makeTimestamp(doc.savedAt),
      authoring_version: "editor-ui",
    },
    map: {
      width: doc.canvas.width,
      height: doc.canvas.height,
      grid_resolution: 20,
      unit_scale_meters: 1,
      origin: { x: 0, y: 0 },
      layers: [{ id: "base", name: "Base", visible: true }],
    },
    entities,
    obstacles,
    demand_zones,
    traffic_classes: [],
    scheduled_traffic: [],
    chaos_events: [],
  };
}

export function scenarioSourceToEditorDocument(
  scenario: ScenarioSource
): EditorDocument {
  const objects: EditorDocument["objects"] = [];

  for (const entity of scenario.entities) {
    switch (entity.type) {
      case "drone":
        objects.push({
          id: entity.id,
          type: "drone",
          x: entity.position.x,
          y: entity.position.y,
          label: entity.label ?? "Drone",
          radioRange: entity.comms_range_m,
          battery: Number(findTagValue(entity.tags, "editor:battery_pct=")) || entity.battery_capacity_mah,
        });
        break;

      case "gateway":
        objects.push({
          id: entity.id,
          type: "gateway",
          x: entity.position.x,
          y: entity.position.y,
          label: entity.label ?? "Gateway",
          uplink: findTagValue(entity.tags, "editor:uplink=") ?? "fiber",
        });
        break;

      case "client":
        objects.push({
          id: entity.id,
          type: "client",
          x: entity.position.x,
          y: entity.position.y,
          label: entity.label ?? "Client",
          demandClass: entity.demand_profile,
        });
        break;
    }
  }

  for (const obstacle of scenario.obstacles) {
    if (obstacle.shape === "rect" && obstacle.type === "building") {
      objects.push({
        id: obstacle.id,
        type: "building",
        x: obstacle.position.x,
        y: obstacle.position.y,
        label: obstacle.label ?? "Building",
        width: obstacle.size.width,
        height: obstacle.size.height,
        attenuation: obstacle.attenuation_db,
      });
      continue;
    }

    if (obstacle.shape === "segment" && obstacle.type === "wall") {
      const dx = obstacle.end.x - obstacle.start.x;
      const dy = obstacle.end.y - obstacle.start.y;
      objects.push({
        id: obstacle.id,
        type: "wall",
        x: (obstacle.start.x + obstacle.end.x) / 2,
        y: (obstacle.start.y + obstacle.end.y) / 2,
        label: obstacle.label ?? "Wall",
        length: Math.sqrt(dx * dx + dy * dy),
        attenuation: obstacle.attenuation_db,
      });
      continue;
    }

    if (obstacle.shape === "circle" && obstacle.type === "vegetation") {
      objects.push({
        id: obstacle.id,
        type: "tree-zone",
        x: obstacle.center.x,
        y: obstacle.center.y,
        label: obstacle.label ?? "Tree Zone",
        radius: obstacle.radius,
        attenuation: obstacle.attenuation_db,
      });
    }
  }

  for (const zone of scenario.demand_zones) {
    objects.push({
      id: zone.id,
      type: "demand-zone",
      x: zone.center.x,
      y: zone.center.y,
      label: zone.label ?? "Demand Zone",
      radius: zone.radius_m,
      intensity: zone.priority,
    });
  }

  const empty = createEmptyEditorDocument();

  return {
    version: 1,
    name: scenario.metadata.title || "untitled-scenario",
    savedAt: null,
    canvas: {
      width: scenario.map.width,
      height: scenario.map.height,
    },
    objects,
    view: {
      ...empty.view,
    },
  };
}
