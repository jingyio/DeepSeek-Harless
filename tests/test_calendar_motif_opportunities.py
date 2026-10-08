"""The Calendar continuation audit must reject stale or unwitnessed paths."""

import copy
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit-calendar-motif-opportunities.py"
SPEC = importlib.util.spec_from_file_location("calendar_motif_audit", SCRIPT)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def fixture():
    find_id, validate_id = "find-call", "validate-call"
    common = {"calendarId": "test", "timeZone": "Asia/Shanghai",
              "timeWindows": [{"start": "2026-10-16T09:00:00+08:00",
                               "end": "2026-10-16T12:00:00+08:00"}],
              "durationMinutes": 55}
    calls = [
        {"name": "mcp__calendar_fixture__find-available-slots", "callId": find_id,
         "step": 2, "arguments": json.dumps(common)},
        {"name": "mcp__calendar_fixture__validate-slot", "callId": validate_id,
         "step": 3, "arguments": json.dumps({**common,
             "candidateStart": "2026-10-16T11:00:00+08:00",
             "candidateEnd": "2026-10-16T11:55:00+08:00"})},
    ]
    results = {
        find_id: {"earliest": {"start": "2026-10-16T11:00:00+08:00",
                                "end": "2026-10-16T11:55:00+08:00"},
                  "sourceSha256": "a" * 64},
        validate_id: {"valid": True, "isEarliest": True,
                      "sourceSha256": "a" * 64},
    }
    return calls, results


def test_witness_and_stale_source():
    calls, results = fixture()
    assert AUDIT.witnessed_continuation(calls, results)["witnessed"]
    changed = copy.deepcopy(results)
    changed["validate-call"]["sourceSha256"] = "b" * 64
    check = AUDIT.witnessed_continuation(calls, changed)
    assert not check["witnessed"] and not check["checks"]["same_fresh_source"]


def test_wrong_parameters_or_same_model_step_cannot_certify():
    calls, results = fixture()
    changed = copy.deepcopy(calls)
    args = json.loads(changed[1]["arguments"])
    args["durationMinutes"] = 45
    changed[1]["arguments"] = json.dumps(args)
    assert not AUDIT.witnessed_continuation(changed, results)["witnessed"]
    parallel = copy.deepcopy(calls)
    parallel[1]["step"] = 2
    assert not AUDIT.witnessed_continuation(parallel, results)["witnessed"]
