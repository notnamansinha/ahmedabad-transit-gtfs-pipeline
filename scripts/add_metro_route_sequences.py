"""
Add Metro line sequences to route_stops.csv and metro routes to routes.csv.
Metro lines are fixed, sequenced corridors — we define them directly from stops.csv data.
"""

import csv
import os

BASE = os.path.join(os.path.dirname(__file__), "..", "final", "transit", "data")
SCRAPED_AT = "2026-05-18T14:37:25+00:00"

# ── Metro line definitions (ordered stop sequences) ───────────────────────────
# Derived from stops.csv metro-blue-*, metro-red-*, metro-violet-* sequences
# + segment times from generate_metro_data.py

METRO_LINES = {
    "metro-line-blue": {
        "route_name": "Blue Line — Vastral Gam to Thaltej Gam",
        "headsign": "Vastral Gam - Thaltej Gam",
        "agency": "metro",
        "first_departure": "06:00:00",
        "last_departure": "22:00:00",
        "stops": [
            ("metro-blue-00", "Vastral Gam",          2.1),
            ("metro-blue-01", "Nirant Cross Road",     2.3),
            ("metro-blue-02", "Vastral",               2.2),
            ("metro-blue-03", "Rabari Colony",         2.0),
            ("metro-blue-04", "Amraivadi",             2.2),
            ("metro-blue-05", "Apparel Park",          2.3),
            ("metro-blue-06", "Kankaria East",         2.5),
            ("metro-blue-07", "Kalupur Metro Station", 3.1),
            ("metro-blue-08", "Gheekanta",             2.8),
            ("metro-blue-09", "Shahpur",               2.4),
            ("metro-blue-10", "Old High Court",        1.8),
            ("metro-blue-11", "SP Stadium",            2.0),
            ("metro-blue-12", "Commerce Six Road",     2.2),
            ("metro-blue-13", "Gujarat University",    2.0),
            ("metro-blue-14", "Gurukul Road",          2.2),
            ("metro-blue-15", "Doordarshan Kendra",    2.0),
            ("metro-blue-16", "Thaltej",               2.1),
            ("metro-blue-17", "Thaltej Gam",           None),
        ],
    },
    "metro-line-red": {
        "route_name": "Red Line — APMC to Motera Stadium",
        "headsign": "APMC - Motera Stadium",
        "agency": "metro",
        "first_departure": "06:00:00",
        "last_departure": "22:00:00",
        "stops": [
            ("metro-red-18", "APMC",                      2.3),
            ("metro-red-19", "Jivraj Park",               2.0),
            ("metro-red-20", "Rajivnagar",                2.5),
            ("metro-red-21", "Shreyas",                   2.3),
            ("metro-red-22", "Paldi",                     2.1),
            ("metro-red-23", "Gandhigram",                3.2),
            ("metro-red-24", "Usmanpura",                 2.3),
            ("metro-red-25", "Vijaynagar",                2.5),
            ("metro-red-26", "Vadaj",                     2.0),
            ("metro-red-27", "Ranip",                     3.8),
            ("metro-red-28", "Sabarmati Railway Station", 2.2),
            ("metro-red-29", "AEC",                       2.3),
            ("metro-red-30", "Sabarmati",                 2.1),
            ("metro-red-31", "Motera Stadium",            None),
        ],
    },
    "metro-line-violet-main": {
        "route_name": "Violet Line — Koteshwar Road to Mahatama Mandir",
        "headsign": "Koteshwar Road - Mahatama Mandir",
        "agency": "metro",
        "first_departure": "06:00:00",
        "last_departure": "22:00:00",
        "stops": [
            ("metro-violet-32", "Koteshwar Road",      2.2),
            ("metro-violet-33", "Vishwakarma College", 2.0),
            ("metro-violet-34", "Tapovan Circle",      2.1),
            ("metro-violet-35", "Narmada Canal",       2.3),
            ("metro-violet-36", "Koba Circle",         2.4),
            ("metro-violet-37", "Juna Koba",           1.9),
            ("metro-violet-38", "Koba Gam",            2.0),
            ("metro-violet-39", "GNLU",                2.1),
            ("metro-violet-40", "Raysan",              2.4),
            ("metro-violet-41", "Randesan",            2.0),
            ("metro-violet-42", "Dholakuva Circle",    2.3),
            ("metro-violet-43", "Infocity",            2.8),
            ("metro-violet-44", "Sector-1",            2.2),
            ("metro-violet-45", "Sector 10A",          2.1),
            ("metro-violet-46", "Sachivalaya",         2.3),
            ("metro-violet-47", "Akshardham",          2.1),
            ("metro-violet-48", "Juna Sachivalaya",    2.4),
            ("metro-violet-49", "Sector-16",           2.0),
            ("metro-violet-50", "Sector-24",           2.2),
            ("metro-violet-51", "Mahatama Mandir",     None),
        ],
    },
    "metro-line-violet-branch": {
        "route_name": "Violet Line Branch — GNLU to Gift City",
        "headsign": "GNLU - Gift City",
        "agency": "metro",
        "first_departure": "06:00:00",
        "last_departure": "22:00:00",
        "stops": [
            ("metro-violet-39", "GNLU",      3.5),
            ("metro-violet-52", "PDEU",      3.8),
            ("metro-violet-53", "Gift City", None),
        ],
    },
}


def main():
    rs_path = os.path.join(BASE, "route_stops.csv")
    routes_path = os.path.join(BASE, "routes.csv")

    # ── Read existing data ────────────────────────────────────────────────────
    with open(rs_path, encoding="utf-8") as f:
        existing_rs = list(csv.DictReader(f))

    existing_route_ids = {r["route_id"] for r in existing_rs}

    with open(routes_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing_routes = list(reader)
        routes_fieldnames = reader.fieldnames

    existing_route_meta = {r["route_id"] for r in existing_routes}

    # ── Build new route_stops rows ────────────────────────────────────────────
    new_rs_rows = []
    new_route_rows = []

    for route_id, line in METRO_LINES.items():
        # Skip if already exists
        if route_id in existing_route_ids:
            print(f"  Skipping {route_id} — already in route_stops")
            continue

        for seq_idx, (stop_id, stop_name, mins_to_next) in enumerate(line["stops"], start=1):
            new_rs_rows.append({
                "route_id": route_id,
                "sequence": seq_idx,
                "stop_id": stop_id,
                "stop_name": stop_name,
                "median_minutes_to_next": mins_to_next if mins_to_next is not None else "",
            })

        # Add to routes.csv if missing
        if route_id not in existing_route_meta:
            new_route_rows.append({
                "route_id": route_id,
                "agency": "metro",
                "route_code": route_id.replace("metro-line-", ""),
                "customer_route_code": route_id.replace("metro-line-", ""),
                "headsign": line["headsign"],
                "first_departure": line["first_departure"],
                "last_departure": line["last_departure"],
                "scraped_at": SCRAPED_AT,
            })

    print(f"Adding {len(new_rs_rows)} route_stop rows and {len(new_route_rows)} route rows")

    # ── Write route_stops.csv ────────────────────────────────────────────────
    rs_fields = ["route_id", "sequence", "stop_id", "stop_name", "median_minutes_to_next"]
    with open(rs_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rs_fields)
        writer.writeheader()
        writer.writerows(existing_rs)
        writer.writerows(new_rs_rows)
    print(f"route_stops.csv: {len(existing_rs) + len(new_rs_rows)} total rows")

    # ── Write routes.csv ─────────────────────────────────────────────────────
    if new_route_rows:
        # Determine fieldnames from existing file
        existing_fields = list(existing_routes[0].keys()) if existing_routes else list(new_route_rows[0].keys())
        # Normalise new rows to match existing fields
        normalised = []
        for r in new_route_rows:
            row = {f: r.get(f, "") for f in existing_fields}
            normalised.append(row)

        with open(routes_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=existing_fields)
            writer.writeheader()
            writer.writerows(existing_routes)
            writer.writerows(normalised)
        print(f"routes.csv: {len(existing_routes) + len(new_route_rows)} total rows")

    print("Done.")


if __name__ == "__main__":
    main()
