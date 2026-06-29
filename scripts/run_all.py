"""
End-to-end orchestrator. Runs scrape -> normalize -> validate -> export.

Use:
    python scripts/run_all.py                # full run, all agencies
    python scripts/run_all.py --sample       # quick smoke test (5 routes per agency)
    python scripts/run_all.py --skip-scrape  # re-build from existing data/raw/
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=REPO)
    if r.returncode != 0:
        print(f"FAILED ({r.returncode}): {' '.join(cmd)}", file=sys.stderr)
        sys.exit(r.returncode)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="Limit per-route fetches to 5 per agency")
    ap.add_argument("--skip-scrape", action="store_true")
    ap.add_argument("--skip-osm", action="store_true")
    args = ap.parse_args()

    if not args.skip_scrape:
        rl = ["--route-limit", "5"] if args.sample else []
        run([sys.executable, "-m", "scripts.scrapers.bus_api", "brt", *rl])
        run([sys.executable, "-m", "scripts.scrapers.bus_api", "municipal_bus", *rl])
        run([sys.executable, "-m", "scripts.scrapers.metro_site"])
        if not args.skip_osm:
            run([sys.executable, "-m", "scripts.scrapers.osm"])

    norm_args = ["--skip-osm-crosscheck"] if args.skip_osm else []
    run([sys.executable, "-m", "scripts.verify.normalize", *norm_args])

    # Schema validation
    for name, schema in (
        ("stops", "stop.schema.json"),
        ("routes", "route.schema.json"),
        ("fares", "fare.schema.json"),
    ):
        run([
            sys.executable, "-m", "scripts.verify.validate",
            f"data/normalized/{name}.json", f"schemas/{schema}",
        ])

    run([sys.executable, "-m", "scripts.export.build_outputs"])
    run([sys.executable, "-m", "scripts.export.coverage_report"])
    print("\nALL DONE. See data/processed/ for outputs.")


if __name__ == "__main__":
    main()
