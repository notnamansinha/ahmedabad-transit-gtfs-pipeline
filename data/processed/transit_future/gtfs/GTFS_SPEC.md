# GTFS Export Specification

Convert the Ahmedabad transit dataset into a standards-compliant GTFS (General Transit Feed Specification) static feed.
A valid GTFS feed enables direct import into Google Maps, Apple Maps, OpenTripPlanner, OSRM, and Navitia.

---

## Files Required (GTFS Static)

| File | Status | Notes |
|---|---|---|
| `agency.txt` | ⬜ To create | 3 rows: BRT (BRT_System), MUNICIPAL_BUS, METRO Metro |
| `stops.txt` | ✅ Ready | Map from `stops.csv` — stop_id, stop_name, stop_lat, stop_lon |
| `routes.txt` | ✅ Ready | Map from `routes.csv` — route_id, agency_id, route_short_name, route_type |
| `trips.txt` | ⬜ Partial | Derive from route timetables; requires headway data per route |
| `stop_times.txt` | ⬜ Blocked | Requires per-stop arrival times (currently only terminal times available) |
| `calendar.txt` | ⬜ To create | Mon–Sat / Sun service patterns — check BRT/MUNICIPAL_BUS schedule |
| `fare_attributes.txt` | ✅ Ready | Derive from `fares.csv` |
| `fare_rules.txt` | ✅ Ready | Derive from `fares.csv` origin/destination pairs |
| `shapes.txt` | ✅ Ready | Convert route GeoJSON LineString coordinates → GTFS shape_pt_lat/lon |
| `frequencies.txt` | ⬜ Blocked | Requires headway data per route (see `headways/HEADWAY_SPEC.md`) |
| `transfers.txt` | ✅ Ready | Derive from `transfer_edges.json` — min_transfer_time in seconds |

---

## Mapping: stops.csv → stops.txt

```
stop_id       = stop_id
stop_name     = name
stop_lat      = lat
stop_lon      = lon
location_type = 0 (stop/platform)
```

## Mapping: fares.csv → fare_attributes.txt + fare_rules.txt

```
fare_id       = "{agency}-{from_stop_id}-{to_stop_id}"
price         = fare_inr
currency_type = INR
payment_method = 0 (on board)
transfers     = 0
```

---

## Immediate Blockers

1. **`stop_times.txt`** — The pipeline currently stores only terminal departure times, not intermediate stop arrival times. This is the single most valuable gap to close. Options:
   - Use `segment_times.csv` median travel times to linearly estimate intermediate arrivals.
   - Scrape BRT AVLS API for historical stop-level arrival timestamps.

2. **`frequencies.txt`** — Headway data (minutes between consecutive departures) is missing for MUNICIPAL_BUS routes and partial for BRT. See `headways/HEADWAY_SPEC.md`.

---

## Validation Tool

Use `gtfstidy` or `gtfs-validator` (Google) to validate the feed before submission:

```bash
# Install
pip install gtfs_kit

# Validate
python -c "import gtfs_kit; feed = gtfs_kit.read_feed('output/gtfs/', dist_units='km'); feed.validate()"
```

---

*Last updated: May 2026*
