"""Stop exactly one identified Linux Web launcher; never scan or delete run directories."""
import json
import os
import re
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if len(sys.argv) != 2 or not re.fullmatch('[0-9a-f]{32}', sys.argv[1]):
    sys.exit('Provide the exact run_id from the Web launcher')
run = ROOT / '.local/web/runs' / sys.argv[1]
record = json.loads((run / 'process.json').read_text())
proc = Path('/proc') / str(record['launcher_pid'])
if not proc.exists():
    print('This run is already stopped')
    sys.exit(0)
ticks = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
command = (proc / 'cmdline').read_bytes().split(b'\0')
if record.get('launcher_start_ticks') != ticks or not any(
        Path(item.decode()).resolve() == ROOT / 'scripts/harness-web.py' for item in command if item):
    sys.exit('Process identity differs from this run; no process was stopped')
os.kill(record['launcher_pid'], signal.SIGTERM)
print('Stopping run ' + run.name + '; private results are retained')
