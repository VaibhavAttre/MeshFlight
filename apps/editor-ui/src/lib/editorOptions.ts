export const GATEWAY_UPLINK_OPTIONS = [
  "fiber",
  "microwave",
  "cellular",
  "satellite",
] as const;

export const DEMAND_CLASS_OPTIONS = [
  "telemetry",
  "video",
  "command",
  "background",
] as const;

export const CHAOS_EVENT_TYPE_OPTIONS = [
  "node_failure",
  "interference_spike",
  "demand_burst",
  "obstacle_appearance",
] as const;

export type GatewayUplink = (typeof GATEWAY_UPLINK_OPTIONS)[number];
export type DemandClass = (typeof DEMAND_CLASS_OPTIONS)[number];
export type ChaosEventTypeOption = (typeof CHAOS_EVENT_TYPE_OPTIONS)[number];

export function normalizeGatewayUplink(value: string): GatewayUplink {
  return GATEWAY_UPLINK_OPTIONS.includes(value as GatewayUplink)
    ? (value as GatewayUplink)
    : "fiber";
}

export function normalizeDemandClass(value: string): DemandClass {
  return DEMAND_CLASS_OPTIONS.includes(value as DemandClass)
    ? (value as DemandClass)
    : "telemetry";
}

export function normalizeChaosEventType(value: string): ChaosEventTypeOption {
  return CHAOS_EVENT_TYPE_OPTIONS.includes(value as ChaosEventTypeOption)
    ? (value as ChaosEventTypeOption)
    : "node_failure";
}

export function getGatewayCapacityMbps(uplink: string) {
  switch (normalizeGatewayUplink(uplink)) {
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

export function getGatewayRange(uplink: string) {
  switch (normalizeGatewayUplink(uplink)) {
    case "satellite":
      return 320;
    case "cellular":
      return 180;
    case "microwave":
      return 240;
    case "fiber":
    default:
      return 260;
  }
}
