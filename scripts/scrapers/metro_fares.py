"""
Scrape City Metro stop-to-stop fares via METRO admin-ajax.php.

Endpoint (from custom-ajax.js on route-and-fares page):
  POST .../wp-admin/admin-ajax.php
  action=get_fare&FromStation=<id>&ToStation=<id>

Station numeric IDs match <option value="N"> on the route-and-fares page.
Checkpoint: logs/metro_fares.ckpt.json
"""

from __future__ import annotations

import json
import re
import sys
import time
import random
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "raw" / "metro"
LOGS = REPO / "logs"
AJAX_URL = "https://www.metro-system.local/ahmedabad/wp-admin/admin-ajax.php"
ROUTE_PAGE = REPO / "data" / "raw" / "metro" / "route_and_fares.html"


def parse_station_index(html: str) -> list[dict]:
    """Return [{metro_id, name}, ...] in dropdown order."""
    out: list[dict] = []
    seen: set[int] = set()
    for vid, name in re.findall(
        r'<option\s+value="(\d+)">([^<]+)</option>', html, flags=re.I
    ):
        gid = int(vid)
        if gid in seen:
            continue
        name = re.sub(r"\s+", " ", name).strip()
        if name in ("From Station", "To Station"):
            continue
        seen.add(gid)
        out.append({"metro_id": gid, "name": name})
    return out


def _safe_int(val: object, default: int = 0) -> int:
    try:
        return int(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def fetch_fare(from_id: int, to_id: int) -> dict | None:
    body = urllib.parse.urlencode(
        {"action": "get_fare", "FromStation": from_id, "ToStation": to_id}
    ).encode()
    req = urllib.request.Request(AJAX_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("User-Agent", "AhmedabadTransitData/1.0 (research)")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8-sig")
        return json.loads(raw)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        return {"error": str(e)}


def scrape(limit: int | None = None) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    if not ROUTE_PAGE.exists():
        print("[metro_fares] missing route_and_fares.html — run scripts.scrapers.metro first")
        sys.exit(1)

    stations = parse_station_index(ROUTE_PAGE.read_text(encoding="utf-8", errors="replace"))
    (RAW / "station_index.json").write_text(json.dumps(stations, indent=2))
    print(f"[metro_fares] {len(stations)} stations indexed")

    ckpt_path = LOGS / "metro_fares.ckpt.json"
    done: set[str] = set()
    if ckpt_path.exists():
        done = set(json.loads(ckpt_path.read_text()).get("done", []))

    out_path = RAW / "fare_pairs.json"
    pairs: dict[str, dict] = {}
    if out_path.exists():
        pairs = json.loads(out_path.read_text())

    ids = [s["metro_id"] for s in stations]
    tasks = [(a, b) for a in ids for b in ids if a != b]
    if limit:
        tasks = tasks[:limit]

    pending = [t for t in tasks if f"{t[0]}->{t[1]}" not in done]
    print(f"[metro_fares] {len(pending)} pairs to fetch ({len(done)} cached)")

    for i, (frm, to) in enumerate(pending, 1):
        key = f"{frm}->{to}"
        data = fetch_fare(frm, to)
        if data and data.get("search_found") == "Yes" and not data.get("error"):
            try:
                fare_inr = float(data.get("fare_price") or 0)
            except (TypeError, ValueError):
                fare_inr = 0.0
            if fare_inr <= 0:
                pairs[key] = {
                    "from_metro_id": frm,
                    "to_metro_id": to,
                    "unavailable": True,
                    "raw": data,
                }
            else:
                pairs[key] = {
                    "from_metro_id": frm,
                    "to_metro_id": to,
                    "fare_inr": fare_inr,
                    "station_count": _safe_int(data.get("station_count")),
                    "station_km": float(data.get("station_km") or 0),
                    "total_minutes": _safe_int(data.get("station_min")),
                    "interchanges": _safe_int(data.get("station_interchange")),
                }
        else:
            pairs[key] = {
                "from_metro_id": frm,
                "to_metro_id": to,
                "unavailable": True,
                "raw": data,
            }
        done.add(key)
        if i % 25 == 0 or i == len(pending):
            ckpt_path.write_text(json.dumps({"done": sorted(done)}, indent=2))
            out_path.write_text(json.dumps(pairs, indent=2))
            print(f"[metro_fares]   {i}/{len(pending)}")
        time.sleep(random.uniform(1.2, 2.2))

    out_path.write_text(json.dumps(pairs, indent=2))
    ok = sum(1 for v in pairs.values() if not v.get("unavailable"))
    print(f"[metro_fares] saved {ok} fares to {out_path}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="Max pairs (for testing)")
    args = ap.parse_args()
    scrape(limit=args.limit)
