"""
Normalization: raw scraped JSON -> schema-conformant records.

Reads everything under raw/{brt,municipal_bus,metro,osm}/ and writes:
- normalized/stops.json         (every stop, every agency)
- normalized/routes.json        (every route, every agency)
- normalized/fares.json         (every fare matrix entry)
- normalized/verification.json  (per-record provenance + conflicts)

Order of operations matters here: stops must exist before routes (routes
reference stop_ids), and conflict resolution happens before final merge.

Why this is one file rather than per-agency normalizers: the conflict
resolution between agencies (e.g. interchange grouping, coord cross-check)
needs all sources in memory simultaneously. Splitting would mean a pass-1
then a pass-2 with brittle intermediate state.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.common.days import api_days_to_iso  # noqa: E402
from scripts.common.geo import (  # noqa: E402
    haversine_m,
    parse_linestring,
    validate_coord,
)
from scripts.verify.segment_times import (  # noqa: E402
    apply_segment_times_to_routes,
    compute_median_segments,
    segment_lookup_map,
)


REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "raw"
NORM = REPO / "data" / "normalized"
NORM.mkdir(parents=True, exist_ok=True)

NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

# Interchange grouping: stops within this radius across agencies are linked.
INTERCHANGE_RADIUS_M = 150.0


def _canon_route_id(agency: str, route_code: str) -> str:
    return f"{agency}-{route_code}"


def _canon_stop_id(agency: str, native_code: int | str) -> str:
    return f"{agency}-{native_code}"


def _normalize_variant(raw: str | None) -> str:
    if not raw:
        return "NORMAL"
    r = raw.strip().upper().replace(" ", "_")
    if r in {"NORMAL", "AC", "EXPRESS", "SHUTTLE"}:
        return r
    if "LADIES" in r:
        return "LADIES_SPECIAL"
    return "OTHER"


def load_brt_municipal_bus_stops(agency: str, verification: dict) -> list[dict]:
    """Read raw/{agency}/stops.json into schema records.

    Coord validation: any stop with invalid coords is *kept* but flagged in
    `verification` and gets lat/lon=null. Downstream consumers can filter on
    `coord_source != null` to get the verified subset.
    """
    src = RAW / agency / "stops.json"
    if not src.exists():
        print(f"[normalize] missing {src}; skipping {agency} stops")
        return []
    rows = json.loads(src.read_text())
    out: list[dict] = []
    for r in rows:
        stop_code = r["stopCode"]
        pos = r.get("Position") or {}
        lat_raw = pos.get("stopLatitude")
        lon_raw = pos.get("stopLongitude")
        lat: float | None = None
        lon: float | None = None
        coord_src: str | None = None
        try:
            lat_f = float(lat_raw) if lat_raw is not None else None
            lon_f = float(lon_raw) if lon_raw is not None else None
        except (TypeError, ValueError):
            lat_f = lon_f = None
        ok, reason = validate_coord(lat_f, lon_f)
        if ok:
            lat, lon = lat_f, lon_f
            coord_src = f"{agency}_api"
        else:
            verification.setdefault("stop_coord_issues", []).append(
                {
                    "stop_id": _canon_stop_id(agency, stop_code),
                    "name": r.get("stopName"),
                    "reason": reason,
                    "raw_lat": lat_raw,
                    "raw_lon": lon_raw,
                }
            )
        record = {
            "stop_id": _canon_stop_id(agency, stop_code),
            "agency": agency,
            "name": (r.get("stopName") or "").strip(),
            "name_alt": [],
            "native_codes": {
                f"{agency}_stop_code": stop_code,
                f"{agency}_station_code": r.get("stationCode"),
            },
            "lat": lat,
            "lon": lon,
            "coord_source": coord_src,
            "coord_cross_check": {},
            "route_codes": [],
            "interchange_group_id": None,
            "stop_type": r.get("stopType") or agency.upper(),
            "sources": [f"{agency}_api"],
            "scraped_at": NOW,
        }
        out.append(record)
    return out


def _stop_record_from_route_row(agency: str, r: dict, verification: dict) -> dict | None:
    """Build a schema stop from a FareMatrix/StopsOnRoute row."""
    stop_code = r.get("stopCode")
    if stop_code is None:
        return None
    pos = r.get("Position") or {}
    lat_raw = pos.get("stopLatitude")
    lon_raw = pos.get("stopLongitude")
    lat: float | None = None
    lon: float | None = None
    coord_src: str | None = None
    try:
        lat_f = float(lat_raw) if lat_raw is not None else None
        lon_f = float(lon_raw) if lon_raw is not None else None
    except (TypeError, ValueError):
        lat_f = lon_f = None
    ok, reason = validate_coord(lat_f, lon_f)
    if ok:
        lat, lon = lat_f, lon_f
        coord_src = f"{agency}_api"
    else:
        verification.setdefault("stop_coord_issues", []).append(
            {
                "stop_id": _canon_stop_id(agency, stop_code),
                "name": r.get("stopName"),
                "reason": reason,
                "raw_lat": lat_raw,
                "raw_lon": lon_raw,
                "source": "per_route",
            }
        )
    return {
        "stop_id": _canon_stop_id(agency, stop_code),
        "agency": agency,
        "name": (r.get("stopName") or "").strip(),
        "name_alt": [],
        "native_codes": {
            f"{agency}_stop_code": stop_code,
            f"{agency}_station_code": r.get("stationCode"),
        },
        "lat": lat,
        "lon": lon,
        "coord_source": coord_src,
        "coord_cross_check": {},
        "route_codes": [],
        "interchange_group_id": None,
        "stop_type": r.get("stopType") or agency.upper(),
        "sources": [f"{agency}_api", f"{agency}_per_route"],
        "scraped_at": NOW,
    }


def ingest_stops_from_per_route_files(
    agency: str, known_ids: set[str], verification: dict
) -> list[dict]:
    """Add stops that appear on routes but not in DistinctStops.

    Per-route /StopsOnRoute responses include sub-stops missing from the
    master stop list. Without these, route planning cannot resolve stop_ids
    or fares for many A→B pairs.
    """
    per_route_dir = RAW / agency / "routes_with_stops"
    if not per_route_dir.exists():
        return []
    added: list[dict] = []
    seen = set(known_ids)
    for path in sorted(per_route_dir.glob("*.json")):
        try:
            rows = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        for row in rows:
            if not isinstance(row, dict) or row.get("stopCode") is None:
                continue
            sid = _canon_stop_id(agency, row["stopCode"])
            if sid in seen:
                continue
            rec = _stop_record_from_route_row(agency, row, verification)
            if rec is None:
                continue
            added.append(rec)
            seen.add(sid)
    verification["route_only_stops_added"] = verification.get(
        "route_only_stops_added", {}
    )
    verification["route_only_stops_added"][agency] = len(added)
    return added


def load_brt_municipal_bus_routes(
    agency: str, stop_index: dict[str, dict], verification: dict
) -> list[dict]:
    """Read raw/{agency}/routes.json + raw/{agency}/routes_with_stops/*.json.

    Builds the full route record with stop_sequence, geometry, headsign, etc.
    """
    routes_src = RAW / agency / "routes.json"
    if not routes_src.exists():
        return []
    routes_meta = json.loads(routes_src.read_text())

    per_route_dir = RAW / agency / "routes_with_stops"
    out: list[dict] = []
    routes_missing_sequence: list[str] = []

    for r in routes_meta:
        route_code = r["routeCode"]
        per_route_file = per_route_dir / f"{route_code.replace('/', '_')}.json"
        stop_sequence: list[dict] = []
        geometry: dict | None = None
        if per_route_file.exists():
            raw_rows = json.loads(per_route_file.read_text())
            # Defensive: API can include `null` entries and rows without
            # Sequence (often a leading row carrying just the routeFlow WKT
            # and no stop data).
            all_dict_rows = [s for s in raw_rows if isinstance(s, dict)]
            seq_rows = sorted(
                [s for s in all_dict_rows if s.get("Sequence") is not None],
                key=lambda s: s["Sequence"],
            )
            for s in seq_rows:
                native = s["stopCode"]
                sid = _canon_stop_id(agency, native)
                stop_sequence.append(
                    {
                        "sequence": s["Sequence"],
                        "stop_id": sid,
                        "stop_name": s.get("stopName"),
                        "expected_minutes_from_start": None,
                    }
                )
                # Backfill RouteCodes onto stops
                idx = stop_index.get(sid)
                if idx is not None and route_code not in idx["route_codes"]:
                    idx["route_codes"].append(route_code)
            # Geometry: any row may carry the routeFlow LINESTRING — pick
            # the first non-empty one (typically the leading metadata row).
            wkt = ""
            for r2 in all_dict_rows:
                cand = r2.get("routeFlow")
                if cand:
                    wkt = cand
                    break
            pts = parse_linestring(wkt)
            if pts:
                geometry = {
                    "type": "LineString",
                    "coordinates": [[lon, lat] for (lat, lon) in pts],
                }
        else:
            routes_missing_sequence.append(route_code)

        # Days conversion: API days field -> ISO
        days_iso = api_days_to_iso(r.get("days") or "")

        start_sid = _canon_stop_id(agency, r["startStopCode"])
        end_sid = _canon_stop_id(agency, r["endStopCode"])

        record = {
            "route_id": _canon_route_id(agency, route_code),
            "agency": agency,
            "route_code": route_code,
            "customer_route_code": r.get("customerRouteCode") or route_code,
            "headsign": r.get("route") or f"{r.get('startName')} - {r.get('endName')}",
            "variant": _normalize_variant(r.get("Variant")),
            "start_stop_id": start_sid,
            "end_stop_id": end_sid,
            "stop_sequence": stop_sequence,
            "geometry": geometry,
            "first_departure": r["startTime"],
            "last_departure": r["endTime"],
            "operating_days": days_iso,
            "headway_minutes": None,
            "total_distance_km": None,
            "total_duration_min": None,
            "sources": [f"{agency}_api"],
            "scraped_at": NOW,
        }
        out.append(record)

    if routes_missing_sequence:
        verification.setdefault("routes_missing_sequence", []).extend(
            routes_missing_sequence
        )
    return out


def load_brt_municipal_bus_fares(agency: str, verification: dict) -> list[dict]:
    """The fare matrix comes as wide-form (one row per From, columns per To).
    Convert to long-form for SQL friendliness.
    """
    src = RAW / agency / "fare_matrix.json"
    if not src.exists():
        return []
    wide = json.loads(src.read_text())
    out: list[dict] = []
    for row in wide:
        frm = row.get("From")
        if not frm:
            continue
        for k, v in row.items():
            if k == "From":
                continue
            if v is None:
                continue
            try:
                fare = float(v)
            except (TypeError, ValueError):
                continue
            if fare <= 0 or fare > 200:
                verification.setdefault("fare_out_of_range", []).append(
                    {"agency": agency, "from": frm, "to": k, "fare": fare}
                )
                continue
            out.append(
                {
                    "agency": agency,
                    "from_stop_id": f"{agency}-name:{frm}",  # name-based; we resolve below
                    "to_stop_id": f"{agency}-name:{k}",
                    "from_stop_name": frm,
                    "to_stop_name": k,
                    "fare_inr": fare,
                    "service_class": "NORMAL",
                    "sources": [f"{agency}_api"],
                    "scraped_at": NOW,
                }
            )
    return out


def resolve_fare_stop_ids(
    fares: list[dict], stops_by_agency_name: dict[tuple[str, str], str]
) -> tuple[list[dict], list[dict]]:
    """Replace the placeholder `{agency}-name:{N}` stop_ids with real ones.

    The fare matrix and DistinctStops endpoints sometimes disagree on
    naming: the fare matrix uses short forms ("Visat") while
    DistinctStops uses the canonical full name ("Visat -Gandhinagar
    Junction"). Resolution proceeds in three passes:

    1. Exact match on (agency, name)
    2. Case-insensitive + space-normalized match
    3. Substring match (fare-matrix short name appears as prefix in a
       single canonical name — if multiple, we mark unresolved to avoid
       guessing)

    Returns (resolved_fares, unresolved).
    """
    # Build agency-scoped indexes for passes 2 & 3.
    agency_canonical: dict[str, list[tuple[str, str]]] = {}  # agency -> [(canonical_name, stop_id)]
    for (agency, name), sid in stops_by_agency_name.items():
        agency_canonical.setdefault(agency, []).append((name, sid))

    # Strip parenthetical suffixes like "(BRT)", "(BRT)", "(MUNICIPAL_BUS)", "(Old Name)"
    # The fare matrix uses bare names; DistinctStops sometimes appends these.
    _suffix_re = __import__("re").compile(r"\s*\([^)]*\)\s*$")

    def _normalize(s: str) -> str:
        s = _suffix_re.sub("", s)
        return "".join(c for c in s.lower() if c.isalnum())

    norm_index: dict[str, dict[str, str]] = {}
    for agency, names in agency_canonical.items():
        norm_index[agency] = {_normalize(n): sid for n, sid in names}

    def _lookup(agency: str, name: str) -> str | None:
        # Pass 1
        sid = stops_by_agency_name.get((agency, name))
        if sid:
            return sid
        # Pass 2
        nm = _normalize(name)
        sid = norm_index.get(agency, {}).get(nm)
        if sid:
            return sid
        # Pass 3: substring (only if unambiguous)
        candidates = [
            s for n, s in norm_index.get(agency, {}).items()
            if nm and (nm in n or n in nm)
        ]
        if len(candidates) == 1:
            return candidates[0]
        return None

    resolved: list[dict] = []
    unresolved: list[dict] = []
    for f in fares:
        agency = f["agency"]
        a = _lookup(agency, f["from_stop_name"])
        b = _lookup(agency, f["to_stop_name"])
        if a and b:
            f["from_stop_id"] = a
            f["to_stop_id"] = b
            resolved.append(f)
        else:
            f.setdefault("_unresolved_reason", [])
            if not a:
                f["_unresolved_reason"].append(f"from_unmatched:{f['from_stop_name']}")
            if not b:
                f["_unresolved_reason"].append(f"to_unmatched:{f['to_stop_name']}")
            unresolved.append(f)
    return resolved, unresolved


def _metro_metro_ids_ordered() -> list[int]:
    """METRO <option value> ids in dropdown order (matches stations.json rows)."""
    idx_path = RAW / "metro" / "station_index.json"
    if idx_path.exists():
        return [int(r["metro_id"]) for r in json.loads(idx_path.read_text())]
    page = RAW / "metro" / "route_and_fares.html"
    if not page.exists():
        return []
    import re

    ids: list[int] = []
    seen: set[int] = set()
    for vid, name in re.findall(
        r'<option\s+value="(\d+)">([^<]+)</option>',
        page.read_text(encoding="utf-8", errors="replace"),
        flags=re.I,
    ):
        gid = int(vid)
        if gid in seen:
            continue
        clean = re.sub(r"\s+", " ", name).strip()
        if clean in ("From Station", "To Station"):
            continue
        seen.add(gid)
        ids.append(gid)
    return ids


def load_metro_fares(stop_index: dict[str, dict], verification: dict) -> list[dict]:
    """Load scraped METRO fare pairs into schema fare records."""
    src = RAW / "metro" / "fare_pairs.json"
    if not src.exists():
        verification["metro_fares_missing"] = True
        return []
    pairs = json.loads(src.read_text())
    metro_to_stop: dict[int, str] = {}
    for s in stop_index.values():
        if s.get("agency") != "metro":
            continue
        gid = (s.get("native_codes") or {}).get("metro_station_id")
        if gid is not None:
            metro_to_stop[int(gid)] = s["stop_id"]

    fares: list[dict] = []
    skipped = 0
    for _key, row in pairs.items():
        if row.get("unavailable"):
            skipped += 1
            continue
        fid, tid = row.get("from_metro_id"), row.get("to_metro_id")
        if fid is None or tid is None:
            skipped += 1
            continue
        from_sid = metro_to_stop.get(int(fid))
        to_sid = metro_to_stop.get(int(tid))
        if not from_sid or not to_sid:
            skipped += 1
            continue
        fare_inr = row.get("fare_inr")
        if fare_inr is None or fare_inr <= 0:
            skipped += 1
            continue
        rec: dict[str, Any] = {
            "agency": "metro",
            "from_stop_id": from_sid,
            "to_stop_id": to_sid,
            "from_stop_name": stop_index[from_sid]["name"],
            "to_stop_name": stop_index[to_sid]["name"],
            "fare_inr": float(fare_inr),
            "service_class": "NORMAL",
            "sources": ["metro_ajax"],
            "scraped_at": NOW,
        }
        if row.get("total_minutes"):
            rec["journey_minutes"] = int(row["total_minutes"])
        fares.append(rec)
    verification["metro_fare_pairs_loaded"] = len(fares)
    verification["metro_fare_pairs_skipped"] = skipped
    return fares


def load_metro_stations(verification: dict) -> list[dict]:
    src = RAW / "metro" / "stations.json"
    if not src.exists():
        return []
    rows = json.loads(src.read_text())
    metro_ids = _metro_metro_ids_ordered()
    out: list[dict] = []
    for i, s in enumerate(rows):
        lat = s.get("lat")
        lon = s.get("lon")
        ok, reason = validate_coord(lat, lon)
        if not ok:
            verification.setdefault("metro_coord_issues", []).append(
                {"name": s.get("station_name"), "reason": reason}
            )
            lat = lon = None
        line = s.get("line") or "unknown"
        sid = f"metro-{line}-{i:02d}"
        metro_id = metro_ids[i] if i < len(metro_ids) else None
        out.append(
            {
                "stop_id": sid,
                "agency": "metro",
                "name": s["station_name"],
                "name_alt": [],
                "native_codes": {
                    "metro_station_code": sid,
                    **({"metro_station_id": metro_id} if metro_id is not None else {}),
                },
                "lat": lat,
                "lon": lon,
                "coord_source": "metro_official" if lat is not None else None,
                "coord_cross_check": {},
                "route_codes": [f"line-{line}"],
                "interchange_group_id": None,
                "stop_type": "METRO",
                "sources": ["metro_official"],
                "scraped_at": NOW,
            }
        )
    return out


def cross_check_with_osm(stops: list[dict], verification: dict) -> None:
    """For each stop with a coord, find the nearest OSM stop and record
    the distance. Logs anything > 250m as a `coord_disagreement`.
    """
    osm_path = RAW / "osm" / "all_bus_stops.json"
    if not osm_path.exists():
        return
    osm = json.loads(osm_path.read_text())
    osm_pts: list[tuple[str, float, float]] = []
    for el in osm.get("elements", []):
        name = (el.get("tags") or {}).get("name", "?")
        lat, lon = el.get("lat"), el.get("lon")
        if lat is None or lon is None:
            continue
        osm_pts.append((name, lat, lon))
    if not osm_pts:
        return

    disagreements: list[dict] = []
    for s in stops:
        if s["lat"] is None or s["agency"] == "metro":
            continue
        best: tuple[float, str] | None = None
        for nm, olat, olon in osm_pts:
            d = haversine_m(s["lat"], s["lon"], olat, olon)
            if best is None or d < best[0]:
                best = (d, nm)
        if best is None:
            continue
        s["coord_cross_check"]["osm_nearest_m"] = round(best[0], 1)
        s["coord_cross_check"]["osm_nearest_name"] = best[1]
        if best[0] > 250 and best[0] < 1500:
            # Suspicious: name match likely exists but not close enough
            disagreements.append(
                {
                    "stop_id": s["stop_id"],
                    "name": s["name"],
                    "osm_nearest": best[1],
                    "distance_m": round(best[0], 1),
                }
            )
        # Add OSM as a corroborating source if within 50m
        if best[0] <= 50:
            if "osm" not in s["sources"]:
                s["sources"].append("osm")
    verification["osm_coord_disagreements"] = disagreements


def group_interchanges(stops: list[dict]) -> None:
    """Assign `interchange_group_id` to cross-agency stops within radius."""
    # O(n^2) — fine at n=3000. If we ever cross 50k, switch to a KDTree.
    valid = [s for s in stops if s["lat"] is not None]
    next_id = 0
    for i, a in enumerate(valid):
        if a["interchange_group_id"]:
            continue
        for b in valid[i + 1 :]:
            if a["agency"] == b["agency"]:
                continue
            d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
            if d <= INTERCHANGE_RADIUS_M:
                if a["interchange_group_id"]:
                    b["interchange_group_id"] = a["interchange_group_id"]
                else:
                    gid = f"ix-{next_id:04d}"
                    next_id += 1
                    a["interchange_group_id"] = gid
                    b["interchange_group_id"] = gid


def dedupe_stops_by_position(
    stops: list[dict], verification: dict
) -> tuple[list[dict], dict[str, str]]:
    """Within a single agency, two stops within 25m of each other with similar
    names are merged (keep the lower stop_code, drop the higher).

    Returns (keepers, merge_map) where merge_map[dropped_id] = kept_id, so
    callers can remap route references to merged-away stops.
    """
    by_agency: dict[str, list[dict]] = {}
    for s in stops:
        by_agency.setdefault(s["agency"], []).append(s)

    merge_map: dict[str, str] = {}
    dropped_log: list[dict] = []
    for agency, group in by_agency.items():
        group_sorted = sorted(group, key=lambda x: x["stop_id"])
        for i, a in enumerate(group_sorted):
            if a["stop_id"] in merge_map:
                continue
            for b in group_sorted[i + 1 :]:
                if b["stop_id"] in merge_map:
                    continue
                if a["lat"] is None or b["lat"] is None:
                    continue
                if haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) > 25:
                    continue
                if not _name_similar(a["name"], b["name"]):
                    continue
                merge_map[b["stop_id"]] = a["stop_id"]
                if b["name"] not in a["name_alt"]:
                    a["name_alt"].append(b["name"])
                dropped_log.append({
                    "merged_id": b["stop_id"],
                    "kept_id": a["stop_id"],
                    "reason": "within_25m_similar_name",
                })

    keepers = [s for s in stops if s["stop_id"] not in merge_map]
    if dropped_log:
        verification["stop_dedupe"] = dropped_log
    return keepers, merge_map


def apply_merge_map_to_routes(routes: list[dict], merge_map: dict[str, str]) -> None:
    """Rewrite route stop references that pointed at a merged-away stop_id."""
    if not merge_map:
        return
    for r in routes:
        if r.get("start_stop_id") in merge_map:
            r["start_stop_id"] = merge_map[r["start_stop_id"]]
        if r.get("end_stop_id") in merge_map:
            r["end_stop_id"] = merge_map[r["end_stop_id"]]
        for s in r.get("stop_sequence", []):
            if s.get("stop_id") in merge_map:
                s["stop_id"] = merge_map[s["stop_id"]]


def _name_similar(a: str, b: str) -> bool:
    a_clean = "".join(ch for ch in a.lower() if ch.isalnum())
    b_clean = "".join(ch for ch in b.lower() if ch.isalnum())
    if not a_clean or not b_clean:
        return False
    if a_clean == b_clean:
        return True
    # Substring containment for cases like "Foo Stop" vs "Foo"
    if a_clean in b_clean or b_clean in a_clean:
        return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--skip-osm-crosscheck", action="store_true",
        help="Skip OSM cross-check (saves a minute on dev runs).",
    )
    args = ap.parse_args()

    verification: dict[str, Any] = {"normalized_at": NOW}

    # 1. Stops
    stops: list[dict] = []
    for agency in ("brt", "municipal_bus"):
        stops.extend(load_brt_municipal_bus_stops(agency, verification))
        known = {s["stop_id"] for s in stops}
        stops.extend(ingest_stops_from_per_route_files(agency, known, verification))
    stops.extend(load_metro_stations(verification))

    stops, merge_map = dedupe_stops_by_position(stops, verification)
    stop_index = {s["stop_id"]: s for s in stops}

    if not args.skip_osm_crosscheck:
        cross_check_with_osm(stops, verification)
    group_interchanges(stops)

    # 2. Routes (resolves stop_ids against stop_index, backfills route_codes)
    routes: list[dict] = []
    for agency in ("brt", "municipal_bus"):
        routes.extend(load_brt_municipal_bus_routes(agency, stop_index, verification))
    apply_merge_map_to_routes(routes, merge_map)

    segment_records = compute_median_segments(routes, stops, stop_index)
    apply_segment_times_to_routes(routes, segment_lookup_map(segment_records))
    verification["segment_time_edges"] = len(segment_records)

    # Surface any route stop_id references that still don't resolve — these
    # are orphan FKs that the exporter would otherwise hide. Common cause:
    # the per-route /StopsOnRoute response cited a stopCode that DistinctStops
    # didn't list (rare; ~0-3 per run).
    orphans: list[dict] = []
    for r in routes:
        if r["start_stop_id"] not in stop_index:
            orphans.append({"route_id": r["route_id"], "field": "start_stop_id", "value": r["start_stop_id"]})
        if r["end_stop_id"] not in stop_index:
            orphans.append({"route_id": r["route_id"], "field": "end_stop_id", "value": r["end_stop_id"]})
        for s in r.get("stop_sequence", []):
            if s["stop_id"] not in stop_index:
                orphans.append({"route_id": r["route_id"], "field": "stop_sequence", "value": s["stop_id"]})
    verification["orphan_stop_refs_in_routes"] = orphans[:50]
    verification["orphan_stop_ref_count"] = len(orphans)

    # 3. Fares
    raw_fares: list[dict] = []
    for agency in ("brt", "municipal_bus"):
        raw_fares.extend(load_brt_municipal_bus_fares(agency, verification))

    stops_by_agency_name = {(s["agency"], s["name"]): s["stop_id"] for s in stops}
    # Also try a normalized-name match (case-insensitive, stripped)
    for s in stops:
        key = (s["agency"], s["name"].strip())
        stops_by_agency_name.setdefault(key, s["stop_id"])
    fares, unresolved_fares = resolve_fare_stop_ids(raw_fares, stops_by_agency_name)
    fares.extend(load_metro_fares(stop_index, verification))
    verification["fare_unresolved_count"] = len(unresolved_fares)
    if unresolved_fares:
        # Sample for debugging
        verification["fare_unresolved_sample"] = unresolved_fares[:20]

    # 4. Write outputs
    (NORM / "stops.json").write_text(json.dumps(stops, indent=2))
    (NORM / "routes.json").write_text(json.dumps(routes, indent=2))
    (NORM / "fares.json").write_text(json.dumps(fares, indent=2))
    (NORM / "segment_times.json").write_text(json.dumps(segment_records, indent=2))
    (NORM / "verification.json").write_text(json.dumps(verification, indent=2))

    print(f"[normalize] stops:  {len(stops)}")
    print(f"[normalize] routes: {len(routes)}")
    print(f"[normalize] fares:  {len(fares)} (unresolved: {len(unresolved_fares)})")
    print(f"[normalize] verification -> normalized/verification.json")


if __name__ == "__main__":
    main()
