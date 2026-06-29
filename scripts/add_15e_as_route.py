"""
Add Route 15E-AS: Iskcon Cross Road → Chandkheda Gam (extended night service)
Full 23-stop sequence verified from 2026 scheduling data.

Two logical segments:
  Core (stops 1–13):  Iskcon → Jaimangal → Shastrinagar  (~20 min)
  Extended (14–23):   Shastrinagar → Chandkheda Gam       (~22 min, evening only ~22:25)

Total journey: ~42 min across 23 stops.
Segment time: 42 / 22 ≈ 1.9 min per segment.
"""

import csv, os

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'final', 'transit', 'data')

ROUTE_ID = 'brt-15E-AS'
TOTAL_MINS = 42    # full Iskcon → Chandkheda Gam
N_STOPS = 23

def seg(total, n):
    return round(total / (n - 1), 1)

MINS_PER_SEG = seg(TOTAL_MINS, N_STOPS)  # ≈ 1.9

STOPS = [
    # ── Core segment (Iskcon → Shastrinagar) ─────────────────────────
    ('brt-143',  'ISKCON Cross Road'),
    ('brt-141',  'Ramdevnagar'),
    ('brt-139',  'ISRO'),
    ('brt-137',  'Star Bazaar'),
    ('brt-135',  'Jodhpur Char Rasta'),
    ('brt-25',   'Himmatlal Park'),
    ('brt-23',   'Andhjan Mandal'),
    ('brt-21',   'University'),
    ('brt-19',   'Memnagar'),
    ('brt-17',   'Shree Valinath Chowk'),
    ('brt-15',   'Sola Cross Road'),
    ('brt-13',   'Jaimangal'),
    ('brt-11',   'Shastrinagar'),
    # ── Extended segment (Shastrinagar → Chandkheda Gam) ─────────────
    ('brt-10',   'Pragatinagar'),
    ('brt-7',    'Akhbarnagar'),
    ('brt-5',    'Bhavsar Hostel'),
    ('brt-3',    'Ranip Cross Road'),
    ('brt-1',    'R.T.O. Circle'),
    ('brt-175',  'Rathi Apartment'),
    ('brt-177',  'Sabarmati Municipal Swimming Pool'),
    ('brt-179',  'Sabarmati Police Station'),
    ('brt-181',  'Motera Cross Road'),
    ('brt-225',  'Chandkheda Gam'),
]

assert len(STOPS) == N_STOPS, f"Expected {N_STOPS} stops, got {len(STOPS)}"


def main():
    rs_path     = os.path.join(DATA, 'route_stops.csv')
    routes_path = os.path.join(DATA, 'routes.csv')

    # ── Load existing data ────────────────────────────────────────────────────
    with open(rs_path, encoding='utf-8') as f:
        existing_rs = list(csv.DictReader(f))
    rs_fields = list(existing_rs[0].keys())

    with open(routes_path, encoding='utf-8') as f:
        existing_routes = list(csv.DictReader(f))
    rt_fields = list(existing_routes[0].keys())

    # ── Check if already present ──────────────────────────────────────────────
    existing_rs_ids = set(r['route_id'] for r in existing_rs)
    if ROUTE_ID in existing_rs_ids:
        old = [r for r in existing_rs if r['route_id'] == ROUTE_ID]
        print(f"{ROUTE_ID} already has {len(old)} entries — replacing with verified 23-stop sequence.")
        existing_rs = [r for r in existing_rs if r['route_id'] != ROUTE_ID]

    # ── Build new route_stop rows ─────────────────────────────────────────────
    new_rs_rows = []
    for seq, (stop_id, stop_name) in enumerate(STOPS, 1):
        is_terminal = (seq == N_STOPS)
        new_rs_rows.append({
            'route_id':               ROUTE_ID,
            'sequence':               seq,
            'stop_id':                stop_id,
            'stop_name':              stop_name,
            'median_minutes_to_next': '' if is_terminal else MINS_PER_SEG,
        })

    # ── Update route metadata if needed ──────────────────────────────────────
    existing_route_ids = {r['route_id'] for r in existing_routes}
    new_route_rows = []
    if ROUTE_ID not in existing_route_ids:
        row = {f: '' for f in rt_fields}
        row['route_id']            = ROUTE_ID
        row['agency']              = 'brt'
        row['route_code']          = '15E-AS'
        row['customer_route_code'] = '15E'
        row['headsign']            = 'Iskcon Cross Road - Chandkheda Gam'
        row['first_departure']     = '22:25:00'
        row['last_departure']      = '22:45:00'
        row['scraped_at']          = '2026-05-18T14:37:25+00:00'
        new_route_rows.append(row)
    else:
        # Update the headsign to reflect full route
        for r in existing_routes:
            if r['route_id'] == ROUTE_ID:
                r['headsign'] = 'Iskcon Cross Road - Chandkheda Gam'

    # ── Write route_stops.csv ─────────────────────────────────────────────────
    all_rs = existing_rs + new_rs_rows
    with open(rs_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=rs_fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(all_rs)

    # ── Write routes.csv ──────────────────────────────────────────────────────
    all_routes = existing_routes + new_route_rows
    with open(routes_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=rt_fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(all_routes)

    print(f"Route:  {ROUTE_ID}")
    print(f"Stops:  {N_STOPS}  ({MINS_PER_SEG} min/segment, {TOTAL_MINS} min total)")
    print(f"Core:   ISKCON Cross Road → Shastrinagar (stops 1–13)")
    print(f"Ext.:   Shastrinagar → Chandkheda Gam (stops 14–23, evening 22:25)")
    print()
    print(f"route_stops.csv : {len(all_rs)} rows")
    print(f"routes.csv      : {len(all_routes)} rows")
    print("Done.")


if __name__ == '__main__':
    main()
