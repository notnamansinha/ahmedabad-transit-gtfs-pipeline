# Sources & Verification Model

Every field in the processed data output has a documented source and verification path. This file is the audit trail.

## 1. Primary sources

### Bus Rapid Transit (BRT) — Municipal Transit API

- **Access:** OAuth2 password grant. Credentials must be provided via the `TRANSIT_API_USER` and `TRANSIT_API_PASS` environment variables.
- **Token TTL:** ~3 days. The scraper refreshes every 2 hours.
- **Endpoints used:**
  - `/token`: POST to acquire access token.
  - `/api/RouteTimeTable`: GET route metadata (code, times, days).
  - `/api/FareMatrix/DistinctStops`: GET all stops and coordinates.
  - `/api/FareMatrix/GetAllFare`: GET fare matrix.
  - `/api/FareMatrix/StopsOnRoute`: GET ordered stops on a route + WKT LineString.

### Municipal Bus Service — Municipal Transit API

- Uses the same infrastructure as the BRT system.
- Credentials and token flows are identical.

### City Metro — Official Site

- **Pages scraped:** Route lists and fare rules are extracted directly from the public HTML pages.
- **Coordinates:** The official site does not publish per-station coordinates in a machine-readable format. Coordinates are sourced from OpenStreetMap and matched by station name.

## 2. Verification source

### OpenStreetMap (Overpass API)

- **Host:** `https://overpass-api.de/api/interpreter`
- **Queries:** Three queries for all bus stops, metro stations, and transit route relations.
- **Use as cross-check:** For every stop with API coordinates, the pipeline finds the nearest OSM stop and records the distance. Close matches confirm the location, while large discrepancies are flagged for review. For the Metro, OSM is the primary coordinate source.

## 3. Field-level provenance

- `stops.stop_id`: Derived from agency and native code.
- `stops.lat`, `stops.lon`: API coordinates cross-checked with OSM.
- `routes.route_id`: Derived from agency and route code.
- `routes.geometry`: Parsed from WKT LineString data.
- `stops.interchange_group_id`: Computed for stops within 150m across agencies.

## 4. Anti-block stack

- Per-host rate limiting with uniform jitter.
- Exponential backoff on rate limits.
- On-disk response caching (24h default).
- Checkpointed per-route scraping.
