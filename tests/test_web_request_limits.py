"""Request-cap CLI diagnostics; reject before starting any model or server."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WebRequestLimitTests(unittest.TestCase):
    def run_script(self, name, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts' / name), *args],
                              cwd=ROOT, capture_output=True, text=True, timeout=15)

    def test_web_default_and_explicit_zero_reach_normal_port_validation(self):
        config = json.loads((ROOT / 'config/harness-web.json').read_text())
        self.assertIsNone(config['request_limit'])
        self.assertIsNone(config['run_request_limit'])
        for flags in ((), ('--request-limit', '0', '--run-request-limit', '0')):
            result = self.run_script('harness-web.py', '--port', '0', *flags)
            self.assertEqual(result.returncode, 2)
            self.assertIn('invalid port or budget', result.stderr)
            self.assertNotIn('Traceback', result.stderr)

    def test_budget_service_unlimited_still_requires_existing_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / '.local' / 'budget'
            for task_flags in ((), ('--task-request-limit', '0')):
                result = self.run_script('serve-web-budget.py', '--output', str(output),
                    '--checkpoint', str(output / 'cumulative.json'), '--budget-usd', '1',
                    '--request-limit', '0', *task_flags)
                self.assertEqual(result.returncode, 2)
                self.assertIn('refusing to reset usage', result.stderr)
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
