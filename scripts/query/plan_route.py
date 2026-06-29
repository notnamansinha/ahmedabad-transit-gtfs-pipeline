"""
Text route planner for BRT / MUNICIPAL_BUS / Metro (single mode).

Usage:
  py -3 -m scripts.query.plan_route brt "Maninagar" "Jawahar Chowk"
  py -3 -m scripts.query.plan_route metro "Vastral Gam" "Kalupur Metro Station"

Loads final/json/ and prints stop list, fare, service hours, and tentative
segment timings (median minutes between consecutive stops).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FINAL = REPO / "final" / "json"
NORM = REPO / "normalized"


def _load(name: str) -> list[dict]:
    for base in (FINAL, NORM):
        p = base / f"{name}.json"
        if p.exists():
            return json.loads(p.read_text())
    print(f"Missing {name}.json — run normalize + export first.", file=sys.stderr)
    sys.exit(1)


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def find_stop(stops: list[dict], agency: str, query: str) -> dict | None:
    q = _norm(query)
    exact = [s for s in stops if s["agency"] == agency and _norm(s["name"]) == q]
    if exact:
        return exact[0]
    partial = [
        s for s in stops
        if s["agency"] == agency and (q in _norm(s["name"]) or _norm(s["name"]) in q)
    ]
    if not partial:
        return None
    partial.sort(key=lambda s: len(s["name"]))
    return partial[0]


def fare_lookup(fares: list[dict], agency: str, a: str, b: str) -> dict | None:
    for f in fares:
        if f["agency"] == agency and f["from_stop_id"] == a and f["to_stop_id"] == b:
            return f
    return None


def segment_minutes(
    segments: list[dict], agency: str, a: str, b: str
) -> float | None:
    for s in segments:
        if (
            s["agency"] == agency
            and s["from_stop_id"] == a
            and s["to_stop_id"] == b
        ):
            return s["median_minutes"]
    return None


def routes_serving(
    routes: list[dict], agency: str, from_id: str, to_id: str
) -> list[tuple[dict, list[dict]]]:
    out: list[tuple[dict, list[dict]]] = []
    for r in routes:
        if r["agency"] != agency:
            continue
        seq = r.get("stop_sequence") or []
        if not seq:
            continue
        idx_a = idx_b = None
        for i, s in enumerate(seq):
            if s["stop_id"] == from_id:
                idx_a = i
            if s["stop_id"] == to_id:
                idx_b = i
        if idx_a is not None and idx_b is not None and idx_a < idx_b:
            out.append((r, seq[idx_a : idx_b + 1]))
    return out


def metro_line_slice(stops: list[dict], from_id: str, to_id: str) -> list[dict] | None:
    by_id = {s["stop_id"]: s for s in stops if s["agency"] == "metro"}
    a, b = by_id.get(from_id), by_id.get(to_id)
    if not a or not b:
        return None
    line_a = a["stop_id"].split("-")[1] if a["stop_id"].startswith("metro-") else None
    line_b = b["stop_id"].split("-")[1] if b["stop_id"].startswith("metro-") else None
    if line_a != line_b:
        return None
    line_stops = sorted(
        [
            s
            for s in stops
            if s["agency"] == "metro" and s["stop_id"].split("-")[1] == line_a
        ],
        key=lambda s: int(s["stop_id"].rsplit("-", 1)[-1]),
    )
    ids = [s["stop_id"] for s in line_stops]
    if from_id not in ids or to_id not in ids:
        return None
    i, j = ids.index(from_id), ids.index(to_id)
    if i > j:
        line_stops = list(reversed(line_stops))
    i = [s["stop_id"] for s in line_stops].index(from_id)
    j = [s["stop_id"] for s in line_stops].index(to_id)
    return line_stops[i : j + 1]


def print_stops_with_timing(
    agency: str,
    stops_on_trip: list[dict],
    segments: list[dict],
    route_seq: list[dict] | None = None,
) -> float:
    """Print stops; return total tentative minutes."""
    total = 0.0
    for i, st in enumerate(stops_on_trip):
        name = st.get("name") or st.get("stop_name") or st["stop_id"]
        mins: float | None = None
        if route_seq and i < len(route_seq) - 1:
            mins = route_seq[i].get("median_minutes_to_next")
        elif i < len(stops_on_trip) - 1:
            nxt = stops_on_trip[i + 1]["stop_id"]
            mins = segment_minutes(segments, agency, st["stop_id"], nxt)
        if mins is not None:
            total += mins
            print(f"  - {name}  (~{mins:.0f} min to next)")
        else:
            print(f"  - {name}")
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description="Text route plan (single agency).")
    ap.add_argument("agency", choices=["brt", "municipal_bus", "metro"])
    ap.add_argument("from_stop", help="Stop name (partial match OK)")
    ap.add_argument("to_stop", help="Stop name (partial match OK)")
    args = ap.parse_args()

    stops = _load("stops")
    routes = _load("routes")
    fares = _load("fares")
    segments = _load("segment_times")

    fs = find_stop(stops, args.agency, args.from_stop)
    ts = find_stop(stops, args.agency, args.to_stop)
    if not fs or not ts:
        missing = [n for n, s in [(args.from_stop, fs), (args.to_stop, ts)] if not s]
        print(f"Could not find stop(s): {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    print(f"From: {fs['name']} ({fs['stop_id']})")
    print(f"To:   {ts['name']} ({ts['stop_id']})")
    print()

    fare_rec = fare_lookup(fares, args.agency, fs["stop_id"], ts["stop_id"])

    if args.agency == "metro":
        line_stops = metro_line_slice(stops, fs["stop_id"], ts["stop_id"])
        if line_stops:
            print(f"Line: {line_stops[0]['stop_id'].split('-')[1].title()}")
        else:
            print("Route: multi-line (per METRO fare planner)")
        print("Stations:")
        if line_stops:
            total = print_stops_with_timing("metro", line_stops, segments)
        else:
            print(f"  - {fs['name']}")
            print(f"  - {ts['name']}")
            total = 0.0
        print()
        if fare_rec:
            print(f"Fare: Rs {fare_rec['fare_inr']:.0f}")
            if fare_rec.get("journey_minutes"):
                print(
                    f"Tentative journey time: ~{fare_rec['journey_minutes']} min "
                    "(METRO planner)"
                )
            elif total > 0:
                print(f"Tentative journey time: ~{total:.0f} min (sum of segments)")
        else:
            print("Fare: run scripts.scrapers.metro_fares then normalize + export")
        return

    options = routes_serving(routes, args.agency, fs["stop_id"], ts["stop_id"])
    if not options:
        print("No direct route found (same vehicle, both stops in order).")
        sys.exit(1)

    options.sort(key=lambda x: len(x[1]))
    route, seq = options[0]

    def _t(s: str) -> str:
        return s[:5] if s and len(s) >= 5 else s

    print(f"Route: {route['customer_route_code']} — {route['headsign']}")
    print(f"Service: {_t(route['first_departure'])} – {_t(route['last_departure'])}")
    print("Stops:")
    total = print_stops_with_timing(args.agency, seq, segments, route_seq=seq)
    print()
    if fare_rec:
        print(f"Fare: Rs {fare_rec['fare_inr']:.0f}")
    else:
        print("Fare: not in matrix for this exact stop pair.")
    if total > 0:
        print(f"Tentative journey time: ~{total:.0f} min (median segment sum)")


if __name__ == "__main__":
    main()
