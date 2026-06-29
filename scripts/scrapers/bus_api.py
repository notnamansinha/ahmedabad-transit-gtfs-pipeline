"""
Municipal Transit API scraper. Both BRT and municipal bus systems run on identical APIs so they share code.

What we scrape (per agency):
1. Full route list             -> data/raw/{agency}/routes.json
2. All distinct stops + coords -> data/raw/{agency}/stops.json
3. Stop sequence per route     -> data/raw/{agency}/routes_with_stops/{routeCode}.json
4. Fare matrix                 -> data/raw/{agency}/fare_matrix.json
5. Per-route geometry (WKT)    -> derived from the per-route stops response

Auth: OAuth2 password-grant. Provide credentials via TRANSIT_API_USER and TRANSIT_API_PASS
environment variables.

Run:
    python -m scripts.scrapers.bus_api brt
    python -m scripts.scrapers.bus_api municipal_bus
    python -m scripts.scrapers.bus_api municipal_bus --route-limit 5    # sample run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Add parent dir to path so `python scripts/scrapers/bus_api.py` works too
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.common.http_client import Checkpoint, HttpClient  # noqa: E402


CONFIG = {
    "brt": {
        "base": "https://www.brt-system.local:8081",
        "service_type": "BRT",
        "raw_dir": "data/raw/brt",
    },
    "municipal_bus": {
        "base": "https://www.municipal-bus.local:8081",
        "service_type": "MUNICIPAL_BUS",
        "raw_dir": "data/raw/municipal_bus",
    },
}

TOKEN_USER = os.environ.get("TRANSIT_API_USER")
TOKEN_PASS = os.environ.get("TRANSIT_API_PASS")


class TransitAPIClient:
    """Thin wrapper that handles the OAuth password-grant + bearer headers."""

    def __init__(self, base: str, http: HttpClient):
        self.base = base.rstrip("/")
        self.http = http
        self._token: str | None = None
        self._token_acquired_at: float = 0.0
        # Issued tokens are valid ~3 days; refresh ours every 2h to be safe.
        self._token_ttl_s = 2 * 3600

    def _ensure_token(self) -> None:
        if not TOKEN_USER or not TOKEN_PASS:
            raise RuntimeError("TRANSIT_API_USER and TRANSIT_API_PASS environment variables must be set.")
        if (
            self._token
            and (time.time() - self._token_acquired_at) < self._token_ttl_s
        ):
            return
        # Token endpoint is never cached — always live POST.
        result = self.http.request(
            "POST",
            f"{self.base}/token",
            data={
                "grant_type": "password",
                "username": TOKEN_USER,
                "password": TOKEN_PASS,
            },
            force_refresh=True,
        )
        if not isinstance(result, dict) or "access_token" not in result:
            raise RuntimeError(f"Token response unexpected: {result!r}")
        self._token = result["access_token"]
        self._token_acquired_at = time.time()

    def _headers(self) -> dict[str, str]:
        self._ensure_token()
        return {"Authorization": f"bearer {self._token}"}

    def get(self, path: str, **params: Any) -> Any:
        return self.http.get(
            f"{self.base}/{path.lstrip('/')}",
            params=params,
            headers=self._headers(),
        )


def fetch_route_index(client: TransitAPIClient) -> list[dict[str, Any]]:
    """Return full list of route records (variant-level)."""
    # Page through if needed. We've seen ~109 and ~772 so
    # Rows=2000 is comfortably above current size; the API caps internally.
    result = client.get("api/RouteTimeTable", Rows=2000, Page=0)
    if not isinstance(result, dict) or "Data" not in result:
        raise RuntimeError(f"Unexpected RouteTimeTable shape: {result!r}")
    return result["Data"]


def fetch_distinct_stops(client: TransitAPIClient, service_type: str) -> list[dict[str, Any]]:
    return client.get("api/FareMatrix/DistinctStops", StopType=service_type)


def fetch_fare_matrix(client: TransitAPIClient, service_type: str) -> list[dict[str, Any]]:
    return client.get("api/FareMatrix/GetAllFare", serviceType=service_type)


def fetch_stops_on_route(client: TransitAPIClient, route_code: str) -> list[dict[str, Any]]:
    return client.get("api/FareMatrix/StopsOnRoute", RouteCode=route_code)


def scrape(agency: str, route_limit: int | None = None) -> None:
    cfg = CONFIG[agency]
    repo = Path(__file__).resolve().parents[2]
    raw_dir = repo / cfg["raw_dir"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "routes_with_stops").mkdir(parents=True, exist_ok=True)

    http = HttpClient(log_name=f"scrape_{agency}")
    client = TransitAPIClient(cfg["base"], http)

    # 1. Route index
    print(f"[{agency}] fetching route index...")
    routes = fetch_route_index(client)
    print(f"[{agency}]   got {len(routes)} route records")
    with open(raw_dir / "routes.json", "w") as f:
        json.dump(routes, f, indent=2)

    # 2. Distinct stops (with coords)
    print(f"[{agency}] fetching distinct stops...")
    stops = fetch_distinct_stops(client, cfg["service_type"])
    print(f"[{agency}]   got {len(stops)} stops")
    with open(raw_dir / "stops.json", "w") as f:
        json.dump(stops, f, indent=2)

    # 3. Fare matrix
    print(f"[{agency}] fetching fare matrix...")
    fare = fetch_fare_matrix(client, cfg["service_type"])
    print(f"[{agency}]   got {len(fare)} fare rows")
    with open(raw_dir / "fare_matrix.json", "w") as f:
        json.dump(fare, f, indent=2)

    # 4. Per-route stop sequences (checkpointed)
    cp = Checkpoint(repo / "logs" / f"{agency}_routes.ckpt.json")
    target_routes = routes
    if route_limit:
        target_routes = routes[:route_limit]
        print(f"[{agency}] route_limit={route_limit} (sample run)")

    total = len(target_routes)
    for i, route in enumerate(target_routes):
        rcode = route["routeCode"]
        if cp.done(rcode):
            continue
        out_path = raw_dir / "routes_with_stops" / f"{rcode.replace('/', '_')}.json"
        try:
            stops_on_route = fetch_stops_on_route(client, rcode)
        except Exception as e:
            print(f"[{agency}]   [{i+1}/{total}] {rcode}: ERROR {e}")
            continue
        with open(out_path, "w") as f:
            json.dump(stops_on_route, f, indent=2)
        cp.mark(rcode)
        if (i + 1) % 10 == 0 or i + 1 == total:
            print(f"[{agency}]   per-route stops: {i+1}/{total} done")

    print(f"[{agency}] scrape complete. Routes done: {cp.count()}/{len(routes)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("agency", choices=["brt", "municipal_bus"])
    ap.add_argument(
        "--route-limit",
        type=int,
        default=None,
        help="Limit per-route scrape to N routes (smoke test).",
    )
    args = ap.parse_args()
    scrape(args.agency, route_limit=args.route_limit)


if __name__ == "__main__":
    main()
