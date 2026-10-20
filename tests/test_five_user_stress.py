"""Free accounting regression: real task discovery and durable ledger receipts."""
import importlib.util
import json
from pathlib import Path
from threading import RLock
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("five_user_stress", ROOT / "scripts/check-five-user-stress.py")
stress = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stress)


@pytest.mark.parametrize("ends,durations,expected", [
    # Actual calls are [9,10) and [7,12): overlap. Treating their end
    # timestamps as starts gives disjoint [10,11), [12,17) and misses it.
    ((10, 12), (1, 5), 2),
    # Actual calls [5,10), [11,12) are disjoint. The old calculation
    # invents overlapping [10,15), [12,13) instead.
    ((10, 12), (5, 1), 1),
    # Endpoints alone do not overlap: [9,10), [10,12).
    ((10, 12), (1, 2), 1),
    # These millisecond endpoints touch. Binary float subtraction would
    # start the second call at 1760988850.0019999 and invent overlap.
    ((1760988850.002, 1760988850.004), (.001, .002), 1),
    # A genuine millisecond overlap at the same large epoch remains visible.
    ((1760988850.002, 1760988850.004), (.001, .003), 2),
])
def test_accounting_uses_completion_timestamps_for_actual_request_overlap(tmp_path, ends, durations, expected):
    output = tmp_path / "member-output"
    ids = ["a" * 32, "b" * 32]
    stress.save(output / "task-index-fixture.json", {"tasks": ids})
    attempts, receipts = [], []
    for index, task_id in enumerate(ids):
        session, request = "native-" + str(index), "request-" + str(index)
        attempts.append({"id": "record-" + str(index), "user_index": 1,
                         "session_id": session, "request_id": request, "sent_at": "diagnostic"})
        stress.save(output / "tasks" / task_id / "task-state.json", {
            "task_id": task_id, "session_id": session, "request_id": request, "status": "completed",
            "stats": {"upstream_requests": 1, "usage_complete": True, "pending_requests": 0,
                      "unknown_usage_requests": 0, "observed_peak_cost_usd": .001},
        })
        receipts.append({"task_id": task_id, "session_id": "turn-" + task_id,
                         "global_request_id": index + 1, "response_status": 200,
                         "observed_peak_usd": .001, "request_utc_epoch": ends[index],
                         "elapsed_seconds": durations[index]})
    # A concurrent request outside these exact discovered tasks must not
    # inflate the experiment's overlap or bill.
    receipts.append({"task_id": "c" * 32, "global_request_id": 999, "response_status": 200,
                     "request_utc_epoch": 100, "elapsed_seconds": 100, "observed_peak_usd": 10})
    ledger = tmp_path / "global-ledger.jsonl"
    ledger.write_text("".join(json.dumps(row) + "\n" for row in receipts), encoding="utf-8")
    runner = stress.Stress.__new__(stress.Stress)
    runner.directory, runner.lock = tmp_path / "audit", RLock()
    runner.args = SimpleNamespace(ledger=ledger)
    runner.result = {"users": [{"index": 1, "output": str(output)}], "attempts": attempts}
    result = runner.accounting()
    assert result["accounting_complete"] is True
    assert result["upstream_requests"] == 2 and result["estimated_cost_usd"] == .002
    assert result["max_overlapping_upstream_requests"] == expected
    assert result["upstream_requests_without_intervals"] == 0


def test_invalid_or_unknown_duration_does_not_invent_an_interval():
    for receipt in ({}, {"request_utc_epoch": 10, "elapsed_seconds": 0},
                    {"request_utc_epoch": 10, "elapsed_seconds": float("inf")},
                    {"request_utc_epoch": True, "elapsed_seconds": 1}):
        assert stress.upstream_interval(receipt) is None
