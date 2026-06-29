"""
Add the 3 missing BRT route sequences to route_stops.csv:
  - brt-4E-LJ  : L.D. Engineering College → Jaimangal (14 stops, ~17 min)
  - brt-14U-SO : Sanand Circle → Naroda Gam (32 stops, ~53 min)
  - brt-15E-IJ : Iskcon Cross Road → Jaimangal (12 stops, ~17 min)

Stop IDs matched from stops.csv.
Median minutes per segment = total_time / (n_stops - 1).
Bhavani Tractors (Railway Overbridge) has no existing stop_id — added as brt-bhavani-rob.
"""

import csv, os, math

DATA = os.path.join(os.path.dirname(__file__), '..', 'final', 'transit', 'data')

def seg(total_mins, n_stops):
    """Evenly distribute total journey time across (n_stops - 1) segments."""
    return round(total_mins / (n_stops - 1), 1)

# ── Route definitions ─────────────────────────────────────────────────────────

ROUTES = {
    # Route 4E: L.D. Engineering College → Jaimangal (14 stops, 17 min)
    'brt-4E-LJ': {
        'total_mins': 17,
        'stops': [
            ('brt-266',          'L.D. Engineering College'),
            ('brt-233',          'Gulbai Tekra Approach'),
            ('brt-231',          'Panjrapole Char Rasta'),
            ('brt-229',          'L Colony'),
            ('brt-31',           'Nehrunagar'),
            ('brt-29',           'Jhansi Ki Rani'),
            ('brt-27',           'Shivranjani'),
            ('brt-25',           'Himmatlal Park'),
            ('brt-23',           'Andhjan Mandal'),
            ('brt-21',           'University'),
            ('brt-19',           'Memnagar'),
            ('brt-17',           'Shree Valinath Chowk'),
            ('brt-15',           'Sola Cross Road'),
            ('brt-13',           'Jaimangal'),
        ],
    },

    # Route 14U-SO: Sanand Circle → Naroda Gam (32 stops, 53 min)
    'brt-14U-SO': {
        'total_mins': 53,
        'stops': [
            ('brt-348',          'Sanand Circle'),
            ('brt-bhavani-rob',  'Bhavani Tractors (Railway Overbridge)'),  # new stop
            ('brt-382',          'Ambar Tower'),
            ('brt-380',          'Khurshid Park'),
            ('brt-378',          'Juhapura Road'),
            ('brt-6865',         'Sarani Kamdar Society'),
            ('brt-374',          'Pravinnagar'),
            ('brt-274',          'Vasna'),
            ('brt-37',           'Anjali'),
            ('brt-39',           'Chandranagar'),
            ('brt-41',           'Khodiyarnagar'),
            ('brt-43',           'Danilimda Char Rasta'),
            ('brt-45',           'Vaikunth Dham Mandir'),
            ('brt-47',           'Swaminarayan College'),
            ('brt-259',          'Mangal Park'),
            ('brt-257',          'Bhulabhai Park'),
            ('brt-255',          'Geeta Mandir'),
            ('brt-197',          'Raipur Darwaja'),
            ('brt-199',          'Karnamukteshwar Mahadev'),
            ('brt-201',          'Sarangpur Darwaja'),
            ('brt-203',          'Kalupur'),
            ('brt-249',          'G.C.S. Hospital'),
            ('brt-247',          'Arvind Mill'),
            ('brt-245',          'Jeening Press'),
            ('brt-243',          'Ashok Mill'),
            ('brt-241',          'Naroda Fruit Market'),
            ('brt-239',          'Memco Cross Road'),
            ('brt-237',          'Municipal North Zone Office'),
            ('brt-261',          'Saijpur Towers'),
            ('brt-121',          'Naroda S.T. Workshop'),
            ('brt-271',          'Bethak'),
            ('brt-273',          'Naroda Gam'),
        ],
    },

    # Route 15E-IJ: Iskcon Cross Road → Jaimangal (12 stops, 17 min)
    'brt-15E-IJ': {
        'total_mins': 17,
        'stops': [
            ('brt-143',          'ISKCON Cross Road'),
            ('brt-141',          'Ramdevnagar'),
            ('brt-139',          'ISRO'),
            ('brt-137',          'Star Bazaar'),
            ('brt-135',          'Jodhpur Char Rasta'),
            ('brt-25',           'Himmatlal Park'),
            ('brt-23',           'Andhjan Mandal'),
            ('brt-21',           'University'),
            ('brt-19',           'Memnagar'),
            ('brt-17',           'Shree Valinath Chowk'),
            ('brt-15',           'Sola Cross Road'),
            ('brt-13',           'Jaimangal'),
        ],
    },
}

# ── Route metadata (for routes.csv) ──────────────────────────────────────────

ROUTE_META = {
    'brt-4E-LJ': {
        'route_code': '4E-LJ',
        'customer_route_code': '4E',
        'headsign': 'L.D. Engineering College - Jaimangal',
        'first_departure': '06:00:00',
        'last_departure': '22:00:00',
    },
    # 14U-SO already exists in routes.csv — no new row needed
    # 15E-IJ already exists in routes.csv — no new row needed
}

NEW_STOP = {
    'stop_id': 'brt-bhavani-rob',
    'agency': 'brt',
    'name': 'Bhavani Tractors (Railway Overbridge)',
    'lat': '23.0073',    # approximate — near Sanand Road / Bhavani area
    'lon': '72.5265',
    'coord_source': 'manual',
    'stop_type': 'BRT',
    'interchange_group_id': '',
    'route_codes': '["14U"]',
    'sources': '["manual"]',
    'scraped_at': '2026-05-18T14:37:25+00:00',
}


def main():
    rs_path     = os.path.join(DATA, 'route_stops.csv')
    routes_path = os.path.join(DATA, 'routes.csv')
    stops_path  = os.path.join(DATA, 'stops.csv')

    # ── Load existing data ────────────────────────────────────────────────────
    with open(rs_path, encoding='utf-8') as f:
        existing_rs = list(csv.DictReader(f))
    rs_fields = list(existing_rs[0].keys()) if existing_rs else ['route_id','sequence','stop_id','stop_name','median_minutes_to_next']

    with open(routes_path, encoding='utf-8') as f:
        existing_routes = list(csv.DictReader(f))
    rt_fields = list(existing_routes[0].keys())

    with open(stops_path, encoding='utf-8') as f:
        existing_stops = list(csv.DictReader(f))
    stops_fields = list(existing_stops[0].keys())

    existing_rs_routes = set(r['route_id'] for r in existing_rs)
    existing_stop_ids  = set(s['stop_id'] for s in existing_stops)
    existing_route_ids = set(r['route_id'] for r in existing_routes)

    new_rs_rows  = []
    new_rt_rows  = []
    new_stop_rows = []

    # ── Add new stop (Bhavani Tractors) ──────────────────────────────────────
    if NEW_STOP['stop_id'] not in existing_stop_ids:
        new_stop_rows.append({f: NEW_STOP.get(f, '') for f in stops_fields})
        print(f"Adding new stop: {NEW_STOP['stop_id']} — {NEW_STOP['name']}")

    # ── Build route_stops rows ────────────────────────────────────────────────
    for route_id, defn in ROUTES.items():
        if route_id in existing_rs_routes:
            print(f"Skipping {route_id} — already in route_stops")
            continue

        stops_list = defn['stops']
        n = len(stops_list)
        mins_per_seg = seg(defn['total_mins'], n)

        for seq, (stop_id, stop_name) in enumerate(stops_list, 1):
            is_terminal = (seq == n)
            new_rs_rows.append({
                'route_id':              route_id,
                'sequence':              seq,
                'stop_id':               stop_id,
                'stop_name':             stop_name,
                'median_minutes_to_next': '' if is_terminal else mins_per_seg,
            })

        # ── Add to routes.csv if not already there ────────────────────────────
        if route_id not in existing_route_ids and route_id in ROUTE_META:
            meta = ROUTE_META[route_id]
            row = {f: '' for f in rt_fields}
            row['route_id']             = route_id
            row['agency']               = 'brt'
            row['route_code']           = meta['route_code']
            row['customer_route_code']  = meta['customer_route_code']
            row['headsign']             = meta['headsign']
            row['first_departure']      = meta['first_departure']
            row['last_departure']       = meta['last_departure']
            row['scraped_at']           = '2026-05-18T14:37:25+00:00'
            new_rt_rows.append(row)

        print(f"Added {n} stop entries for {route_id} ({mins_per_seg} min/seg)")

    # ── Write back ────────────────────────────────────────────────────────────

    # stops.csv
    if new_stop_rows:
        with open(stops_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=stops_fields, extrasaction='ignore')
            w.writeheader()
            w.writerows(existing_stops)
            w.writerows(new_stop_rows)

    # route_stops.csv
    with open(rs_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=rs_fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(existing_rs)
        w.writerows(new_rs_rows)

    # routes.csv
    if new_rt_rows:
        with open(routes_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=rt_fields, extrasaction='ignore')
            w.writeheader()
            w.writerows(existing_routes)
            w.writerows(new_rt_rows)

    print()
    print(f"route_stops.csv : {len(existing_rs) + len(new_rs_rows)} rows (+{len(new_rs_rows)})")
    print(f"routes.csv      : {len(existing_routes) + len(new_rt_rows)} rows (+{len(new_rt_rows)})")
    print(f"stops.csv       : {len(existing_stops) + len(new_stop_rows)} rows (+{len(new_stop_rows)})")
    print("Done.")


if __name__ == '__main__':
    main()
