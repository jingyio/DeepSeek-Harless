"""私有用户反馈、离线学习队列和受控版本发布；不启动云模型。

用户任务只收集显式授权的数据。合格正常轨迹进入待学习队列，失败用于
诊断。编译复用已有 motif_v6，认证成功仍是 candidate；后续独立任务的
配对质量/费用审阅通过后，才允许人工明确启用。此模块不修改在线规则。
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORE = ROOT / '.local/research-ppt/feedback-learning'
COST_FIELDS = ('requests', 'cache_hit_input_tokens', 'cache_miss_input_tokens',
               'output_tokens', 'proxy_usd', 'billed_usd', 'recovery_usd', 'elapsed_seconds')
VERSION_FIELDS = ('model', 'provider', 'reasoning_effort', 'tool_schema_sha256',
                  'prompt_sha256', 'prompt_prefix_sha256', 'template_sha256', 'runtime_sha256')
COMPATIBILITY_FIELDS = ('model', 'provider', 'reasoning_effort', 'tool_schema_sha256',
                        'prompt_prefix_sha256', 'template_sha256', 'runtime_sha256')
QUALITY_FIELDS = ('delivery', 'scientific', 'visual')
TASK_PROMPT_MARKER = '\n本次任务：\n'
EXECUTION_PROMPT_MARKER = '\n本次执行方式：'
STRATEGY_SUFFIXES = {
    ('generate', 'steps'): '分别调用 render_deck、inspect_deck、validate_deck、deliver_deck，保持真实核验。',
    ('generate', 'composed'): '计划确定后使用 render_delivery 一次调用完成生成、检查、预览和交付。',
    ('restyle', 'steps'): '分别调用 restyle_deck、inspect_deck、validate_deck、deliver_deck，保持全部内容及真实核验。',
    ('restyle', 'composed'): '使用 build_delivery({"operation":"restyle","source_id":"实际返回的句柄","template":"任务模板"}) 完成风格转换、检查、预览和交付。',
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private(path: Path | str, *, exists=False) -> Path:
    target = Path(path).resolve(strict=exists)
    if not target.is_relative_to((ROOT / '.local').resolve()):
        raise ValueError('反馈、原始轨迹和候选版本必须保存在仓库 .local')
    return target


def _read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def _new(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    path.chmod(0o600)


def _number(value, name, *, integer=False) -> None:
    if value is None:
        return
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or (integer and not isinstance(value, int))):
        raise ValueError(name + ' 必须为非负数或 null（未知）')


def _sha(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in '0123456789abcdef' for ch in value)


def _compatibility(row: dict) -> dict:
    """Stable configuration only; every full per-run prompt remains evidence-bound."""
    versions = row.get('versions', {})
    if any(versions.get(field) is None for field in COMPATIBILITY_FIELDS):
        raise ValueError('缺少稳定提示前缀或实际版本；旧记录需显式重新收集，不能自动迁移')
    return {field: versions[field] for field in COMPATIBILITY_FIELDS}


def _prompt_binding(row: dict, manifest: dict | None = None) -> dict:
    """Derive stable prefix and paired task from actual prompt bytes, never labels."""
    evidence = row.get('prompt_evidence')
    if not isinstance(evidence, dict):
        raise ValueError('缺少实际提示文件证据；旧记录不能自动作为稳定前缀学习数据')
    path = _private(evidence.get('path', ''), exists=True)
    raw = path.read_bytes()
    full_sha = hashlib.sha256(raw).hexdigest()
    if full_sha != evidence.get('sha256') or full_sha != row['versions'].get('prompt_sha256'):
        raise ValueError('完整提示文件与版本摘要不一致')
    text = raw.decode('utf-8')
    if text.count(TASK_PROMPT_MARKER) != 1 or text.count(EXECUTION_PROMPT_MARKER) != 1:
        raise ValueError('提示未使用唯一公共任务/执行分界，不能猜测稳定前缀')
    shared, suffix = text.split(EXECUTION_PROMPT_MARKER, 1)
    prefix, task_text = shared.split(TASK_PROMPT_MARKER, 1)
    task = json.loads(task_text)
    if (not prefix.strip() or not isinstance(task, dict)
            or set(task) != {'instruction', 'slides', 'template', 'operation', 'inputs'}):
        raise ValueError('实际公共提示中的任务格式不完整')
    strategy = row.get('execution_strategy')
    if STRATEGY_SUFFIXES.get((task.get('operation'), strategy)) != suffix:
        raise ValueError('策略后缀与声明不符或改变了公共任务要求')
    prefix_sha = hashlib.sha256(prefix.encode('utf-8')).hexdigest()
    shared_sha = hashlib.sha256(shared.encode('utf-8')).hexdigest()
    if (prefix_sha != row['versions'].get('prompt_prefix_sha256')
            or prefix_sha != evidence.get('prefix_sha256')
            or shared_sha != row.get('shared_prompt_sha256')
            or shared_sha != evidence.get('shared_prompt_sha256')):
        raise ValueError('稳定前缀或共同题面摘要不是由实际提示文件导出')
    if manifest is not None and (manifest.get('question') != text or manifest.get('prompt_sha256') != full_sha):
        raise ValueError('实际运行完整提示与反馈文件不同')
    return {'prefix_sha256': prefix_sha, 'shared_prompt_sha256': shared_sha,
            'prompt_sha256': full_sha, 'task': task, 'execution_strategy': strategy}


def _require_compatible_prompts(rows: list[dict], *, paired=False) -> list[dict]:
    bindings = [_prompt_binding(row, _read(_private(row['run_dir'], exists=True) / 'manifest.json')) for row in rows]
    if len({_digest(_compatibility(row)) for row in rows}) != 1:
        raise ValueError('实际模型、稳定提示前缀、工具、模板或实现版本不同')
    if paired:
        if (len(bindings) != 2 or bindings[0]['execution_strategy'] != 'steps'
                or bindings[0]['shared_prompt_sha256'] != bindings[1]['shared_prompt_sha256']
                or bindings[0]['task'] != bindings[1]['task']):
            raise ValueError('配对须共用真实题面与稳定前缀，仅允许执行策略后缀不同')
    elif any(binding['execution_strategy'] != 'steps' for binding in bindings):
        raise ValueError('正常训练/独立认证输入必须使用逐步策略')
    return bindings


def _compiler_schema(path: Path) -> tuple[dict, str]:
    """Bind actual MCP export without changing source schema or core compiler."""
    payload = _read(path)
    if isinstance(payload, dict) and isinstance(payload.get('actual_tools'), list):
        observed = payload['actual_tools']
        effective = _digest(observed)
        if payload.get('schema_sha256') != effective:
            raise ValueError('MCP schema摘要与真实工具列表不一致')
        rows = [{**row, 'name': row['name'] if row['name'].startswith('mcp__') else 'mcp__ppt__' + row['name']}
                for row in observed]
        return {'tools': rows}, effective
    from .motif_v6 import schema_tools
    return schema_tools(payload), _hash(path)


def _validate_record(record: dict) -> dict:
    if not isinstance(record, dict) or record.get('schema_version') != 1:
        raise ValueError('反馈需要 schema_version=1')
    for field in ('run_id', 'task_identity', 'pair_id'):
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise ValueError('反馈缺少 ' + field)
    if record.get('group') not in ('baseline', 'optimized'):
        raise ValueError('group 必须为 baseline 或 optimized')
    consent = record.get('consent')
    if (not isinstance(consent, dict) or consent.get('collect') is not True
            or type(consent.get('learn')) is not bool):
        raise ValueError('必须明确授权 collect=true，并明确 learn=true/false')
    sources = record.get('source_evidence')
    if (not isinstance(sources, list) or not sources or any(
            not isinstance(row, dict) or not isinstance(row.get('source_id'), str)
            or not row['source_id'] or not _sha(row.get('sha256')) for row in sources)):
        raise ValueError('来源需匿名 source_id 和精确 sha256')
    if len({row['source_id'] for row in sources}) != len(sources):
        raise ValueError('source_id 不能重复')
    if not isinstance(record.get('versions'), dict):
        raise ValueError('需要实际生效的 versions；未知字段明确为 null')
    versions = record['versions']
    if any(field not in versions for field in VERSION_FIELDS):
        raise ValueError('versions 缺少必需配置字段')
    for field, value in versions.items():
        if not isinstance(field, str) or (value is not None and not isinstance(value, (str, bool, int, float))):
            raise ValueError('版本字段只能为简单实际值或 null')
        if field.endswith('_sha256') and value is not None and not _sha(value):
            raise ValueError('配置哈希无效: ' + field)
    quality = record.get('quality')
    if (not isinstance(quality, dict) or any(quality.get(key) not in ('passed', 'failed', 'pending')
                                           for key in QUALITY_FIELDS)):
        raise ValueError('quality 需 delivery/scientific/visual 三项 passed/failed/pending')
    if not isinstance(quality.get('reviewer'), str):
        raise ValueError('quality.reviewer 必须明确为 human/user/ai-assisted/unreviewed')
    if 'revision_minutes' not in quality:
        raise ValueError('人工修订分钟未知时明确 revision_minutes=null')
    _number(quality['revision_minutes'], 'revision_minutes')
    cost = record.get('cost')
    if not isinstance(cost, dict) or any(key not in cost for key in COST_FIELDS):
        raise ValueError('完整费用字段必需，未知值用 null，不能省略或当零')
    for field in COST_FIELDS:
        _number(cost[field], field, integer=field in COST_FIELDS[:4])
    if type(record.get('identity_confirmed', False)) is not bool:
        raise ValueError('identity_confirmed 必须为布尔值')
    if record.get('run_dir') is not None:
        record = {**record, 'run_dir': str(_private(record['run_dir'], exists=True))}
    if record.get('feedback') is not None and not isinstance(record['feedback'], str):
        raise ValueError('feedback 必须为文字；不要写密钥或来源正文')
    if record.get('delivery_evidence') is not None:
        evidence = record['delivery_evidence']
        if (not isinstance(evidence, dict) or not _sha(evidence.get('sha256'))
                or not isinstance(evidence.get('path'), str)):
            raise ValueError('交付证据需要私有 path 与 sha256')
        record = {**record, 'delivery_evidence': {**evidence, 'path': str(_private(evidence['path'], exists=True))}}
    if record.get('prompt_evidence') is not None:
        evidence = record['prompt_evidence']
        if (not isinstance(evidence, dict) or not isinstance(evidence.get('path'), str)
                or any(not _sha(evidence.get(field)) for field in ('sha256', 'shared_prompt_sha256', 'prefix_sha256'))):
            raise ValueError('提示证据需私有文件及完整/前缀/共同题面摘要')
        record = {**record, 'prompt_evidence': {**evidence, 'path': str(_private(evidence['path'], exists=True))}}
    if record.get('shared_prompt_sha256') is not None and not _sha(record['shared_prompt_sha256']):
        raise ValueError('共同题面摘要无效')
    if record.get('execution_strategy') is not None and record['execution_strategy'] not in ('steps', 'composed'):
        raise ValueError('执行策略须为 steps/composed')
    if record.get('accounting_run_dirs') is not None:
        if not isinstance(record['accounting_run_dirs'], list) or not record['accounting_run_dirs']:
            raise ValueError('accounting_run_dirs 需列出全部尝试；无数据请省略')
        dirs = [str(_private(item, exists=True)) for item in record['accounting_run_dirs']]
        if len(set(dirs)) != len(dirs) or record.get('run_dir') not in dirs:
            raise ValueError('账本目录不能重复，并须包含交付 run_dir')
        record = {**record, 'accounting_run_dirs': dirs}
    # 允许可选任务交付/账本定位，不把未知成本补成零。
    return json.loads(json.dumps(record, allow_nan=False))


class FeedbackStore:
    def __init__(self, store: Path | str = DEFAULT_STORE):
        self.path = _private(store)

    @contextmanager
    def _lock(self):
        self.path.mkdir(parents=True, exist_ok=True)
        marker = self.path / '.write-lock'
        try:
            _new(marker, {'created_at': _now(), 'scope': 'feedback_learning'})
        except FileExistsError as exc:
            raise ValueError('反馈库正在写入；异常退出后先确认无写入者再移除 .write-lock') from exc
        try:
            yield
        finally:
            marker.unlink()

    def _records(self, *, latest=True) -> list[dict]:
        rows = [_read(path) for path in sorted((self.path / 'records').glob('*.json'))]
        if not latest:
            return rows
        current = {}
        for row in rows:
            previous = current.get(row['run_id'])
            if previous is None or row['revision'] > previous['revision']:
                current[row['run_id']] = row
        return sorted(current.values(), key=lambda row: (row['created_at'], row['record_id']))

    def _record(self, record_id: str) -> dict:
        if len(record_id) != 32 or any(ch not in '0123456789abcdef' for ch in record_id):
            raise ValueError('record_id 格式无效')
        return _read(_private(self.path / 'records' / (record_id + '.json'), exists=True))

    @staticmethod
    def _qualified(row: dict) -> bool:
        return (all(row['quality'][key] == 'passed' for key in QUALITY_FIELDS)
                and row['quality']['reviewer'] in ('human', 'user'))

    @staticmethod
    def _evidence(row: dict, *, require_normal=False) -> dict:
        """Actual byte/ledger evidence; feedback `passed` cannot certify tools."""
        if not row.get('run_dir') or not row.get('evidence_lock'):
            raise ValueError('缺少真实运行和收集时的证据字节锁')
        for path, sha256 in row['evidence_lock'].items():
            if _hash(_private(path, exists=True)) != sha256:
                raise ValueError('运行、账本或交付证据已变化')
        directory = _private(row['run_dir'], exists=True)
        manifest, metrics = _read(directory / 'manifest.json'), _read(directory / 'metrics.json')
        if (manifest.get('model_call_enabled') is not True or manifest.get('reasoning_effort') != 'off'
                or manifest.get('fixture') is True or metrics.get('status') != 'done'
                or (require_normal and manifest.get('mode') != 'baseline')):
            raise ValueError('需要完成的真实运行；预览、模拟或失败不能认证')
        if (manifest.get('model') != row['versions']['model']
                or manifest.get('prompt_sha256') != row['versions']['prompt_sha256']):
            raise ValueError('模型或提示记录与实际运行manifest不同')
        binding = _prompt_binding(row, manifest)
        if require_normal and binding['execution_strategy'] != 'steps':
            raise ValueError('训练正常组必须使用未经组合优化的逐步策略')
        sums = {key: 0 for key in ('requests', 'proxy_usd', 'cache_hit_input_tokens', 'cache_miss_input_tokens', 'output_tokens')}
        fields = {'cache_hit_input_tokens': 'prompt_cache_hit_tokens',
                  'cache_miss_input_tokens': 'prompt_cache_miss_tokens', 'output_tokens': 'completion_tokens'}
        for path in row.get('accounting_run_dirs', [row['run_dir']]):
            run = _private(path, exists=True)
            run_metrics = _read(run / 'metrics.json')
            ledger = [json.loads(line) for line in (run / 'cost-ledger.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
            requests = [item for item in ledger if 'request_id' in item]
            if run_metrics.get('upstream_requests') != len(requests) or not requests:
                raise ValueError('费用必须包括真实完整上游请求账本')
            if len({item['request_id'] for item in requests}) != len(requests):
                raise ValueError('请求账本 ID 重复')
            sums['requests'] += len(requests)
            for request in requests:
                value = request.get('observed_peak_usd')
                if value is None:
                    raise ValueError('完整代理估费缺失，不能按零晋级')
                _number(value, 'observed_peak_usd'); sums['proxy_usd'] += value
                usage = request.get('response_usage', {})
                for target, source in fields.items():
                    value = usage.get(source)
                    if value is None:
                        raise ValueError('真实 token 计数缺失，不以局部可见值晋级')
                    _number(value, source, integer=True); sums[target] += value
        if not any(json.loads(line).get('response_status') == 200 for line in
                   (directory / 'cost-ledger.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()):
            raise ValueError('没有成功真实API请求证据')
        for key, value in sums.items():
            reported = row['cost'].get(key)
            if reported is None or not math.isclose(reported, value, rel_tol=1e-8, abs_tol=1e-8):
                raise ValueError('反馈费用与完整原始账本不一致: ' + key)
        evidence = row.get('delivery_evidence')
        if not evidence or _hash(Path(evidence['path'])) != evidence['sha256']:
            raise ValueError('缺少实际机械交付证据')
        receipt = _read(Path(evidence['path']))
        if (receipt.get('mechanical_delivery_verified') is not True
                or receipt.get('run_events_sha256') != _hash(directory / 'agent-events.jsonl')
                or not isinstance(receipt.get('files'), list) or not receipt['files']):
            raise ValueError('机械交付回执必须绑定实际 tool/result 事件和文件')
        for item in receipt['files']:
            if not _sha(item.get('sha256')) or _hash(_private(item['path'], exists=True)) != item['sha256']:
                raise ValueError('交付文件字节变化')
        from src.adapters.dsh_event_projection import is_original_tool_result
        from src.adapters.dsh_trajectory import _observation_digest
        names, observed_receipts = {}, []
        for line in (directory / 'agent-events.jsonl').read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            event = json.loads(line); data = event.get('data', {})
            if event.get('type') == 'tool/call':
                names[data.get('callId')] = data.get('name')
            elif is_original_tool_result(event):
                name = names.get(data.get('message', {}).get('source', {}).get('callId'))
                if name in ('mcp__ppt__deliver_deck', 'mcp__ppt__render_delivery', 'mcp__ppt__build_delivery'):
                    success, _, value = _observation_digest(event, name)
                    if success and isinstance(value, dict) and value.get('delivered') is not False:
                        observed_receipts.append(value)
        if not observed_receipts or any(value not in observed_receipts for value in receipt.get('receipts', [])):
            raise ValueError('交付证据没有来自实际原始成功工具回执')
        receipt_files = {(str(_private(item['path'], exists=True)), item['sha256']) for item in receipt['files']}
        delivered_files = set()
        for value in observed_receipts:
            if isinstance(value.get('path'), str) and _sha(value.get('file_sha256')):
                delivered_files.add((str(_private(value['path'], exists=True)), value['file_sha256']))
            for item in value.get('artifacts', []):
                if isinstance(item, dict) and item.get('path') and _sha(item.get('sha256')):
                    delivered_files.add((str(_private(item['path'], exists=True)), item['sha256']))
        if not receipt_files.issubset(delivered_files):
            raise ValueError('交付文件不是实际成功工具返回的文件')
        # Human scientific/visual judgement remains explicit, not inferred from render.
        return sums

    @staticmethod
    def _eligibility(row: dict) -> tuple[bool, str]:
        if not row['consent']['learn']:
            return False, 'learning_not_authorized'
        if row['group'] != 'baseline':
            return False, 'optimized_trace_not_normal_training'
        if not FeedbackStore._qualified(row):
            return False, 'quality_failed_or_not_human_reviewed'
        if not row.get('identity_confirmed') or not row.get('run_dir'):
            return False, 'independent_frozen_identity_needed'
        if any(row['versions'].get(field) is None for field in VERSION_FIELDS):
            return False, 'effective_configuration_incomplete'
        try:
            from src.adapters.task_identity import load_trace_identity
            directory = _private(row['run_dir'], exists=True)
            identity = load_trace_identity(directory / 'task-identity.json', directory / 'agent-events.jsonl', ROOT / '.local')
            if identity['research_decision_id'] != row['task_identity']:
                return False, 'frozen_task_identity_mismatch'
            FeedbackStore._evidence(row, require_normal=True)
        except (ValueError, OSError, json.JSONDecodeError):
            return False, 'real_trace_cost_or_delivery_evidence_changed_or_missing'
        return True, 'normal_quality_reviewed_frozen_trace'

    def collect(self, record: dict) -> dict:
        """append-only feedback revision; never starts learning or model calls."""
        row = _validate_record(record)
        with self._lock():
            previous = next((item for item in self._records() if item['run_id'] == row['run_id']), None)
            stable = ('task_identity', 'pair_id', 'group', 'source_evidence', 'versions', 'run_dir', 'candidate_version',
                      'prompt_evidence', 'shared_prompt_sha256', 'execution_strategy')
            if previous and any(previous.get(key) != row.get(key) for key in stable):
                raise ValueError('同一 run 的任务、来源、配置和候选版本不能追改')
            paths = []
            for directory in row.get('accounting_run_dirs', [row['run_dir']] if row.get('run_dir') else []):
                paths += [Path(directory) / name for name in
                          ('manifest.json', 'metrics.json', 'agent-events.jsonl', 'cost-ledger.jsonl', 'task-identity.json')]
            if row.get('delivery_evidence'):
                paths.append(Path(row['delivery_evidence']['path']))
                receipt = _read(paths[-1])
                if isinstance(receipt.get('files'), list):
                    paths += [_private(item['path'], exists=True) for item in receipt['files'] if isinstance(item, dict) and item.get('path')]
            if row.get('prompt_evidence'):
                paths.append(Path(row['prompt_evidence']['path']))
            if row.get('run_dir'):
                metrics_path = Path(row['run_dir']) / 'metrics.json'
                if metrics_path.is_file():
                    session = _read(metrics_path).get('session_id')
                    if isinstance(session, str) and session:
                        paths.append(Path(row['run_dir']) / '.local/online-motif' /
                                     (hashlib.sha256(session.encode()).hexdigest() + '.jsonl'))
            row['evidence_lock'] = {str(path.resolve()): _hash(path) for path in paths if path.is_file()}
            row.update(record_id=uuid4().hex, created_at=_now(), revision=previous['revision'] + 1 if previous else 1,
                       supersedes=previous['record_id'] if previous else None)
            _new(self.path / 'records' / (row['record_id'] + '.json'), row)
        eligible, reason = self._eligibility(row)
        return {'record_id': row['record_id'], 'revision': row['revision'], 'eligible': eligible,
                'queue': 'learning' if eligible else 'diagnostic_only', 'reason': reason,
                'model_requests': 0, 'learning_started': False}

    def queue(self) -> dict:
        seen_tasks, seen_pairs, rows = set(), set(), []
        for row in self._records():
            eligible, reason = self._eligibility(row)
            if eligible and (row['task_identity'] in seen_tasks or row['pair_id'] in seen_pairs):
                eligible, reason = False, 'same_task_or_pair_already_counted'
            if eligible:
                seen_tasks.add(row['task_identity']); seen_pairs.add(row['pair_id'])
            rows.append({'record_id': row['record_id'], 'run_id': row['run_id'], 'task_identity': row['task_identity'],
                         'eligible': eligible, 'reason': reason})
        return {'records': rows, 'independent_eligible_tasks': len(seen_tasks), 'automatic_learning': False}

    def preview(self, train: list[str], heldout: list[str], *, contracts: Path, version_fields: Path,
                tool_schema: Path, mining='sequence') -> dict:
        if len(train) != 2 or len(heldout) != 1 or len(set(train + heldout)) != 3:
            raise ValueError('最小预览需两个 train 和一个独立 heldout 记录')
        if mining not in ('sequence', 'witnessed_edges'):
            raise ValueError('未知现有编译入口')
        rows = [self._record(item) for item in train + heldout]
        if any(not self._eligibility(row)[0] for row in rows):
            raise ValueError('只有授权、合格、正常、已冻结的轨迹可进入学习')
        if len({row['pair_id'] for row in rows}) != 3 or len({row['task_identity'] for row in rows}) != 3:
            raise ValueError('同一任务的双组或续写不能算独立训练/认证任务')
        from src.adapters.task_identity import load_trace_identity, require_distinct_decisions
        identities = [load_trace_identity(Path(row['run_dir']) / 'task-identity.json',
                                         Path(row['run_dir']) / 'agent-events.jsonl', ROOT / '.local') for row in rows]
        require_distinct_decisions(identities)
        _require_compatible_prompts(rows)
        config = {name: {'path': str(Path(path).resolve(strict=True)), 'sha256': _hash(Path(path).resolve(strict=True))}
                  for name, path in [('contracts', contracts), ('version_fields', version_fields), ('tool_schema', tool_schema)]}
        compile_schema, effective_schema_hash = _compiler_schema(Path(config['tool_schema']['path']))
        config['tool_schema']['effective_schema_sha256'] = effective_schema_hash
        if any(row['versions']['tool_schema_sha256'] != effective_schema_hash for row in rows):
            raise ValueError('tool_schema 必须为这些运行实际生效的相同 schema')
        plan_id = uuid4().hex
        plan = {'schema_version': 1, 'plan_id': plan_id, 'created_at': _now(), 'train': train, 'heldout': heldout,
                'records': [{'id': row['record_id'], 'sha256': _hash(self.path / 'records' / (row['record_id'] + '.json'))}
                            for row in rows], 'identities': identities, 'config': config, 'mining': mining,
                'impact': 'offline_compilation_only_candidate_not_enabled', 'model_requests': 0,
                'training_task_count': 2, 'heldout_task_count': 1}
        with self._lock():
            path = self.path / 'plans' / (plan_id + '.json'); _new(path, plan)
            _new(self.path / 'plans' / (plan_id + '-compiler-schema.json'), compile_schema)
        return {'plan_path': str(path), 'plan_sha256': _hash(path), **plan}

    def learn(self, plan_path: Path, *, confirm=False) -> dict:
        path = _private(plan_path, exists=True)
        if path.parent != self.path / 'plans':
            raise ValueError('只能确认此反馈库的预览计划')
        plan = _read(path)
        if not confirm:
            return {'preview': True, 'plan_path': str(path), 'impact': plan['impact'], 'model_requests': 0}
        with self._lock():
            attempt_path = self.path / 'attempts' / (plan['plan_id'] + '.json')
            if attempt_path.exists():
                raise ValueError('此划分已有认证尝试；失败需新计划，不能覆盖负面证据')
            rows = []
            for item in plan['records']:
                record_path = self.path / 'records' / (item['id'] + '.json')
                if _hash(record_path) != item['sha256']:
                    raise ValueError('预览后的反馈证据变化')
                row = self._record(item['id'])
                latest = next(record for record in self._records() if record['run_id'] == row['run_id'])
                if latest['record_id'] != row['record_id'] or not self._eligibility(latest)[0]:
                    raise ValueError('反馈已更新或授权/质量/身份失效，请重新预览')
                rows.append(row)
            for item in plan['config'].values():
                if _hash(Path(item['path'])) != item['sha256']:
                    raise ValueError('工具契约/schema变化，请重新预览')
            dataset_path = self.path / 'datasets' / (plan['plan_id'] + '.json')
            by_id = {row['record_id']: row for row in rows}
            _new(dataset_path, {split: [by_id[key]['run_dir'] for key in plan[split]] for split in ('train', 'heldout')})
            _new(attempt_path, {'started_at': _now(), 'plan_sha256': _hash(path), 'status': 'started', 'model_requests': 0})
            start = time.monotonic()
            from . import motif_v6
            try:
                schema_path = path.parent / (plan['plan_id'] + '-compiler-schema.json')
                actual_schema, _ = _compiler_schema(Path(plan['config']['tool_schema']['path']))
                if _read(schema_path) != actual_schema:
                    raise ValueError('编译器schema投影发生变化')
                manifest = motif_v6.learn(dataset_path,
                    contracts_path=Path(plan['config']['contracts']['path']),
                    version_fields_path=Path(plan['config']['version_fields']['path']),
                    tool_schema_path=schema_path,
                    guard_paths=(Path(plan['config']['tool_schema']['path']),),
                    out_dir=self.path / 'compiled' / plan['plan_id'], mining=plan['mining'])
                motif_v6.validate_compilation(manifest)
            except Exception as exc:
                _new(self.path / 'outcomes' / (plan['plan_id'] + '.json'),
                     {'status': 'not_promoted', 'error_type': type(exc).__name__, 'elapsed_seconds': time.monotonic() - start,
                      'model_requests': 0, 'model_usd': 0, 'human_minutes': None})
                raise
            version = uuid4().hex
            candidate = {'schema_version': 1, 'version': version, 'created_at': _now(), 'status': 'candidate',
                         'manifest': str(manifest), 'manifest_sha256': _hash(manifest), 'plan_path': str(path),
                         'plan_sha256': _hash(path), 'training_task_identities': [row['task_identity'] for row in rows],
                         'training_pair_ids': [row['pair_id'] for row in rows],
                         'identities': plan['identities'], 'quality_cost_promoted': False,
                         'learning_cost': {'model_requests': 0, 'model_usd': 0,
                                           'elapsed_seconds': time.monotonic() - start, 'human_minutes': None,
                                           'compute_usd': None},
                         'scope': 'existing_trace_compiler_only_not_generated_tool_or_layout_learning'}
            _new(self.path / 'candidates' / (version + '.json'), candidate)
            _new(self.path / 'outcomes' / (plan['plan_id'] + '.json'), candidate)
        return candidate

    def _candidate(self, version: str) -> dict:
        if len(version) != 32 or any(ch not in '0123456789abcdef' for ch in version):
            raise ValueError('候选 version 无效')
        row = _read(_private(self.path / 'candidates' / (version + '.json'), exists=True))
        from .motif_v6 import validate_compilation
        if _hash(Path(row['manifest'])) != row['manifest_sha256'] or _hash(Path(row['plan_path'])) != row['plan_sha256']:
            raise ValueError('候选或训练划分已变化')
        latest_by_run = {item['run_id']: item for item in self._records()}
        for item in _read(Path(row['plan_path']))['records']:
            path = self.path / 'records' / (item['id'] + '.json')
            if _hash(path) != item['sha256']:
                raise ValueError('学习反馈证据变化')
            original = self._record(item['id'])
            if not self._eligibility(latest_by_run[original['run_id']])[0]:
                raise ValueError('学习授权已撤回或最新质量/版本不合格')
        validate_compilation(Path(row['manifest']))
        return row

    def candidate_manifest(self, version: str) -> dict:
        """Explicit staging only: certified candidate is not a production release."""
        candidate = self._candidate(version)
        return {'version': version, 'manifest': candidate['manifest'],
                'manifest_sha256': candidate['manifest_sha256'], 'stage': 'candidate_evaluation',
                'quality_cost_promoted': False}

    @staticmethod
    def _candidate_execution(row: dict, candidate: dict) -> dict:
        directory = _private(row['run_dir'], exists=True)
        manifest, metrics = _read(directory / 'manifest.json'), _read(directory / 'metrics.json')
        compiled = _read(_private(candidate['manifest'], exists=True))
        if (row.get('candidate_version') != candidate['version'] or manifest.get('mode') != 'execute'
                or manifest.get('manifest_digest') != compiled.get('manifest_digest')
                or not _sha(compiled.get('manifest_digest'))):
            raise ValueError('候选标签不是执行证据；需要真实 execute 和对应 manifest_digest')
        count, session = metrics.get('model_requests_skipped_verified'), metrics.get('session_id')
        if type(count) is not int or count < 1 or not isinstance(session, str) or not session:
            raise ValueError('此候选没有 verified 模型请求旁路，普通组合收益不能用于晋级')
        audit = directory / '.local/online-motif' / (hashlib.sha256(session.encode()).hexdigest() + '.jsonl')
        if not audit.is_file() or row.get('evidence_lock', {}).get(str(audit.resolve())) != _hash(audit):
            raise ValueError('缺少收集时冻结的候选执行审计')
        rows = [json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines() if line.strip()]
        verified = [item for item in rows if item.get('kind') == 'model_request_skipped_verified']
        if (len(verified) != count or any(item.get('session_id') != session
                or type(item.get('tool_count')) is not int or item['tool_count'] < 1 for item in verified)
                or len({item.get('batch_id') for item in verified}) != count
                or any(not isinstance(item.get('batch_id'), str) or not item['batch_id'] for item in verified)):
            raise ValueError('候选旁路计数、会话或批次与真实审计不一致')
        return {'manifest_digest': compiled['manifest_digest'], 'verified_requests': count,
                'audit_sha256': _hash(audit)}

    def _release_gate(self, version: str) -> dict:
        releases = [_read(path) for path in (self.path / 'releases').glob('*.json')]
        releases.sort(key=lambda row: row['sequence'], reverse=True)
        approved = next((row for row in releases if row.get('active_version') == version
                         and row.get('reason') == 'explicit_quality_cost_reviewed_activation'), None)
        if approved is None:
            raise ValueError('缺少此版本明确授权的质量/成本晋级记录')
        old = approved['evidence']
        current = self.activate(version, [pair['pair_id'] for pair in old['pairs']], confirm=False)['gate']
        if current != old:
            raise ValueError('发布后评审、授权或收益证据已变化；重新核验并明确晋级')
        return current

    def active_manifest(self) -> dict | None:
        """Only promoted + currently valid versions may be inherited by entry."""
        version = self.status()['active_version']
        if version is None:
            return None
        candidate = self._candidate(version)
        self._release_gate(version)
        return {'version': version, 'manifest': candidate['manifest'],
                'manifest_sha256': candidate['manifest_sha256'],
                'scope': 'entry_still_checks_current_task_schema_versions_and_permissions'}

    def status(self) -> dict:
        events = [_read(path) for path in sorted((self.path / 'releases').glob('*.json'))]
        events.sort(key=lambda row: row['sequence'])
        active = events[-1]['active_version'] if events else None
        candidates = [_read(path) for path in sorted((self.path / 'candidates').glob('*.json'))]
        states = []
        for row in candidates:
            try:
                self._candidate(row['version']); valid = True
            except (ValueError, OSError):
                valid = False
            states.append({'version': row['version'], 'status': 'active' if row['version'] == active else 'candidate',
                           'valid': valid, 'manifest': row['manifest'], 'learning_cost': row['learning_cost']})
        return {'active_version': active, 'candidates': states, 'last_release': events[-1] if events else None,
                'automatic_activation': False, 'online_entry_must_explicitly_load_valid_active_manifest': True}

    def _release(self, active: str | None, reason: str, evidence: dict) -> dict:
        current = self.status()
        previous = current['last_release']
        sequence = previous['sequence'] + 1 if previous else 1
        row = {'schema_version': 1, 'sequence': sequence, 'created_at': _now(), 'active_version': active,
               'previous_active_version': current['active_version'], 'reason': reason, 'evidence': evidence}
        _new(self.path / 'releases' / (f'{sequence:06d}-' + uuid4().hex + '.json'), row)
        return row

    def activate(self, version: str, pairs: list[str], *, confirm=False) -> dict:
        """Explicit release after >=2 unseen quality-passed matched paired tasks.

        API proxy estimate is not invoice or total human/compute cost. Release
        gate reports that distinction; it does not assert a break-even point.
        """
        candidate = self._candidate(version)
        if len(pairs) < 2 or len(set(pairs)) != len(pairs):
            raise ValueError('晋级至少需要两个新的独立配对任务')
        records = self._records(); evidence = []
        if any(row.get('candidate_version') == version and row['group'] == 'optimized'
               and any(row['quality'][key] == 'failed' for key in QUALITY_FIELDS) for row in records):
            raise ValueError('此候选仍有失败任务反馈；不能跳过反例只选择成功任务')
        for pair in pairs:
            rows = [row for row in records if row['pair_id'] == pair]
            baseline = [row for row in rows if row['group'] == 'baseline']
            optimized = [row for row in rows if row['group'] == 'optimized' and row.get('candidate_version') == version]
            if len(baseline) != 1 or len(optimized) != 1:
                raise ValueError('每个配对需恰好一份普通组和此候选优化组的最新反馈')
            base, opt = baseline[0], optimized[0]
            if (base['task_identity'] != opt['task_identity'] or base['source_evidence'] != opt['source_evidence']
                    or _compatibility(base) != _compatibility(opt)):
                raise ValueError('配对须共用真实题面、来源、稳定前缀和模型/工具版本，仅允许执行策略后缀不同')
            _require_compatible_prompts([base, opt], paired=True)
            if pair in candidate['training_pair_ids'] or base['task_identity'] in candidate['training_task_identities']:
                raise ValueError('训练/认证任务不能充当下一轮收益验证')
            if any(not self._qualified(row) for row in rows):
                raise ValueError('质量未人工评审或不合格，不得晋级')
            self._evidence(base, require_normal=True); self._evidence(opt)
            execution = self._candidate_execution(opt, candidate)
            if not base.get('identity_confirmed') or not opt.get('identity_confirmed'):
                raise ValueError('后续任务身份也须明确确认并冻结')
            from src.adapters.task_identity import load_trace_identity, require_distinct_decisions
            identities = [load_trace_identity(Path(row['run_dir']) / 'task-identity.json',
                                             Path(row['run_dir']) / 'agent-events.jsonl', ROOT / '.local') for row in (base, opt)]
            if any(item['research_decision_id'] != base['task_identity'] for item in identities):
                raise ValueError('配对运行的实际冻结任务身份不同')
            require_distinct_decisions([*candidate['identities'], identities[0]])
            if any(row['quality']['revision_minutes'] is None or row['cost']['proxy_usd'] is None for row in (base, opt)):
                raise ValueError('晋级需要完整代理费用与人工修订时间，未知不能当零')
            if opt['quality']['revision_minutes'] > base['quality']['revision_minutes']:
                raise ValueError('人工修订变多，不能仅凭API费用晋级')
            if opt['cost']['proxy_usd'] > base['cost']['proxy_usd']:
                raise ValueError('存在新任务代理费用反例；先诊断，不只挑节省的记录')
            evidence.append({'pair_id': pair, 'task_identity': base['task_identity'],
                             'candidate_execution': execution,
                             'question_sha256': identities[0]['question_sha256'],
                             'records': [{'id': row['record_id'], 'sha256': _hash(self.path / 'records' / (row['record_id'] + '.json'))}
                                         for row in (base, opt)],
                             'baseline_proxy_usd': base['cost']['proxy_usd'], 'optimized_proxy_usd': opt['cost']['proxy_usd'],
                             'baseline_revision_minutes': base['quality']['revision_minutes'],
                             'optimized_revision_minutes': opt['quality']['revision_minutes']})
        if len({row['task_identity'] for row in evidence}) != len(evidence):
            raise ValueError('收益验证需要不同任务身份')
        if len({row['question_sha256'] for row in evidence}) != len(evidence):
            raise ValueError('相同研究问题的续写不算新的独立收益验证')
        baseline_cost = sum(row['baseline_proxy_usd'] for row in evidence)
        optimized_cost = sum(row['optimized_proxy_usd'] for row in evidence)
        if optimized_cost >= baseline_cost:
            raise ValueError('没有观察到后续合格任务代理费用净下降')
        gate = {'pairs': evidence, 'baseline_proxy_usd': baseline_cost, 'optimized_proxy_usd': optimized_cost,
                'saving_proxy_usd': baseline_cost - optimized_cost, 'learning_cost': candidate['learning_cost'],
                'scope': 'human_reviewed_quality_api_proxy_cost_and_revision_minutes_only',
                'invoice_compute_maintenance_total_cost': 'not_established', 'break_even': 'not_established'}
        if not confirm:
            return {'preview': True, 'version': version, 'gate': gate, 'production_changed': False}
        with self._lock():
            self._candidate(version)
            latest_ids = {row['record_id'] for row in self._records()}
            if any(item['id'] not in latest_ids for pair in gate['pairs'] for item in pair['records']):
                raise ValueError('晋级预览后用户反馈变化；重新核验')
            return self._release(version, 'explicit_quality_cost_reviewed_activation', gate)

    def rollback(self, *, confirm=False) -> dict:
        state = self.status()
        if state['last_release'] is None:
            raise ValueError('暂无发布可回滚')
        previous = state['last_release']['previous_active_version']
        if previous is not None:
            self._candidate(previous)
            self._release_gate(previous)
        if not confirm:
            return {'preview': True, 'active_version': state['active_version'], 'rollback_to': previous}
        with self._lock():
            return self._release(previous, 'explicit_rollback', {'from': state['active_version']})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, default=DEFAULT_STORE)
    commands = parser.add_subparsers(dest='command', required=True)
    collect = commands.add_parser('collect'); collect.add_argument('--record', type=Path, required=True)
    commands.add_parser('queue'); commands.add_parser('status'); commands.add_parser('active-manifest')
    preview = commands.add_parser('preview')
    preview.add_argument('--train', nargs=2, required=True); preview.add_argument('--heldout', nargs=1, required=True)
    preview.add_argument('--contracts', type=Path, default=Path(__file__).parent / 'contracts.json')
    preview.add_argument('--version-fields', type=Path, default=Path(__file__).parent / 'version-fields.json')
    preview.add_argument('--tool-schema', type=Path, required=True)
    preview.add_argument('--mining', choices=['sequence', 'witnessed_edges'], default='sequence')
    learn = commands.add_parser('learn'); learn.add_argument('--plan', type=Path, required=True); learn.add_argument('--confirm', action='store_true')
    activate = commands.add_parser('activate'); activate.add_argument('--version', required=True)
    activate.add_argument('--pairs', nargs='+', required=True); activate.add_argument('--confirm', action='store_true')
    rollback = commands.add_parser('rollback'); rollback.add_argument('--confirm', action='store_true')
    args = parser.parse_args(); store = FeedbackStore(args.store)
    if args.command == 'collect':
        result = store.collect(_read(_private(args.record, exists=True)))
    elif args.command == 'preview':
        result = store.preview(args.train, args.heldout, contracts=args.contracts,
                               version_fields=args.version_fields, tool_schema=args.tool_schema, mining=args.mining)
    elif args.command == 'learn':
        result = store.learn(args.plan, confirm=args.confirm)
    elif args.command == 'activate':
        result = store.activate(args.version, args.pairs, confirm=args.confirm)
    elif args.command == 'rollback':
        result = store.rollback(confirm=args.confirm)
    elif args.command == 'active-manifest':
        result = store.active_manifest()
    else:
        result = getattr(store, args.command)()
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
