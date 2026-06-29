/**
 * index.ts
 * Public API barrel — re-exports everything Nakshatra Nav needs to import.
 *
 * In your app:
 *   import { TransitRouter, formatItinerary } from "@/transit/router";
 */

export { TransitRouter } from "./router";
export type { Location, RouteResult } from "./router";
export { buildGraph, haversine } from "./graph";
export { dijkstra } from "./dijkstra";
export { buildItinerary, buildFareMap, formatItinerary } from "./itinerary";
export type {
  Stop,
  AgencyId,
  RouteStop,
  SegmentTime,
  FareEntry,
  GraphEdge,
  EdgeType,
  Itinerary,
  ItineraryLeg,
  LegMode,
  RouterOptions,
} from "./types";
