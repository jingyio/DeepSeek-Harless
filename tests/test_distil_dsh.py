"""No-model wire test for the isolated DSH → Distil route."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MockProvider(BaseHTTPRequestHandler):
    requests: list[dict] = []
    expand_first = False

    def do_POST(self) -> None:  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path == "/v1/files":
            self.requests.append({"path": self.path, "bytes": len(body)})
            response = b'{"id":"file-api-local-mock","type":"file"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        parsed = json.loads(body)
        self.requests.append({"path": self.path, "body": parsed})
        if self.expand_first and len(self.requests) == 1:
            match = re.search(r"handle=([0-9a-f]{8})", json.dumps(parsed.get("messages", [])))
            if match:
                response = json.dumps({"id": "mock-expand", "object": "chat.completion",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": None,
                    "tool_calls": [{"id": "expand-1", "type": "function", "function": {
                    "name": "distil_expand", "arguments": json.dumps({"handle": match.group(1)})}}]},
                    "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 1,
                    "completion_tokens": 1, "total_tokens": 2}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                return
        if parsed.get("stream"):
            chunks = [
                {"id": "mock", "object": "chat.completion.chunk", "created": 1,
                 "model": "deepseek-flash", "choices": [{"index": 0,
                 "delta": {"role": "assistant", "content": "READY"}, "finish_reason": None}]},
                {"id": "mock", "object": "chat.completion.chunk", "created": 1,
                 "model": "deepseek-flash", "choices": [{"index": 0, "delta": {},
                 "finish_reason": "stop"}], "usage": {"prompt_tokens": 1,
                 "completion_tokens": 1, "total_tokens": 2,
                 "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 1}},
            ]
            response = ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
                        + "data: [DONE]\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        response = json.dumps({"id": "mock", "object": "chat.completion",
                               "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                                            "finish_reason": "stop"}],
                               "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                                         "total_tokens": 2}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *_args) -> None:
        pass


class DistilDshWireTest(unittest.TestCase):
    def test_files_api_passes_through_budget_gate(self) -> None:
        MockProvider.requests.clear()
        with ThreadingHTTPServer(("127.0.0.1", 0), MockProvider) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            child = (
                "import os,urllib.request;"
                "req=urllib.request.Request(os.environ['DEEPSEEK_BASE_URL']+"
                "'/files',data=b'mock-image-bytes',method='POST',"
                "headers={'Content-Type':'application/octet-stream'});"
                "print(urllib.request.urlopen(req,timeout=10).status)"
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "run-distil-dsh.py"),
                 "--mode", "plain", "--budget-usd", "0.01", "--upstream",
                 f"http://127.0.0.1:{server.server_port}", "--", sys.executable,
                 "-c", child], cwd=ROOT, text=True, capture_output=True, timeout=30)
            server.shutdown()
        self.assertEqual(result.returncode, 0, result.stderr[-1000:])
        self.assertEqual(MockProvider.requests, [{"path": "/v1/files", "bytes": 16}])

    def test_expansion_request_is_metered_upstream(self) -> None:
        MockProvider.requests.clear()
        MockProvider.expand_first = True
        ledger = ROOT / ".local" / "distil-sss" / "expand-budget-test.jsonl"
        prior_rows = len(ledger.read_text().splitlines()) if ledger.exists() else 0
        try:
            with ThreadingHTTPServer(("127.0.0.1", 0), MockProvider) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                child = (
                    "import json,os,urllib.request;"
                    "body={'model':'deepseek-flash','max_tokens':20,'stream':False,"
                    "'messages':[{'role':'user','content':'summarize'},"
                    "{'role':'tool','tool_call_id':'call-1','content':"
                    "'\\n'.join('log line %04d status=ok'%i for i in range(600))}]};"
                    "req=urllib.request.Request(os.environ['DEEPSEEK_BASE_URL']+"
                    "'/chat/completions',data=json.dumps(body).encode(),"
                    "headers={'Content-Type':'application/json'});"
                    "print(urllib.request.urlopen(req,timeout=10).status)"
                )
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "run-distil-dsh.py"),
                     "--upstream", f"http://127.0.0.1:{server.server_port}",
                     "--distil-profile", "context-only",
                     "--budget-usd", "0.01", "--ledger", str(ledger),
                     "--", sys.executable, "-c", child], cwd=ROOT,
                    text=True, capture_output=True, timeout=30)
                server.shutdown()
        finally:
            MockProvider.expand_first = False
        self.assertEqual(result.returncode, 0, result.stderr[-1400:])
        self.assertGreaterEqual(len(MockProvider.requests), 2)
        self.assertGreaterEqual(len(ledger.read_text().splitlines()) - prior_rows, 2)

    def test_plain_mode_is_budgeted_without_distil_tool(self) -> None:
        MockProvider.requests.clear()
        with ThreadingHTTPServer(("127.0.0.1", 0), MockProvider) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            child = (
                "import json,os,urllib.request;"
                "body={'model':'deepseek-flash','max_tokens':20,'stream':False,"
                "'messages':[{'role':'user','content':'test'}]};"
                "req=urllib.request.Request(os.environ['DEEPSEEK_BASE_URL']+"
                "'/chat/completions',data=json.dumps(body).encode(),"
                "headers={'Content-Type':'application/json'});"
                "print(urllib.request.urlopen(req,timeout=10).status)"
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "run-distil-dsh.py"),
                 "--mode", "plain", "--budget-usd", "0.01", "--upstream",
                 f"http://127.0.0.1:{server.server_port}", "--", sys.executable,
                 "-c", child], cwd=ROOT, text=True, capture_output=True, timeout=30)
            server.shutdown()
        self.assertEqual(result.returncode, 0, result.stderr[-1000:])
        self.assertEqual(len(MockProvider.requests), 1)
        self.assertNotIn("distil_expand", json.dumps(MockProvider.requests[0]["body"]))

    def test_v1_route_reaches_distil_and_recovery_tool(self) -> None:
        MockProvider.requests.clear()
        with ThreadingHTTPServer(("127.0.0.1", 0), MockProvider) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            upstream = f"http://127.0.0.1:{server.server_port}"
            child = (
                "import json,os,urllib.request;"
                "base=os.environ['DEEPSEEK_BASE_URL'];"
                "body={'model':'deepseek-flash','stream':False,'messages':["
                "{'role':'user','content':'Summarize the test result'},"
                "{'role':'tool','tool_call_id':'test-call','content':"
                "'\\n'.join('repeated log line %04d: status=ok'%i for i in range(600))}]};"
                "req=urllib.request.Request(base+'/chat/completions',"
                "data=json.dumps(body).encode(),headers={'Content-Type':'application/json'});"
                "print(urllib.request.urlopen(req,timeout=10).status)"
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "run-distil-dsh.py"),
                 "--upstream", upstream, "--distil-profile", "context-only",
                 "--", sys.executable, "-c", child],
                cwd=ROOT, text=True, capture_output=True, timeout=30,
                env={**os.environ, "DISTIL_RETENTION_SAMPLE": "0"},
            )
            server.shutdown()
        self.assertEqual(result.returncode, 0, result.stderr[-1000:])
        self.assertIn("200", result.stdout)
        self.assertEqual(len(MockProvider.requests), 1)
        forwarded = MockProvider.requests[0]
        self.assertEqual(forwarded["path"], "/v1/chat/completions")
        self.assertIn("distil_expand", json.dumps(forwarded["body"].get("tools", [])))
        original = "\n".join(f"repeated log line {i:04d}: status=ok" for i in range(600))
        compressed = forwarded["body"]["messages"][1]["content"]
        self.assertLess(len(compressed), len(original))

    def test_real_dsh_adapter_uses_isolated_proxy(self) -> None:
        MockProvider.requests.clear()
        ledger = ROOT / ".local" / "distil-sss" / "budget-test.jsonl"
        prior_rows = len(ledger.read_text().splitlines()) if ledger.exists() else 0
        with ThreadingHTTPServer(("127.0.0.1", 0), MockProvider) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            upstream = f"http://127.0.0.1:{server.server_port}"
            child = (
                "from deepseek_harness import DeepSeekHarness;"
                "from pathlib import Path;from uuid import uuid4;"
                "root=Path.cwd();"
                "h=DeepSeekHarness(provider='deepseek-official',model='deepseek-flash',"
                "reasoning_effort='off',max_tokens=20,cwd=str(root),runtime_cwd=str(root),"
                "dsh_bin=str(root/'node_modules/.bin/dsh'),profile='sdk',"
                "patches=(str(root/'config/semantic-sdk.patch.yml'),),"
                "dsh_home=str(root/'.local/distil-dsh-smoke'),request_timeout_seconds=20);"
                "h.__enter__();"
                "r=h.run('Reply READY.',session_id='distil-dsh-local-smoke-'+uuid4().hex);"
                "print(r.final_response);"
                "h.__exit__(None,None,None)"
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "run-distil-dsh.py"),
                 "--upstream", upstream, "--budget-usd", "0.01",
                 "--distil-profile", "context-only",
                 "--ledger", str(ledger), "--",
                 sys.executable, "-c", child],
                cwd=ROOT, text=True, capture_output=True, timeout=60,
                env={**os.environ, "DEEPSEEK_API_KEY": "local-mock-key"},
            )
            server.shutdown()
        self.assertEqual(result.returncode, 0, result.stderr[-1400:])
        self.assertIn("READY", result.stdout)
        self.assertGreaterEqual(len(MockProvider.requests), 1)
        self.assertTrue(all(row["path"] == "/v1/chat/completions"
                            for row in MockProvider.requests))
        self.assertGreater(len(ledger.read_text().splitlines()), prior_rows)


if __name__ == "__main__":
    unittest.main()
