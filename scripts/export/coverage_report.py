"""
Generate data/processed/COVERAGE_REPORT.json — an honest, derived-from-data audit.

Unlike the old FINAL_REPORT.json (which made up "0 failed requests, 4.2
hour generation" claims unsupported by the data), this report is computed
*from* the normalized output. Every number here is reproducible by
re-running the same queries against data/processed/sqlite/transit.db.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
FINAL = REPO / "data" / "processed"
NORM = REPO / "data" / "normalized"


def main() -> None:
    db = FINAL / "sqlite" / "transit.db"
    if not db.exists():
        raise SystemExit("data/processed/sqlite/transit.db not found. Run build_outputs first.")

    conn = sqlite3.connect(db)
    c = conn.cursor()

    def fetch_one(sql: str, *params) -> int:
        c.execute(sql, params)
        return c.fetchone()[0]

    def fetch_dict(sql: str) -> dict:
        c.execute(sql)
        return {r[0]: r[1] for r in c.fetchall()}

    verification = {}
    vpath = NORM / "verification.json"
    if vpath.exists():
        v = json.loads(vpath.read_text())
        verification = {
            "stop_coord_issues_count": len(v.get("stop_coord_issues", [])),
            "stop_dedupe_count": len(v.get("stop_dedupe", [])),
            "osm_coord_disagreements_count": len(v.get("osm_coord_disagreements", [])),
            "routes_missing_sequence_count": len(v.get("routes_missing_sequence", [])),
            "fare_out_of_range_count": len(v.get("fare_out_of_range", [])),
            "fare_unresolved_count": v.get("fare_unresolved_count", 0),
            "orphan_stop_ref_count": v.get("orphan_stop_ref_count", 0),
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "city": "Ahmedabad",
        "stops": {
            "total": fetch_one("SELECT COUNT(*) FROM stops"),
            "by_agency": fetch_dict("SELECT agency, COUNT(*) FROM stops GROUP BY agency"),
            "with_coords_by_agency": fetch_dict(
                "SELECT agency, SUM(CASE WHEN lat IS NOT NULL THEN 1 ELSE 0 END) "
                "FROM stops GROUP BY agency"
            ),
            "interchange_groups": fetch_one(
                "SELECT COUNT(DISTINCT interchange_group_id) FROM stops "
                "WHERE interchange_group_id IS NOT NULL"
            ),
            "stops_in_interchange_groups": fetch_one(
                "SELECT COUNT(*) FROM stops WHERE interchange_group_id IS NOT NULL"
            ),
        },
        "routes": {
            "total": fetch_one("SELECT COUNT(*) FROM routes"),
            "by_agency": fetch_dict("SELECT agency, COUNT(*) FROM routes GROUP BY agency"),
            "by_variant": fetch_dict("SELECT variant, COUNT(*) FROM routes GROUP BY variant"),
            "with_geometry_by_agency": fetch_dict(
                "SELECT agency, SUM(CASE WHEN geometry_json IS NOT NULL THEN 1 ELSE 0 END) "
                "FROM routes GROUP BY agency"
            ),
            "unique_customer_codes_by_agency": fetch_dict(
                "SELECT agency, COUNT(DISTINCT customer_route_code) FROM routes GROUP BY agency"
            ),
        },
        "route_stops": {
            "total": fetch_one("SELECT COUNT(*) FROM route_stops"),
            "routes_with_full_sequence": fetch_one(
                "SELECT COUNT(*) FROM (SELECT route_id FROM route_stops GROUP BY route_id HAVING COUNT(*) >= 2)"
            ),
        },
        "fares": {
            "total": fetch_one("SELECT COUNT(*) FROM fares"),
            "by_agency": fetch_dict("SELECT agency, COUNT(*) FROM fares GROUP BY agency"),
            "min_inr": fetch_one("SELECT MIN(fare_inr) FROM fares"),
            "max_inr": fetch_one("SELECT MAX(fare_inr) FROM fares"),
            "median_inr_approx": _median_fare(c),
        },
        "verification": verification,
        "output_files": [
            str(p.relative_to(REPO)) for p in sorted((FINAL).rglob("*"))
            if p.is_file() and p.name != "COVERAGE_REPORT.json"
        ],
    }

    out = FINAL / "COVERAGE_REPORT.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"[coverage] wrote {out}")
    conn.close()


def _median_fare(c: sqlite3.Cursor) -> float | None:
    """Cheap median: pick the middle row by ORDER BY fare_inr."""
    c.execute("SELECT COUNT(*) FROM fares")
    n = c.fetchone()[0]
    if n == 0:
        return None
    c.execute("SELECT fare_inr FROM fares ORDER BY fare_inr LIMIT 1 OFFSET ?", (n // 2,))
    row = c.fetchone()
    return row[0] if row else None


if __name__ == "__main__":
    main()
