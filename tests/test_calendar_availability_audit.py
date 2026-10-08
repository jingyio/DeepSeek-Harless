"""Guard against missing recommendation formats in the Calendar answer audit."""

import importlib.util
from datetime import datetime
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit-calendar-availability-agent.py"
SPEC = importlib.util.spec_from_file_location("calendar_availability_audit", SCRIPT)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def test_extracts_heading_with_weekday_and_iso_final():
    answer = (
        "## 结论：推荐时段 2026-10-12 10:15–11:15（Asia/Shanghai）\n"
        "**推荐时段：2026-10-13（周二）15:30 – 16:15**\n"
        "**推荐：开始 2026-10-12T10:15:00+08:00，结束 2026-10-12T11:15:00+08:00。**"
    )
    found = AUDIT.recommendations(answer)
    assert len(found) == 3
    assert found[0][0] == datetime.fromisoformat("2026-10-12T10:15:00+08:00")
    assert found[1][1] == datetime.fromisoformat("2026-10-13T16:15:00+08:00")
    assert found[2] == found[0]


def test_extracts_conflicting_recommendations_for_independent_check():
    answer = "推荐时段：2026-10-14 15:00–16:30。\n推荐时段：2026-10-14 14:00–15:30。"
    found = AUDIT.recommendations(answer)
    assert len(found) == 2
    assert found[0] != found[1]
