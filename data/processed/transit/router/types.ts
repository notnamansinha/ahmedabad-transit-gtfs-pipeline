/**
 * types.ts
 * Core type definitions for the Nakshatra Nav multi-modal transit router.
 */

// ── Stop / Station ───────────────────────────────────────────────────────────

export type AgencyId = "brt" | "municipal_bus" | "metro";

export interface Stop {
  stop_id: string;
  agency: AgencyId;
  name: string;
  lat: number;
  lon: number;
  interchange_group_id?: string;
}

// ── Route / Sequence ─────────────────────────────────────────────────────────

export interface RouteStop {
  route_id: string;
  stop_id: string;
  stop_sequence: number;
  agency: AgencyId;
}

// ── Fares ────────────────────────────────────────────────────────────────────

export interface FareEntry {
  agency: AgencyId;
  from_stop_id: string;
  to_stop_id: string;
  fare_inr: number;
}

// ── Segment Times ─────────────────────────────────────────────────────────────

export interface SegmentTime {
  agency: AgencyId;
  from_stop_id: string;
  to_stop_id: string;
  median_minutes: number;
}

// ── Graph Edges ───────────────────────────────────────────────────────────────

export type EdgeType = "in-vehicle" | "transfer-walk" | "transfer-wait" | "first-mile-walk" | "last-mile-walk";

export interface GraphEdge {
  from_id: string;
  to_id: string;
  type: EdgeType;
  weight_secs: number;       // Dijkstra weight (seconds)
  agency?: AgencyId;
  route_id?: string;
  dist_m?: number;
  walk_mins?: number;
  fare_inr?: number;
}

// ── Itinerary ─────────────────────────────────────────────────────────────────

export type LegMode = "BRT" | "MUNICIPAL_BUS" | "METRO" | "WALK";

export interface ItineraryLeg {
  mode: LegMode;
  agency?: AgencyId;
  route_id?: string;
  from_stop_id: string;
  from_stop_name: string;
  to_stop_id: string;
  to_stop_name: string;
  duration_mins: number;
  fare_inr?: number;
  dist_m?: number;
  instruction?: string;        // e.g. "Walk via Underground passage to Gate 3"
}

export interface Itinerary {
  legs: ItineraryLeg[];
  total_duration_mins: number;
  total_fare_inr: number;
  transfers: number;
}

// ── Router Options ────────────────────────────────────────────────────────────

export interface RouterOptions {
  maxTransfers?: number;       // default 3
  maxWalkMins?: number;        // default 15
  arrivalTime?: Date;          // for time-aware routing (future)
}
