"""Copy immutable experiment evidence into a portable, private result bundle.

Run after the experiment; no model calls and no changes to original run files.
Re-run after reviews to include their JSON evidence and the final benchmark source.
"""
from pathlib import Path
import argparse
import json
import shutil


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    source, output = args.experiment.resolve(), args.output.resolve()
    if source == output or source in output.parents:
        raise ValueError('Delivery must be outside the original experiment')
    evidence = output / 'evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    for name in ('data', 'runs', 'comparison_figures'):
        shutil.copytree(source / name, evidence / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('dsh', '__pycache__'))
    for name in ('RESULTS.json', 'library.json', 'global-ledger.jsonl'):
        shutil.copy2(source / name, evidence / name)
    if (source / 'review').exists():
        shutil.copytree(source / 'review', evidence / 'review', dirs_exist_ok=True)
    bench = Path(__file__).resolve().parent
    shutil.copytree(bench, output / 'source' / bench.name, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    reports = output / 'reports'
    reports.mkdir(exist_ok=True)
    for case in ('eval_biology', 'eval_education', 'eval_energy'):
        run = source / 'runs' / (case + '_execute')
        verifications = [json.loads(x.read_text(encoding='utf-8')) for x in (run / 'workspace' / 'records').glob('rra-report_verification-*.json')]
        passed = [v for v in verifications if v['payload']['quality_passed']]
        if len(passed) != 1:
            raise ValueError('Do not guess between final report verifications')
        record = json.loads((run / 'workspace' / 'records' / (passed[0]['payload']['report_id'] + '.json')).read_text(encoding='utf-8'))
        relative = record['payload']['path'].replace('\\', '/').split('/workspace/', 1)[1]
        shutil.copy2(run / 'workspace' / relative, reports / (case + '_original.pdf'))
    print(json.dumps({'output': str(output), 'evidence_runs': len(list((evidence / 'runs').glob('*/metrics.json'))),
                      'original_reports_preserved': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
