"""Thin CLI alias: unchanged v3 compiler, real baseline witnesses mandatory."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from benchmarks.research_report_agent_v3.compile_motifs import main

if __name__ == '__main__':
    main()
