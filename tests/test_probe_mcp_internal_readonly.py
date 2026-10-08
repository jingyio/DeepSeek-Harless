"""The live MCP probe must not count provider-level failures as success."""

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/probe-mcp-internal-readonly.py"
SPEC = importlib.util.spec_from_file_location("probe_mcp_internal_readonly", SCRIPT)
assert SPEC and SPEC.loader
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class ProbeMCPInternalReadonlyTests(unittest.TestCase):
    def test_provider_unavailable_is_failure_even_when_mcp_call_succeeds(self) -> None:
        reply = SimpleNamespace(is_error=False, structured_content={
            "status": "unavailable", "papers": [], "provider_error": "rate limited"})
        self.assertFalse(PROBE.ok(reply))

    def test_successful_response_without_status_field_is_accepted(self) -> None:
        reply = SimpleNamespace(is_error=False, structured_content={"message_ids": ["x"]})
        self.assertTrue(PROBE.ok(reply))


if __name__ == "__main__":
    unittest.main()
