# Nakshatra Nav — Transit Integration Package

**Drop this `transit/` folder directly into your Nakshatra Nav repository.**
It contains every data file and TypeScript module needed to power the multi-modal trip planner across Metro, BRT, and MUNICIPAL_BUS.

---

## Quick Answer: Is Everything Here?

| Feature Required | Status | File(s) |
|---|---|---|
| MUNICIPAL_BUS stops + coordinates | ✅ **4,774 stops** | `data/stops.csv` |
| MUNICIPAL_BUS route sequences (intermediate stops) | ✅ **772 routes, 34,927 entries** | `data/route_stops.csv` |
| MUNICIPAL_BUS fares | ✅ **11,273 O-D pairs** | `data/fares.csv` |
| BRT stops + coordinates | ✅ **584 stops** | `data/stops.csv` |
| BRT route sequences (intermediate stops) | ✅ **106/109 routes, 2,293 entries** | `data/route_stops.csv` |
| BRT fares | ✅ **36,672 O-D pairs** | `data/fares.csv` |
| Metro stations + coordinates | ✅ **53 stations** | `data/stops.csv` |
| Metro line sequences (Blue, Red, Violet + branch) | ✅ **4 lines, 55 station-entries** | `data/route_stops.csv` |
| Metro fares (METRO slab tariff) | ✅ **950 O-D pairs** | `data/fares.csv` |
| Median inter-stop travel times | ✅ **7,842 segments** (BRT+MUNICIPAL_BUS+Metro) | `data/segment_times.csv` |
| Interchange nodes (Metro ↔ BRT ↔ MUNICIPAL_BUS) | ✅ **39 hubs** | `data/interchange_nodes.json` |
| Transfer-walk edges (spatial ≤ 500 m) | ✅ **14,788 edges** | `data/transfer_edges.json` |
| GeoJSON route polylines (for map rendering) | ✅ | `data/routes.geojson` |
| GeoJSON stop markers (for map rendering) | ✅ | `data/stops.geojson` |
| Multi-modal Dijkstra router (TypeScript) | ✅ | `router/` |
| First/last-mile walk injection | ✅ | `router/router.ts` |
| Physical transfer instructions (8 key hubs) | ✅ | `router/itinerary.ts` |

**Known gaps (minor):**
- 3 BRT routes missing intermediate stop sequences (`brt-4E-AB`, `brt-14U-SO`, `brt-15E-AS`) — terminal stops only
- 199 MUNICIPAL_BUS stops have missing/unverified GPS coordinates (geocoded from stop name; may be imprecise for some peripheral routes)

---

## Folder Structure

```
transit/
├── README.md                    ← You are here
│
├── data/                        ← All source data
│   ├── stops.csv                   5,411 stops across BRT (584), MUNICIPAL_BUS (4,774), Metro (53)
│   ├── stops.geojson               GeoJSON Point features for map markers
│   ├── routes.csv                  885 routes: BRT (109), MUNICIPAL_BUS (772), Metro (4 lines)
│   ├── routes.geojson              GeoJSON LineString polylines for map rendering
│   ├── route_stops.csv             37,275 ordered stop-sequence entries (intermediate stops)
│   ├── segment_times.csv           7,842 median inter-stop travel times (minutes)
│   ├── fares.csv                   48,895 origin-destination fare pairs (₹)
│   ├── interchange_nodes.json      39 Metro-anchored interchange hubs
│   └── transfer_edges.json         14,788 bidirectional walk transfer edges
│
└── router/                      ← TypeScript multi-modal router
    ├── index.ts                    Public barrel — single import point
    ├── types.ts                    All TypeScript type definitions
    ├── graph.ts                    Unified graph builder (in-vehicle + transfer edges)
    ├── dijkstra.ts                 Binary-min-heap Dijkstra pathfinder
    ├── itinerary.ts                Leg merger + physical transfer walk instructions
    └── router.ts                   TransitRouter class (main entry point)
```

---

## Installation

```bash
# No npm packages needed — uses only TypeScript types + your project's existing loader

# Copy the transit/ folder into your project
cp -r transit/ path/to/nakshatra-nav/src/transit/
```

---

## Usage

### 1. Load Data (Node.js / Next.js API route)

```typescript
import fs from "fs";
import path from "path";
import { parse } from "csv-parse/sync"; // npm i csv-parse

function loadCSV(filename: string) {
  const raw = fs.readFileSync(path.join(process.cwd(), "src/transit/data", filename), "utf-8");
  return parse(raw, { columns: true, skip_empty_lines: true });
}

const stops          = loadCSV("stops.csv");
const routeStops     = loadCSV("route_stops.csv");
const segmentTimes   = loadCSV("segment_times.csv");
const fares          = loadCSV("fares.csv");
import transferEdges from "../transit/data/transfer_edges.json";
```

### 2. Initialize the Router (singleton — do once at startup)

```typescript
import { TransitRouter } from "@/transit/router";

const router = new TransitRouter(
  stops.map(s => ({
    stop_id: s.stop_id,
    agency:  s.agency,
    name:    s.name,
    lat:     parseFloat(s.lat),
    lon:     parseFloat(s.lon),
  })),
  routeStops.map(r => ({
    route_id:      r.route_id,
    stop_id:       r.stop_id,
    stop_sequence: parseInt(r.sequence),
    agency: r.route_id.startsWith("metro") ? "metro"
          : r.route_id.startsWith("brt")  ? "brt"  : "municipal_bus",
  })),
  segmentTimes.map(s => ({
    agency:          s.agency,
    from_stop_id:    s.from_stop_id,
    to_stop_id:      s.to_stop_id,
    median_minutes:  parseFloat(s.median_minutes),
  })),
  transferEdges,
  fares.map(f => ({
    agency:      f.agency,
    from_stop_id: f.from_stop_id,
    to_stop_id:   f.to_stop_id,
    fare_inr:    parseFloat(f.fare_inr),
  })),
);
```

### 3. Route by Stop ID

```typescript
const result = router.route("brt-6871", "metro-blue-12");
// result.itinerary.legs → array of ItineraryLeg
// result.itinerary.total_duration_mins → number
// result.itinerary.total_fare_inr → number
```

### 4. Route by GPS Coordinates (auto-snaps to nearest stops)

```typescript
const result = router.route(
  { lat: 23.0301, lon: 72.4690 },   // Bopal (no stop ID needed)
  { lat: 23.0035, lon: 72.6477 },   // Vastral
);

if (result.itinerary) {
  for (const leg of result.itinerary.legs) {
    if (leg.mode === "WALK") {
      console.log(`WALK: ${leg.instruction}`);
    } else {
      console.log(`${leg.mode}: ${leg.from_stop_name} → ${leg.to_stop_name}  (${leg.duration_mins} min, ₹${leg.fare_inr ?? 0})`);
    }
  }
  console.log(`Total: ${result.itinerary.total_duration_mins} min | ₹${result.itinerary.total_fare_inr} | ${result.itinerary.transfers} transfer(s)`);
}
```

**Example output (Bopal → Vastral):**
```
WALK: Walk 4 min to Bopal BRT stop.
BRT: Bopal → Shivranjani  (22 min, ₹15)
WALK: Walk 3 min to Commerce Six Road Metro.
METRO: Commerce Six Road → Vastral  (8 min, ₹10)
──────────────────────────────────────────────────
Total: 37 min  |  ₹25  |  1 transfer
```

### 5. Find Nearby Stops

```typescript
const nearby = router.nearbyStops(23.0301, 72.4690, 500); // within 500m
// Returns Stop[] sorted by distance, each with .dist_m property
```

---

## Data Schemas

### stops.csv

| Column | Type | Description |
|---|---|---|
| `stop_id` | string | Unique ID (e.g. `brt-6871`, `metro-blue-07`, `municipal_bus-12345`) |
| `agency` | `brt` / `municipal_bus` / `metro` | Operator |
| `name` | string | Official stop name |
| `lat` | float | WGS-84 latitude |
| `lon` | float | WGS-84 longitude |
| `stop_type` | string | BRT / MUNICIPAL_BUS / Metro |
| `interchange_group_id` | string | Interchange hub ID if applicable |

### route_stops.csv

| Column | Type | Description |
|---|---|---|
| `route_id` | string | e.g. `brt-1D`, `municipal_bus-136`, `metro-line-blue` |
| `sequence` | int | 1-indexed stop order along the route |
| `stop_id` | string | References `stops.csv` |
| `stop_name` | string | Display name |
| `median_minutes_to_next` | float | Travel time to the next stop (blank for terminal) |

### fares.csv

| Column | Type | Description |
|---|---|---|
| `agency` | string | `brt` / `municipal_bus` / `metro` |
| `from_stop_id` | string | Origin stop |
| `to_stop_id` | string | Destination stop |
| `fare_inr` | float | Fare in Indian Rupees |

**Fare structures:**
- **Metro (METRO):** Slab-based — 0–3 stops ₹5, 4–7 ₹10, 8–11 ₹15, 12–15 ₹20, 16+ ₹25
- **BRT (BRT_System):** Distance-based Haversine slab — ₹5 to ₹30
- **MUNICIPAL_BUS:** Stage-based — ₹5 to ₹18

### transfer_edges.json

```json
{
  "from_id": "brt-7821",
  "to_id": "metro-blue-07",
  "type": "transfer-walk",
  "weight_secs": 240,
  "dist_m": 120,
  "walk_mins": 1.7
}
```

### interchange_nodes.json

```json
{
  "hub_id": "ix-kalupur",
  "name": "Kalupur Railway Station",
  "metro_stops": ["metro-blue-07"],
  "brt_stops": ["brt-kl"],
  "municipal_bus_stops": ["municipal_bus-1234", "municipal_bus-5678"],
  "walk_instruction": "Exit Metro via Gate 1. Walk 120m through underground concourse."
}
```

---

## Metro Lines Reference

| Line | From | To | Stations | Interchange |
|---|---|---|---|---|
| **Blue** | Vastral Gam | Thaltej Gam | 18 | Old High Court (Red Line) |
| **Red** | APMC | Motera Stadium | 14 | Old High Court (Blue Line), Usmanpura |
| **Violet** | Koteshwar Road | Mahatama Mandir | 20 | GNLU (branch split) |
| **Violet Branch** | GNLU | Gift City | 3 | — |

**Metro-BRT key interchanges (physical):**

| Metro Station | Nearest BRT Stop | Walk Time | Notes |
|---|---|---|---|
| Kalupur | Kalupur ST Stand | ~2 min | Underground concourse |
| Ranip | Ranip BRT | ~1 min | Road level |
| Sabarmati | Sabarmati BRT | ~3 min | Railway station forecourt |
| Apparel Park | Apparel Park BRT | ~1 min | Adjacent |
| Gheekanta | Gheekanta BRT | ~2 min | Cross road |
| Old High Court | SP Stadium BRT | ~4 min | Street level |
| Thaltej Gam | Thaltej BRT | ~3 min | Foot overbridge |

---

## Router Options

```typescript
interface RouterOptions {
  maxTransfers?: number;    // default 3
  maxWalkMins?: number;     // default 15 — max walk for first/last mile snap
  arrivalTime?: Date;       // reserved for future time-aware routing
}

router.route(from, to, { maxTransfers: 2, maxWalkMins: 10 });
```

---

## TypeScript Types Quick Reference

```typescript
import type {
  Stop, AgencyId, RouteStop, SegmentTime, FareEntry,
  GraphEdge, Itinerary, ItineraryLeg, LegMode, RouterOptions,
} from "@/transit/router";
```

---

## What's in transit_future/

See `../transit_future/README.md` for Phase 2 modules:
- **`db/transit.db`** — 19 MB SQLite mirror for server-side caching
- **`gtfs/`** — GTFS export spec (Google Maps / OTP compatibility)
- **`realtime/`** — BRT AVLS + Metro live feed integration plan
- **`headways/`** — Per-route frequency data collection spec

---

*Dataset: Ahmedabad Transit DataSync pipeline — May 2026*
*Coverage: BRT (BRT_System), MUNICIPAL_BUS, METRO Metro (Blue, Red, Violet lines)*
