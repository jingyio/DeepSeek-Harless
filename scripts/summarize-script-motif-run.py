#!/usr/bin/env python3
"""离线核算真实任务；模型请求、脚本回执与实际 PDF 交付分别报告。"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def summarize(task):
    task = Path(task)
    state = json.loads((task / 'task-state.json').read_text())
    config = json.loads((task / 'effective-config.json').read_text())
    events = [json.loads(line) for line in (task / 'events.jsonl').read_text().splitlines() if line]
    audit_path = task / 'script-motif-audit.jsonl'
    audit = [json.loads(line) for line in audit_path.read_text().splitlines() if line] if audit_path.exists() else []
    counts = Counter(row['kind'] for row in audit)
    workspace = Path(config['workspace']).resolve()
    outputs = workspace / 'outputs'
    # Uploaded manuscript/figure PDFs never satisfy report delivery.
    reports = []
    if outputs.is_dir():
        for path in outputs.rglob('*.pdf'):
            if path.is_symlink() or not path.resolve().is_relative_to(outputs.resolve()):
                continue
            data = path.read_bytes()
            if data.startswith(b'%PDF-'):
                reports.append({'file': str(path.relative_to(workspace)),
                                'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    stops = [row['data'].get('reason') for row in events if row.get('type') == 'turn/end']
    def learning_record(name):
        path=task/name
        return json.loads(path.read_text()) if path.exists() else None
    return {
        'task_id': state['task_id'], 'native_status': state['status'],
        'native_failure': state.get('failure'), 'provider_mode': config.get('provider_mode'),
        'duration_ms': state.get('duration_ms'), 'stats': state.get('stats', {}),
        'script_events': dict(counts),
        'verified_script_skips': counts['script_model_request_skipped_verified'],
        'shadow_candidates': counts['script_shadow_candidate'],
        'embedding_ms_recorded': sum(row.get('elapsed_ms', 0) for row in audit),
        'embedding_timing_available': counts['script_embedding'] > 0,
        'turn_stop_reasons': stops, 'pdf_files': reports,
        'pdf_delivery_observed': bool(reports),
        'quality': 'not_independently_reviewed',
        'loaded_learning_generation': learning_record('script-learning-snapshot.json'),
        'post_task_learning': learning_record('script-learning-status.json'),
        'cost_scope': 'proxy_estimate_not_provider_bill; skips_are_not_net_savings',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    value = json.dumps(summarize(args.task), ensure_ascii=False, indent=2) + '\n'
    if args.output:
        # Never silently overwrite prior experimental evidence.
        with args.output.open('x') as stream:
            stream.write(value)
        args.output.chmod(0o600)
    else:
        print(value, end='')


if __name__ == '__main__':
    main()
