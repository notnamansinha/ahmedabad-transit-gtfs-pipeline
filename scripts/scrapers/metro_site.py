"""
City Metro scraper.

Sources:
- Official METRO HTML for the canonical station list (in operational order).
  https://www.metro-system.local/ahmedabad/route-and-fares/
  The page does NOT publish per-station coordinates — only a single embedded
  Google MyMaps link covering the whole network. So names come from the
  page, coords come from OSM.
- OpenStreetMap for per-station coordinates. data/raw/osm/metro_stations.json
  must already exist (run scripts.scrapers.osm first).

Line assignment uses an endpoint-anchored sweep:
- Blue:   Vastral Gam → Thaltej Gam
- Red:    APMC → Motera Stadium
- Violet: Koteshwar Road → Gift City
This works because the official dropdown lists stations in operational
sequence along each line, line-by-line. If METRO reorders the dropdown,
this assumption breaks and we'd need to switch to per-station line tags.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.common.geo import haversine_m, validate_coord  # noqa: E402
from scripts.common.http_client import HttpClient  # noqa: E402


METRO_ROUTE_PAGE = "https://www.metro-system.local/ahmedabad/route-and-fares/"
METRO_FARE_PAGE = "https://www.metro-system.local/ahmedabad/fare-rules/"
METRO_TRAIN_INFO = "https://www.metro-system.local/ahmedabad/train-information/"


# Endpoint pairs in (start_name, end_name) order. Names must match exactly
# the cleaned station name from the dropdown (case + punctuation matter).
LINE_ENDPOINTS = [
    ("blue", "Vastral Gam", "Thaltej Gam"),
    ("red", "APMC", "Motera Stadium"),
    ("violet", "Koteshwar Road", "Gift City"),
]


# Maximum distance (meters) for an OSM name-match to be accepted as the
# coordinate source. Beyond this, treat the OSM record as a different
# nearby place that happens to share a name fragment.
MAX_OSM_MATCH_DIST_M = 800.0  # only relevant when fuzzy-matching


# Name aliases — site name on the left, OSM name on the right. The site
# uses inconsistent transliteration in a few spots. Add new mappings here
# rather than editing the parser.
NAME_ALIASES = {
    "Mahatama Mandir": "Mahatma Mandir",  # site typo
    "Sector 10A": "Sector-10A",
    "PDEU": "PDPU",                       # university renamed
    "Gift City": "GIFT City",
    "Amraivadi": "Amraiwadi",             # transliteration variant
    "Commerce Six Road": "Commerce Sixth Road",
    "Rajivnagar": "Rajiv Nagar",
    "Vijaynagar": "Vijay Nagar",
    "Kalupur Metro Station": "Kalupur Railway Station",  # co-located with railway
    "Nirant Cross Road": "Nirant Cross Roads",
    "Gujarat University": "Gujarat University Station",
    "Shahpur": "Shahpur Station",
    "SP Stadium": "Stadium",
}


def fetch_raw(http: HttpClient, url: str) -> str:
    raw = http.get(url, as_json=False)
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def parse_station_names(html: str) -> list[str]:
    """Extract clean station names in operational order from dropdown options.

    The route-and-fares page renders two identical <select> dropdowns
    (From/To). We dedupe while preserving first-seen order, which IS
    operational sequence — Blue stations first, then Red, then Violet.
    """
    opts = re.findall(r"<option[^>]*>(.*?)</option>", html)
    ignored = {"From Station", "To Station", "Service Type"}
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in opts:
        name = re.sub(r"\s+", " ", raw).strip()
        if not name or name in ignored or name in seen:
            continue
        # Strip parenthetical status notes for the canonical name
        name_no_status = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
        if name_no_status in seen:
            continue
        seen.add(name_no_status)
        ordered.append(name)
    return ordered


def index_osm_metro_stations() -> dict[str, tuple[float, float]]:
    """Map normalized OSM station name -> (lat, lon)."""
    osm_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "osm" / "metro_stations.json"
    if not osm_path.exists():
        print("[metro] WARN: data/raw/osm/metro_stations.json missing; coords will be null")
        return {}
    data = json.loads(osm_path.read_text())
    out: dict[str, tuple[float, float]] = {}
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        lat = el.get("lat")
        lon = el.get("lon")
        if lat is None or lon is None:
            # `way` elements have center (lat, lon) under "center"
            center = el.get("center") or {}
            lat = center.get("lat")
            lon = center.get("lon")
        if lat is None or lon is None:
            continue
        # Prefer first occurrence (don't overwrite better-tagged matches)
        out.setdefault(name, (lat, lon))
    return out


def match_station(site_name: str, osm: dict[str, tuple[float, float]]) -> tuple[float | None, float | None, str]:
    """Try direct then alias name match. Returns (lat, lon, match_method)."""
    # Strip status suffix like "(WORK IN PROGRESS)"
    clean = re.sub(r"\s*\(.*?\)\s*$", "", site_name).strip()

    # 1. Direct match
    if clean in osm:
        lat, lon = osm[clean]
        return lat, lon, "direct"

    # 2. Alias map
    alias = NAME_ALIASES.get(clean)
    if alias and alias in osm:
        lat, lon = osm[alias]
        return lat, lon, "alias"

    # 3. Case-insensitive + space-normalized substring
    needle = clean.lower().replace("-", " ").replace("  ", " ")
    for osm_name, (lat, lon) in osm.items():
        haystack = osm_name.lower().replace("-", " ").replace("  ", " ")
        if needle == haystack:
            return lat, lon, "case_insensitive"
        if needle in haystack or haystack in needle:
            return lat, lon, "substring"

    return None, None, "no_match"


def assign_lines(stations: list[dict]) -> list[dict]:
    name_to_idx = {s["station_name"]: i for i, s in enumerate(stations)}
    line_for: dict[int, str] = {}
    for line, start, end in LINE_ENDPOINTS:
        s_idx = name_to_idx.get(start)
        e_idx = name_to_idx.get(end)
        if s_idx is None or e_idx is None:
            print(f"[metro] WARN: line '{line}' endpoints {start}↔{end} not both found")
            continue
        lo, hi = sorted([s_idx, e_idx])
        for i in range(lo, hi + 1):
            line_for.setdefault(i, line)
    for i, s in enumerate(stations):
        s["line"] = line_for.get(i, "unknown")
    return stations


def scrape() -> None:
    repo = Path(__file__).resolve().parents[2]
    raw_dir = repo / "data" / "raw" / "metro"
    raw_dir.mkdir(parents=True, exist_ok=True)
    http = HttpClient(log_name="scrape_metro")

    print("[metro] fetching route-and-fares page...")
    html = fetch_raw(http, METRO_ROUTE_PAGE)
    (raw_dir / "route_and_fares.html").write_text(html)

    print("[metro] parsing station names from dropdown...")
    names = parse_station_names(html)
    print(f"[metro]   parsed {len(names)} unique station names")

    print("[metro] loading OSM metro stations for coord matching...")
    osm = index_osm_metro_stations()
    print(f"[metro]   {len(osm)} OSM stations available")

    stations: list[dict] = []
    match_stats = {"direct": 0, "alias": 0, "case_insensitive": 0, "substring": 0, "no_match": 0}
    for nm in names:
        clean = re.sub(r"\s*\(.*?\)\s*$", "", nm).strip()
        lat, lon, method = match_station(nm, osm)
        match_stats[method] = match_stats.get(method, 0) + 1
        valid_coord = False
        if lat is not None and lon is not None:
            ok, _ = validate_coord(lat, lon)
            valid_coord = ok
        stations.append({
            "station_name": clean,
            "raw_name": nm,
            "lat": lat if valid_coord else None,
            "lon": lon if valid_coord else None,
            "coord_match_method": method,
            "operational": "(WORK IN PROGRESS)" not in nm,
        })
    stations = assign_lines(stations)

    print(f"[metro]   match stats: {match_stats}")
    with_coord = sum(1 for s in stations if s["lat"] is not None)
    print(f"[metro]   stations with coords: {with_coord}/{len(stations)}")

    with open(raw_dir / "stations.json", "w") as f:
        json.dump(stations, f, indent=2)

    print("[metro] fetching fare-rules page...")
    (raw_dir / "fare_rules.html").write_text(fetch_raw(http, METRO_FARE_PAGE))
    print("[metro] fetching train-information page...")
    (raw_dir / "train_information.html").write_text(fetch_raw(http, METRO_TRAIN_INFO))

    by_line: dict[str, int] = {}
    for s in stations:
        by_line[s["line"]] = by_line.get(s["line"], 0) + 1
    print(f"[metro]   by line: {by_line}")
    print("[metro] scrape complete.")


if __name__ == "__main__":
    scrape()
