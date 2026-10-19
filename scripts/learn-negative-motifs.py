#!/usr/bin/env python3
"""Private negative-Motif compiler; reads real failures as well as successes."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.script_negative_compiler import collect_negative, compile_negative, RUNTIME_FILES, sha


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task', type=Path, action='append', required=True)
    p.add_argument('--implementation-file', action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    locks = {}
    for name in a.implementation_file:
        path = ROOT / name
        if Path(name).is_absolute() or '..' in Path(name).parts or not path.is_file():
            raise ValueError('relative_implementation_file_required')
        locks[name] = sha(path.read_bytes())
    rows = []
    for task in a.task:
        task = task.resolve(strict=True)
        if not task.is_relative_to(ROOT / '.local'): raise ValueError('private_trace_required')
        run = task.parent.parent.name
        snapshot = json.loads((ROOT / '.local/script-motif-experiments' / run / 'source-snapshot.json').read_text())
        if any(snapshot.get(k) != v for k, v in locks.items()):
            raise ValueError('historical_tool_implementation_changed')
        rows.extend(collect_negative(task))
    library = compile_negative(rows, locks, {k: sha((ROOT / k).read_bytes()) for k in RUNTIME_FILES})
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / 'library.json').write_text(json.dumps(library, ensure_ascii=False, indent=2) + '\n')
    (a.output / 'library.json').chmod(0o600)
    print(json.dumps({'rules': len(library['rules']), 'digest': library['digest'], 'model_requests': 0}))


if __name__ == '__main__': main()
