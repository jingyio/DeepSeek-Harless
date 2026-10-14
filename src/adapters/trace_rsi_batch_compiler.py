"""从完整正常请求编译有界批次 Shadow 候选；不执行历史代码或工具。

批次来自助手声明与实际派发/结果的一一对应。返回正文只留在私有轨迹，
库保存其摘要和当前冻结程序/状态的结果契约，不授予执行或科研判断权限。
"""
from collections import Counter, defaultdict
from pathlib import Path
import re

from .trace_rsi_motif_compiler import (
    ROOT, PREFIX, RECEIPT_FIELDS, _registered_hashes, _receipt, _root_events,
    _training_run, _validate_projected_input, file_sha256,
)
from .trace_tool_evidence import digest

ADDITIONS = ('src/adapters/trace_rsi_batch_compiler.py',
             'src/adapters/dsh_trace_rsi_batch_shadow.ts',
             'scripts/paper-rsi-batch-shadow.py')
MAX_BATCH = 64


def _messages(events):
    """完整模型请求边界；不删除旁白，也不选择声明中的部分工具。"""
    rows = []
    for line, event in events:
        if event['type'] != 'assistant/message':
            continue
        content = event['data']['message']['content']
        rows.append({'line': line, 'content_sha256': digest(content),
                     'call_ids': [b['id'] for b in content if b.get('type') == 'tool-call'],
                     'text_blocks': sum(b.get('type') == 'text' and bool(b.get('text', '').strip())
                                        for b in content)})
    return rows


def _no_arguments_contract(parameters):
    return (parameters.get('type') == 'object' and parameters.get('properties') == {}
            and parameters.get('required', []) == []
            and parameters.get('additionalProperties') is False)


def _readonly_result(action, receipt, frozen, tools, config, catalog_text, catalog_sha):
    """冻结检查、无参读取，以及显式允许的当前私有产物导出契约。"""
    if (not action['ok'] or not action['name'].startswith(PREFIX)
            or _receipt(action['value'], config, catalog_sha) != receipt):
        raise ValueError('batch_failed_or_receipt_mismatch')
    value, arguments = action['value'], action['arguments']
    if action['name']==PREFIX+'export_revision_report':
        if (config.get('private_export_policy')!='current_task_revision_report_only' or
            arguments!={'input_id':receipt['input_id']} or
            set(value)!={*RECEIPT_FIELDS,'artifact_name','artifact_sha256','scope','output'} or
            value['artifact_name']!='revision-report.md' or
            value['scope']!='structural_revision_not_full_bibliography_verification' or
            not isinstance(value['artifact_sha256'],str) or not re.fullmatch(r'[0-9a-f]{64}',value['artifact_sha256'])):
            raise ValueError('bounded_private_artifact_contract_required')
        return {'tool':action['name'],'arguments_binding':{'input_id':'/input_id'},
                'result_kind':'private_artifact_output','effect':'private_current_report_export'}
    if action['name'] == PREFIX + frozen['candidate']['name']:
        if (arguments != {'input_id': receipt['input_id']}
                or set(value) != {*RECEIPT_FIELDS, 'output'}):
            raise ValueError('batch_candidate_input_or_result_mismatch')
        return {'tool': action['name'], 'arguments_binding': {'input_id': '/input_id'},
                'result_kind': 'candidate_output'}
    parameters = next(t['parameters'] for t in tools if t['name'] == action['name'])
    if (arguments != {} or not _no_arguments_contract(parameters)
            or set(value) != {*RECEIPT_FIELDS, 'report', 'input'}
            or not isinstance(value['report'], dict) or not isinstance(value['input'], dict)):
        raise ValueError('unsupported_batch_tool_or_result_contract')
    _validate_projected_input(action, receipt, frozen, catalog_text)
    return {'tool': action['name'], 'arguments': {}, 'result_kind': 'task_state'}


def _anchor_receipt(action, frozen, tools, config, catalog_text, catalog_sha):
    if not action['ok'] or not action['name'].startswith(PREFIX):
        raise ValueError('unsupported_or_failed_batch_anchor')
    receipt = _receipt(action['value'], config, catalog_sha)
    _validate_projected_input(action, receipt, frozen, catalog_text)
    if set(action['value']) == set(RECEIPT_FIELDS):
        # A successful report write may anchor a batch, but writes are never
        # inferred as read-only members of the predicted batch.
        full_write=(set(action['arguments'])=={'report_sha256','report'} and
                    isinstance(action['arguments']['report'],dict))
        compact_write=(action['name']==PREFIX+'apply_revision_plan' and
                    set(action['arguments'])=={'report_sha256','plan'} and
                    isinstance(action['arguments']['plan'],dict) and
                    set(action['arguments']['plan'])=={'set_ids','keep_once_keys','remove_keys','add_records'} and
                    all(isinstance(v,list) for v in action['arguments']['plan'].values()) and
                    config.get('code_files',{}).get(config.get('patch_library_path'))==config.get('patch_library_sha256') and
                    isinstance(config.get('patch_library_sha256'),str))
        if not (full_write or compact_write):
            raise ValueError('unsupported_receipt_only_anchor')
    else:
        _readonly_result(action, receipt, frozen, tools, config, catalog_text, catalog_sha)
    return receipt


def _request_actions(actions, messages):
    by_request = defaultdict(list)
    for action in actions:
        by_request[action['ordinal']].append(action)
    for ordinal, message in enumerate(messages, 1):
        observed = sorted(by_request[ordinal], key=lambda a: a['call_order'])
        if [a['call_id'] for a in observed] != message['call_ids']:
            raise ValueError('request_declaration_dispatch_order_mismatch')
        end = messages[ordinal]['line'] if ordinal < len(messages) else float('inf')
        if any(not (message['line'] < a['line'] < a['result_line'] < end) for a in observed):
            raise ValueError('request_dispatch_result_boundary_mismatch')
        by_request[ordinal] = observed
    return by_request


def _additions(code_additions, root, baseline):
    required = {str(root / name) for name in ADDITIONS}
    if not isinstance(code_additions, dict) or set(code_additions) != required:
        raise ValueError('explicit_batch_observer_additions_required')
    _registered_hashes(code_additions, root)
    base_paths = {str((Path(name) if Path(name).is_absolute() else root / name).resolve())
                  for name in baseline}
    if any(str(Path(name).resolve()) in base_paths for name in code_additions):
        raise ValueError('cannot_replace_training_code')
    return dict(code_additions)


def compile_trace_rsi_batches(runs, candidate=None, *, root=ROOT, code_additions=None):
    """完整请求批次候选；至少两 Session 的支持由在线 Shadow 再校验。"""
    root = Path(root)
    paths = [Path(run) for run in runs]
    if (not paths or len({str(p.resolve()) for p in paths}) != len(paths)
            or any(p.is_symlink() for p in paths)):
        raise ValueError('distinct_regular_training_runs_required')
    groups, sources, sessions, rejected = defaultdict(list), {}, set(), Counter()
    common = None
    for run in paths:
        config, frozen, tools, requests, event_path, actions, catalog_text, catalog_sha = _training_run(
            run, root, candidate)
        session, run_id = config['session_id'], config.get('run_id', run.name)
        if not isinstance(run_id, str) or not run_id or len(run_id) > 256:
            raise ValueError('bounded_training_run_identity_required')
        if session in sessions or run_id in sources:
            raise ValueError('independent_named_training_sessions_required')
        sessions.add(session)
        current = {'tool_digest': config['tool_digest'], 'candidate_sha256': config['candidate_sha256'],
                   'tools': tools, 'code_files_sha256': config['code_files']}
        if config.get('export_result_protocol') is not None:
            if config['export_result_protocol'] != 'revision_receipt_v2':
                raise ValueError('unknown_export_result_protocol')
            current['export_result_protocol'] = config['export_result_protocol']
        if common is not None and current != common:
            raise ValueError('training_tool_candidate_or_code_drift')
        common = current
        event_hash = file_sha256(event_path)
        sources[run_id] = {'run_id': run_id, 'session_id': session, 'case_id': config['case_id'],
            'source_version': config['source_version'], 'source_files_sha256': config['source_files'],
            'prompt_sha256': config['prompt_sha256'], 'events_sha256': event_hash,
            'config_sha256': file_sha256(run / 'config.json'),
            'manifest_sha256': file_sha256(run / 'manifest.json'),
            'verification_sha256': file_sha256(run / 'verification.json'),
            'requests': {p.name: file_sha256(p) for p in requests}}
        messages = _messages(_root_events(event_path, session))
        by_request = _request_actions(actions, messages)
        for ordinal in range(1, len(messages)):
            previous, following = by_request[ordinal], by_request[ordinal + 1]
            if not following:
                continue
            try:
                if len(following) > MAX_BATCH:
                    raise ValueError('bounded_batch_size_required')
                if len(previous) != 1:
                    raise ValueError('single_complete_request_anchor_required')
                anchor = previous[0]
                receipt = _anchor_receipt(anchor, frozen, tools, config, catalog_text, catalog_sha)
                next_message = messages[ordinal]
                if anchor['result_line'] >= next_message['line']:
                    raise ValueError('anchor_not_completed_before_batch_request')
                batch, observed = [], []
                for action in following:
                    descriptor = _readonly_result(action, receipt, frozen, tools, config,
                                                  catalog_text, catalog_sha)
                    batch.append(descriptor)
                    item = {'call_id': action['call_id'], 'tool': action['name'],
                            'call_line': action['line'], 'result_line': action['result_line'],
                            'arguments_sha256': digest(action['arguments']),
                            'result_sha256': digest(action['value']), 'receipt': receipt}
                    if descriptor['result_kind'] == 'candidate_output':
                        item['output_sha256'] = digest(action['value']['output'])
                    observed.append(item)
                witness = {'session_id': session, 'run_id': run_id, 'case_id': config['case_id'],
                    'anchor_call_id': anchor['call_id'], 'events_sha256': event_hash,
                    'anchor_line': anchor['line'], 'anchor_result_line': anchor['result_line'],
                    'anchor_request': ordinal, 'next_request': ordinal + 1,
                    'anchor_text_blocks': messages[ordinal - 1]['text_blocks'],
                    'next_text_blocks': next_message['text_blocks'],
                    'anchor_message_sha256': messages[ordinal - 1]['content_sha256'],
                    'next_message_sha256': next_message['content_sha256'],
                    'next_message_line': next_message['line'], 'receipt': receipt, 'batch': observed}
                graph = {'anchor': anchor['name'], 'batch': batch}
                groups[digest(graph)].append((graph, witness))
            except (ValueError, TypeError, KeyError, IndexError) as error:
                rejected[str(error)] += 1
    additions = _additions(code_additions, root, common['code_files_sha256'])
    motifs = []
    for key, observations in sorted(groups.items()):
        graph = observations[0][0]
        witnesses = [w for _, w in observations]
        support = len({w['session_id'] for w in witnesses})
        motifs.append({'motif_id': 'trace-rsi-batch-' + key[:16], **graph,
                       'witnesses': witnesses, 'training_session_count': support,
                       'support': 'repeated_sessions' if support >= 2 else 'single_session_candidate',
                       'status': 'shadow_candidate'})
    library = {'schema_version': 1, 'kind': 'trace_rsi_batch_continuation_shadow',
        'execution_policy': 'shadow_only', **common, 'code_additions_sha256': additions,
        'motifs': motifs, 'sources': sources, 'rejected': dict(rejected),
        'scope': 'normal_case_sessions_same_paper',
        'limitations': ['同论文正常案例及独立 Session，不是跨论文认证。',
            '批次来自完整下一请求的声明、派发、结果；不编造场景 DAG 或工具顺序。',
            '只支持冻结候选句柄和实际无参状态读取；未知项、失败或收据变化拒绝整批。',
            '返回正文留在私有轨迹；库的结果契约与摘要需由当前版本在线复核。',
            '单 Session 候选保留；至少两个独立 Session 支持才允许 Shadow 预测。',
            '完整工具集合不覆盖科研旁白；文字原样保存，严格无文本机会须另计。',
            '未从本批学习结束条件；重复检查的在线保守拒绝不称学习所得守卫。',
            '摘要不认证来源签名，不授权执行、模型跳过或费用节省。']}
    library['manifest_digest'] = digest(library)
    return library
