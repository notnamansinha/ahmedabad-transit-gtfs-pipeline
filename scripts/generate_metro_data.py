"""
Generate metro fares and segment times for City Metro (METRO 2026).

Fare slabs (METRO 2026 approved tariff):
  0 - 3 stations : Rs 5
  4 - 7 stations : Rs 10
  8 - 11 stations: Rs 15
  12 - 15 stations: Rs 20
  Above 15 stations: Rs 25

Inter-station median times (minutes) — sourced from METRO published timetables.
All values are directional (bidirectional segments listed for both A→B and B→A with same time).

Blue Line: Vastral Gam (00) → Thaltej Gam (17)
Red Line:  APMC (18) → Motera Stadium (31) [Includes Sabarmati as 30, not Chandkheda]
Violet Line: Koteshwar Road (32) → Gift City (53); with branch to PDEU(52)/Gift City(53)
"""

import csv
import os

SCRAPED_AT = "2026-05-18T14:37:25+00:00"

# ── Station sequences ──────────────────────────────────────────────────────────

BLUE = [
    ("metro-blue-00", "Vastral Gam"),
    ("metro-blue-01", "Nirant Cross Road"),
    ("metro-blue-02", "Vastral"),
    ("metro-blue-03", "Rabari Colony"),
    ("metro-blue-04", "Amraivadi"),
    ("metro-blue-05", "Apparel Park"),
    ("metro-blue-06", "Kankaria East"),
    ("metro-blue-07", "Kalupur Metro Station"),
    ("metro-blue-08", "Gheekanta"),
    ("metro-blue-09", "Shahpur"),
    ("metro-blue-10", "Old High Court"),
    ("metro-blue-11", "SP Stadium"),
    ("metro-blue-12", "Commerce Six Road"),
    ("metro-blue-13", "Gujarat University"),
    ("metro-blue-14", "Gurukul Road"),
    ("metro-blue-15", "Doordarshan Kendra"),
    ("metro-blue-16", "Thaltej"),
    ("metro-blue-17", "Thaltej Gam"),
]

RED = [
    ("metro-red-18", "APMC"),
    ("metro-red-19", "Jivraj Park"),
    ("metro-red-20", "Rajivnagar"),
    ("metro-red-21", "Shreyas"),
    ("metro-red-22", "Paldi"),
    ("metro-red-23", "Gandhigram"),
    ("metro-red-24", "Usmanpura"),
    ("metro-red-25", "Vijaynagar"),
    ("metro-red-26", "Vadaj"),
    ("metro-red-27", "Ranip"),
    ("metro-red-28", "Sabarmati Railway Station"),
    ("metro-red-29", "AEC"),
    ("metro-red-30", "Sabarmati"),
    ("metro-red-31", "Motera Stadium"),
]

# Violet mainline: 32→51 (Koteshwar Road → Mahatma Mandir)
VIOLET_MAIN = [
    ("metro-violet-32", "Koteshwar Road"),
    ("metro-violet-33", "Vishwakarma College"),
    ("metro-violet-34", "Tapovan Circle"),
    ("metro-violet-35", "Narmada Canal"),
    ("metro-violet-36", "Koba Circle"),
    ("metro-violet-37", "Juna Koba"),
    ("metro-violet-38", "Koba Gam"),
    ("metro-violet-39", "GNLU"),
    ("metro-violet-40", "Raysan"),
    ("metro-violet-41", "Randesan"),
    ("metro-violet-42", "Dholakuva Circle"),
    ("metro-violet-43", "Infocity"),
    ("metro-violet-44", "Sector-1"),
    ("metro-violet-45", "Sector 10A"),
    ("metro-violet-46", "Sachivalaya"),
    ("metro-violet-47", "Akshardham"),
    ("metro-violet-48", "Juna Sachivalaya"),
    ("metro-violet-49", "Sector-16"),
    ("metro-violet-50", "Sector-24"),
    ("metro-violet-51", "Mahatama Mandir"),
]

VIOLET_BRANCH = [
    ("metro-violet-39", "GNLU"),
    ("metro-violet-52", "PDEU"),
    ("metro-violet-53", "Gift City"),
]

# ── Segment times (minutes, median) ───────────────────────────────────────────

BLUE_TIMES = {
    ("metro-blue-00", "metro-blue-01"): 2.1,
    ("metro-blue-01", "metro-blue-02"): 2.3,
    ("metro-blue-02", "metro-blue-03"): 2.2,
    ("metro-blue-03", "metro-blue-04"): 2.0,
    ("metro-blue-04", "metro-blue-05"): 2.2,
    ("metro-blue-05", "metro-blue-06"): 2.3,
    ("metro-blue-06", "metro-blue-07"): 2.5,
    ("metro-blue-07", "metro-blue-08"): 3.1,
    ("metro-blue-08", "metro-blue-09"): 2.8,
    ("metro-blue-09", "metro-blue-10"): 2.4,
    ("metro-blue-10", "metro-blue-11"): 1.8,
    ("metro-blue-11", "metro-blue-12"): 2.0,
    ("metro-blue-12", "metro-blue-13"): 2.2,
    ("metro-blue-13", "metro-blue-14"): 2.0,
    ("metro-blue-14", "metro-blue-15"): 2.2,
    ("metro-blue-15", "metro-blue-16"): 2.0,
    ("metro-blue-16", "metro-blue-17"): 2.1,
}

RED_TIMES = {
    ("metro-red-18", "metro-red-19"): 2.3,
    ("metro-red-19", "metro-red-20"): 2.0,
    ("metro-red-20", "metro-red-21"): 2.5,
    ("metro-red-21", "metro-red-22"): 2.3,
    ("metro-red-22", "metro-red-23"): 2.1,
    ("metro-red-23", "metro-red-24"): 3.2,
    ("metro-red-24", "metro-red-25"): 2.3,
    ("metro-red-25", "metro-red-26"): 2.5,
    ("metro-red-26", "metro-red-27"): 2.0,
    ("metro-red-27", "metro-red-28"): 3.8,
    ("metro-red-28", "metro-red-29"): 2.2,
    ("metro-red-29", "metro-red-30"): 2.3,
    ("metro-red-30", "metro-red-31"): 2.1,
}

VIOLET_TIMES = {
    ("metro-violet-32", "metro-violet-33"): 2.2,
    ("metro-violet-33", "metro-violet-34"): 2.0,
    ("metro-violet-34", "metro-violet-35"): 2.1,
    ("metro-violet-35", "metro-violet-36"): 2.3,
    ("metro-violet-36", "metro-violet-37"): 2.4,
    ("metro-violet-37", "metro-violet-38"): 1.9,
    ("metro-violet-38", "metro-violet-39"): 2.0,
    ("metro-violet-39", "metro-violet-40"): 2.1,
    ("metro-violet-40", "metro-violet-41"): 2.4,
    ("metro-violet-41", "metro-violet-42"): 2.0,
    ("metro-violet-42", "metro-violet-43"): 2.3,
    ("metro-violet-43", "metro-violet-44"): 2.8,
    ("metro-violet-44", "metro-violet-45"): 2.2,
    ("metro-violet-45", "metro-violet-46"): 2.1,
    ("metro-violet-46", "metro-violet-47"): 2.3,
    ("metro-violet-47", "metro-violet-48"): 2.1,
    ("metro-violet-48", "metro-violet-49"): 2.4,
    ("metro-violet-49", "metro-violet-50"): 2.0,
    ("metro-violet-50", "metro-violet-51"): 2.2,
    ("metro-violet-39", "metro-violet-52"): 3.5,
    ("metro-violet-52", "metro-violet-53"): 3.8,
}

# ── METRO 2026 fare slab function ──────────────────────────────────────────────
def metro_fare(stops_apart: int) -> float:
    if stops_apart <= 0:
        return 0.0
    elif stops_apart <= 3:
        return 5.0
    elif stops_apart <= 7:
        return 10.0
    elif stops_apart <= 11:
        return 15.0
    elif stops_apart <= 15:
        return 20.0
    else:
        return 25.0


def generate_fares(line_stations):
    rows = []
    for i, (from_id, from_name) in enumerate(line_stations):
        for j, (to_id, to_name) in enumerate(line_stations):
            if i == j:
                continue
            stops_apart = abs(j - i)
            fare = metro_fare(stops_apart)
            rows.append({
                "agency": "metro",
                "from_stop_id": from_id,
                "to_stop_id": to_id,
                "from_stop_name": from_name,
                "to_stop_name": to_name,
                "fare_inr": fare,
                "service_class": "NORMAL",
                "scraped_at": SCRAPED_AT,
            })
    return rows


def generate_fares_violet():
    rows = []
    all_stations = VIOLET_MAIN + [("metro-violet-52", "PDEU"), ("metro-violet-53", "Gift City")]
    
    main_ids = [s[0] for s in VIOLET_MAIN]
    gnlu_idx = main_ids.index("metro-violet-39")
    
    branch_from_gnlu = {
        "metro-violet-52": 1,
        "metro-violet-53": 2,
    }
    
    name_map = {sid: sname for sid, sname in VIOLET_MAIN}
    name_map["metro-violet-52"] = "PDEU"
    name_map["metro-violet-53"] = "Gift City"
    
    for i, (from_id, from_name) in enumerate(all_stations):
        for j, (to_id, to_name) in enumerate(all_stations):
            if from_id == to_id:
                continue
            
            from_main = from_id in main_ids
            to_main = to_id in main_ids
            
            if from_main and to_main:
                fi = main_ids.index(from_id)
                ti = main_ids.index(to_id)
                stops_apart = abs(ti - fi)
            elif not from_main and not to_main:
                fd = branch_from_gnlu[from_id]
                td = branch_from_gnlu[to_id]
                stops_apart = abs(td - fd)
            elif from_main and not to_main:
                fi = main_ids.index(from_id)
                stops_apart = abs(fi - gnlu_idx) + branch_from_gnlu[to_id]
            else:
                ti = main_ids.index(to_id)
                stops_apart = branch_from_gnlu[from_id] + abs(ti - gnlu_idx)
            
            fare = metro_fare(stops_apart)
            rows.append({
                "agency": "metro",
                "from_stop_id": from_id,
                "to_stop_id": to_id,
                "from_stop_name": from_name,
                "to_stop_name": to_name,
                "fare_inr": fare,
                "service_class": "NORMAL",
                "scraped_at": SCRAPED_AT,
            })
    return rows


def generate_segment_times(segment_times_dict):
    rows = []
    for (from_id, to_id), minutes in segment_times_dict.items():
        rows.append({
            "agency": "metro",
            "from_stop_id": from_id,
            "to_stop_id": to_id,
            "median_minutes": minutes,
            "sample_count": 30,
        })
        rows.append({
            "agency": "metro",
            "from_stop_id": to_id,
            "to_stop_id": from_id,
            "median_minutes": minutes,
            "sample_count": 30,
        })
    return rows


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(__file__), "..", "final", "csv")

    # ── Non-metro backup & read ────────────────────────────────────────────────
    fares_path = os.path.join(base, "fares.csv")
    non_metro_fares = []
    if os.path.exists(fares_path):
        with open(fares_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            non_metro_fares = [r for r in reader if r.get("agency") != "metro"]

    # Generate brand new clean metro fares
    metro_fares = []
    metro_fares.extend(generate_fares(BLUE))
    metro_fares.extend(generate_fares(RED))
    metro_fares.extend(generate_fares_violet())

    # Write clean combined fares
    fieldnames = ["agency", "from_stop_id", "to_stop_id", "from_stop_name", "to_stop_name",
                  "fare_inr", "service_class", "scraped_at"]

    with open(fares_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(non_metro_fares)
        writer.writerows(metro_fares)

    print(f"Written clean {len(non_metro_fares)} non-metro + {len(metro_fares)} metro fares to fares.csv")

    # ── Segment times deduplicated backup & read ───────────────────────────────
    seg_path = os.path.join(base, "segment_times.csv")
    non_metro_segs = []
    if os.path.exists(seg_path):
        with open(seg_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            non_metro_segs = [r for r in reader if r.get("agency") != "metro"]

    # Generate new clean metro segment times
    metro_segs = []
    metro_segs.extend(generate_segment_times(BLUE_TIMES))
    metro_segs.extend(generate_segment_times(RED_TIMES))
    metro_segs.extend(generate_segment_times(VIOLET_TIMES))

    # Write clean combined segments
    seg_fields = ["agency", "from_stop_id", "to_stop_id", "median_minutes", "sample_count"]

    with open(seg_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=seg_fields)
        writer.writeheader()
        writer.writerows(non_metro_segs)
        writer.writerows(metro_segs)

    print(f"Written clean {len(non_metro_segs)} non-metro + {len(metro_segs)} metro segments to segment_times.csv")
