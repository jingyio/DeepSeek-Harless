"""从正常衔接与非衔接见证学习会话状态条件；不改变工具或提示。

这是有界二值特征的工程学习器。条件值从轨迹决定，不预设论文 DAG；
不是由模型自行生成的任意守卫程序，也不授权自动执行。
"""
from collections import defaultdict
import copy
from pathlib import Path

from .trace_rsi_motif_compiler import (
    ROOT, RECEIPT_FIELDS, _receipt, _training_run, _root_events,
    _validate_projected_input, compile_trace_rsi_motifs, file_sha256,
)
from .trace_tool_evidence import digest

FEATURE = 'prior_same_input_check'
ADDITIONS = ('src/adapters/trace_rsi_state_compiler.py',
             'src/adapters/dsh_trace_rsi_state_shadow.ts',
             'scripts/paper-rsi-state-shadow.py')


def receipt_fingerprint(receipt):
    return digest({k: receipt[k] for k in RECEIPT_FIELDS if k != 'input_id'})


def learn_binary_condition(observations):
    """仅选择能保留所有正例并拒绝全部已观察负例的条件。"""
    positives = [o for o in observations if o['continues']]
    negatives = [o for o in observations if not o['continues']]
    if not negatives:
        return {'status': 'no_negative_evidence', 'condition': None}
    values = {o['features'][FEATURE] for o in positives}
    if len(values) != 1 or not positives:
        return {'status': 'ambiguous_state', 'condition': None}
    value = next(iter(values))
    if any(o['features'][FEATURE] == value for o in negatives):
        return {'status': 'ambiguous_state', 'condition': None}
    return {'status': 'learned_condition', 'condition': {'feature': FEATURE, 'equals': value}}


def compile_stateful_trace_motifs(runs, additions, *, root=ROOT):
    paths = [Path(p) for p in runs]
    base = compile_trace_rsi_motifs(paths, root=root)
    # The old implementation remains byte-identical. Only explicit new observer
    # files enter the derived runtime version; no source witness is relabelled.
    if set(additions) != {str(Path(root)/p) for p in ADDITIONS}:
        raise ValueError('explicit_observer_additions_required')
    if any(file_sha256(p) != h for p, h in additions.items()):
        raise ValueError('observer_addition_version_changed')
    if set(additions) & set(base['code_files_sha256']):
        raise ValueError('cannot_replace_training_code')
    by_motif = defaultdict(list)
    observed_edges = {(w['session_id'], w['anchor_call_id']): m['motif_id']
                     for m in base['motifs'] for w in m['witnesses']}
    motif_for_anchor = {m['anchor']: m for m in base['motifs']}
    for run in paths:
        config, frozen, tools, requests, event_path, actions, catalog_text, catalog_sha = _training_run(run, Path(root), None)
        messages = [e for _, e in _root_events(event_path, config['session_id']) if e['type'] == 'assistant/message']
        checked = set()
        next_name = tools[[t['name'] for t in tools].index(
            'mcp__paper_trace_rsi__' + frozen['candidate']['name'])]['name']
        for action in sorted(actions, key=lambda a: a['call_order']):
            if not action['ok']:
                checked.clear()
                continue
            if action['name'] == next_name:
                try:
                    receipt = _receipt(action['value'], config, catalog_sha)
                    if action['arguments'] == {'input_id': receipt['input_id']} and 'output' in action['value']:
                        checked.add(receipt_fingerprint(receipt))
                except (ValueError, TypeError, KeyError):
                    checked.clear()
                continue
            if action['name'] not in motif_for_anchor or action['declared_count'] != 1:
                continue
            try:
                receipt = _receipt(action['value'], config, catalog_sha)
                _validate_projected_input(action, receipt, frozen, catalog_text)
            except (ValueError, TypeError, KeyError):
                continue
            ordinal = action['ordinal']
            if ordinal >= len(messages):
                continue
            blocks = messages[ordinal]['data']['message']['content']
            next_tools = [b['name'] for b in blocks if b.get('type') == 'tool-call']
            positive = (config['session_id'], action['call_id']) in observed_edges
            # Failed/ambiguous same-tool attempts are censored, not negatives.
            if not positive and (next_name in next_tools or len(next_tools) > 1):
                continue
            if not positive and not next_tools and not any(b.get('text', '').strip() for b in blocks if b.get('type') == 'text'):
                continue
            by_motif[motif_for_anchor[action['name']]['motif_id']].append({
                'session_id': config['session_id'], 'run_id': run.name,
                'anchor_call_id': action['call_id'], 'anchor_request': ordinal,
                'events_sha256': file_sha256(event_path), 'receipt': receipt,
                'features': {FEATURE: receipt_fingerprint(receipt) in checked},
                'continues': positive, 'next_request': ordinal + 1,
                'next_tools': next_tools,
                'next_text_blocks': sum(b.get('type') == 'text' and bool(b.get('text', '').strip()) for b in blocks),
            })
    guards = []
    for motif in base['motifs']:
        observations = by_motif[motif['motif_id']]
        learnt = learn_binary_condition(observations)
        guards.append({'motif_id': motif['motif_id'], **learnt, 'observations': observations,
                       'positive_count': sum(o['continues'] for o in observations),
                       'negative_count': sum(not o['continues'] for o in observations)})
    derived = copy.deepcopy(base)
    derived['code_files_sha256'] = {**base['code_files_sha256'], **additions}
    derived.pop('manifest_digest')
    derived['manifest_digest'] = digest(derived)
    library = {'schema_version': 1, 'kind': 'trace_rsi_state_shadow', 'execution_policy': 'shadow_only',
               'base_library': base, 'derived_library': derived, 'guards': guards,
               'feature_protocol': {'name': FEATURE, 'key_fields': list(RECEIPT_FIELDS[1:]),
                                    'scope': 'current_session_successful_generated_check'},
               'observer_additions_sha256': additions,
               'limitations': ['仅新增观察器，不迁移工具实现或来源逻辑。',
                               '二值状态特征由工程提供，条件由正常正反轨迹选择。',
                               '同论文的负例，不是结束语义判断或跨论文认证。']}
    library['manifest_digest'] = digest(library)
    return library
