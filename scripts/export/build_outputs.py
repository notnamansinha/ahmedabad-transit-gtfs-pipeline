"""
Build data/processed/ outputs from data/normalized/ records.

Outputs (every record set, four formats):
    data/processed/json/stops.json             data/processed/csv/stops.csv
    data/processed/json/routes.json            data/processed/csv/routes.csv  + data/processed/csv/route_stops.csv
    data/processed/json/fares.json             data/processed/csv/fares.csv
    data/processed/geojson/stops.geojson
    data/processed/geojson/routes.geojson
    data/processed/sqlite/transit.db
    data/processed/checksums.csv               (SHA-256 per output file)

Naming convention: snake_case, no agency in filename (agency is a column).

Why all four: each downstream tool prefers a different format. Routing
engines like GeoJSON LineStrings. Analytics ingests CSV. App backends
hit SQLite directly. JSON is the canonical schema-validated form.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


REPO = Path(__file__).resolve().parents[2]
NORM = REPO / "data" / "normalized"
FINAL = REPO / "data" / "processed"


def _read(path: Path) -> list[dict]:
    return json.loads(path.read_text()) if path.exists() else []


def write_csv(rows: list[dict], path: Path, fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            # Serialize complex fields
            out = {}
            for k in fields:
                v = r.get(k)
                if isinstance(v, (list, dict)):
                    out[k] = json.dumps(v, separators=(",", ":"))
                else:
                    out[k] = v
            w.writerow(out)


def write_json(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2))


def write_stops_geojson(stops: list[dict], path: Path) -> None:
    features = []
    for s in stops:
        if s.get("lat") is None or s.get("lon") is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
            "properties": {
                "stop_id": s["stop_id"],
                "name": s["name"],
                "agency": s["agency"],
                "route_codes": s["route_codes"],
                "interchange_group_id": s.get("interchange_group_id"),
            },
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def write_routes_geojson(routes: list[dict], path: Path) -> None:
    features = []
    for r in routes:
        geom = r.get("geometry")
        if not geom:
            continue
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "route_id": r["route_id"],
                "agency": r["agency"],
                "route_code": r["route_code"],
                "customer_route_code": r["customer_route_code"],
                "headsign": r["headsign"],
                "first_departure": r["first_departure"],
                "last_departure": r["last_departure"],
            },
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def build_sqlite(
    stops: list[dict],
    routes: list[dict],
    fares: list[dict],
    segments: list[dict],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    c = conn.cursor()
    # FK enforcement is OFF during load to tolerate the small number of
    # orphan stop_ids the upstream API occasionally returns (logged in
    # data/normalized/verification.json -> orphan_stop_refs_in_routes). The FK
    # *constraints* still exist as schema documentation; analytics tools
    # that want enforcement can run `PRAGMA foreign_keys = ON;` and
    # `PRAGMA foreign_key_check;` against the loaded DB.
    c.executescript("""

    CREATE TABLE stops (
      stop_id TEXT PRIMARY KEY,
      agency TEXT NOT NULL,
      name TEXT NOT NULL,
      lat REAL,
      lon REAL,
      coord_source TEXT,
      stop_type TEXT,
      interchange_group_id TEXT,
      sources_json TEXT,
      scraped_at TEXT
    );
    CREATE INDEX idx_stops_agency ON stops(agency);
    CREATE INDEX idx_stops_name ON stops(name);
    CREATE INDEX idx_stops_interchange ON stops(interchange_group_id);

    CREATE TABLE routes (
      route_id TEXT PRIMARY KEY,
      agency TEXT NOT NULL,
      route_code TEXT NOT NULL,
      customer_route_code TEXT,
      headsign TEXT,
      variant TEXT,
      start_stop_id TEXT,
      end_stop_id TEXT,
      first_departure TEXT,
      last_departure TEXT,
      operating_days_json TEXT,
      geometry_json TEXT,
      sources_json TEXT,
      scraped_at TEXT,
      FOREIGN KEY(start_stop_id) REFERENCES stops(stop_id),
      FOREIGN KEY(end_stop_id) REFERENCES stops(stop_id)
    );
    CREATE INDEX idx_routes_agency ON routes(agency);
    CREATE INDEX idx_routes_customer ON routes(customer_route_code);

    CREATE TABLE route_stops (
      route_id TEXT NOT NULL,
      sequence INTEGER NOT NULL,
      stop_id TEXT NOT NULL,
      stop_name TEXT,
      median_minutes_to_next REAL,
      PRIMARY KEY (route_id, sequence),
      FOREIGN KEY(route_id) REFERENCES routes(route_id),
      FOREIGN KEY(stop_id) REFERENCES stops(stop_id)
    );
    CREATE INDEX idx_route_stops_stop ON route_stops(stop_id);

    CREATE TABLE segment_times (
      agency TEXT NOT NULL,
      from_stop_id TEXT NOT NULL,
      to_stop_id TEXT NOT NULL,
      median_minutes REAL NOT NULL,
      sample_count INTEGER NOT NULL,
      PRIMARY KEY (agency, from_stop_id, to_stop_id),
      FOREIGN KEY(from_stop_id) REFERENCES stops(stop_id),
      FOREIGN KEY(to_stop_id) REFERENCES stops(stop_id)
    );
    CREATE INDEX idx_segment_from ON segment_times(from_stop_id);

    CREATE TABLE fares (
      agency TEXT NOT NULL,
      from_stop_id TEXT NOT NULL,
      to_stop_id TEXT NOT NULL,
      from_stop_name TEXT,
      to_stop_name TEXT,
      fare_inr REAL NOT NULL,
      service_class TEXT NOT NULL,
      PRIMARY KEY (agency, from_stop_id, to_stop_id, service_class)
    );
    CREATE INDEX idx_fares_from ON fares(from_stop_id);
    CREATE INDEX idx_fares_to ON fares(to_stop_id);
    """)

    c.executemany(
        """INSERT INTO stops(stop_id, agency, name, lat, lon, coord_source, stop_type,
           interchange_group_id, sources_json, scraped_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                s["stop_id"], s["agency"], s["name"], s.get("lat"), s.get("lon"),
                s.get("coord_source"), s.get("stop_type"), s.get("interchange_group_id"),
                json.dumps(s.get("sources", [])), s["scraped_at"],
            )
            for s in stops
        ],
    )

    c.executemany(
        """INSERT INTO routes(route_id, agency, route_code, customer_route_code,
           headsign, variant, start_stop_id, end_stop_id, first_departure,
           last_departure, operating_days_json, geometry_json, sources_json, scraped_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                r["route_id"], r["agency"], r["route_code"], r.get("customer_route_code"),
                r.get("headsign"), r.get("variant"), r.get("start_stop_id"),
                r.get("end_stop_id"), r["first_departure"], r["last_departure"],
                json.dumps(r.get("operating_days", [])),
                json.dumps(r.get("geometry")) if r.get("geometry") else None,
                json.dumps(r.get("sources", [])),
                r["scraped_at"],
            )
            for r in routes
        ],
    )

    rs_rows = []
    for r in routes:
        for s in r.get("stop_sequence", []):
            rs_rows.append(
                (
                    r["route_id"],
                    s["sequence"],
                    s["stop_id"],
                    s.get("stop_name"),
                    s.get("median_minutes_to_next"),
                )
            )
    # Drop duplicate (route_id, sequence) — some API responses repeat
    rs_seen: set[tuple[str, int]] = set()
    rs_clean = []
    for row in rs_rows:
        key = (row[0], row[1])
        if key in rs_seen:
            continue
        rs_seen.add(key)
        rs_clean.append(row)
    c.executemany(
        """INSERT INTO route_stops(route_id, sequence, stop_id, stop_name,
           median_minutes_to_next) VALUES(?,?,?,?,?)""",
        rs_clean,
    )

    c.executemany(
        """INSERT INTO segment_times(agency, from_stop_id, to_stop_id,
           median_minutes, sample_count) VALUES(?,?,?,?,?)""",
        [
            (
                s["agency"],
                s["from_stop_id"],
                s["to_stop_id"],
                s["median_minutes"],
                s["sample_count"],
            )
            for s in segments
        ],
    )

    # Deduplicate fares — the matrix has commutative-but-not-equal entries
    fare_seen: set[tuple[str, str, str, str]] = set()
    fare_rows = []
    for f in fares:
        k = (f["agency"], f["from_stop_id"], f["to_stop_id"], f["service_class"])
        if k in fare_seen:
            continue
        fare_seen.add(k)
        fare_rows.append(
            (
                f["agency"], f["from_stop_id"], f["to_stop_id"],
                f.get("from_stop_name"), f.get("to_stop_name"),
                f["fare_inr"], f["service_class"],
            )
        )
    c.executemany(
        """INSERT INTO fares(agency, from_stop_id, to_stop_id, from_stop_name,
           to_stop_name, fare_inr, service_class) VALUES(?,?,?,?,?,?,?)""",
        fare_rows,
    )

    conn.commit()
    conn.close()


def write_checksums(out_dir: Path) -> None:
    rows: list[tuple[str, str, int]] = []
    for p in sorted(out_dir.rglob("*")):
        if p.is_dir() or p.name == "checksums.csv":
            continue
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        rows.append((str(p.relative_to(out_dir)), h, p.stat().st_size))
    path = out_dir / "checksums.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "sha256", "bytes"])
        w.writerows(rows)


STOP_FIELDS = [
    "stop_id", "agency", "name", "lat", "lon", "coord_source", "stop_type",
    "interchange_group_id", "route_codes", "sources", "scraped_at",
]
ROUTE_FIELDS = [
    "route_id", "agency", "route_code", "customer_route_code", "headsign",
    "variant", "start_stop_id", "end_stop_id", "first_departure",
    "last_departure", "operating_days", "sources", "scraped_at",
]
ROUTE_STOP_FIELDS = [
    "route_id", "sequence", "stop_id", "stop_name", "median_minutes_to_next",
]
SEGMENT_FIELDS = [
    "agency", "from_stop_id", "to_stop_id", "median_minutes", "sample_count",
]
FARE_FIELDS = [
    "agency", "from_stop_id", "to_stop_id", "from_stop_name", "to_stop_name",
    "fare_inr", "service_class", "scraped_at",
]


def main() -> None:
    stops = _read(NORM / "stops.json")
    routes = _read(NORM / "routes.json")
    fares = _read(NORM / "fares.json")
    segments = _read(NORM / "segment_times.json")
    print(
        f"[export] stops={len(stops)} routes={len(routes)} "
        f"fares={len(fares)} segments={len(segments)}"
    )

    write_json(stops, FINAL / "json" / "stops.json")
    write_json(routes, FINAL / "json" / "routes.json")
    write_json(fares, FINAL / "json" / "fares.json")
    write_json(segments, FINAL / "json" / "segment_times.json")

    write_csv(stops, FINAL / "csv" / "stops.csv", STOP_FIELDS)
    write_csv(routes, FINAL / "csv" / "routes.csv", ROUTE_FIELDS)
    rs_flat = []
    for r in routes:
        for s in r.get("stop_sequence", []):
            rs_flat.append({**s, "route_id": r["route_id"]})
    write_csv(rs_flat, FINAL / "csv" / "route_stops.csv", ROUTE_STOP_FIELDS)
    write_csv(fares, FINAL / "csv" / "fares.csv", FARE_FIELDS)
    write_csv(segments, FINAL / "csv" / "segment_times.csv", SEGMENT_FIELDS)

    write_stops_geojson(stops, FINAL / "geojson" / "stops.geojson")
    write_routes_geojson(routes, FINAL / "geojson" / "routes.geojson")

    build_sqlite(stops, routes, fares, segments, FINAL / "sqlite" / "transit.db")

    write_checksums(FINAL)
    print(f"[export] wrote outputs under {FINAL}/")


if __name__ == "__main__":
    main()
