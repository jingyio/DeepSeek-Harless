"""Start the official Web literature profile; keep the existing private key loader."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import signal
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if __name__ == '__main__':
    env = os.environ.copy()
    if '--real-model' in sys.argv:
        spec = importlib.util.spec_from_file_location('literature_web_key', HERE / 'run-live.py')
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        env['DEEPSEEK_API_KEY'] = mod.load_key(mod.KEY_FILE, env)
    child = subprocess.Popen([sys.executable, str(ROOT / 'scripts/harness-web.py'),
        '--scenario', 'literature-pdf', '--request-limit', '90', '--run-request-limit', '180',
        '--budget-usd', '3', '--run-budget-usd', '6', *sys.argv[1:]], cwd=ROOT, env=env)
    def stop(number, _frame):
        if child.poll() is None: child.send_signal(number)
    for number in (signal.SIGTERM, signal.SIGINT): signal.signal(number, stop)
    raise SystemExit(child.wait())
