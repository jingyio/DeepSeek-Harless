"""科研 PPT 公共运行记账；未知费用不按零计，代理估费不冒充实付。"""
from __future__ import annotations

import json
import math
from pathlib import Path
import subprocess

from .documents import file_hash

ROOT = Path(__file__).resolve().parents[2]


def lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.is_file() else []


def version(command: list[str]) -> str:
    try:
        return subprocess.check_output(command, cwd=ROOT, text=True, encoding='utf-8', timeout=15).strip()
    except (OSError, subprocess.SubprocessError):
        return 'unknown'


def token_totals(ledger: list[dict], metrics: dict) -> dict:
    """未知计数保持 None；metrics 回退仅是可见消息的观测量。"""
    fields = {'prompt_cache_miss_tokens': 'inputTokens', 'prompt_cache_hit_tokens': 'cacheReadTokens',
              'completion_tokens': 'outputTokens', 'total_tokens': 'totalTokens'}
    requests = [r for r in ledger if 'request_id' in r]
    totals, sources, partial = {}, {}, {}
    for field, metric in fields.items():
        values = [r.get('response_usage', {}).get(field) for r in requests]
        known = [v for v in values if type(v) is int and v >= 0]
        if values and len(known) == len(values):
            totals[field], sources[field] = sum(known), 'upstream_ledger'
        else:
            fallback = metrics.get(metric)
            seen = metrics.get('model_requests')
            evidence = (type(seen) is int and seen > 0) or metrics.get('upstream_requests') == 0
            totals[field] = fallback if evidence and type(fallback) is int and fallback >= 0 else None
            sources[field] = 'metrics_observed_only' if totals[field] is not None else 'unknown'
            partial[field] = sum(known) if known else None
    return {'tokens': totals, 'token_sources': sources, 'ledger_observed_subtotals': partial,
            'token_accounting_complete': all(s == 'upstream_ledger' for s in sources.values()) or metrics.get('upstream_requests') == 0}


def collect_accounting(run: Path) -> dict:
    """完整阶段账本；保留失败请求和部分证据，预算上限不当实付。"""
    metrics = json.loads((run / 'metrics.json').read_text(encoding='utf-8')) if (run / 'metrics.json').is_file() else {}
    ledger = lines(run / 'cost-ledger.jsonl')
    requests = [row for row in ledger if 'request_id' in row]
    count = metrics.get('upstream_requests')
    complete = type(count) is int and count >= 0 and count == len(requests)
    values = [row.get('observed_peak_usd') for row in requests]
    observed_complete = bool(values) and all(isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(value) and value >= 0 for value in values)
    hashes = {name: file_hash(run / name) for name in ('manifest.json', 'preview.json', 'metrics.json',
        'agent-events.jsonl', 'cost-ledger.jsonl', 'answer.md') if (run / name).is_file()}
    return {'run_dir': str(run), 'metrics': metrics, 'raw_file_sha256': hashes,
        'paid_model_requests': count if complete else None, 'observed_request_subtotal': len(requests),
        'request_accounting_complete': complete, 'proxy_budget_accounted_usd': metrics.get('budget_accounted_usd'),
        'proxy_observed_estimate_usd': sum(values) if observed_complete else (0.0 if complete and count == 0 else None),
        'upstream_failures': sum(row.get('response_status') != 200 for row in requests),
        'actual_invoice_usd': None, **token_totals(ledger, metrics)}


def aggregate_attempts(area: Path, *, experiment_id: str | None = None) -> dict:
    """汇总同目录的全部阶段，包括失败及修订；不绑定某一历史实验。"""
    records = [json.loads(path.read_text(encoding='utf-8')) for path in sorted(area.glob('*/result.json'))]
    paid = [row for row in records if row.get('model_call_enabled') is True]
    accounting = [item for row in paid for item in row.get('accounting', [])]
    known = all(row.get('accounting_complete') is True for row in paid)

    def total(key):
        values = [row.get(key) for row in accounting]
        return sum(values) if known and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values) else None

    value = {'schema_version': 1,
        'scope': 'seed_and_all_revision_attempts_including_failures; estimates_not_invoice',
        'phase_attempts': [{'phase': row['phase'], 'status': row.get('status', 'unknown'), 'returncode': row['returncode'],
            'model_call_enabled': row['model_call_enabled'], 'elapsed_seconds': row['elapsed_seconds']} for row in records],
        'paid_model_requests': total('paid_model_requests'), 'proxy_observed_estimate_usd': total('proxy_observed_estimate_usd'),
        'observed_request_subtotal': sum(row.get('observed_request_subtotal', 0) for row in accounting),
        'proxy_budget_accounted_usd': total('proxy_budget_accounted_usd'), 'actual_invoice_usd': None,
        'all_attempts_elapsed_seconds': sum(row['elapsed_seconds'] for row in records),
        'accounting_complete': known, 'quality': 'not_reviewed', 'human_revision_minutes': None,
        'tokens': {key: sum(item['tokens'][key] for item in accounting) if known and all(item['tokens'].get(key) is not None for item in accounting) else None
            for key in ('prompt_cache_miss_tokens', 'prompt_cache_hit_tokens', 'completion_tokens', 'total_tokens')}}
    if experiment_id is not None:
        value['experiment_id'] = experiment_id
    (area / 'aggregate.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return value
