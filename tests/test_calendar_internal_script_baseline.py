"""Boundary and invalidation checks for the calendar fixture's deterministic comparator."""

import importlib.util
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "calendar_script_baseline", ROOT / "scripts/run-calendar-internal-script-baseline.py")
assert SPEC and SPEC.loader
baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baseline)


class CalendarSlotTests(unittest.TestCase):
    def test_end_at_next_busy_start_is_valid(self) -> None:
        task = next(row for row in baseline.TASKS if row["id"] == "B")
        busy = [
            (datetime.fromisoformat("2026-10-13T14:30:00+08:00"),
             datetime.fromisoformat("2026-10-13T15:30:00+08:00")),
            (datetime.fromisoformat("2026-10-13T16:15:00+08:00"),
             datetime.fromisoformat("2026-10-13T17:00:00+08:00")),
        ]
        result = baseline.earliest_slot(task, busy)
        self.assertEqual(result[0].isoformat(), "2026-10-13T15:30:00+08:00")
        self.assertEqual(result[1].isoformat(), "2026-10-13T16:15:00+08:00")

    def test_new_conflict_breaks_old_recommendation(self) -> None:
        task = next(row for row in baseline.TASKS if row["id"] == "C")
        old = [
            (datetime.fromisoformat("2026-10-14T10:00:00+08:00"),
             datetime.fromisoformat("2026-10-14T11:00:00+08:00")),
            (datetime.fromisoformat("2026-10-14T14:00:00+08:00"),
             datetime.fromisoformat("2026-10-14T15:00:00+08:00")),
        ]
        self.assertEqual(baseline.earliest_slot(task, old)[0].hour, 11)
        changed = old + [
            (datetime.fromisoformat("2026-10-14T11:30:00+08:00"),
             datetime.fromisoformat("2026-10-14T12:30:00+08:00")),
        ]
        self.assertEqual(baseline.earliest_slot(task, changed)[0].isoformat(),
                         "2026-10-14T15:00:00+08:00")


if __name__ == "__main__":
    unittest.main()
