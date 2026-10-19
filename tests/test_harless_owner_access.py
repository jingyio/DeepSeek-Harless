import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('owner_access', Path(__file__).resolve().parents[1] / 'scripts/harless_owner_access.py')
access = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(access)


class OwnerAccessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.token = 'n' * 48
        self.page_status = 200
        self.issue_cookie = True
        test = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/?token=' + test.token:
                    self.send_response(303)
                    self.send_header('Location', '/')
                    if test.issue_cookie:
                        self.send_header('Set-Cookie', 'dsh-auth-test=verified; HttpOnly')
                elif self.path == '/' and self.headers.get('Cookie') == 'dsh-auth-test=verified':
                    self.send_response(test.page_status)
                else:
                    self.send_response(401)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.addCleanup(self.server.server_close)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_port
        self.url = 'http://127.0.0.1:%s/?token=%s' % (self.port, self.token)
        self.target = self.root / 'owner-access.txt'
        self.target.write_text('previous credential\n', encoding='utf-8')
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({'ownerPort': self.port, 'ownerTokenFile': str(self.target)}), encoding='utf-8')
        self.log = self.root / 'startup.log'
        self.log.write_text('dsh web: ' + self.url + '\n', encoding='utf-8')

    def test_refresh_replaces_stale_credential_after_authenticated_page_check(self):
        result = access.sync_owner_access(self.config, self.log)
        self.assertTrue(result['owner_launch_authenticated'])
        self.assertEqual(self.target.read_text(encoding='utf-8'), self.url + '\n')
        if os.name != 'nt':
            self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)

    def test_rejected_token_keeps_previous_file(self):
        self.log.write_text('dsh web: ' + self.url.replace(self.token, 'x' * 48) + '\n', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            access.sync_owner_access(self.config, self.log)
        self.assertEqual(self.target.read_text(encoding='utf-8'), 'previous credential\n')

    def test_missing_cookie_and_unhealthy_authenticated_page_are_rejected(self):
        for cookie, status in [(False, 200), (True, 503)]:
            with self.subTest(cookie=cookie, status=status):
                self.issue_cookie, self.page_status = cookie, status
                with self.assertRaises(RuntimeError):
                    access.sync_owner_access(self.config, self.log)
                self.assertEqual(self.target.read_text(encoding='utf-8'), 'previous credential\n')

    def test_append_log_requires_current_launch_slice(self):
        previous = 'dsh web: ' + self.url.replace(self.token, 'x' * 48) + '\n'
        self.log.write_text(previous + 'dsh web: ' + self.url + '\n', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            access.sync_owner_access(self.config, self.log)
        access.sync_owner_access(self.config, self.log, len(previous.encode()))
        self.assertEqual(self.target.read_text(encoding='utf-8'), self.url + '\n')

    def test_untrusted_host_port_and_missing_log_are_rejected_before_publish(self):
        for url in [self.url.replace('127.0.0.1', 'example.test'), self.url + '#fragment',
                    self.url.replace(str(self.port), str(self.port + 1)), 'no launch URL']:
            with self.subTest(url_kind='invalid'):
                self.log.write_text('dsh web: ' + url + '\n', encoding='utf-8')
                with self.assertRaises((ValueError, RuntimeError)):
                    access.sync_owner_access(self.config, self.log)
                self.assertEqual(self.target.read_text(encoding='utf-8'), 'previous credential\n')

    def test_cli_failure_does_not_print_credential(self):
        self.target.write_text(self.url.replace(self.token, 'x' * 48) + '\n', encoding='utf-8')
        result = subprocess.run([sys.executable, str(SPEC.origin), '--config', str(self.config), '--check'],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertIn('RuntimeError', result.stderr)
        self.assertNotIn('x' * 48, result.stdout + result.stderr)
        self.assertNotIn('?token=', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
