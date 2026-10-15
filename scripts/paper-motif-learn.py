"""Server offline learning entry; no model calls and no execution of stored code."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.parameter_learning import advance_round, latest_round


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--train-run', type=Path, action='append', default=[])
    parser.add_argument('--validation-run', type=Path, action='append')
    args = parser.parse_args()
    private = (ROOT / '.local').resolve()
    for path in [args.store, *args.train_run, *(args.validation_run or [])]:
        if not path.resolve().is_relative_to(private): parser.error('private learning paths must stay under .local')
    path, record, library = (advance_round(args.store, args.train_run, args.validation_run)
                             if args.train_run else latest_round(args.store))
    print(json.dumps({'round': path.name, 'training_sessions': len(record['training']),
                      'validation_sessions': len(record['validation']), 'added_motifs': record['added_motifs'],
                      'motifs': [{'motif_id': m['motif_id'], 'contract': m['prototype']['contract'],
                                  'training_instances': len(m['training_witnesses']),
                                  'validation_instances': len(m['heldout_witnesses'])} for m in library['motifs']],
                      'library_digest': library['manifest_digest'], 'production_activation': False,
                      'paid_calls': 0}, ensure_ascii=False))


if __name__ == '__main__': main()
