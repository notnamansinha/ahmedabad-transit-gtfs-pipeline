"""
OpenStreetMap Overpass scraper. Primary use: cross-verify BRT/MUNICIPAL_BUS/Metro
coordinates from the official APIs.

Why we run this AT ALL given the official APIs return coords:
- The official APIs occasionally return swapped lat/lon for a small number
  of stops (we've seen ~3 cases). OSM is independent and catches these.
- OSM has many stops the official BRT/MUNICIPAL_BUS APIs don't list (closed routes,
  newly opened stops) — useful for the conflict report.
- For Metro, the official HTML doesn't expose machine-readable coords for
  every station; OSM fills gaps.

We query the Overpass API politely:
- 3-6s jitter (configured in http_client.HostPolicy)
- 7-day cache (transit infra changes rarely)
- Single query rather than per-stop (Overpass charges by query, not result)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.common.http_client import HttpClient  # noqa: E402


OVERPASS = "https://overpass-api.de/api/interpreter"


# Bounding box: (lat_s, lon_w, lat_n, lon_e) — Overpass uses S,W,N,E order.
AHM_OVERPASS_BBOX = "22.85,72.40,23.40,72.85"


QUERIES = {
    "all_bus_stops": f"""
[out:json][timeout:60];
(
  node[highway=bus_stop]({AHM_OVERPASS_BBOX});
  node[public_transport=stop_position][bus=yes]({AHM_OVERPASS_BBOX});
  node[public_transport=platform][bus=yes]({AHM_OVERPASS_BBOX});
);
out body;
""",
    "metro_stations": f"""
[out:json][timeout:60];
(
  node[railway=station][station=subway]({AHM_OVERPASS_BBOX});
  node[public_transport=station][station=subway]({AHM_OVERPASS_BBOX});
  node[railway=stop][station=subway]({AHM_OVERPASS_BBOX});
  node[railway=halt][station=subway]({AHM_OVERPASS_BBOX});
  node[public_transport=stop_position][train=yes]({AHM_OVERPASS_BBOX});
  way[railway=station][station=subway]({AHM_OVERPASS_BBOX});
);
out center;
""",
    "brt_routes": f"""
[out:json][timeout:120];
(
  relation[route=bus][type=route]({AHM_OVERPASS_BBOX});
);
out body;
>;
out skel qt;
""",
}


def run_query(http: HttpClient, ql: str) -> dict:
    return http.post(
        OVERPASS,
        data={"data": ql},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def scrape() -> None:
    repo = Path(__file__).resolve().parents[2]
    raw_dir = repo / "data" / "raw" / "osm"
    raw_dir.mkdir(parents=True, exist_ok=True)
    http = HttpClient(log_name="scrape_osm")

    for name, ql in QUERIES.items():
        print(f"[osm] querying {name} ...")
        try:
            result = run_query(http, ql.strip())
        except Exception as e:
            print(f"[osm]   FAILED {name}: {e}")
            continue
        elements = result.get("elements", []) if isinstance(result, dict) else []
        print(f"[osm]   {name}: {len(elements)} elements")
        with open(raw_dir / f"{name}.json", "w") as f:
            json.dump(result, f, indent=2)

    print("[osm] scrape complete.")


if __name__ == "__main__":
    scrape()
