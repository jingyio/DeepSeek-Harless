#!/usr/bin/env python3
"""Compile native reuse contracts from real tasks; preserve each private round."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.reuse_compiler import collect, compile_library

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if len(set(t.resolve() for t in a.task)) < 2:
        p.error('two distinct real tasks required')
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    rows = [r for t in a.task for r in collect(t)]
    library = compile_library(rows, ROOT)
    target = a.output / 'reuse-library.json'
    target.write_text(json.dumps(library, ensure_ascii=False, indent=2) + '\n'); target.chmod(0o600)
    print(json.dumps({'contracts': len(library['contracts']), 'digest': library['digest']}))
