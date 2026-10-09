"""No-model checks for SSS-owned latest-batch projection and exact restoration."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.adapters.motif_output_projection import (CompactJsonProjector, LatestToolProjector,
                                                  load_certified_projection)


ROOT = Path(__file__).resolve().parents[1]
class ProjectionArtifactCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.adapters.dsh_trajectory import ToolContract, extract_dsh_trace
        from src.motif_core.offline.library_builder import build_read_motif_library
        from tests.test_trace_compiled_read_motif import event_pair
        contracts = {
            "snapshot_sources": ToolContract(("root",), True, ("sha256",), replay_stable=True),
            "retrieve_point": ToolContract(("source_sha",), True, (),
                                          provenance_params=("source_sha",), replay_stable=True),
        }
        traces = []
        for index, label in enumerate(["alpha", "beta", "gamma"]):
            events = (event_pair(1, "snapshot_sources", {"root": label}, {"sha256": "sha-"+label})
                      + event_pair(2, "retrieve_point", {"source_sha": "sha-"+label},
                                   {"evidence": "Synthetic evidence " + label}))
            traces.append(extract_dsh_trace(events, contracts, trace_id="projection-"+label,
                task_fingerprint="synthetic-decision-"+label,
                provenance_by_call_id={"c2": {"source_sha": {
                    "from_call_id": "c1", "from_field": "sha256"}}}))
        library = build_read_motif_library(traces[:2], traces[2:], contracts)
        assert len(library["artifacts"]) == 1
        cls.fixture_directory = tempfile.TemporaryDirectory()
        cls.artifact = Path(cls.fixture_directory.name) / "artifact.json"
        cls.artifact.write_text(json.dumps(library["artifacts"][0]), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.fixture_directory.cleanup()



def batch() -> tuple[dict, str, str]:
    source = json.dumps({"sha256": "sha-a", "title": "Sensitive title", "notes": "x" * 500},
                        ensure_ascii=False)
    point = json.dumps({"citation": "A citation", "evidence": "y" * 500},
                       ensure_ascii=False)
    body = {"model": "mock", "messages": [
        {"role": "user", "content": "Assess the evidence"},
        {"role": "assistant", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "snapshot_sources", "arguments": "{}"}},
            {"id": "c2", "type": "function", "function": {"name": "retrieve_point", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": source},
        {"role": "tool", "tool_call_id": "c2", "content": point}]}
    return body, source, point


class ProjectionTest(ProjectionArtifactCase):
    def test_compact_json_preserves_every_field_and_records_exact_original(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            projector = CompactJsonProjector(Path(temp))
            source = '{\n  "source_version": "abc",\n  "native_result": {\n    "rows": [[1, "a b"], [2, "c"]],\n    "formula": "=SUM(A1:A2)"\n  }\n}'
            body = {"messages": [
                {"role": "assistant", "tool_calls": [
                    {"id": "c1", "function": {"name": "read_numbers", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "c1", "content": source}]}
            result = projector.project(body)
            view = result["messages"][1]["content"]
            self.assertLess(len(view), len(source))
            self.assertEqual(json.loads(view), json.loads(source))
            self.assertEqual(projector.project(body), result)
            self.assertEqual(next((Path(temp) / "originals").glob("*.txt")).read_text(), source)
            audit = json.loads(next((Path(temp) / "audit").glob("*.json")).read_text())
            self.assertEqual(audit["original_bytes"] - audit["view_bytes"], len(source) - len(view))
            body["messages"][1]["content"] = "tool failed: unavailable"
            self.assertEqual(projector.project(body), body)

    def test_compact_json_only_changes_newest_tool_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            projector = CompactJsonProjector(Path(temp))
            old = '{\n  "payload": [1, 2, 3]\n}'
            new = '{\n  "payload": [4, 5, 6]\n}'
            body = {"messages": [
                {"role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "first"}}]},
                {"role": "tool", "tool_call_id": "c1", "content": old},
                {"role": "assistant", "content": "intermediate reasoning"},
                {"role": "assistant", "tool_calls": [{"id": "c2", "function": {"name": "second"}}]},
                {"role": "tool", "tool_call_id": "c2", "content": new}]}
            result = projector.project(body)
            self.assertEqual(result["messages"][1]["content"], old)
            self.assertNotEqual(result["messages"][4]["content"], new)
            self.assertEqual(len(list((Path(temp) / "audit").glob("*.json"))), 1)

    def test_recent_batch_projects_only_certified_fields_and_recovers_original(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            projector = LatestToolProjector(self.artifact, Path(temp))
            request, source, point = batch()
            projected = projector.project(request)
            self.assertEqual(request["messages"][2]["content"], source)
            view = json.loads(projected["messages"][2]["content"])["sss_projection"]
            handle = re.search(r"handle=([0-9a-f]{8})", view["restore"]).group(1)
            self.assertEqual(projector.expand(handle), source)
            self.assertEqual(json.loads(projected["messages"][2]["content"])
                             ["sss_projection"]["kept"], {"sha256": "sha-a"})
            self.assertEqual(projected["messages"][3]["content"], point)
            self.assertEqual(projector.project(request), projected)
            self.assertEqual(LatestToolProjector(self.artifact, Path(temp)).project(request), projected)
            self.assertEqual(len(list((Path(temp) / "originals").iterdir())), 2)
            (Path(temp) / "restore" / handle).write_text("tampered")
            with self.assertRaises(ValueError):
                projector.expand(handle)

    def test_old_batch_is_replayed_without_new_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            projector = LatestToolProjector(self.artifact, Path(temp))
            old, _, _ = batch()
            prior_view = projector.project(old)
            later = json.loads(json.dumps(old))
            later["messages"] += [
                {"role": "assistant", "content": "First answer"},
                {"role": "user", "content": "Next"},
                {"role": "assistant", "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "snapshot_sources", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "c1", "content": json.dumps(
                    {"sha256": "sha-b", "notes": "z" * 500})}]
            result = projector.project(later)
            self.assertEqual(result["messages"][2:4], prior_view["messages"][2:4])
            self.assertIn("sss_projection", result["messages"][-1]["content"])
            fresh = LatestToolProjector(self.artifact, Path(temp) / "fresh").project(later)
            self.assertEqual(fresh["messages"][2:4], old["messages"][2:4])

    def test_uncertified_artifact_and_failed_results_are_not_projected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            copy = Path(temp) / "bad.json"
            artifact = json.loads(self.artifact.read_text())
            artifact["tools"].append("unreviewed")
            copy.write_text(json.dumps(artifact))
            with self.assertRaises(ValueError):
                load_certified_projection(copy)
            projector = LatestToolProjector(self.artifact, Path(temp) / "state")
            request, _, _ = batch()
            request["messages"][2]["content"] = json.dumps({"status": "error", "notes": "x" * 500})
            result = projector.project(request)
            self.assertEqual(result["messages"][2], request["messages"][2])


class RecoveringProvider(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append(body)
        if len(self.requests) == 1:
            match = re.search(r"handle=([0-9a-f]{8})", json.dumps(body["messages"]))
            content = None
            calls = [{"id": "expand-1", "type": "function", "function": {
                "name": "sss_expand", "arguments": json.dumps({"handle": match.group(1)})}}]
            finish = "tool_calls"
        else:
            content, calls, finish = "RECOVERED", None, "stop"
        payload = {"id": "mock", "created": 1, "model": "mock", "object": "chat.completion",
                   "choices": [{"index": 0, "message": {"role": "assistant", "content": content,
                               **({"tool_calls": calls} if calls else {})}, "finish_reason": finish}],
                   "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}}
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args) -> None:
        pass


class CompactProvider(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        self.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        payload = {"id": "mock", "created": 1, "model": "mock", "object": "chat.completion",
                   "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"},
                                "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}}
        streaming = self.requests[-1].get("stream") is True
        raw = (("data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n").encode()
               if streaming else json.dumps(payload).encode())
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if streaming else "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args) -> None:
        pass


class ProjectionWireTest(ProjectionArtifactCase):
    def test_compact_json_preserves_streaming_request_and_response(self) -> None:
        CompactProvider.requests = []
        with tempfile.TemporaryDirectory() as temp, ThreadingHTTPServer(
                ("127.0.0.1", 0), CompactProvider) as provider:
            thread = threading.Thread(target=provider.serve_forever, daemon=True)
            thread.start()
            with ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler) as slot:
                port = slot.server_port
            process = subprocess.Popen([sys.executable, "-m", "src.adapters.motif_output_projection",
                                        "--upstream", f"http://127.0.0.1:{provider.server_port}",
                                        "--compact-json-only", "--local-dir", temp, "--port", str(port)],
                                       cwd=ROOT, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.PIPE, text=True)
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for _ in range(100):
                    if process.poll() is not None:
                        self.fail(process.stderr.read())
                    try:
                        with opener.open(f"http://127.0.0.1:{port}/projection/health", timeout=.2):
                            break
                    except OSError:
                        time.sleep(.03)
                body = {"model": "mock", "stream": True, "messages": [
                    {"role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "read"}}]},
                    {"role": "tool", "tool_call_id": "c1", "content": '{\n "rows": [1, 2]\n}'}]}
                request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                                 data=json.dumps(body).encode(),
                                                 headers={"Content-Type": "application/json"})
                with opener.open(request, timeout=5) as response:
                    returned = response.read().decode()
                    self.assertEqual(response.headers["Content-Type"], "text/event-stream")
                self.assertIn("data: [DONE]", returned)
                self.assertTrue(CompactProvider.requests[0]["stream"])
                self.assertEqual(CompactProvider.requests[0]["messages"][-1]["content"],
                                 '{"rows":[1,2]}')
                self.assertNotIn("tools", CompactProvider.requests[0])
            finally:
                process.terminate()
                process.wait(timeout=5)
                process.stderr.close()
                provider.shutdown()


    def test_sss_expand_uses_local_original_and_returns_stream(self) -> None:
        RecoveringProvider.requests = []
        with tempfile.TemporaryDirectory() as temp, ThreadingHTTPServer(
                ("127.0.0.1", 0), RecoveringProvider) as provider:
            thread = threading.Thread(target=provider.serve_forever, daemon=True)
            thread.start()
            with ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler) as slot:
                port = slot.server_port
            process = subprocess.Popen([sys.executable, "-m", "src.adapters.motif_output_projection",
                                        "--upstream", f"http://127.0.0.1:{provider.server_port}",
                                        "--artifact", str(self.artifact), "--local-dir", temp,
                                        "--port", str(port)], cwd=ROOT,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                health = f"http://127.0.0.1:{port}/projection/health"
                for _ in range(100):
                    if process.poll() is not None:
                        self.fail(process.stderr.read())
                    try:
                        with opener.open(health, timeout=0.2):
                            break
                    except OSError:
                        time.sleep(0.03)
                else:
                    self.fail(f"projection health timed out, process={process.poll()}")
                request, source, _ = batch()
                request["stream"] = True
                raw = json.dumps(request).encode()
                call = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                              data=raw, headers={"Content-Type": "application/json"})
                try:
                    with opener.open(call, timeout=5) as response:
                        result = response.read().decode()
                except urllib.error.HTTPError as error:
                    self.fail(f"{error.read().decode()} requests={RecoveringProvider.requests}")
                self.assertIn("RECOVERED", result)
                self.assertIn("data: [DONE]", result)
                self.assertEqual(len(RecoveringProvider.requests), 2)
                first, second = RecoveringProvider.requests
                self.assertFalse(first["stream"])
                self.assertIn("sss_expand", json.dumps(first["tools"]))
                self.assertEqual(second["messages"][-1]["content"], source)
                self.assertEqual(second["tools"], first["tools"])
            finally:
                process.terminate()
                process.wait(timeout=5)
                process.stderr.close()
                provider.shutdown()




if __name__ == "__main__":
    unittest.main()
