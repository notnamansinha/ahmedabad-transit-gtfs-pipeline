"""
Geo helpers + Ahmedabad-specific coordinate validation.

We need to reject:
- (0, 0) and other obviously-null coords (the Transit Data dataset had these)
- Coords outside the Ahmedabad/Gandhinagar metropolitan bounding box
- Swapped lat/lon (a common Indian-portal bug)

The bounding box below is intentionally generous — it covers Sanand in the
west, Naroda/Vatva in the east, Sarkhej in the south, and Mahatma Mandir
(Gandhinagar) in the north, with ~5km padding. Anything outside this is
either bad data or refers to a different city.
"""

from __future__ import annotations

import math
from typing import Optional


# Generous Ahmedabad + Gandhinagar bounding box (lat_min, lat_max, lon_min, lon_max)
AHM_BBOX = (22.85, 23.40, 72.40, 72.85)


def in_ahm_bbox(lat: float, lon: float) -> bool:
    return AHM_BBOX[0] <= lat <= AHM_BBOX[1] and AHM_BBOX[2] <= lon <= AHM_BBOX[3]


def validate_coord(lat: Optional[float], lon: Optional[float]) -> tuple[bool, str]:
    """Return (is_valid, reason_if_not).

    Caller is expected to use `reason` to populate verification log entries.
    """
    if lat is None or lon is None:
        return False, "null_coords"
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return False, "non_numeric"
    if lat_f == 0 and lon_f == 0:
        return False, "zero_zero"
    if not math.isfinite(lat_f) or not math.isfinite(lon_f):
        return False, "non_finite"

    if in_ahm_bbox(lat_f, lon_f):
        return True, ""
    # Common swap case: API returned (lon, lat) instead of (lat, lon)
    if in_ahm_bbox(lon_f, lat_f):
        return False, "swapped_latlon"
    return False, "outside_ahm_bbox"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    R = 6_371_000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def parse_linestring(wkt: str) -> list[tuple[float, float]]:
    """Parse 'LINESTRING (lon lat, lon lat, ...)' WKT into [(lat, lon), ...].

    The BRT API returns route geometry as a WKT LINESTRING with (lon lat)
    ordering — the OGC standard. We return (lat, lon) to match every other
    coord in this codebase.
    """
    if not wkt or "LINESTRING" not in wkt:
        return []
    inside = wkt.split("LINESTRING", 1)[1].strip()
    if inside.startswith("("):
        inside = inside[1:]
    if inside.endswith(")"):
        inside = inside[:-1]
    pts: list[tuple[float, float]] = []
    for pair in inside.split(","):
        pair = pair.strip()
        if not pair:
            continue
        parts = pair.split()
        if len(parts) < 2:
            continue
        try:
            lon = float(parts[0])
            lat = float(parts[1])
            pts.append((lat, lon))
        except ValueError:
            continue
    return pts
