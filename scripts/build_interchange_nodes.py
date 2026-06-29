"""
Build the interchange node catalogue and transfer edge data.
Scans stops.csv for BRT/Metro stops within 500m of each other,
computes Haversine distances, and emits a structured interchange JSON.

Also generates:
  - interchange_nodes.json   — physical transfer hubs with walk times
  - transfer_edges.json      — graph edges for the multi-modal router

Output → final/transit/data/
"""

import csv
import json
import math
import os

BASE = os.path.join(os.path.dirname(__file__), "..", "final")
CSV_DIR = os.path.join(BASE, "csv")
OUT_DIR = os.path.join(BASE, "transit", "data")
os.makedirs(OUT_DIR, exist_ok=True)

WALK_SPEED_MPS = 1.2          # m/s
MAX_TRANSFER_DIST_M = 500     # max proximity to create a transfer edge
TRANSFER_THRESHOLD_SAME = 80  # within 80m → "same node" transfer

# ── Load stops ──────────────────────────────────────────────────────────────
stops = []
with open(os.path.join(CSV_DIR, "stops.csv"), encoding="utf-8") as f:
    for row in csv.DictReader(f):
        try:
            stops.append({
                "stop_id":   row["stop_id"],
                "stop_name": row["name"],
                "agency":    row["agency"],
                "lat":       float(row["lat"]),
                "lon":       float(row["lon"]),
            })
        except (ValueError, KeyError):
            continue

metro_stops = [s for s in stops if s["agency"] == "metro"]
brt_stops  = [s for s in stops if s["agency"] == "brt"]
municipal_bus_stops  = [s for s in stops if s["agency"] == "municipal_bus"]
print(f"Loaded: {len(metro_stops)} metro, {len(brt_stops)} brt, {len(municipal_bus_stops)} municipal_bus")

# ── Haversine ────────────────────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2) -> float:
    """Return distance in metres."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def walk_mins(dist_m: float) -> float:
    return round(dist_m / WALK_SPEED_MPS / 60, 1)

# ── Manually curated walk overrides for known major hubs ─────────────────────
# These come from on-ground knowledge / Nakshatra Nav roadmap.
# Format: { (metro_stop_id, brt_stop_id): walk_minutes }
MANUAL_WALK_OVERRIDES = {
    # Kalupur area — BRT stop is on the street level, Metro underground
    ("metro-blue-07", "brt-ka"): 5.0,       # Kalupur Railway Station → Kalupur BRT
    # Ranip — BRT and Metro are on the same elevated corridor
    ("metro-red-27", "brt-rn"): 2.5,
    # Sabarmati Railway Station — large interchange
    ("metro-red-28", "brt-sb"): 4.0,
    # AEC
    ("metro-red-29", "brt-ae"): 3.0,
    # Thaltej Gam
    ("metro-blue-17", "brt-th"): 3.5,
    # Apparel Park (existing mapped node)
    ("metro-blue-05", "brt-ap"): 2.0,
    # Gheekanta (Metro-Blue + BRT node)
    ("metro-blue-08", "brt-gh"): 3.0,
    # Shahpur
    ("metro-blue-09", "brt-sh"): 3.0,
    # Old High Court — Blue/Red interchange within metro itself
    ("metro-blue-10", "metro-red-24"): 3.5,  # Blue ↔ Red interchange
    # SP Stadium
    ("metro-blue-11", "brt-sp"): 2.0,
    # Commerce Six Roads
    ("metro-blue-12", "brt-cs"): 2.5,
    # Gujarat University
    ("metro-blue-13", "brt-gu"): 2.5,
    # Doordarshan Kendra / Drive-In
    ("metro-blue-15", "brt-dd"): 3.0,
}

# ── Find proximity pairs (Metro ↔ BRT) ─────────────────────────────────────
print("Computing Metro↔BRT proximity pairs...")
metro_brt_pairs = []
for ms in metro_stops:
    for bs in brt_stops:
        d = haversine(ms["lat"], ms["lon"], bs["lat"], bs["lon"])
        if d <= MAX_TRANSFER_DIST_M:
            wm = MANUAL_WALK_OVERRIDES.get((ms["stop_id"], bs["stop_id"]), walk_mins(d))
            metro_brt_pairs.append({
                "from_id":   ms["stop_id"],
                "from_name": ms["stop_name"],
                "from_mode": "metro",
                "to_id":     bs["stop_id"],
                "to_name":   bs["stop_name"],
                "to_mode":   "brt",
                "dist_m":    round(d, 1),
                "walk_mins": wm,
            })

# ── Find proximity pairs (Metro ↔ MUNICIPAL_BUS) ─────────────────────────────────────
print("Computing Metro↔MUNICIPAL_BUS proximity pairs...")
metro_municipal_bus_pairs = []
for ms in metro_stops:
    for ams in municipal_bus_stops:
        d = haversine(ms["lat"], ms["lon"], ams["lat"], ams["lon"])
        if d <= MAX_TRANSFER_DIST_M:
            metro_municipal_bus_pairs.append({
                "from_id":   ms["stop_id"],
                "from_name": ms["stop_name"],
                "from_mode": "metro",
                "to_id":     ams["stop_id"],
                "to_name":   ams["stop_name"],
                "to_mode":   "municipal_bus",
                "dist_m":    round(d, 1),
                "walk_mins": walk_mins(d),
            })

# ── Find proximity pairs (BRT ↔ MUNICIPAL_BUS) ─────────────────────────────────────
print("Computing BRT↔MUNICIPAL_BUS proximity pairs...")
brt_municipal_bus_pairs = []
for bs in brt_stops:
    for ams in municipal_bus_stops:
        d = haversine(bs["lat"], bs["lon"], ams["lat"], ams["lon"])
        if d <= MAX_TRANSFER_DIST_M:
            brt_municipal_bus_pairs.append({
                "from_id":   bs["stop_id"],
                "from_name": bs["stop_name"],
                "from_mode": "brt",
                "to_id":     ams["stop_id"],
                "to_name":   ams["stop_name"],
                "to_mode":   "municipal_bus",
                "dist_m":    round(d, 1),
                "walk_mins": walk_mins(d),
            })

# ── Metro Blue ↔ Red line interchange (Old High Court) ───────────────────────
# Defined as a walk within the same physical station
metro_metro_pairs = [
    {
        "from_id":   "metro-blue-10",
        "from_name": "Old High Court (Blue)",
        "from_mode": "metro",
        "to_id":     "metro-red-24",
        "to_name":   "Usmanpura (Red)",
        "to_mode":   "metro",
        "dist_m":    0,
        "walk_mins": 3.5,
        "note":      "In-station interchange: Blue Line ↔ Red Line via concourse level. Follow Red Line signs."
    }
]

print(f"\nProximity pairs found:")
print(f"  Metro ↔ BRT : {len(metro_brt_pairs)}")
print(f"  Metro ↔ MUNICIPAL_BUS : {len(metro_municipal_bus_pairs)}")
print(f"  BRT  ↔ MUNICIPAL_BUS : {len(brt_municipal_bus_pairs)}")
print(f"  Metro ↔ Metro: {len(metro_metro_pairs)}")

# ── Build Transfer Edges (for router consumption) ────────────────────────────
all_transfer_edges = []
for pair in metro_brt_pairs + metro_municipal_bus_pairs + brt_municipal_bus_pairs + metro_metro_pairs:
    # Add both directions
    all_transfer_edges.append({
        "edge_type":   "transfer-walk",
        "from_stop_id": pair["from_id"],
        "to_stop_id":   pair["to_id"],
        "from_mode":    pair["from_mode"],
        "to_mode":      pair["to_mode"],
        "dist_m":       pair["dist_m"],
        "walk_mins":    pair["walk_mins"],
        "weight_secs":  round(pair["walk_mins"] * 60),
    })
    all_transfer_edges.append({
        "edge_type":   "transfer-walk",
        "from_stop_id": pair["to_id"],
        "to_stop_id":   pair["from_id"],
        "from_mode":    pair["to_mode"],
        "to_mode":      pair["from_mode"],
        "dist_m":       pair["dist_m"],
        "walk_mins":    pair["walk_mins"],
        "weight_secs":  round(pair["walk_mins"] * 60),
    })

print(f"\nTotal transfer edges (bidirectional): {len(all_transfer_edges)}")

# ── Build Interchange Node Catalogue ────────────────────────────────────────
# Group pairs by Metro station to create logical interchange hubs
from collections import defaultdict

hub_map = defaultdict(lambda: {
    "metro_stop_ids": [],
    "brt_stop_ids": [],
    "municipal_bus_stop_ids": [],
    "walk_times": [],
})

for pair in metro_brt_pairs:
    mid = pair["from_id"]
    hub_map[mid]["metro_stop_ids"].append(mid)
    hub_map[mid]["brt_stop_ids"].append({
        "stop_id": pair["to_id"], "stop_name": pair["to_name"],
        "dist_m": pair["dist_m"], "walk_mins": pair["walk_mins"],
    })

for pair in metro_municipal_bus_pairs:
    mid = pair["from_id"]
    hub_map[mid]["metro_stop_ids"].append(mid)
    hub_map[mid]["municipal_bus_stop_ids"].append({
        "stop_id": pair["to_id"], "stop_name": pair["to_name"],
        "dist_m": pair["dist_m"], "walk_mins": pair["walk_mins"],
    })

# Build a name lookup
stop_name = {s["stop_id"]: s["stop_name"] for s in stops}

interchange_nodes = []
for metro_id, hub in hub_map.items():
    interchange_nodes.append({
        "node_id":       f"NODE-{metro_id.upper().replace('-','_')}",
        "name":          stop_name.get(metro_id, metro_id),
        "metro_stop_id": metro_id,
        "brt_stops":    hub["brt_stop_ids"],
        "municipal_bus_stops":    hub["municipal_bus_stop_ids"],
    })

interchange_nodes.sort(key=lambda n: n["metro_stop_id"])
print(f"Interchange hubs (Metro-anchored): {len(interchange_nodes)}")

# ── Write outputs ────────────────────────────────────────────────────────────
out_interchange = os.path.join(OUT_DIR, "interchange_nodes.json")
out_transfers   = os.path.join(OUT_DIR, "transfer_edges.json")

with open(out_interchange, "w", encoding="utf-8") as f:
    json.dump(interchange_nodes, f, indent=2, ensure_ascii=False)
print(f"Written: {out_interchange}")

with open(out_transfers, "w", encoding="utf-8") as f:
    json.dump(all_transfer_edges, f, indent=2, ensure_ascii=False)
print(f"Written: {out_transfers}")
