"""No API: freeze local continuation candidates from explicit normal baselines."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.paper_shadow_compiler import compile_paper_shadow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train', action='append', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    for path in [*args.train, args.output]:
        if not path.resolve().is_relative_to(ROOT/'.local'):
            parser.error('private .local paths required')
    library = compile_paper_shadow(args.train)
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with args.output.open('x', encoding='utf-8') as stream:
        args.output.chmod(0o600)
        stream.write(json.dumps(library, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'motifs': len(library['motifs']), 'manifest_digest': library['manifest_digest'],
                      'model_requests': 0, 'execution_policy': 'shadow_only'}))


if __name__ == '__main__':
    main()
