"""Offline tests: no cloud requests, no API key required."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner, compiler = load("runner"), load("compile_motifs")
PRICING = json.loads((HERE / "pricing.json").read_text(encoding="utf-8"))


class BudgetTests(unittest.TestCase):
    def test_startup_diagnostics_keep_error_but_redact_keys(self):
        text = "Cannot load plugin: detail\nAuthorization: Bearer unit-secret\nsk-1234567890abcdef"
        value = runner.redact_diagnostics(text, ("unit-secret",))
        self.assertIn("Cannot load plugin: detail", value)
        self.assertNotIn("unit-secret", value)
        self.assertNotIn("sk-1234567890abcdef", value)

    def test_real_loopback_http_records_requests_sse_and_usage_without_credentials(self):
        received = []
        usage = {"prompt_tokens": 100, "prompt_cache_hit_tokens": 80, "prompt_cache_miss_tokens": 20,
                 "completion_tokens": 10, "total_tokens": 110}
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append((body, self.headers.get("Authorization")))
                answer = ("data: " + json.dumps({"choices": [], "usage": usage}) + "\n\ndata: [DONE]\n\n").encode()
                self.send_response(200); self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(answer))); self.end_headers(); self.wfile.write(answer)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
            up_worker = threading.Thread(target=upstream.serve_forever, daemon=True); up_worker.start()
            gate = runner.BudgetGate(ledger=root / "global.jsonl", output=root, run_id="test", pricing=PRICING,
                                     key="unit-test-secret", upstream=f"http://127.0.0.1:{upstream.server_port}")
            server = gate.create_server()
            worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
            try:
                body = json.dumps({"model": "deepseek-flash", "messages": [{"role": "user", "content": "分析"}],
                                   "max_tokens": 128, "stream": True}).encode()
                req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/chat/completions", body,
                                             {"Content-Type": "application/json", "Authorization": "Bearer " + gate.local_token})
                with urllib.request.urlopen(req) as response:
                    self.assertIn(b"[DONE]", response.read())
                self.assertEqual(received[0][1], "Bearer unit-test-secret")
                self.assertEqual(received[0][0]["thinking"], {"type": "disabled"})
                self.assertEqual(received[0][0]["stream_options"], {"include_usage": True})
                self.assertEqual(gate.rows[0]["usage"], usage)
                self.assertEqual(len(list((root / "model-requests").glob("*.request.json"))), 1)
                self.assertFalse(any(b"unit-test-secret" in path.read_bytes() for path in root.rglob("*") if path.is_file()))
            finally:
                server.shutdown(); server.server_close(); worker.join(5)
                upstream.shutdown(); upstream.server_close(); up_worker.join(5)

    def test_global_budget_cannot_reset_between_runs_and_partial_usage_stays_reserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = runner.BudgetGate(ledger=root / "ledger.jsonl", output=root, run_id="one", pricing=PRICING,
                                    cap=0.02, output_cap=1000)
            body = json.dumps({"model": "deepseek-flash", "max_tokens": 1000, "messages": []}).encode()
            identifier, reserved, _ = one.book(body)
            one.settle(identifier, reserved, 200, {"total_tokens": 10})
            two = runner.BudgetGate(ledger=root / "ledger.jsonl", output=root, run_id="two", pricing=PRICING,
                                    cap=0.02, output_cap=1000)
            with self.assertRaisesRegex(ValueError, "budget_exhausted"):
                two.book(body)
            self.assertAlmostEqual(one.current_total(), reserved)

    def test_valid_usage_settles_conservatively_and_models_are_restricted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate = runner.BudgetGate(ledger=root / "ledger.jsonl", output=root, run_id="one", pricing=PRICING,
                                     cap=100, output_cap=1000)
            body = json.dumps({"model": "deepseek-flash", "max_tokens": 1000, "messages": []}).encode()
            identifier, reserved, _ = gate.book(body)
            usage = {"prompt_tokens": 100, "prompt_cache_hit_tokens": 80, "prompt_cache_miss_tokens": 20,
                     "completion_tokens": 10, "total_tokens": 110}
            peak, offpeak = gate.settle(identifier, reserved, 200, usage)
            self.assertAlmostEqual(peak, 0.0001232)
            self.assertAlmostEqual(offpeak, peak / 2)
            self.assertAlmostEqual(gate.current_total(), peak)
            with self.assertRaisesRegex(ValueError, "unapproved_model"):
                gate.book(body.replace(b"deepseek-flash", b"another-model"))


class MiningTests(unittest.TestCase):
    def setUp(self):
        self.source = "mcp__research_report__plan_analysis"
        self.target = "mcp__research_report__run_analysis"
        self.contracts = {self.source: {"required_params": ["plan"], "output_fields": ["plan_id"], "execution": "semantic"},
                          self.target: {"required_params": ["plan_id"], "output_fields": ["analysis_id"], "execution": "workspace_idempotent"}}

    def records(self, permissions=None, failed=False, parallel=False):
        identifier = "rra-plan-" + "a" * 32
        return [{"name": self.source, "call_id": "c1", "seq": 1, "result_seq": 2,
                 "ok": True, "arguments": {"plan": {}},
                 "output": {"plan_id": identifier, "_provenance": {"authorized_tools": permissions if permissions is not None else ["run_analysis"]}}},
                {"name": self.target, "call_id": "c2", "seq": 1 if parallel else 3, "result_seq": 4,
                 "ok": not failed, "arguments": {"plan_id": identifier}, "output": {"analysis_id": "rra-analysis-" + "b" * 32}}]

    def test_learn_actual_binding_but_reject_no_permission_failure_parallel_and_semantic_targets(self):
        self.assertEqual(len(compiler.witnessed_edges(self.records(), self.contracts)), 1)
        self.assertEqual(compiler.witnessed_edges(self.records(permissions=[]), self.contracts), {})
        self.assertEqual(compiler.witnessed_edges(self.records(failed=True), self.contracts), {})
        self.assertEqual(compiler.witnessed_edges(self.records(parallel=True), self.contracts), {})
        self.contracts[self.target]["execution"] = "semantic"
        self.assertEqual(compiler.witnessed_edges(self.records(), self.contracts), {})

    def test_independent_certification_and_evidence_are_required(self):
        edges = compiler.witnessed_edges(self.records(), self.contracts)
        make = lambda case: {"case_id": case, "run_id": case, "events_sha256": "a" * 64, "edges": edges, "tool_schemas": {}}
        result = compiler.compile_library([make("train1"), make("train2")], make("cert"), self.contracts)
        self.assertEqual(len(result["artifacts"]), 1)
        self.assertEqual(result["artifacts"][0]["from_field"], "plan_id")
        with self.assertRaisesRegex(ValueError, "distinct"):
            compiler.compile_library([make("train1"), make("train2")], make("train1"), self.contracts)
        cert = make("cert"); cert["edges"] = {}
        with self.assertRaisesRegex(ValueError, "No independently"):
            compiler.compile_library([make("train1"), make("train2")], cert, self.contracts)


if __name__ == "__main__":
    unittest.main()
