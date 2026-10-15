"""Real local HTTP streaming and settlement; never contacts a paid provider."""

import http.client
import json
import socket
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.adapters.deepseek_cost_gate import (
    State, StreamUsage, create_server, observed_peak_cost, reservation,
)
from src.adapters.web_task_budget import TaskBudgetRegistry


BODY = b'{"model":"deepseek-flash","max_tokens":100,"messages":[],"stream":true}'
USAGE = {"prompt_tokens": 12, "prompt_cache_hit_tokens": 8,
         "prompt_cache_miss_tokens": 4, "completion_tokens": 3, "total_tokens": 15}
FIRST = b'data: {"choices":[{"delta":{"content":"first private token"}}],"usage":null}\n\n'
LAST = b'data: ' + json.dumps({"usage": USAGE}).encode() + b'\r\n\r\ndata: [DONE]\r\n\r\n'


class CostGateStreamTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.checkpoint = self.root / 'cumulative.json'
        self.checkpoint.write_text('{"request_count":1000,"reserved_usd":0.1}')
        self.state = State(cap_usd=1, output_cap=100, request_limit=0,
                           record=self.root / 'gate.jsonl', checkpoint=self.checkpoint)
        self.release = threading.Event()
        self.upstream_done = threading.Event()
        self.calls = []
        self.mode = 'stream'
        test = self

        class Upstream(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *_args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                test.calls.append(dict(self.headers))
                if test.mode in ('json', 'error'):
                    raw = json.dumps({'usage': USAGE} if test.mode == 'json'
                                     else {'error': 'provider refused'}).encode()
                    self.send_response(200 if test.mode == 'json' else 503)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    test.upstream_done.set()
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                if test.mode == 'short_length':
                    self.send_header('Content-Length', str(len(FIRST + LAST) + 10))
                else:
                    self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()

                def write(chunk):
                    self.wfile.write(chunk if test.mode == 'short_length' else
                                     f'{len(chunk):X}\r\n'.encode() + chunk + b'\r\n')
                    self.wfile.flush()

                try:
                    write(FIRST)
                    # The test must receive FIRST while this is still blocked.
                    if not test.release.wait(5):
                        raise TimeoutError('test never released upstream')
                    if test.mode != 'missing_usage':
                        for offset in range(0, len(LAST), 7):
                            write(LAST[offset:offset + 7])
                    if test.mode not in ('broken', 'short_length'):
                        self.wfile.write(b'0\r\n\r\n')
                        self.wfile.flush()
                finally:
                    self.close_connection = True
                    test.upstream_done.set()

        self.upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        self.gate = create_server('127.0.0.1', 0,
                                  f'http://127.0.0.1:{self.upstream.server_port}', self.state)
        self.servers = [self.upstream, self.gate]
        self.clients = []
        for server in self.servers:
            threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01},
                             daemon=True).start()

    def tearDown(self):
        self.release.set()
        for client in self.clients:
            client.close()
        for server in reversed(self.servers):
            server.shutdown()
            server.server_close()
        self.temporary.cleanup()

    def request(self, headers=None, server=None):
        conn = http.client.HTTPConnection('127.0.0.1', (server or self.gate).server_port, timeout=2)
        self.clients.append(conn)
        conn.request('POST', '/v1/chat/completions', BODY,
                     {'Content-Type': 'application/json', **(headers or {})})
        return conn, conn.getresponse()

    def settled(self):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if self.state.record.exists():
                rows = self.state.record.read_text().splitlines()
                if rows:
                    try:
                        return json.loads(rows[-1])
                    except json.JSONDecodeError:
                        pass
            time.sleep(0.005)
        self.fail('gate failed to settle and record upstream request')

    def test_first_bytes_arrive_before_upstream_finishes_and_settle_checkpoint(self):
        _, response = self.request({'Connection': 'close', 'Authorization': 'Bearer fixture'})
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader('Transfer-Encoding'), 'chunked')
        self.assertEqual(response.getheader('X-Accel-Buffering'), 'no')
        self.assertIsNone(response.getheader('Content-Length'))
        self.assertEqual(response.read(len(FIRST)), FIRST)
        self.assertFalse(self.upstream_done.is_set())
        self.assertEqual(self.state.request_count, 1001)
        self.assertTrue(self.state.pending)
        _, maximum, _ = reservation(BODY, max_output=100)
        self.assertAlmostEqual(self.state.reserved_usd, 0.1 + maximum)
        self.release.set()
        self.assertEqual(response.read(), LAST)
        row = self.settled()
        self.assertTrue(row['streamed'])
        self.assertEqual(row['response_bytes'], len(FIRST + LAST))
        self.assertEqual(row['response_usage'], USAGE)
        self.assertFalse(self.state.pending)
        self.assertAlmostEqual(self.state.reserved_usd, 0.1 + observed_peak_cost('deepseek-flash', USAGE))
        self.assertEqual(json.loads(self.checkpoint.read_text())['request_count'], 1001)
        self.assertEqual(self.calls[0]['Authorization'], 'Bearer fixture')
        self.assertEqual(self.calls[0]['Accept-Encoding'], 'identity')
        self.assertNotIn('private token', self.state.record.read_text())
        self.assertNotIn('Bearer fixture', self.state.record.read_text())

    def test_browser_disconnect_still_drains_and_settles_complete_usage(self):
        conn, response = self.request()
        self.assertEqual(response.read(len(FIRST)), FIRST)
        conn.sock.shutdown(socket.SHUT_RDWR)
        conn.close()
        response.close()
        self.release.set()
        row = self.settled()
        self.assertTrue(self.upstream_done.wait(1))
        self.assertTrue(row['downstream_disconnected'])
        self.assertEqual(row['response_usage'], USAGE)
        self.assertEqual(self.state.request_count, 1001)
        self.assertFalse(self.state.pending)
        self.assertAlmostEqual(self.state.reserved_usd, 0.1 + observed_peak_cost('deepseek-flash', USAGE))

    def test_truncated_stream_keeps_full_reservation_even_after_usage_event(self):
        for mode in ('broken', 'short_length'):
            with self.subTest(mode=mode):
                self.mode = mode
                before = self.state.reserved_usd
                _, response = self.request()
                self.assertEqual(response.read(len(FIRST)), FIRST)
                self.release.set()
                with self.assertRaises(http.client.IncompleteRead):
                    response.read()
                row = self.settled()
                self.assertEqual(row['response_status'], 502)
                self.assertIsNone(row['observed_peak_usd'])
                _, maximum, _ = reservation(BODY, max_output=100)
                self.assertAlmostEqual(self.state.reserved_usd, before + maximum)

    def test_missing_usage_preserves_dollar_guard_before_any_second_upstream_call(self):
        self.mode = 'missing_usage'
        _, maximum, _ = reservation(BODY, max_output=100)
        self.state.cap_usd = self.state.reserved_usd + maximum * 1.5
        _, response = self.request()
        self.assertEqual(response.read(len(FIRST)), FIRST)
        _, denied = self.request()
        self.assertEqual(denied.status, 429)
        denied.read()
        self.assertEqual(len(self.calls), 1)
        self.release.set()
        self.assertEqual(response.read(), b'')
        self.assertFalse(self.state.pending)
        self.assertAlmostEqual(self.state.reserved_usd, 0.1 + maximum)
        _, denied = self.request()
        self.assertEqual(denied.status, 429)
        denied.read()
        self.assertEqual(len(self.calls), 1)

    def test_regular_json_and_upstream_error_keep_status_and_content(self):
        for mode, status in (('json', 200), ('error', 503)):
            with self.subTest(mode=mode):
                self.mode = mode
                _, response = self.request()
                self.assertEqual(response.status, status)
                self.assertIsNone(response.getheader('Transfer-Encoding'))
                self.assertEqual(json.loads(response.read()), {'usage': USAGE} if mode == 'json'
                                 else {'error': 'provider refused'})
        self.assertEqual(self.state.request_count, 1002)

    def test_routed_stream_bills_only_authorized_lane_and_cumulative_budget(self):
        registry = TaskBudgetRegistry(run_state=self.state, tasks_root=self.root / '.local' / 'tasks',
                                      task_request_limit=None)
        registry.register('1' * 32, 'lane-one', 0.5)
        registry.register('2' * 32, 'lane-two', 0.5)
        registry.activate('lane-one')
        registry.activate('lane-two')
        gate = create_server('127.0.0.1', 0, f'http://127.0.0.1:{self.upstream.server_port}',
                             self.state, state_selector=registry.state_for, gate_token='private-test-token')
        self.servers.append(gate)
        threading.Thread(target=gate.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True).start()
        _, refused = self.request({'X-DeepSeek-Harness-Session-Id': 'lane-one'}, server=gate)
        self.assertEqual(refused.status, 403)
        refused.read()
        self.assertEqual(len(self.calls), 0)
        _, response = self.request({'X-DeepSeek-Harness-Session-Id': 'lane-one',
                                    'X-SSS-Model-Gate-Token': 'private-test-token'}, server=gate)
        self.assertEqual(response.read(len(FIRST)), FIRST)
        self.assertEqual(registry.stats('lane-one')['pending_requests'], 1)
        self.release.set()
        self.assertEqual(response.read(), LAST)
        self.assertEqual(registry.stats('lane-one')['upstream_requests'], 1)
        self.assertTrue(registry.stats('lane-one')['usage_complete'])
        self.assertEqual(registry.stats('lane-two')['upstream_requests'], 0)
        self.assertEqual(self.state.request_count, 1001)
        self.assertNotIn('X-Sss-Model-Gate-Token', self.calls[0])


class StreamUsageTests(unittest.TestCase):
    def test_fragmented_multiline_events_keep_only_complete_usage(self):
        stream = StreamUsage()
        raw = b': keepalive\r\n\r\ndata: {"usage":\r\ndata: ' + json.dumps(USAGE).encode() + b'}\r\n\r\n'
        for byte in raw:
            stream.feed(bytes([byte]))
        self.assertEqual(stream.finish(), USAGE)

    def test_invalid_or_oversized_events_cannot_release_budget(self):
        for prefix in (b'data: invalid\n\n', b'data: ' + b'x' * (1024 * 1024 + 1) + b'\n\n'):
            stream = StreamUsage()
            for offset in range(0, len(prefix), 16384):
                stream.feed(prefix[offset:offset + 16384])
            stream.feed(LAST)
            self.assertEqual(stream.finish(), {})
            self.assertLessEqual(len(stream.pending) + sum(map(len, stream.data)), 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
