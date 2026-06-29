/**
 * itinerary.ts
 * Converts a raw Dijkstra edge path into a structured, human-readable
 * multi-modal itinerary with transfer instructions and fare totals.
 *
 * Output format:
 *   [BRT: Bopal → Shivranjani]
 *   [Transfer: Walk 3 min via underpass]
 *   [Metro: Commerce Six Road → Vastral]
 */

import type { GraphEdge, TransitGraph } from "./graph";
import type { Itinerary, ItineraryLeg, LegMode, AgencyId, FareEntry } from "./types";

// ── Manual transfer instructions for known physical interchanges ───────────────
// Keyed by "from_stop_id|to_stop_id"
const TRANSFER_INSTRUCTIONS: Record<string, string> = {
  // Metro Blue ↔ Red interchange at Old High Court
  "metro-blue-10|metro-red-24":
    "At Old High Court: ascend to concourse level, follow Red Line signs, descend to Platform 2.",
  "metro-red-24|metro-blue-10":
    "At Old High Court: ascend to concourse level, follow Blue Line signs, descend to Platform 1.",

  // Kalupur — underground concourse to street level BRT
  "metro-blue-07|brt-kl":
    "Exit Metro via Gate 1 (Railway Station side). Walk 120 m through the underground concourse to Kalupur BRT shelter.",
  "brt-kl|metro-blue-07":
    "Enter Kalupur Metro station from the underground concourse (main entry from ST Stand side). Platform is one level down.",

  // Ranip — surface level, short walk
  "metro-red-27|brt-rn":
    "Exit Metro north side. Walk 80 m along Sarkhej–Gandhinagar Highway to the Ranip BRT shelter.",
  "brt-rn|metro-red-27":
    "From Ranip BRT shelter, walk south 80 m to the Metro station entry.",

  // Sabarmati Railway Station — large multi-modal hub
  "metro-red-28|brt-sb":
    "Exit Metro east side. Walk 200 m through the railway station forecourt to the Sabarmati BRT stop.",
  "brt-sb|metro-red-28":
    "From Sabarmati BRT stop, walk 200 m west through railway station forecourt to the Metro station.",

  // Apparel Park — both at road level
  "metro-blue-05|brt-ap":
    "Exit Metro south side. Apparel Park BRT shelter is directly adjacent, 60 m walk.",
  "brt-ap|metro-blue-05":
    "From Apparel Park BRT shelter, walk north 60 m to the Metro station entry.",

  // Gheekanta
  "metro-blue-08|brt-gh":
    "Exit Metro east side. Gheekanta BRT shelter is 150 m along the main road (cross at signal).",

  // Thaltej Gam
  "metro-blue-17|brt-th":
    "Exit Metro north side. Walk 250 m to the Thaltej Gam BRT shelter via the foot overbridge.",
};

// ── Agency → LegMode mapping ──────────────────────────────────────────────────
function agencyToLegMode(agency?: AgencyId): LegMode {
  switch (agency) {
    case "metro": return "METRO";
    case "brt":  return "BRT";
    case "municipal_bus":  return "MUNICIPAL_BUS";
    default:      return "WALK";
  }
}

// ── Build a FareEntry lookup map ──────────────────────────────────────────────
export function buildFareMap(fares: FareEntry[]): Map<string, number> {
  const map = new Map<string, number>();
  for (const f of fares) {
    map.set(`${f.from_stop_id}|${f.to_stop_id}`, f.fare_inr);
  }
  return map;
}

/**
 * Convert a Dijkstra edge path into a structured itinerary.
 * Consecutive in-vehicle edges on the same route are merged into a single leg.
 */
export function buildItinerary(
  path: GraphEdge[],
  graph: TransitGraph,
  fareMap: Map<string, number>,
): Itinerary {
  if (path.length === 0) {
    return { legs: [], total_duration_mins: 0, total_fare_inr: 0, transfers: 0 };
  }

  const legs: ItineraryLeg[] = [];
  let i = 0;

  while (i < path.length) {
    const edge = path[i];

    if (edge.type === "in-vehicle") {
      // Merge consecutive in-vehicle edges on the same route into one leg
      const routeId = edge.route_id;
      const agency = edge.agency!;
      const mode = agencyToLegMode(agency);
      const boardStop = edge.from_id;
      let alightStop = edge.to_id;
      let totalSecs = edge.weight_secs;

      while (
        i + 1 < path.length &&
        path[i + 1].type === "in-vehicle" &&
        path[i + 1].route_id === routeId
      ) {
        i++;
        alightStop = path[i].to_id;
        totalSecs += path[i].weight_secs;
      }

      const fareKey = `${boardStop}|${alightStop}`;
      const fare = fareMap.get(fareKey);

      legs.push({
        mode,
        agency,
        route_id: routeId,
        from_stop_id: boardStop,
        from_stop_name: graph.stops.get(boardStop)?.name ?? boardStop,
        to_stop_id: alightStop,
        to_stop_name: graph.stops.get(alightStop)?.name ?? alightStop,
        duration_mins: parseFloat((totalSecs / 60).toFixed(1)),
        fare_inr: fare,
      });
    } else if (edge.type === "transfer-walk") {
      const instrKey = `${edge.from_id}|${edge.to_id}`;
      const instruction = TRANSFER_INSTRUCTIONS[instrKey];
      const fromStop = graph.stops.get(edge.from_id);
      const toStop = graph.stops.get(edge.to_id);

      legs.push({
        mode: "WALK",
        from_stop_id: edge.from_id,
        from_stop_name: fromStop?.name ?? edge.from_id,
        to_stop_id: edge.to_id,
        to_stop_name: toStop?.name ?? edge.to_id,
        duration_mins: parseFloat(((edge.walk_mins ?? edge.weight_secs / 60)).toFixed(1)),
        dist_m: edge.dist_m,
        instruction:
          instruction ??
          `Walk ~${Math.ceil((edge.walk_mins ?? edge.weight_secs / 60))} min to ${toStop?.name ?? edge.to_id}.`,
      });
    } else if (edge.type === "first-mile-walk" || edge.type === "last-mile-walk") {
      const fromStop = graph.stops.get(edge.from_id);
      const toStop = graph.stops.get(edge.to_id);
      legs.push({
        mode: "WALK",
        from_stop_id: edge.from_id,
        from_stop_name: fromStop?.name ?? edge.from_id,
        to_stop_id: edge.to_id,
        to_stop_name: toStop?.name ?? edge.to_id,
        duration_mins: parseFloat((edge.weight_secs / 60).toFixed(1)),
        dist_m: edge.dist_m,
        instruction: edge.type === "first-mile-walk"
          ? `Walk ${Math.ceil(edge.weight_secs / 60)} min to the nearest stop.`
          : `Walk ${Math.ceil(edge.weight_secs / 60)} min to your destination.`,
      });
    }

    i++;
  }

  const total_duration_mins = parseFloat(
    (legs.reduce((sum, l) => sum + l.duration_mins, 0)).toFixed(1)
  );
  const total_fare_inr = legs.reduce((sum, l) => sum + (l.fare_inr ?? 0), 0);
  const transfers = legs.filter((l) => l.mode === "WALK").length;

  return { legs, total_duration_mins, total_fare_inr, transfers };
}

/**
 * Format an itinerary as a human-readable text summary.
 * Useful for debugging or simple display.
 *
 * Example output:
 *   [BRT] Bopal → Shivranjani  (12 min, ₹15)
 *   [WALK] Transfer: Walk 3 min to Commerce Six Road Metro
 *   [METRO] Commerce Six Road → Vastral  (8 min, ₹10)
 *   ─────────────────────────────────────
 *   Total: 23 min  |  ₹25  |  1 transfer
 */
export function formatItinerary(itin: Itinerary): string {
  const lines: string[] = [];
  for (const leg of itin.legs) {
    const fareStr = leg.fare_inr !== undefined ? `  ₹${leg.fare_inr}` : "";
    if (leg.mode === "WALK") {
      lines.push(`  [WALK] ${leg.instruction ?? `Walk ${leg.duration_mins} min`}`);
    } else {
      lines.push(
        `  [${leg.mode}] ${leg.from_stop_name} → ${leg.to_stop_name}  (${leg.duration_mins} min${fareStr})`
      );
    }
  }
  lines.push("  " + "─".repeat(50));
  lines.push(
    `  Total: ${itin.total_duration_mins} min  |  ₹${itin.total_fare_inr}  |  ${itin.transfers} transfer(s)`
  );
  return lines.join("\n");
}
