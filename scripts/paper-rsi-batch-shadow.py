"""统一调度输出协议下，正常轨迹编译完整工具批次，再前瞻 Shadow。

沿用真实服务器、累计预算与独立副本验收；没有 execute 入口。
旧提示与旧统计不修改。新协议同时用于 baseline 和 Shadow。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.file_lock import exclusive_lock
from src.adapters.trace_rsi_motif_compiler import CONFIG_FIELDS

spec = importlib.util.spec_from_file_location('batch_task_base', ROOT / 'scripts/paper-rsi-generated-task.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
EXP = ROOT / '.local/paper-reference/paper-rsi-batch-shadow-20261011-v1'
base.EXP = EXP
ADDITIONS = ('src/adapters/trace_rsi_batch_compiler.py',
             'src/adapters/dsh_trace_rsi_batch_shadow.ts',
             'scripts/paper-rsi-batch-shadow.py')
FILES = [*base.FILES, *ADDITIONS]
PROTOCOLS = {'narration-v1': '''
本轮调度输出约定（baseline 与 Shadow 相同）：已有科研判断仍按上文完整保留在报告。新的修订选择、冲突解释、科研判断及最终结论不能省略；可在最终回复中说明修订依据和限制。若当前请求仅调度已决定的工具操作，直接调用工具，避免重复“现在读取/接着检查”等调度旁白。若当前请求需要新的判断、解释冲突或请求授权，照常输出必要文字。自行决定需要调用哪些工具，不预设工具顺序或检查流程。最终说明遗漏、重复、标识配对的修订依据，并明确真实性和正式版本尚未在本轮核验。'''
,
'tool-channel-v2': '''
本轮采用工具调度通道（baseline 与 Shadow 相同）：正常工具调用阶段只输出 tool call，不附自然语言调度旁白。修订选择及依据、已有科研判断和最终结论仍需完整保留，不能以省略判断换取少说话；已有条目按上文原样保留，最终回复明确说明遗漏、重复、标识配对三类修订的依据，并说明本轮未核验文献真实性和正式版本。若遇到新的实质冲突、依据不足、失败恢复或需要授权，立即正常输出必要文字，不受工具通道约定限制。自行决定工具选择、数量及顺序，不预设检查流程。'''}
PROTOCOL_VERSION = 'narration-v1'
PROTOCOL = PROTOCOLS[PROTOCOL_VERSION]
PROMPT = base.PROMPT + PROTOCOL
save, load, sha = base.save, base.load, base.sha


def ordered_outcome(blocks, prediction, results, live_verified):
    """完整声明、每项结果和实时核验缺一不可；文字仍挡住严格替代。"""
    if not prediction:
        return 'no_prediction'
    calls = [b for b in blocks if b.get('type') == 'tool-call']
    actual = [{'tool': b['name'], 'arguments': json.loads(b['arguments'])
               if isinstance(b['arguments'], str) else b['arguments']} for b in calls]
    if actual != prediction['expected_tools']:
        return 'different_whole_tool_batch'
    expected = prediction['expected_results']
    if len(calls) != len(expected) or any(b['id'] not in results or results[b['id']] != value
                                            for b, value in zip(calls, expected)):
        return 'different_result_or_version'
    if not live_verified:
        return 'live_batch_unverified'
    if any(b.get('type') != 'tool-call' and not
           (b.get('type') == 'text' and not b.get('text', '').strip()) for b in blocks):
        return 'whole_batch_match_text_requires_review'
    return 'strict_whole_request'


def matched_request_cost(rows, ledger, request_files, actual_requests):
    """仅同一原生轨迹的已观察成本；不冒充替代后反事实费用。"""
    names = sorted(request_files, key=lambda p: int(p.stem))
    if len(rows) != actual_requests or len(names) != actual_requests:
        return {'mapping_status': 'request_boundary_not_one_to_one', 'matched_request_observed_usd': None}
    by_id = {r['request_id']: r for r in ledger}
    ids = [int(p.stem) for p in names]
    if len(by_id) != len(ledger) or any(i not in by_id or by_id[i].get('observed_peak_usd') is None
                                        or by_id[i].get('response_status') != 200 for i in ids):
        return {'mapping_status': 'incomplete_or_failed_usage', 'matched_request_observed_usd': None}
    observed = sum(by_id[i]['observed_peak_usd'] for i in ids)
    matched = sum(by_id[ids[r['ordinal'] - 1]]['observed_peak_usd']
                  for r in rows if r['outcome'] == 'strict_whole_request')
    return {'mapping_status': 'complete_one_to_one_observed_usage',
            'all_request_observed_usd': observed,
            'matched_request_observed_usd': matched,
            'matched_observed_cost_fraction': matched / observed if observed else 0,
            'actual_cost_saved_usd': 0, 'counterfactual_cost_after_takeover': 'unknown'}


def score(run):
    events = base.parent.events(run)
    messages = [e for e in events if e['type'] == 'assistant/message']
    audit = [json.loads(s) for s in (run / 'work/shadow.jsonl').read_text().splitlines()]
    boundaries = [r for r in audit if r['kind'] in ['prediction', 'deferred']]
    if len(messages) != len(boundaries) or [r['request_ordinal'] for r in boundaries] != list(range(1, len(messages) + 1)):
        raise ValueError('missing_prospective_request_boundaries')
    results = {}
    for event in events:
        if event['type'] != 'tool/result':
            continue
        for block in event['data']['message']['content']:
            if block.get('type') != 'tool-result' or block.get('isError') or event['data'].get('error'):
                continue
            try:
                results[block['toolCallId']] = json.loads(''.join(b.get('text', '') for b in block.get('content', []) if b.get('type') == 'text'))
            except (ValueError, TypeError):
                pass
    rows = []
    for message, row in zip(messages, boundaries):
        prediction = row.get('prediction')
        verified = any(a['kind'] == 'shadow_batch_result' and a['request_ordinal'] == row['request_ordinal']
                       and a.get('verified') is True for a in audit)
        rows.append({'ordinal': row['request_ordinal'],
                     'outcome': ordered_outcome(message['data']['message']['content'], prediction, results, verified),
                     'predicted_batch_size': len(prediction['expected_tools']) if prediction else 0,
                     'defer_reason': row.get('reason')})
    metrics = load(run / 'metrics.json')
    n = metrics['actual_requests']  # 全部真实请求，含重试/子 Agent，绝不缩小分母。
    strict = sum(r['outcome'] == 'strict_whole_request' for r in rows)
    matching = sum(r['outcome'] in ['strict_whole_request', 'whole_batch_match_text_requires_review'] for r in rows)
    result = {'actual_requests': n, 'root_messages': len(rows), 'strict_whole_request': strict,
              'matching_whole_tool_batch': matching, 'strict_ratio': strict / n if n else 0,
              'actual_model_skips': 0, 'new_estimated_usd': metrics['new_estimated_usd'],
              'semantic_quality': 'not_reviewed', 'interface_protocol_changed': True,
              'frozen_library_sha256': sha(EXP / 'shadow-library.json'), 'rows': rows}
    ledger = [json.loads(line) for line in (run / 'cost-ledger.jsonl').read_text().splitlines()]
    result['observed_cost_analysis'] = matched_request_cost(rows, ledger, list((run / 'requests').glob('*.json')), n)
    save(run / 'shadow-score.json', result)
    print(json.dumps({'run': run.name, **result}), flush=True)
    return result


def task(case, mode, label):
    config = base.prepare(case)
    config['mode'] = mode
    plugin = ROOT / 'src/adapters/dsh_trace_rsi_shadow.ts'
    files = base.FILES
    if mode == 'shadow':
        library = load(EXP / 'shadow-library.json')
        config.update(shadow_library=str(EXP / 'shadow-library.json'), batch_library_digest=library['manifest_digest'])
        config['code_files'] = {str(ROOT / p): sha(ROOT / p) for p in FILES}
        if config['code_files'] != {**library['code_files_sha256'], **library['code_additions_sha256']}:
            raise ValueError('batch_library_code_drift')
        plugin = ROOT / 'src/adapters/dsh_trace_rsi_batch_shadow.ts'
        files = FILES
    path = EXP / 'runs' / label / 'config.json'
    policy = '\n- insert:\n    - name: "@deepseek-ai/dsh-mcp-client"\n      config:\n        serverName: paper_trace_rsi\n        transport: stdio\n        failOnStartupError: true\n        command: ' + json.dumps(shutil.which('node')) + '\n        args: ' + json.dumps(['--experimental-strip-types', str(ROOT / 'scenarios/paper-submission/trace-rsi-task-server.ts')]) + '\n        cwd: ' + json.dumps(str(ROOT)) + '\n        env:\n          SSS_TRACE_RSI_TASK_CONFIG: ' + json.dumps(str(path)) + '\n    - name: ' + json.dumps(plugin.as_uri()) + '\n'
    base.parent.EXP = EXP
    base.parent.FILES = files
    run = base.parent.paid(label, PROMPT, policy, config, ['SSS_TRACE_RSI_TASK_CONFIG'])
    effective, manifest = load(run / 'config.json'), load(run / 'manifest.json')
    manifest.update({k: effective[k] for k in CONFIG_FIELDS})
    manifest.update(binding_snapshot_stage='post_run_effective_config',
                    orchestration_sha256=sha(Path(__file__)),
                    control_protocol_sha256=base.parent.digest(PROTOCOL),
                    control_protocol_version=PROTOCOL_VERSION,
                    unchanged_base_prompt_sha256=base.parent.digest(base.PROMPT),
                    semantic_judgment_retained=True)
    save(run / 'manifest.json', manifest)
    base.verify(run)
    if mode == 'shadow' and (run / 'events.jsonl').exists():
        score(run)


def compile_library(labels):
    from src.adapters.trace_rsi_batch_compiler import compile_trace_rsi_batches
    path = EXP / 'shadow-library.json'
    if path.exists():
        raise ValueError('preserve_frozen_batch_library')
    runs = [EXP / 'runs' / label for label in labels]
    if any((run / 'prompt.md').read_text() != PROMPT for run in runs):
        raise ValueError('shared_control_protocol_required')
    library = compile_trace_rsi_batches(runs, root=ROOT,
               code_additions={str(ROOT / p): sha(ROOT / p) for p in ADDITIONS})
    save(path, library)
    print(json.dumps({'manifest_digest': library['manifest_digest'],
          'motifs': [{'anchor': m['anchor'], 'batch': m['batch'], 'support': m['training_session_count']}
                     for m in library['motifs']]}), flush=True)


def main():
    global EXP, PROTOCOL, PROMPT, PROTOCOL_VERSION
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['preview', 'baseline', 'compile', 'shadow', 'verify', 'score'])
    parser.add_argument('--case', default='t01_main')
    parser.add_argument('--label')
    parser.add_argument('--training', nargs='+', default=['baseline-main', 'baseline-abstract'])
    parser.add_argument('--protocol-version', choices=list(PROTOCOLS), default='narration-v1')
    args = parser.parse_args()
    PROTOCOL_VERSION = args.protocol_version
    PROTOCOL = PROTOCOLS[PROTOCOL_VERSION]
    PROMPT = base.PROMPT + PROTOCOL
    if PROTOCOL_VERSION == 'tool-channel-v2':
        EXP = ROOT / '.local/paper-reference/paper-rsi-batch-shadow-20261011-v2'
        base.EXP = EXP
    EXP.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.phase == 'preview':
        _, prior, _ = base.parent.rsi.reference.budget.account(EXP)
        print(json.dumps({'experiment': EXP.name, 'paid_enabled': False, 'model': 'deepseek-flash',
              'reasoning_effort': 'off', 'output_cap': 8192, 'request_limit': None, 'compression': False,
              'cumulative_cap_usd': base.parent.rsi.load_budget_record(base.parent.AUTH)['cap_usd'],
              'cumulative_estimated_usd': prior, 'prompt_changed_for_all_groups': True,
              'control_protocol_version': PROTOCOL_VERSION,
              'mode': 'shadow_only_no_execute'}))
        return
    if args.phase == 'compile':
        compile_library(args.training)
        return
    if not args.label:
        parser.error('--label required')
    if args.phase in ['verify', 'score']:
        (base.verify if args.phase == 'verify' else score)(EXP / 'runs' / args.label)
        return
    lock = ROOT / '.local/paper-motif/.budget.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(lock) as stream:
        task(args.case, args.phase, args.label)


if __name__ == '__main__':
    main()
