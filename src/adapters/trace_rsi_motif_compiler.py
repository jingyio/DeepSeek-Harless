"""从合格正常 Session 编译生成工具的局部 Shadow 后继。

工具算法来自冻结的模型生成程序；此处只从完整调用证据学习边。
库不授权执行，也不把同论文的不同正常案例称作独立论文认证。
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from .trace_tool_evidence import bounded_read, digest, project_inputs

ROOT = Path(__file__).resolve().parents[2]
PREFIX = 'mcp__paper_trace_rsi__'
RECEIPT_FIELDS = ('input_id', 'input_sha256', 'report_sha256', 'source_version',
                  'candidate_sha256', 'catalog_sha256')
CONFIG_FIELDS = ('mode', 'case_id', 'session_id', 'work', 'library_path',
                 'tool_digest', 'candidate_sha256', 'source_version',
                 'source_files', 'code_files', 'prompt_sha256',
                 'catalog_path', 'catalog_sha256')
VERIFICATION_FIELDS = ('completed', 'normal_case_valid', 'source_unchanged',
                       'stage_output_passed')


def file_sha256(path):
    return hashlib.sha256(bounded_read(path, 32_000_000)).hexdigest()


def _json(path, limit=4_000_000):
    def reject(_):
        raise ValueError('non_finite_json')
    return json.loads(bounded_read(path, limit), parse_constant=reject)


def _sha(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def _object(value, reason):
    if not isinstance(value, dict):
        raise ValueError(reason)
    return value


def _arguments(value):
    return _object(json.loads(value) if isinstance(value, str) else value,
                   'object_tool_arguments_required')


def _registered_hashes(value, root):
    if not isinstance(value, dict) or not value:
        raise ValueError('registered_file_hashes_required')
    for name, expected in value.items():
        if not isinstance(name, str) or not name or not _sha(expected):
            raise ValueError('invalid_registered_file_hash')
        path = Path(name)
        if not path.is_absolute():
            path = root / path
        if file_sha256(path) != expected:
            raise ValueError('registered_file_version_changed')
    return value


def _frozen(path):
    frozen = _object(_json(path, 192000), 'frozen_trace_tool_required')
    body = {k: v for k, v in frozen.items() if k != 'manifest_digest'}
    if (frozen.get('schema_version') != 1
            or frozen.get('kind') != 'model_generated_trace_tool'
            or frozen.get('manifest_digest') != digest(body)):
        raise ValueError('invalid_frozen_trace_tool')
    candidate = _object(frozen.get('candidate'), 'frozen_candidate_required')
    if (not isinstance(candidate.get('name'), str)
            or not re.fullmatch('[a-z][a-z0-9]*(?:_[a-z0-9]+)*', candidate['name'])
            or frozen.get('candidate_sha256') != digest(candidate)
            or frozen.get('provenance_sha256') != digest(frozen.get('provenance'))
            or frozen.get('certification_sha256') != digest(frozen.get('certification'))):
        raise ValueError('invalid_frozen_candidate_or_evidence')
    certification = _object(frozen.get('certification'), 'source_replay_certification_required')
    if (certification.get('status') != 'passed' or certification.get('kind') != 'source_replay'
            or type(certification.get('heldout_cases')) is not int
            or certification['heldout_cases'] < 2):
        raise ValueError('source_replay_certification_required')
    return frozen


def load_provider_tools(path):
    """代理保存的请求可能是 JSON 对象，或被 JSON 字符串包装一次。"""
    request = _json(path, 32_000_000)
    if isinstance(request, str):
        request = json.loads(request)
    request = _object(request, 'provider_request_object_required')
    tools, names = [], set()
    for row in request.get('tools', []):
        function = _object(row.get('function'), 'provider_function_required')
        name, parameters = function.get('name'), function.get('parameters')
        if not isinstance(name, str) or not name or name in names or not isinstance(parameters, dict):
            raise ValueError('unique_ordered_tool_contracts_required')
        names.add(name)
        tools.append({'name': name, 'parameters': parameters})
    if not tools:
        raise ValueError('provider_tools_required')
    return tools


def _root_events(path, session):
    events = []
    for line, text in enumerate(bounded_read(path, 32_000_000).decode().splitlines(), 1):
        row = _object(json.loads(text), 'session_event_wrapper_required')
        sid = row.get('sessionId', row.get('session_id'))
        if not isinstance(sid, str) or not sid:
            raise ValueError('event_session_identity_missing')
        if ('sessionId' in row and 'session_id' in row and row['sessionId'] != row['session_id']):
            raise ValueError('conflicting_event_session_identity')
        if sid == session:
            event = _object(row.get('event'), 'session_event_required')
            events.append((line, event))
    if not events:
        raise ValueError('root_session_events_required')
    return events


def _actions(events, tools, request_count):
    """模型声明、实际派发、完成结果必须一一对应；不接受后台猜测。"""
    names = {tool['name'] for tool in tools}
    declared, calls, results, actions = {}, {}, set(), []
    seen_ids, ordinal, count, text_count, step = set(), 0, 0, 0, None
    for line, event in events:
        data = _object(event.get('data', {}), 'event_data_required')
        kind = event.get('type')
        if kind == 'assistant/message':
            if any(call_id not in results for call_id in declared):
                raise ValueError('model_request_before_tool_completion')
            ordinal += 1
            blocks = data.get('message', {}).get('content', [])
            if not isinstance(blocks, list):
                raise ValueError('assistant_content_required')
            declared = {}
            for block in blocks:
                if block.get('type') != 'tool-call':
                    continue
                call_id, name = block.get('id'), block.get('name')
                if not isinstance(call_id, str) or not call_id or call_id in seen_ids or name not in names:
                    raise ValueError('unique_registered_model_call_required')
                seen_ids.add(call_id)
                declared[call_id] = (name, _arguments(block.get('arguments')))
            count = len(declared)
            text_count = sum(b.get('type') == 'text' and bool(b.get('text', '').strip()) for b in blocks)
            step = data.get('step')
        elif kind == 'tool/call':
            call_id, name = data.get('callId'), data.get('name')
            args = _arguments(data.get('arguments'))
            if (call_id in calls or declared.get(call_id) != (name, args)
                    or (step is not None and data.get('step') is not None and step != data['step'])):
                raise ValueError('tool_call_differs_from_model_declaration')
            calls[call_id] = {'call_id': call_id, 'name': name, 'arguments': args,
                             'ordinal': ordinal, 'declared_count': count,
                             'text_blocks': text_count, 'line': line, 'call_order': len(calls)}
        elif kind == 'tool/result':
            message = _object(data.get('message'), 'tool_result_message_required')
            for block in message.get('content', []):
                if block.get('type') != 'tool-result':
                    continue
                call_id = block.get('toolCallId')
                source_id = message.get('source', {}).get('callId')
                if call_id not in calls or call_id in results or source_id not in (None, call_id):
                    raise ValueError('unpaired_or_duplicate_tool_result')
                results.add(call_id)
                parts = block.get('content', [])
                value = None
                if parts and all(p.get('type') == 'text' for p in parts):
                    try:
                        value = json.loads(''.join(p.get('text', '') for p in parts))
                    except (ValueError, TypeError):
                        pass
                actions.append({**calls[call_id], 'ok': not data.get('error') and not block.get('isError'),
                                'value': value, 'result_line': line})
    if (ordinal != request_count or len(calls) != len(seen_ids) or set(calls) != results):
        raise ValueError('request_or_tool_completion_boundary_mismatch')
    return actions


def _receipt(value, config, catalog_sha256):
    if not isinstance(value, dict) or any(k not in value for k in RECEIPT_FIELDS):
        raise ValueError('observed_receipt_required')
    receipt = {k: value[k] for k in RECEIPT_FIELDS}
    if (any(not _sha(receipt[k]) for k in RECEIPT_FIELDS if k != 'input_id')
            or receipt['source_version'] != config['source_version']
            or receipt['candidate_sha256'] != config['candidate_sha256']
            or receipt['catalog_sha256'] != catalog_sha256):
        raise ValueError('receipt_version_mismatch')
    base = {k: receipt[k] for k in RECEIPT_FIELDS if k != 'input_id'}
    if receipt['input_id'] != 'trace-input-' + digest({**base, 'session_id': config['session_id']}):
        raise ValueError('receipt_input_identity_mismatch')
    return receipt


def _validate_projected_input(anchor, receipt, frozen, catalog_text):
    value, args = anchor['value'], anchor['arguments']
    if 'input' in value and digest(value['input']) != receipt['input_sha256']:
        raise ValueError('receipt_input_hash_mismatch')
    report = args.get('report', value.get('report'))
    bindings = frozen.get('provenance', {}).get('proposal', {}).get('input_bindings')
    if report is not None and isinstance(bindings, dict):
        projected = project_inputs({'catalog.json': catalog_text,
                                    'triage.json': json.dumps(report, ensure_ascii=False)}, bindings)
        if digest(projected) != receipt['input_sha256']:
            raise ValueError('receipt_projected_input_mismatch')
    if 'report_sha256' in args and not _sha(args['report_sha256']):
        raise ValueError('invalid_report_compare_and_swap')


def _training_run(run, root, supplied_candidate):
    config, manifest, metrics = (_object(_json(run / name), 'run_metadata_required')
                                for name in ('config.json', 'manifest.json', 'metrics.json'))
    verification = _object(_json(run / 'verification.json'), 'normal_case_verification_required')
    if (any(field not in config for field in CONFIG_FIELDS)
            or config['mode'] != 'baseline' or metrics.get('status') != 'completed'
            or type(metrics.get('actual_model_skips')) is not int or metrics['actual_model_skips'] != 0
            or metrics.get('verified_skips', 0) != 0
            or not all(verification.get(field) is True for field in VERIFICATION_FIELDS)):
        raise ValueError('verified_normal_baseline_required')
    if any(manifest.get(field) != config[field] for field in CONFIG_FIELDS):
        raise ValueError('config_manifest_dependency_mismatch')
    for field, value in config.items():
        if 'policy' in field and manifest.get(field) != value:
            raise ValueError('config_manifest_policy_mismatch')
    for field in ('tool_digest', 'candidate_sha256', 'source_version', 'prompt_sha256', 'catalog_sha256'):
        if not _sha(config[field]):
            raise ValueError('run_version_digest_required')
    if any(not isinstance(config[field], str) or not config[field] for field in ('session_id', 'case_id')):
        raise ValueError('normal_case_identity_required')
    _registered_hashes(config['source_files'], root)
    _registered_hashes(config['code_files'], root)
    if (not isinstance(config['catalog_path'], str)
            or config['source_files'].get(config['catalog_path']) != config['catalog_sha256']):
        raise ValueError('catalog_not_bound_to_source_versions')
    library_path = Path(config['library_path'])
    frozen = _frozen(library_path if library_path.is_absolute() else root / library_path)
    candidate = frozen['candidate']
    if frozen['candidate_sha256'] != config['candidate_sha256']:
        raise ValueError('run_candidate_version_mismatch')
    if frozen['manifest_digest'] != config['tool_digest']:
        raise ValueError('run_frozen_tool_version_mismatch')
    if config['session_id'] == frozen.get('provenance', {}).get('learning_session_id'):
        raise ValueError('learning_session_cannot_train_continuation')
    if supplied_candidate is not None:
        supplied = supplied_candidate.get('candidate', supplied_candidate)
        if not isinstance(supplied, dict) or any(candidate.get(k) != v for k, v in supplied.items()):
            raise ValueError('supplied_candidate_differs_from_run')
    paths = list((run / 'requests').glob('*.json'))
    if any(not path.stem.isdecimal() for path in paths):
        raise ValueError('ordered_request_receipts_required')
    paths.sort(key=lambda p: int(p.stem))
    n = metrics.get('actual_requests')
    if type(n) is not int or n < 1 or len(paths) != n:
        raise ValueError('request_receipt_count_mismatch')
    tools = load_provider_tools(paths[0])
    if any(load_provider_tools(p) != tools for p in paths[1:]):
        raise ValueError('ordered_tool_contract_drift')
    next_tool = PREFIX + candidate['name']
    if not any(t['name'] == next_tool for t in tools):
        raise ValueError('generated_tool_contract_missing')
    next_schema = next(t['parameters'] for t in tools if t['name'] == next_tool)
    if (next_schema.get('type') != 'object'
            or set(next_schema.get('properties', {})) != {'input_id'}
            or next_schema['properties']['input_id'].get('type') != 'string'
            or next_schema.get('required') != ['input_id']
            or next_schema.get('additionalProperties') is not False):
        raise ValueError('registered_input_handle_contract_required')
    event_path = run / 'events.jsonl'
    if not event_path.exists():
        event_path = run / 'session-events.jsonl'
    events = _root_events(event_path, config['session_id'])
    actions = _actions(events, tools, n)
    work = Path(config['work'])
    if not work.is_absolute():
        work = run / work
    catalog_path = Path(config['catalog_path'])
    if not catalog_path.is_absolute():
        catalog_path = root / catalog_path
    if catalog_path.name != 'catalog.json':
        raise ValueError('registered_catalog_filename_required')
    catalog_text = bounded_read(catalog_path, 192000).decode()
    catalog_sha256 = hashlib.sha256(catalog_text.encode()).hexdigest()
    report_sha256 = file_sha256(work / 'triage.json')
    receipts = []
    for action in actions:
        if action['ok'] and action['name'].startswith(PREFIX) and isinstance(action['value'], dict):
            try:
                receipts.append(_receipt(action['value'], config, catalog_sha256))
            except ValueError:
                pass
    if not receipts or receipts[-1]['report_sha256'] != report_sha256:
        raise ValueError('final_report_receipt_version_mismatch')
    return config, frozen, tools, paths, event_path, actions, catalog_text, catalog_sha256


def compile_trace_rsi_motifs(runs, candidate=None, *, root=ROOT):
    """编译局部候选；一次 Session 的重复频率不能冒充两次支持。"""
    paths = [Path(run) for run in runs]
    if not paths or len({str(p.resolve()) for p in paths}) != len(paths) or any(p.is_symlink() for p in paths):
        raise ValueError('distinct_regular_training_runs_required')
    groups, sources, rejected, sessions = defaultdict(list), {}, Counter(), set()
    common = None
    for run in paths:
        config, frozen, tools, requests, event_path, actions, catalog_text, catalog_sha = _training_run(
            run, Path(root), candidate)
        session = config['session_id']
        run_id = config.get('run_id', run.name)
        if not isinstance(run_id, str) or not run_id or len(run_id) > 256:
            raise ValueError('bounded_training_run_identity_required')
        if session in sessions or run_id in sources:
            raise ValueError('independent_named_training_sessions_required')
        sessions.add(session)
        current = {'tool_digest': config['tool_digest'], 'candidate_sha256': config['candidate_sha256'],
                   'tools': tools, 'code_files_sha256': config['code_files']}
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
        next_tool = PREFIX + frozen['candidate']['name']
        for anchor, check in zip(actions, actions[1:]):
            if check['name'] != next_tool:
                continue
            try:
                if (anchor['name'] == next_tool or not anchor['name'].startswith(PREFIX)
                        or not anchor['ok'] or not check['ok']
                        or anchor['declared_count'] != 1 or check['declared_count'] != 1
                        or check['ordinal'] != anchor['ordinal'] + 1
                        or check['call_order'] != anchor['call_order'] + 1
                        or anchor['result_line'] >= check['line']):
                    raise ValueError('nonlocal_failed_or_interleaved_edge')
                receipt = _receipt(anchor['value'], config, catalog_sha)
                if _receipt(check['value'], config, catalog_sha) != receipt:
                    raise ValueError('anchor_check_receipt_mismatch')
                if check['arguments'] != {'input_id': receipt['input_id']} or 'output' not in check['value']:
                    raise ValueError('generated_check_input_or_output_mismatch')
                _validate_projected_input(anchor, receipt, frozen, catalog_text)
                witness = {'session_id': session, 'run_id': run_id, 'case_id': config['case_id'],
                    'anchor_call_id': anchor['call_id'], 'next_call_id': check['call_id'],
                    'events_sha256': event_hash, 'anchor_line': anchor['line'],
                    'anchor_result_line': anchor['result_line'], 'next_line': check['line'],
                    'next_result_line': check['result_line'],
                    'anchor_request': anchor['ordinal'], 'next_request': check['ordinal'],
                    'anchor_text_blocks': anchor['text_blocks'], 'next_text_blocks': check['text_blocks'],
                    'receipt': receipt, 'output_sha256': digest(check['value']['output'])}
                groups[(anchor['name'], next_tool)].append(witness)
            except (ValueError, KeyError, TypeError, IndexError) as error:
                rejected[str(error)] += 1
    motifs = []
    for (anchor, next_tool), witnesses in sorted(groups.items()):
        binding = {'input_id': '/input_id'}
        support = len({w['session_id'] for w in witnesses})
        graph = {'anchor': anchor, 'next': next_tool, 'parameter_binding': binding}
        motifs.append({'motif_id': 'trace-rsi-' + digest(graph)[:16], **graph,
            'witnesses': witnesses, 'training_session_count': support,
            'support': 'repeated_sessions' if support >= 2 else 'single_session_candidate',
            'status': 'shadow_candidate'})
    library = {'schema_version': 1, 'kind': 'trace_rsi_continuation_shadow',
        'execution_policy': 'shadow_only', **common, 'motifs': motifs, 'sources': sources,
        'rejected': dict(rejected), 'scope': 'normal_case_sessions_same_paper',
        'limitations': ['同论文正常案例及独立 Session，不是跨论文认证。',
            '算法为已冻结的模型生成工具；局部边仅来自正常调用证据。',
            '单 Session 候选保留，至少两个不同 Session 支持后才允许 Shadow 预测。',
            '文本原样保留在原轨迹；局部命中不等于整请求覆盖或实际模型跳过。',
            '摘要验证文件完整性，不认证来源签名，也不授予执行权限。']}
    library['manifest_digest'] = digest(library)
    return library
