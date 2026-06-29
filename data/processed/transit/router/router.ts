/**
 * router.ts
 * The main entry point for the Nakshatra Nav multi-modal transit router.
 *
 * Responsibilities:
 *   1. Accept an origin & destination (either stop_id or {lat, lon})
 *   2. Inject first-mile and last-mile walk edges to the nearest stops
 *   3. Run Dijkstra on the unified graph
 *   4. Convert the result into a structured Itinerary
 *
 * Usage:
 *   import { TransitRouter } from "./router";
 *   import stopsData from "../data/stops.json";
 *   import routeStopsData from "../data/route_stops.json";
 *   import segmentTimesData from "../data/segment_times.json";
 *   import transferEdgesData from "../data/transfer_edges.json";
 *   import faresData from "../data/fares.json";
 *
 *   const router = new TransitRouter(stopsData, routeStopsData, segmentTimesData, transferEdgesData, faresData);
 *   const result = router.route({ lat: 23.030, lon: 72.508 }, { lat: 23.003, lon: 72.668 });
 *   console.log(result);
 */

import { buildGraph, haversine, type TransitGraph } from "./graph";
import { dijkstra } from "./dijkstra";
import { buildItinerary, buildFareMap, formatItinerary } from "./itinerary";
import type {
  Stop,
  RouteStop,
  SegmentTime,
  GraphEdge,
  FareEntry,
  Itinerary,
  RouterOptions,
} from "./types";

const WALK_SPEED_MPS = 1.2;          // 1.2 m/s walking speed
const MAX_SNAP_DIST_M = 800;         // Max distance to snap a coordinate to a stop
const VIRTUAL_ORIGIN_ID = "__ORIGIN__";
const VIRTUAL_DEST_ID   = "__DEST__";

export type Location = string | { lat: number; lon: number };

export interface RouteResult {
  itinerary: Itinerary | null;
  error?: string;
}

export class TransitRouter {
  private graph: TransitGraph;
  private fareMap: Map<string, number>;
  private stops: Stop[];

  constructor(
    stops: Stop[],
    routeStops: RouteStop[],
    segmentTimes: SegmentTime[],
    transferEdges: GraphEdge[],
    fares: FareEntry[],
  ) {
    this.stops = stops;
    this.graph = buildGraph(stops, routeStops, segmentTimes, transferEdges);
    this.fareMap = buildFareMap(fares);
  }

  /**
   * Main routing function.
   * @param from  stop_id string OR {lat, lon} coordinate
   * @param to    stop_id string OR {lat, lon} coordinate
   * @param opts  optional routing settings
   */
  route(from: Location, to: Location, opts: RouterOptions = {}): RouteResult {
    const { maxWalkMins = 15 } = opts;
    const maxWalkM = maxWalkMins * 60 * WALK_SPEED_MPS;

    // Resolve origin
    const originId = this._resolveStopId(from, VIRTUAL_ORIGIN_ID, maxWalkM, "first-mile-walk");
    if (!originId) {
      return { itinerary: null, error: "No stop found within walking distance of origin." };
    }

    // Resolve destination
    const destId = this._resolveStopId(to, VIRTUAL_DEST_ID, maxWalkM, "last-mile-walk");
    if (!destId) {
      return { itinerary: null, error: "No stop found within walking distance of destination." };
    }

    // Run Dijkstra
    const result = dijkstra(this.graph, originId, destId);

    if (!result.found) {
      return { itinerary: null, error: "No route found between the given locations." };
    }

    const itinerary = buildItinerary(result.path, this.graph, this.fareMap);
    return { itinerary };
  }

  /**
   * Returns the formatted string of the best route between two points.
   * Convenience wrapper around route().
   */
  routeFormatted(from: Location, to: Location, opts?: RouterOptions): string {
    const result = this.route(from, to, opts);
    if (!result.itinerary) return `Error: ${result.error}`;
    return formatItinerary(result.itinerary);
  }

  /**
   * Find all stops within `maxDistM` of a coordinate, sorted by distance.
   */
  nearbyStops(lat: number, lon: number, maxDistM = 500): Array<Stop & { dist_m: number }> {
    return this.stops
      .map((s) => ({ ...s, dist_m: haversine(lat, lon, s.lat, s.lon) }))
      .filter((s) => s.dist_m <= maxDistM)
      .sort((a, b) => a.dist_m - b.dist_m);
  }

  // ── Private helpers ──────────────────────────────────────────────────────────

  /**
   * Resolves a Location to a stop_id.
   * - If already a stop_id string, returns it directly.
   * - If a coordinate, finds the K-nearest stops and injects virtual walk edges.
   * Returns the virtual node ID (for coord input) or the stop_id directly.
   */
  private _resolveStopId(
    location: Location,
    virtualId: string,
    maxWalkM: number,
    edgeType: "first-mile-walk" | "last-mile-walk",
  ): string | null {
    if (typeof location === "string") {
      // Already a stop ID — verify it exists
      return this.graph.stops.has(location) ? location : null;
    }

    const { lat, lon } = location;
    const nearby = this.nearbyStops(lat, lon, maxWalkM);
    if (nearby.length === 0) return null;

    // Create a virtual node and inject walk edges
    if (!this.graph.adjacency.has(virtualId)) {
      this.graph.adjacency.set(virtualId, []);
    }

    const virtualStop: Stop = {
      stop_id: virtualId,
      agency: "brt", // placeholder
      name: edgeType === "first-mile-walk" ? "Your Location" : "Your Destination",
      lat,
      lon,
    };
    this.graph.stops.set(virtualId, virtualStop);

    // Take the nearest N stops (avoid exploding the graph)
    const candidates = nearby.slice(0, 5);
    for (const stop of candidates) {
      const walkSecs = Math.round(stop.dist_m / WALK_SPEED_MPS);
      const edge: GraphEdge = {
        from_id: virtualId,
        to_id: stop.stop_id,
        type: edgeType,
        weight_secs: walkSecs,
        dist_m: Math.round(stop.dist_m),
      };
      // For last-mile, reverse direction: nearest stop → virtual dest
      if (edgeType === "last-mile-walk") {
        const bucket = this.graph.adjacency.get(stop.stop_id) ?? [];
        bucket.push({ ...edge, from_id: stop.stop_id, to_id: virtualId });
        this.graph.adjacency.set(stop.stop_id, bucket);
      } else {
        const bucket = this.graph.adjacency.get(virtualId)!;
        bucket.push(edge);
      }
    }

    return virtualId;
  }
}
