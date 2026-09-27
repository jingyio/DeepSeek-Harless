"""No-model wire test for the isolated DSH → Distil route."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import unittest
from uuid import uuid4
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MockProvider(BaseHTTPRequestHandler):
    requests: list[dict] = []
    expand_first = False
    mixed_expand_first = False
    recovery_handle = ""

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
        if self.mixed_expand_first and len(self.requests) == 1:
            if self.recovery_handle:
                if parsed.get("stream"):
                    chunks = [
                        {"id": "mock-restore", "object": "chat.completion.chunk", "created": 1,
                         "model": "deepseek-flash", "choices": [{"index": 0, "delta": {
                             "role": "assistant", "tool_calls": [{"index": 0, "id": "restore-1",
                             "type": "function", "function": {
                                 "name": "distil_expand",
                                 "arguments": json.dumps({"handle": self.recovery_handle})}},
                             {"index": 1, "id": "read-1", "type": "function", "function": {
                                 "name": "read", "arguments": json.dumps({
                                     "file_path": str(ROOT / "README.md"), "limit": 1})}}]},
                             "finish_reason": None}]},
                        {"id": "mock-restore", "object": "chat.completion.chunk", "created": 1,
                         "model": "deepseek-flash", "choices": [{"index": 0, "delta": {},
                         "finish_reason": "tool_calls"}]},
                    ]
                    response = ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
                                + "data: [DONE]\n\n").encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)
                    return
                response = json.dumps({"id": "mock-restore", "object": "chat.completion",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": None,
                    "tool_calls": [{"id": "restore-1", "type": "function", "function": {
                    "name": "distil_expand",
                    "arguments": json.dumps({"handle": self.recovery_handle})}},
                    {"id": "read-1", "type": "function", "function": {
                    "name": "read", "arguments": json.dumps({
                        "file_path": str(ROOT / "README.md"), "limit": 1})}}]},
                    "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 1,
                    "completion_tokens": 1, "total_tokens": 2}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                return
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
    def test_mixed_turn_bridge_reads_distil_digest_in_real_dsh(self) -> None:
        MockProvider.requests.clear()
        MockProvider.mixed_expand_first = True
        home = ROOT / ".local" / "distil-sss" / "homes" / ("restore-wire-" + uuid4().hex)
        home.mkdir(parents=True)
        MockProvider.recovery_handle = "abcd1234"
        seeded = subprocess.run(
            [sys.executable, "-c", "from distil.mcp_server import record_restore; "
             "assert record_restore('abcd1234', 'log line restored evidence')"],
            cwd=ROOT, capture_output=True, text=True,
            env={**os.environ, "DISTIL_HOME": str(home),
                 "PYTHONPATH": str(ROOT / ".local/distil-upstream") + os.pathsep + str(ROOT)},
        )
        self.assertEqual(seeded.returncode, 0, seeded.stderr)
        patch_path = home / "dsh-expand.patch.yml"
        patch_path.write_text(
            (ROOT / "config/distil-expand-dsh.patch.yml").read_text().replace(
                "__SSS_DISTIL_EXPAND_PLUGIN__",
                json.dumps((ROOT / "src/adapters/dsh_distil_expand_bridge.mjs").as_uri())),
            encoding="utf-8",
        )
        try:
            with ThreadingHTTPServer(("127.0.0.1", 0), MockProvider) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                child = (
                    "import os;from deepseek_harness import DeepSeekHarness;"
                    "from pathlib import Path;from uuid import uuid4;"
                    "root=Path.cwd();"
                    "h=DeepSeekHarness(provider='deepseek-official',model='deepseek-flash',"
                    "reasoning_effort='off',max_tokens=20,cwd=str(root),runtime_cwd=str(root),"
                    "dsh_bin=str(root/'node_modules/.bin/dsh'),profile='sdk',"
                    "patches=(os.environ['SSS_DISTIL_BRIDGE_PATCH'],),"
                    "dsh_home=str(root/'.local/distil-dsh-smoke'),request_timeout_seconds=20);"
                    "h.__enter__();"
                    "r=h.run('Recover the needed context.',"
                    "session_id='distil-restore-smoke-'+uuid4().hex);"
                    "print(r.final_response, r.finish_reason, [(e.get('type'),"
                    "str(e.get('data'))[:300]) for e in r.events if e.get('type') "
                    "in ('tool/result','turn/end')]);h.__exit__(None,None,None)"
                )
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "run-distil-dsh.py"),
                     "--upstream", f"http://127.0.0.1:{server.server_port}",
                     "--distil-profile", "context-only",
                     "--distil-home", str(home),
                     "--budget-usd", "1", "--", sys.executable, "-c", child],
                    cwd=ROOT, text=True, capture_output=True, timeout=60,
                    env={**os.environ, "DEEPSEEK_API_KEY": "local-mock-key",
                         "SSS_MCP_PYTHON": sys.executable,
                         "SSS_PROJECT_ROOT": str(ROOT),
                         "SSS_DISTIL_BRIDGE_PATCH": str(patch_path)},
                )
                server.shutdown()
        finally:
            MockProvider.mixed_expand_first = False
            MockProvider.recovery_handle = ""
        self.assertEqual(result.returncode, 0, result.stderr[-1400:])
        self.assertIn("READY", result.stdout, result.stderr[-1600:])
        self.assertGreaterEqual(len(MockProvider.requests), 2)
        forwarded = MockProvider.requests[0]["body"]
        tool_names = [tool.get("function", {}).get("name") for tool in forwarded.get("tools", [])]
        self.assertEqual(tool_names.count("distil_expand"), 1)
        messages = MockProvider.requests[1]["body"].get("messages", [])
        self.assertIn("log line restored evidence", json.dumps(messages))
        self.assertIn("read-1", json.dumps(messages))

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
