"""
Operating-days normalization.

The BRT/MUNICIPAL_BUS API returns `days` as a comma-separated string where 1=Sunday,
2=Monday, ..., 7=Saturday (the .NET / SQL Server DATEPART convention).

We normalize everything to ISO 8601: 1=Monday ... 7=Sunday.

If anyone changes one of these mappings without thinking, every downstream
"is this route running today" check breaks silently. So we keep the two
conversion functions tiny, named, and tested below in __main__.
"""

from __future__ import annotations


# Upstream convention -> ISO day number
_API_TO_ISO = {1: 7, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6}


def api_days_to_iso(raw: str) -> list[int]:
    """Convert API days string ('1,2,3,4,5,6,7' = all week) to ISO day list.

    Returns sorted unique ISO day numbers (1=Mon..7=Sun).
    """
    if not raw:
        return []
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            api_day = int(part)
        except ValueError:
            continue
        iso = _API_TO_ISO.get(api_day)
        if iso:
            out.add(iso)
    return sorted(out)


def iso_days_human(days: list[int]) -> str:
    """Render ISO day list as human text, condensing common patterns."""
    if not days:
        return "no service"
    s = set(days)
    if s == {1, 2, 3, 4, 5, 6, 7}:
        return "daily"
    if s == {1, 2, 3, 4, 5}:
        return "weekdays"
    if s == {6, 7}:
        return "weekends"
    labels = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
    return ", ".join(labels[d] for d in sorted(days))


if __name__ == "__main__":
    assert api_days_to_iso("1,2,3,4,5,6,7") == [1, 2, 3, 4, 5, 6, 7]
    assert iso_days_human([1, 2, 3, 4, 5, 6, 7]) == "daily"
    assert api_days_to_iso("1") == [7]  # API day 1 == Sunday == ISO 7
    assert api_days_to_iso("2") == [1]  # API day 2 == Monday == ISO 1
    assert api_days_to_iso("") == []
    assert iso_days_human([1, 2, 3, 4, 5]) == "weekdays"
    print("days.py self-tests ok")
