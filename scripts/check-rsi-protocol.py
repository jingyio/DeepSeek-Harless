"""One free entry point for generated protocol data and targeted regressions."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
env = {**os.environ, 'SSS_PYTHON': sys.executable}
for command in ([sys.executable, 'scripts/build-rsi-schema.py', '--check'],
                [sys.executable, 'scripts/rsi-protocol-fixtures.py', '--check'],
                [sys.executable, '-m', 'pytest', 'tests/test_rsi_protocol.py', '-q'],
                ['node', '--test', 'tests/test_rsi_protocol.mjs', 'tests/test_rsi_native_harness.mjs']):
    subprocess.run(command, cwd=ROOT, env=env, check=True)
