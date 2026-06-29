# Headway / Frequency Data Collection Specification

Headway = the time between consecutive departures of the same route from the same stop.
This is the single most impactful missing data element. It directly controls how long a passenger waits at an interchange, which is often 30–50% of total journey time.

---

## Current State

| Mode | Headway Data | Used By Router |
|---|---|---|
| Metro | ✅ Published (8 min peak / 12 min off-peak) | ✅ Static average used in `graph.ts` |
| BRT | ⬜ Terminal departure times only | ⚠️ Using 10 min average — inaccurate for low-frequency routes |
| MUNICIPAL_BUS | ⬜ No data | ⚠️ Using 20 min average — very rough estimate |

---

## Data Schema (Target)

For each route-direction pair, collect:

```json
{
  "route_id": "brt-1D",
  "direction": 0,
  "terminal_stop_id": "brt-ghuma",
  "peak_headway_mins": 7,
  "offpeak_headway_mins": 12,
  "first_departure": "06:00:00",
  "last_departure": "22:45:00",
  "service_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
  "sunday_headway_mins": 15,
  "source": "brt_system_timetable_2025"
}
```

---

## Collection Sources — Priority Order

### 1. BRT (BRT_System)

| Source | Method | Coverage |
|---|---|---|
| BRT_System official website timetables (PDF) | Download + PDF parse | All routes — ~161 routes |
| AVLS departure log scraping | Observe actual departure times over 1 week | All routes (high accuracy) |
| TransitAPI AVLS `/api/schedule/{route_id}` | REST API call | Routes with published schedule |

**Recommended approach:** Run the AVLS scraper for 5 weekdays (Mon–Fri) during peak (07:00–10:00) and off-peak (14:00–16:00). Compute median inter-departure interval per route. This produces empirical headways that are more accurate than published timetables.

### 2. MUNICIPAL_BUS

| Source | Method | Coverage |
|---|---|---|
| MUNICIPAL_BUS official website (`municipal-bus.local`) | Web scrape route pages | ~200–300 routes with published data |
| MUNICIPAL_BUS Lal Darwaza HQ | Request printed timetable booklets | All 742 routes |
| MoHUA Open Transit Data (`data.gov.in`) | Download GTFS if published | Unknown coverage |

**Recommended approach:** Scrape `municipal-bus.local` first (quick win). Then send an RTI request to MUNICIPAL_BUS for electronic timetable data.

### 3. Metro

Metro headways are already published by METRO:
- **Peak (07:00–10:00, 17:00–21:00):** 8 minutes
- **Off-peak:** 12 minutes
- **Late night (after 21:00):** 15 minutes

Update `graph.ts` `AVG_HEADWAY_MINS` to use time-of-day aware values once arrival time routing is implemented.

---

## Impact on Router

Once headway data is collected, update `graph.ts`:

```typescript
// Instead of flat average:
const AVG_HEADWAY_MINS: Record<AgencyId, number> = { metro: 8, brt: 10, municipal_bus: 20 };

// Use per-route headways:
function getHeadway(route_id: string, time: Date): number {
  const hw = headwayMap.get(route_id);
  if (!hw) return 10; // fallback
  const isPeak = isPeakHour(time);
  return isPeak ? hw.peak_headway_mins : hw.offpeak_headway_mins;
}
```

This reduces transfer-wait estimation error from ±5 min to ±1 min on BRT.

---

## Collection Script Skeleton

```python
# scripts/scrape_headways.py
# For each BRT route, observe AVLS departure events over 5 days
# and compute empirical median headways

import requests, statistics, datetime

def fetch_departures(route_id, stop_id, date_str):
    # Poll AVLS departure events for this route/stop on the given date
    ...

def compute_headway(departures):
    gaps = [departures[i+1] - departures[i] for i in range(len(departures)-1)]
    return round(statistics.median([g.total_seconds()/60 for g in gaps]), 1)
```

---

*Last updated: May 2026*
