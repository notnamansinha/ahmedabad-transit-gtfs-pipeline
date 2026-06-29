# transit_future/

Future-facing data and specifications for the Nakshatra Nav transit platform.
None of this is required for the current router to function — everything in `transit_future/` is preparatory work for Phase 2 and Phase 3 features.

---

## Folder Map

```
transit_future/
├── db/
│   └── transit.db              SQLite mirror of all CSV data (20 MB) — for server-side APIs
│
├── gtfs/
│   └── GTFS_SPEC.md            Spec for converting this dataset into standard GTFS feeds
│
├── realtime/
│   └── REALTIME_SPEC.md        Spec for live BRT AVLS + Metro GTFS-RT integration
│
├── headways/
│   └── HEADWAY_SPEC.md         Spec for per-route frequency/headway data collection
│
└── analytics/
    ├── COVERAGE_REPORT.json    Pipeline coverage statistics (stop counts, source breakdown)
    └── checksums.csv           SHA-256 checksums for data integrity verification
```

---

## Priority Order for Future Work

| Priority | Module | Unblocks |
|---|---|---|
| 1 | **Headway data** (`headways/`) | Transfer wait penalty accuracy; schedule-aware routing |
| 2 | **GTFS export** (`gtfs/`) | Google Maps / OSRM / OpenTripPlanner interop |
| 3 | **Real-time feed** (`realtime/`) | Live arrival times; predictive ETAs |
| 4 | **SQLite API** (`db/`) | Server-side route caching; backend search endpoint |

---

*Generated: May 2026 — Ahmedabad Transit DataSync pipeline*
