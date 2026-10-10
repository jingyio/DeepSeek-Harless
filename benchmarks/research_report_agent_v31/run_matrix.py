"""Thin CLI alias: all execution stays in the unchanged v3 matrix/DSH runner."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from benchmarks.research_report_agent_v3.run_matrix import main

if __name__ == '__main__':
    if not any(arg=='--experiment-id' or arg.startswith('--experiment-id=') for arg in sys.argv[1:]):
        sys.argv.extend(['--experiment-id','research-report-agent-v31-20261010'])
    raise SystemExit(main())
