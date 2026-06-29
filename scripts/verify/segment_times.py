"""
Median travel minutes between consecutive stops.

For each directed edge (A -> B) seen on any route, collect distance-based
time estimates from stop coordinates, then take the median. Used for
tentative segment timings in text route plans (not official schedules).
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from scripts.common.geo import haversine_m

# Typical in-traffic speeds + dwell at each stop
AGENCY_SPEED_KMH: dict[str, float] = {
    "brt": 22.0,
    "municipal_bus": 18.0,
    "metro": 32.0,
}
AGENCY_DWELL_MIN: dict[str, float] = {
    "brt": 0.5,
    "municipal_bus": 0.75,
    "metro": 1.5,
}


def _estimate_minutes(
    agency: str, lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    dist_m = haversine_m(lat1, lon1, lat2, lon2)
    speed = AGENCY_SPEED_KMH[agency]
    travel = (dist_m / 1000.0) / speed * 60.0
    return travel + AGENCY_DWELL_MIN[agency]


def collect_segment_samples(
    routes: list[dict],
    stop_index: dict[str, dict],
    agency: str,
) -> dict[tuple[str, str], list[float]]:
    samples: dict[tuple[str, str], list[float]] = defaultdict(list)
    for route in routes:
        if route.get("agency") != agency:
            continue
        seq = route.get("stop_sequence") or []
        for i in range(len(seq) - 1):
            a_id = seq[i]["stop_id"]
            b_id = seq[i + 1]["stop_id"]
            sa, sb = stop_index.get(a_id), stop_index.get(b_id)
            if not sa or not sb:
                continue
            if sa.get("lat") is None or sb.get("lat") is None:
                continue
            minutes = _estimate_minutes(
                agency, sa["lat"], sa["lon"], sb["lat"], sb["lon"]
            )
            samples[(a_id, b_id)].append(minutes)
    return samples


def metro_line_routes(stops: list[dict]) -> list[dict]:
    """Synthetic one-way 'routes' per metro line for segment sampling."""
    by_line: dict[str, list[dict]] = defaultdict(list)
    for s in stops:
        if s.get("agency") != "metro":
            continue
        parts = s["stop_id"].split("-")
        if len(parts) < 3:
            continue
        line = parts[1]
        try:
            idx = int(parts[2])
        except ValueError:
            continue
        by_line[line].append((idx, s))
    routes: list[dict] = []
    for line, items in by_line.items():
        items.sort(key=lambda x: x[0])
        seq = [
            {
                "sequence": i + 1,
                "stop_id": s["stop_id"],
                "stop_name": s["name"],
            }
            for i, (_, s) in enumerate(items)
        ]
        routes.append({"agency": "metro", "stop_sequence": seq, "route_id": f"metro-line-{line}"})
    return routes


def compute_median_segments(
    routes: list[dict],
    stops: list[dict],
    stop_index: dict[str, dict],
) -> list[dict]:
    """Return long-form segment_time records."""
    all_routes = list(routes) + metro_line_routes(stops)
    records: list[dict] = []
    for agency in ("brt", "municipal_bus", "metro"):
        samples = collect_segment_samples(all_routes, stop_index, agency)
        for (from_id, to_id), vals in samples.items():
            if not vals:
                continue
            records.append(
                {
                    "agency": agency,
                    "from_stop_id": from_id,
                    "to_stop_id": to_id,
                    "median_minutes": round(statistics.median(vals), 1),
                    "sample_count": len(vals),
                }
            )
    return records


def apply_segment_times_to_routes(
    routes: list[dict], segment_lookup: dict[tuple[str, str, str], float]
) -> None:
    """Set median_minutes_to_next on each stop in stop_sequence (except last)."""
    for route in routes:
        agency = route.get("agency")
        seq = route.get("stop_sequence") or []
        for i, stop in enumerate(seq):
            if i >= len(seq) - 1:
                stop["median_minutes_to_next"] = None
                continue
            nxt = seq[i + 1]["stop_id"]
            key = (agency, stop["stop_id"], nxt)
            stop["median_minutes_to_next"] = segment_lookup.get(key)


def segment_lookup_map(
    segments: list[dict],
) -> dict[tuple[str, str, str], float]:
    return {
        (s["agency"], s["from_stop_id"], s["to_stop_id"]): s["median_minutes"]
        for s in segments
    }
