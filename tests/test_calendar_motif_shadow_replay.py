"""A trace-derived Calendar candidate never authorizes stale validation."""

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/replay-calendar-motif-candidate.py"
SPEC = importlib.util.spec_from_file_location("calendar_motif_replay", SCRIPT)
assert SPEC and SPEC.loader
REPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPLAY)


def candidate():
    return {"status": "candidate_only_requires_independent_heldout",
            "online_execution_allowed": False,
            "output_edges": [
                {"from_field": "earliest.start", "to_param": "candidateStart"},
                {"from_field": "earliest.end", "to_param": "candidateEnd"}],
            "argument_carryover": [
                {"from_param": key, "to_param": key}
                for key in ("calendarId", "timeZone", "timeWindows", "durationMinutes")]}


def test_copies_witnessed_values_and_rejects_stale_source():
    root = {"calendarId": "test", "timeZone": "Asia/Shanghai",
            "timeWindows": [{"start": "2026-10-16T09:00:00+08:00",
                             "end": "2026-10-16T12:00:00+08:00"}],
            "durationMinutes": 55, "maxCandidates": 5}
    found = {"status": "available", "sourceSha256": "a" * 64,
             "earliest": {"start": "2026-10-16T11:00:00+08:00",
                          "end": "2026-10-16T11:55:00+08:00"}}
    proposed = REPLAY.proposed_arguments(candidate(), root, found)
    assert proposed["candidateStart"] == found["earliest"]["start"]
    assert proposed["durationMinutes"] == 55
    assert "maxCandidates" not in proposed
    assert REPLAY.check_result(found, {"sourceSha256": "a" * 64,
                                       "valid": True, "isEarliest": True})
    assert not REPLAY.check_result(found, {"sourceSha256": "b" * 64,
                                           "valid": True, "isEarliest": True})
    assert not REPLAY.check_result(found, {"sourceSha256": "a" * 64,
                                           "valid": False, "isEarliest": True})
    with pytest.raises(ValueError):
        REPLAY.proposed_arguments(candidate(), root, {**found, "status": "no_slot"})
