"""Freeze dependencies while reviewed baseline sources are still available."""
import argparse
from pathlib import Path
from pdf_dependencies import compile_graph
from pdf_tools import ROOT, save_private


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True, help='directory containing source-checked evidence and source-check.json')
    parser.add_argument('--run', type=Path, required=True, help='original run containing pdf-input-snapshot.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / '.local') or output.exists():
        parser.error('output must be a new private .local file')
    envelope = compile_graph(args.review / 'source-checked-evidence.json', args.review / 'source-check.json',
                             args.run / 'pdf-input-snapshot.json')
    save_private(output, envelope)
    print(output)


if __name__ == '__main__':
    main()
