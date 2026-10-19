#!/usr/bin/env python3
"""Experimental composition root; tool schemas and native guards stay unchanged."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scenarios.paper_proofreading import server
from src.adapters.evidence_report import SessionReport
server.SessionReport=SessionReport
if __name__=='__main__':
    server.create_server(Path(sys.argv[1]),sys.argv[2] if len(sys.argv)>2 else None).run(transport='stdio')
