# Schemas

JSON Schema (draft 2020-12) definitions for every data type produced by this pipeline.

| File | Purpose |
|---|---|
| `stop.schema.json` | One physical transit stop per agency. Cross-agency interchanges link via `interchange_group_id`. |
| `route.schema.json` | One route variant. `customer_route_code` groups variants (e.g. `1S-CG`, `1S-JG` both have `customer_route_code = "1S"`). |
| `fare.schema.json` | One row of the stop-to-stop fare matrix per (agency, service_class). |

## Conventions

- **IDs.** `{agency}-{native_code}` everywhere. Stable across runs as long as the upstream native code is stable.
- **Coordinates.** Always stored as separate `lat`/`lon` numbers. GeoJSON output flips to `[lon, lat]` per RFC 7946.
- **Operating days.** ISO 8601 day numbers: `1=Monday … 7=Sunday`. The BRT/MUNICIPAL_BUS API returns `1=Sunday`; the normalizer remaps on ingest. **This is the single most error-prone field — always read days through `scripts/common/days.py`.**
- **Sources.** Every record carries a `sources` list naming the scrapers that contributed. A record produced by `brt_api` only and never cross-verified will have `["brt_api"]`. After a verification pass adds OSM corroboration, it becomes `["brt_api", "osm"]`.
- **Bounding box.** Stops outside `(22.85, 23.40) × (72.40, 72.85)` are rejected by the validator. See `scripts/common/geo.py:AHM_BBOX`.
- **Fare cap.** `fare_inr ≤ 200`. Real-world Ahmedabad fares max around ₹50; anything over ₹200 indicates a parse error.

## Validation

Validate any normalized file against its schema:

```bash
python -m scripts.verify.validate normalized/stops.json schemas/stop.schema.json
```
