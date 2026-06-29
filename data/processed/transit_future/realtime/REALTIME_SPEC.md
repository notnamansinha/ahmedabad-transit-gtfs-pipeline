# Real-Time Integration Specification

Live arrival data turns Nakshatra Nav from a static trip planner into a real-time commuter assistant.
This document specifies how to integrate live feeds from BRT (BRT_System AVLS) and Metro (METRO).

---

## BRT — BRT_System AVLS REST API

### Known Endpoints (TransitAPI AVLS)
The BRT_System AVLS system exposes a REST API used by the official BRT_System app and previously by the TransitAPI platform.

| Endpoint | Data | Refresh Rate |
|---|---|---|
| `/api/routes` | All route metadata | Static |
| `/api/buses/live` | Real-time bus positions (lat, lon, speed, route_id) | ~30 sec |
| `/api/eta/{stop_id}` | Estimated arrival time for next bus at a stop | ~30 sec |

### Integration Plan
1. **Poll `/api/buses/live`** every 30 seconds.
2. Map bus positions to the nearest stop using Haversine snapping.
3. Inject live ETAs into the router as `transfer-wait` edge weights, replacing static headway/2 estimates.
4. Cache last known position per bus in Redis or a simple in-memory store.

### Data Shape (expected)
```json
{
  "bus_id": "JAN-042",
  "route_id": "brt-1D",
  "lat": 23.0302,
  "lon": 72.5640,
  "speed_kmh": 18,
  "next_stop_id": "brt-7821",
  "eta_secs": 145
}
```

---

## Metro — METRO GTFS-RT

METRO does not currently publish a public GTFS-RT feed. Two options:

### Option A: METRO Mobile App API (reverse-engineered)
- The METRO mobile app likely polls an internal REST endpoint for train positions.
- Requires network inspection via a proxy (e.g., Charles Proxy / mitmproxy) to map the API surface.

### Option B: Timetable-Based Simulation
Until a live feed is available, simulate Metro real-time ETAs using:
1. Published headways: ~8 min peak, ~12 min off-peak (from METRO timetable).
2. Given the current time, compute expected departure from origin: `next_departure = ceil(now / headway) * headway`.
3. Add accumulated segment times from `segment_times.csv` to project arrival.

This gives ±2 min accuracy — acceptable for Metro given its high reliability.

---

## Integration Points in the Router

In `router.ts`, the `RouterOptions` interface already has an `arrivalTime` field for time-aware routing.
The real-time module should:
1. Maintain a `LiveFeedCache` singleton.
2. Override `AVG_HEADWAY_MINS` in `graph.ts` with real-time wait times when available.
3. Expose a `router.routeRealtime(from, to)` method that triggers a fresh graph rebuild with live weights.

---

## Phase 4 MUNICIPAL_BUS

MUNICIPAL_BUS does not currently publish any vehicle positioning system (VPS) data.
When/if MUNICIPAL_BUS deploys GPS tracking (expected as part of Smart City Mission Phase 2), integrate via the same AVLS pattern as BRT.

---

*Last updated: May 2026*
