"""从正常真实轨迹提炼、生成、执行并独立认证一个 TypeScript 图件目录工具。

算法由真实 DeepSeek 响应产生，本模块只提供冻结输入、宿主调用、功能
reference 和有界学习流程。全部证据私有；默认预览，--call-model 才付费。
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import shlex
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
SCENE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scenarios.research_ppt import generated_tools as host
from scenarios.research_ppt.documents import file_hash
from scenarios.research_ppt.experiment import lines, token_totals, version
from scenarios.research_ppt.figure_catalog import catalog_input, expected_catalog, verify_catalog
from scenarios.research_ppt.service import private_path
from src.adapters.deepseek_cost_gate import State, create_server
from src.adapters.dsh_client import SemanticValidationError, call_bounded_prompt
from src.adapters.dsh_event_projection import is_original_tool_result
from src.adapters.dsh_trajectory import _observation_digest

EXPERIMENT_ID = 'research-ppt-v6-tool-rsi-20261011'
MODEL = 'deepseek-flash'
MAX_PROMPT_CHARACTERS = 120_000
MAX_OUTPUT_TOKENS = 6000

RULES = '''你正在改进真实科研 PPT Agent 的一个机械目录能力。
下面的 source_trajectory_package 来自已成功的正常 DeepSeek PPT 工具轨迹。
分析实际 read_page / extract_figure 的重复查找、页码和候选句柄传递，然后
提炼一个可复用的纯 JSON 转换工具。服务器会编译并实际运行你输出的代码。
不允许模拟工具返回，不允许写入固定论文答案、来源ID、哈希、候选ID或图注。
本轮工程范围已选为“将整个已固定 PDF 的图件候选整理为可追溯目录”；
具体实现、工具描述和提炼依据由你提出，不能声称自主选择了不受限功能范围。

函数输入只含 source_id:string, version_sha256:string, pages:Array<{
 page:number, figure_candidates:Array<{candidate_id:string,caption:string,bbox:number[]}>}>。
pages 是真实 PDF 全部页面的候选元数据，可能有零个或多个候选；图注不是选图授权。
输出必须且只能是 {source_id,version_sha256,figures:[{page,candidate_id,caption,bbox}]}。
全部原候选恰好保留一次，所有字段和值原样保留，按 page 升序、candidate_id
字典序排序，不合并/缩写/猜测图注，不新增候选，不依据科研含义选择或丢弃图。
输入由固定 PDF reader 获取，文件版本及领域一致性由独立宿主核验。

candidate 必须恰好含 name,description,input_schema,code 四字段；name 必须
read_pinned_[a-z0-9_]+。input_schema 根为 object 且 additionalProperties=false。
schema 支持 object/array/string/number/integer/boolean/null、properties/required/
additionalProperties/items、minItems/maxItems、minLength/maxLength、minimum/maximum、
enum/const/description/title；禁止 $ref、anyOf、pattern 或额外扩展。

code 必须仅有一个同步 export function run(input: any): object {...}，不含其它
顶层语句、辅助函数、类、import、require、new、process、global、网络、文件、
eval、Function、正则、TypeScript 忽略检查、类型断言或异步代码。
可用 const/let、if、return、for-of、对象/数组字面量、箭头回调、比较和算术；
支持 map/flatMap/filter/find/findIndex/some/every/reduce/slice/concat/includes/indexOf/
join/sort/push/pop/shift/unshift/reverse/trim/toLowerCase/toUpperCase/startsWith/endsWith/
split/substring/charAt/replace/replaceAll/toFixed/toString，Array.isArray，
Object.keys/values/entries/fromEntries，Math.abs/min/max/floor/ceil/round/trunc，
Number.isFinite/isInteger/isSafeInteger/parseInt/parseFloat，及 Number/String/Boolean。
只能直接调用上述内建函数/方法，不能调用自定义函数或递归；不能用 Set/Map。
仅允许命名属性访问或 [0] 等数字字面量索引；input.rows[i]、obj[key]、解构禁止。
所有输入已深度冻结。不得 sort/push 修改输入；复制后再整理。有限运行时拒绝
constructor/prototype/__proto__ 属性。候选还必须通过严格 tsc 类型检查。

初次或失败修订：只返回 JSON {decision:"propose"|"stop",reason:string,
evidence:[{run_id:string,call_ids:string[],observation:string}],candidate:{...}|null}。
reason/evidence 必须依据提供的真实轨迹，指出该工具能省哪类机械调度，不能
声称已经节约请求、形成 Motif、认证审美/科学质量或阅读未知留出来源。
训练反馈显示通过后，将另请你决定 accept/revise/stop；只有 accept 才启动
一次隐藏独立认证。最多三候选，失败也计数。不得查看或猜测留出材料。
'''


def _read(path: Path) -> dict:
    value = json.loads(private_path(path).read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('学习配置需 JSON 对象')
    return value


def _write(path: Path, value: dict, *, exclusive=False):
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if exclusive:
        with path.open('x', encoding='utf-8') as stream:
            stream.write(raw)
    else:
        temporary = private_path(path.with_name(path.name + '.' + uuid4().hex + '.tmp'))
        temporary.write_text(raw, encoding='utf-8')
        temporary.replace(path)
    path.chmod(0o600)


def _text(path: Path, value: str):
    path = private_path(path)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(value)
    path.chmod(0o600)


def _freeze(path: Path, value: dict):
    _write(path, value, exclusive=True)
    _text(path.with_name(path.name + '.sha256'), file_hash(path))


def _load_key(path: Path | None):
    if path is None:
        return
    path = private_path(path.resolve(strict=True))
    if os.name != 'nt' and path.stat().st_mode & 0o077:
        raise ValueError('API 环境文件须限制为当前用户读取')
    matches = []
    for raw in path.read_text(encoding='utf-8').splitlines():
        value = raw.strip()
        if value.startswith('export '):
            value = value[7:].lstrip()
        if value.startswith('DEEPSEEK_API_KEY='):
            parts = shlex.split(value.partition('=')[2], comments=True)
            if len(parts) != 1 or not parts[0] or any(token in parts[0] for token in ('$', '`', '\n')):
                raise ValueError('API 环境文件仅接受字面量 DEEPSEEK_API_KEY')
            matches.append(parts[0])
    if len(matches) != 1:
        raise ValueError('API 环境文件须恰好包含一个 DEEPSEEK_API_KEY')
    os.environ['DEEPSEEK_API_KEY'] = matches[0]


@contextmanager
def _budget(area: Path, cap: float, api_env: Path | None):
    names = ('DEEPSEEK_API_KEY', 'DEEPSEEK_BASE_URL', 'SSS_BUDGET_GATE_ACTIVE',
             'SSS_BUDGET_CAP_USD', 'SSS_BUDGET_LEDGER')
    previous = {name: os.environ.get(name) for name in names}
    gate = worker = None
    try:
        _load_key(api_env)
        # Harness 凭证存储也可提供密钥；不读取/输出该存储内容。
        state = State(cap_usd=cap, output_cap=MAX_OUTPUT_TOKENS, record=area / 'cost-ledger.jsonl')
        gate = create_server('127.0.0.1', 0, 'https://api.deepseek.com', state)
        worker = threading.Thread(target=gate.serve_forever, daemon=True)
        worker.start()
        os.environ.update(DEEPSEEK_BASE_URL=f'http://127.0.0.1:{gate.server_port}/v1',
                          SSS_BUDGET_GATE_ACTIVE='1', SSS_BUDGET_CAP_USD=str(cap),
                          SSS_BUDGET_LEDGER=str(area / 'cost-ledger.jsonl'))
        yield state
    finally:
        if gate is not None:
            gate.shutdown(); gate.server_close()
        if worker is not None:
            worker.join(timeout=5)
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _history(job_path: Path, run_path: Path) -> dict:
    job_path, run_path = private_path(job_path.resolve(strict=True)), private_path(run_path.resolve(strict=True))
    job = _read(job_path)
    if not isinstance(job.get('inputs'), list) or len(job['inputs']) != 1:
        raise ValueError('每个训练 job 必须是唯一 PDF；不要从多文档任务猜测来源')
    source = job['inputs'][0]
    path = private_path(Path(source['path']).resolve(strict=True))
    if path.suffix.lower() != '.pdf' or file_hash(path) != source['version_sha256']:
        raise ValueError('训练 PDF 来源版本变化')
    metrics_path, ledger_path, events_path = (run_path / name for name in
                                             ('metrics.json', 'cost-ledger.jsonl', 'agent-events.jsonl'))
    metrics, ledger = _read(metrics_path), lines(ledger_path)
    if (metrics.get('status') != 'done' or not metrics.get('upstream_requests') or
            not any(row.get('response_status') == 200 and row.get('request_id') is not None for row in ledger)):
        raise ValueError('训练运行须有成功正常 API 账本，不接受模拟或仅文件回放')
    events = lines(events_path)
    calls, results = [], {}
    for offset, event in enumerate(events):
        data = event.get('data', {})
        if event.get('type') == 'tool/call' and isinstance(data, dict):
            calls.append((offset, data))
        elif is_original_tool_result(event) and isinstance(data, dict):
            call_id = data.get('message', {}).get('source', {}).get('callId')
            if call_id:
                results.setdefault(call_id, event)
    summaries = []
    counts = {}
    source_witness = False
    for offset, data in calls:
        name, call_id = data.get('name', ''), data.get('callId', '')
        counts[name] = counts.get(name, 0) + 1
        success, observed_sha, observed = _observation_digest(results.get(call_id, {}), name)
        if name.endswith('__pin_source') and success and observed and observed.get('version_sha256') == source['version_sha256']:
            source_witness = True
        if not name.endswith(('__pin_source', '__read_source', '__read_page', '__extract_figure')):
            continue
        try:
            arguments = json.loads(data.get('arguments', ''))
        except (TypeError, ValueError):
            arguments = None
        item = {'event_offset': offset, 'call_id': call_id, 'tool': name, 'arguments': arguments,
                'success': success, 'observation_sha256': observed_sha}
        if observed:
            item['observation'] = {key: observed[key] for key in ('source_id', 'version_sha256', 'document_id',
                'page', 'page_count', 'candidate_id', 'caption', 'bbox', 'width', 'height', 'evidence_scope') if key in observed}
            if isinstance(observed.get('figure_candidates'), list):
                item['observation']['figure_candidates'] = [{key: row.get(key) for key in
                    ('candidate_id', 'caption', 'bbox')} for row in observed['figure_candidates'][:6]]
            if 'text' in observed:
                item['observation']['text_excerpt'] = str(observed['text'])[:300]
            if 'pages' in observed:
                item['observation']['returned_pages'] = len(observed['pages'])
        summaries.append(item)
    if not source_witness:
        raise ValueError('历史模型轨迹没有对应训练 PDF 哈希的真实 pin_source 结果')
    source_id = 'source-' + hashlib.sha256((source['document_id'] + source['version_sha256']).encode()).hexdigest()[:32]
    return {'run_id': run_path.name, 'task_id': job['job_id'], 'source_path': str(path),
            'source_sha256': source['version_sha256'], 'source_id': source_id,
            'job_path': str(job_path), 'job_sha256': file_hash(job_path),
            'events_source': str(events_path), 'events_source_sha256': file_hash(events_path),
            'metrics_path': str(metrics_path), 'metrics_sha256': file_hash(metrics_path),
            'ledger_path': str(ledger_path), 'ledger_sha256': file_hash(ledger_path),
            'tool_counts': counts, 'tool_order': [row[1].get('name') for row in calls],
            'mechanical_observations': summaries[:16], 'observation_excerpt_limit': 16,
            'full_events_preserved_at_original_source': True}


def _case(area: Path, *, identity: str, task_id: str, run_id: str, source: Path,
          source_id: str, source_sha256: str) -> tuple[dict, dict]:
    payload = catalog_input(source, source_id, source_sha256)
    expected = expected_catalog(payload)
    case_area = area / 'cases' / identity
    _freeze(case_area / 'input.json', payload)
    _freeze(case_area / 'reference.json', expected)
    return {'id': identity, 'task_id': task_id, 'run_id': run_id,
            'input_path': str(case_area / 'input.json'), 'input_sha256': file_hash(case_area / 'input.json'),
            'expected_path': str(case_area / 'reference.json'), 'expected_sha256': file_hash(case_area / 'reference.json'),
            'source_evidence': [{'path': str(source), 'sha256': source_sha256}]}, payload


def _parse_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith('```'):
        match = re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```', text, re.S)
        if not match:
            raise ValueError('模型需返回完整 JSON 对象')
        text = match.group(1)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError('模型需返回 JSON 对象')
    return value


def _ask(area: Path, state: State, prompt: str, kind: str, summary: dict) -> tuple[dict | None, dict]:
    call_id = uuid4().hex
    directory = area / 'model-calls' / call_id
    directory.mkdir(parents=True)
    _text(directory / 'prompt.txt', prompt)
    before = state.request_count
    raw, metrics, error = '', {}, None
    started = time.monotonic()
    try:
        raw, metrics = call_bounded_prompt(prompt, root=ROOT, model=MODEL,
                                          max_output_tokens=MAX_OUTPUT_TOKENS,
                                          max_prompt_characters=MAX_PROMPT_CHARACTERS)
    except SemanticValidationError as exc:
        raw, metrics, error = exc.raw_response, exc.metrics, type(exc).__name__
    except Exception as exc:
        error = type(exc).__name__
    _text(directory / 'response.txt', raw)
    metrics.update(call_id=call_id, phase=kind, upstream_requests_delta=state.request_count - before,
                   elapsed_controller_seconds=round(time.monotonic() - started, 3), error_type=error)
    _freeze(directory / 'metrics.json', metrics)
    value, parse_error = None, None
    if error is None:
        try:
            value = _parse_response(raw)
        except (ValueError, TypeError) as exc:
            parse_error = str(exc)[:500]
    call = {'run_id': call_id, 'kind': kind, 'directory': str(directory), 'metrics': metrics,
            'prompt_path': str(directory / 'prompt.txt'), 'prompt_sha256': file_hash(directory / 'prompt.txt'),
            'response_path': str(directory / 'response.txt'), 'response_sha256': file_hash(directory / 'response.txt'),
            'parse_error': parse_error}
    _freeze(directory / 'call.json', call)
    summary['model_calls'].append(call)
    _write(area / 'summary.json', summary)
    if error:
        raise ValueError('真实模型请求失败，保留账本；错误类型 ' + error)
    return value, call


def _proposal(value: dict | None, material_identities: set[str]) -> dict:
    if not isinstance(value, dict):
        return {}
    candidate = value.get('candidate', {})
    if not isinstance(candidate, dict):
        return {}
    # 只拒绝硬编码训练身份，不替模型修复代码或填 schema。
    code_schema = json.dumps({'code': candidate.get('code'), 'schema': candidate.get('input_schema')}, ensure_ascii=False)
    if any(identity and identity in code_schema for identity in material_identities):
        return {'rejected_hardcoded_training_identity': True}
    return candidate


def _config(args, histories: list[dict]) -> dict:
    names = ('tool_learning.py', 'generated_tools.py', 'figure_catalog.py', 'documents.py', 'package-lock.json')
    packages = {}
    for package in ('deepseek-harness-sdk', 'PyMuPDF', 'mcp'):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = 'missing'
    return {'schema_version': 1, 'experiment_id': EXPERIMENT_ID,
            'started_utc': datetime.now(timezone.utc).isoformat(), 'type': 'real_model_generated_tool_learning',
            'provider': 'deepseek-official', 'model': MODEL, 'reasoning_effort': 'off',
            'compression': 'disabled_semantic_profile', 'model_facing_tools': [], 'max_candidates': 3,
            'max_output_tokens': MAX_OUTPUT_TOKENS, 'max_prompt_characters': MAX_PROMPT_CHARACTERS,
            'budget_cap_usd': args.budget_usd, 'interval_seconds': args.interval_seconds,
            'code_hashes': {str((SCENE / name).relative_to(ROOT)): file_hash(SCENE / name) for name in names},
            'public_adapter_hashes': {name: file_hash(ROOT / name) for name in
                ('src/adapters/dsh_client.py', 'src/adapters/deepseek_cost_gate.py',
                 'src/adapters/harness_runtime.py', 'config/semantic-sdk.patch.yml')},
            'commit': version(['git', 'rev-parse', 'HEAD']),
            'worktree_status': version(['git', 'status', '--porcelain', '--untracked-files=no']),
            'python': platform.python_version(), 'node': version(['node', '--version']),
            'os': platform.platform(), 'packages': packages,
            'train_source_versions': [row['source_sha256'] for row in histories],
            'scope_selected_by_engineering': 'trace_informed_full_figure_metadata_catalog',
            'candidate_implementation_authorship': 'actual_deepseek_response_only',
            'functional_oracle': 'all_original_candidate_fields_preserved_exactly_sorted_page_then_candidate_id',
            'scientific_selection': 'continues_to_require_semantic_model',
            'missing_configuration': ['bounded_helper_internal_session_id', 'provider_invoice',
                                      'human_review_minutes', 'development_and_server_cost']}


def run(args) -> dict:
    if len(args.train_job) != 2 or len(args.train_run) != 2:
        raise ValueError('需要恰好两个独立 train-job 与对应 train-run，按参数顺序配对')
    if not math.isfinite(args.budget_usd) or not 0 < args.budget_usd <= 100 or not 0 <= args.interval_seconds <= 60:
        raise ValueError('预算或请求间隔无效')
    histories = [_history(job, run_path) for job, run_path in zip(args.train_job, args.train_run)]
    if (len({row['task_id'] for row in histories}) != 2 or len({row['run_id'] for row in histories}) != 2 or
            len({row['source_sha256'] for row in histories}) != 2):
        raise ValueError('两个训练任务/run/PDF 版本必须不同')
    heldout = private_path(args.heldout_input.resolve(strict=True))
    if heldout.suffix.lower() != '.pdf':
        raise ValueError('独立留出须是真实 PDF')
    heldout_sha = file_hash(heldout)
    if heldout_sha in {row['source_sha256'] for row in histories}:
        raise ValueError('独立留出 PDF 不能复用训练来源')
    area = private_path(args.out.resolve())
    preview = {'experiment_id': EXPERIMENT_ID, 'out': str(area), 'model_call_enabled': args.call_model,
               'train_runs': [row['run_id'] for row in histories], 'train_tasks': [row['task_id'] for row in histories],
               'heldout_disclosure': 'hidden_from_all_model_prompts', 'budget_cap_usd': args.budget_usd,
               'max_candidates': 3, 'reasoning_effort': 'off', 'compression': 'disabled',
               'impact': 'creates private compiled modules/evidence; no user source edits or Git operations'}
    print(json.dumps(preview, ensure_ascii=False, indent=2), flush=True)
    if not args.call_model:
        return preview
    if area.exists() and any(area.iterdir()):
        raise ValueError('学习目录已使用，禁止重复付费或覆盖旧证据；如需新配置使用新的实验目录')
    area.mkdir(parents=True, exist_ok=True, mode=0o700)
    _write(area / 'driver.lock', {'pid': os.getpid(), 'started_utc': datetime.now(timezone.utc).isoformat()}, exclusive=True)
    _freeze(area / 'config.json', _config(args, histories))
    _freeze(area / 'training-normal-trajectory.json', {'schema_version': 1, 'runs': histories,
             'events_are_real_original_records': True, 'projection': 'bounded_excerpt_for_tool_learning_only'})
    _freeze(area / 'heldout-source-lock.json', {'path': str(heldout), 'sha256': heldout_sha,
                                              'disclosed_to_model': False})
    job_path = area / 'job.json'
    _freeze(job_path, {'job_id': uuid4().hex, 'allow_rsi': True, 'allow_output': True,
                      'inputs': [{'path': row['source_path'], 'version_sha256': row['source_sha256']}
                                 for row in histories], 'experiment_id': EXPERIMENT_ID})
    cases, payloads, identities = [], [], set()
    for index, row in enumerate(histories, 1):
        case, payload = _case(area, identity=f'train_{index}', task_id=row['task_id'], run_id=row['run_id'],
                             source=Path(row['source_path']), source_id=row['source_id'], source_sha256=row['source_sha256'])
        # 原始正常轨迹也进入宿主证据锁；不是只锁一个可共享的摘要文件。
        case['source_evidence'].extend({'path': row[path_key], 'sha256': row[sha_key]}
            for path_key, sha_key in (('events_source', 'events_source_sha256'),
                                     ('metrics_path', 'metrics_sha256'), ('ledger_path', 'ledger_sha256'),
                                     ('job_path', 'job_sha256')))
        cases.append(case); payloads.append(payload)
        identities.update((row['source_id'], row['source_sha256']))
        identities.update(candidate['candidate_id'] for page in payload['pages'] for candidate in page['figure_candidates'])
    _freeze(area / 'training-cases.json', {'cases': cases})
    context = {'source_trajectory_package': histories, 'real_training_inputs': payloads,
               'scope': 'mechanical_catalog_not_semantic_figure_selection', 'training_references_visible': False}
    prefix = RULES + '\n真实训练证据：\n' + json.dumps(context, ensure_ascii=False, separators=(',', ':'))
    summary = {'schema_version': 1, 'experiment_id': EXPERIMENT_ID, 'status': 'starting',
               'config_path': str(area / 'config.json'), 'config_sha256': file_hash(area / 'config.json'),
               'job_path': str(job_path), 'model_calls': [], 'proposals': [], 'certificate_path': None,
               'generated_tool': False, 'learned_motif': False, 'quality': 'not_human_reviewed',
               'scientific_quality_certification': False}
    _write(area / 'summary.json', summary)
    started, state, feedback, pending = time.monotonic(), None, None, None
    try:
        with _budget(area, args.budget_usd, args.api_env) as state:
            while host.candidate_status(job_path)['attempts_remaining'] > 0:
                if pending is None:
                    if summary['model_calls'] and args.interval_seconds:
                        time.sleep(args.interval_seconds)
                    suffix = {'phase': 'propose', 'attempts_remaining': host.candidate_status(job_path)['attempts_remaining'],
                              'latest_training_feedback': feedback, 'heldout_feedback': 'not_available'}
                    value, call = _ask(area, state, prefix + '\n当前反馈：\n' + json.dumps(suffix, ensure_ascii=False), 'propose', summary)
                    if value and value.get('decision') == 'stop':
                        summary.update(status='model_declined', stop_reason=value.get('reason'))
                        break
                    candidate = _proposal(value, identities)
                else:
                    value, call, candidate = pending
                    pending = None
                provenance = {'provider': 'deepseek-official', 'model': MODEL, 'run_id': call['run_id'],
                    'reasoning_effort': 'off', 'response_path': call['response_path'], 'response_sha256': call['response_sha256'],
                    'trajectory_path': str(area / 'training-normal-trajectory.json'),
                    'trajectory_sha256': file_hash(area / 'training-normal-trajectory.json'),
                    'training_run_ids': [row['run_id'] for row in histories]}
                proposal = host.propose_candidate(job_path, candidate, provenance)
                record = {'proposal': proposal, 'generation_call_id': call['run_id'],
                          'model_reason': value.get('reason') if value else None,
                          'model_extraction_evidence': value.get('evidence') if value else None}
                if proposal['compile_passed']:
                    training = host.evaluate_candidate(proposal['candidate_path'], cases, split='train')
                    record['training'] = training
                    # 场景独立核验使用真实 source payload，绝不只信任 schema 或 passed 标志。
                    for case, payload in zip(cases, payloads):
                        if training['passed']:
                            verify_catalog(payload, host.run_candidate(proposal['candidate_path'], payload)['output'])
                else:
                    training = {'passed': False, 'cases': [], 'diagnostics': proposal['diagnostics']}
                summary['proposals'].append(record)
                _write(area / 'summary.json', summary)
                feedback = {'last_candidate': candidate, 'compilation': proposal,
                            'training': training, 'reference_rule': 'all_candidate_fields_preserved_sorted',
                            'no_heldout_information': True}
                if not training['passed']:
                    continue
                if args.interval_seconds:
                    time.sleep(args.interval_seconds)
                decision_prompt = prefix + '\n真实训练结果与候选：\n' + json.dumps(feedback, ensure_ascii=False) + '''
训练已通过，但尚未查看独立材料。请根据这些结果决定，返回 JSON：
{decision:"accept"|"revise"|"stop",reason:string,evidence:[...],candidate:null|{name,description,input_schema,code}}。
accept=冻结当前候选，启动一次独立认证；revise=给出新的完整候选且消耗剩余提案次数；
stop=不晋级。不能称已经通过独立认证、形成Motif或科学质量合格。'''
                decision, decision_call = _ask(area, state, decision_prompt, 'post_training_decision', summary)
                record['model_post_result_decision'] = {'response': decision, 'run_id': decision_call['run_id']}
                _write(area / 'summary.json', summary)
                if decision and decision.get('decision') == 'revise':
                    pending = decision, decision_call, _proposal(decision, identities)
                    continue
                if not decision or decision.get('decision') != 'accept':
                    summary.update(status='model_stopped_after_training', stop_reason=decision.get('reason') if decision else 'invalid_decision')
                    break
                # 首次读取/处理留出内容发生在模型的 accept 之后。任何失败都不再问模型。
                if file_hash(heldout) != heldout_sha:
                    raise ValueError('隐藏独立来源在认证前变化')
                heldout_case, heldout_payload = _case(area, identity='heldout_1', task_id='independent-heldout-' + uuid4().hex,
                    run_id='functional-certification-' + uuid4().hex, source=heldout,
                    source_id='source-' + hashlib.sha256(('heldout' + heldout_sha).encode()).hexdigest()[:32],
                    source_sha256=heldout_sha)
                certified = host.certify_candidate(proposal['candidate_path'], training['evaluation_path'], [heldout_case])
                record['certification'] = certified
                summary.update(status='functional_certified' if certified['certified'] else 'heldout_rejected',
                               generated_tool=certified['certified'], certificate_path=certified['certificate_path'])
                if certified['certified']:
                    tool = host.load_certified_tool(certified['certificate_path'])
                    verify_catalog(heldout_payload, host.run_certified_tool(certified['certificate_path'], heldout_payload)['output'])
                    _freeze(area / 'certificate-pointer.json', {'certificate_path': certified['certificate_path'],
                        'certificate_sha256': certified['certificate_sha256'], 'tool_name': tool['name'],
                        'code_sha256': tool['code_sha256'], 'input_schema_sha256': tool['input_schema_sha256'],
                        'generated_by_model': True, 'learned_motif': False,
                        'quality_scope': 'functional_metadata_preservation_not_scientific_or_aesthetic'})
                    summary.update(tool_name=tool['name'], code_sha256=tool['code_sha256'],
                                   certificate_sha256=tool['certificate_sha256'])
                break
            if summary['status'] == 'starting':
                summary['status'] = 'no_accepted_candidate_within_limit'
    except BaseException as exc:
        summary.update(status='error' if not isinstance(exc, KeyboardInterrupt) else 'interrupted',
                       error_type=type(exc).__name__, error_stage='bounded_tool_learning')
        _write(area / 'failure.json', {'error_type': type(exc).__name__, 'message': str(exc)[:1200],
                                     'negative_evidence_retained': True})
    finally:
        ledger = lines(area / 'cost-ledger.jsonl')
        fallback = {'upstream_requests': state.request_count if state else 0}
        summary.update(elapsed_seconds=round(time.monotonic() - started, 3),
                       actual_upstream_requests=state.request_count if state else 0,
                       budget_accounted_usd=state.reserved_usd if state else 0.0,
                       ledger_path=str(area / 'cost-ledger.jsonl'), invoice='unknown',
                       tokens=token_totals(ledger, fallback), attempts=host.candidate_status(job_path),
                       cost_scope='learning_generation_decisions_functional_certification; downstream_tasks_separate',
                       learning_trace_scope='two_normal_paid_historical_tasks; heldout_real_pdf_functional_replay')
        _write(area / 'summary.json', summary)
    print(json.dumps({key: summary.get(key) for key in ('status', 'certificate_path', 'tool_name',
        'actual_upstream_requests', 'budget_accounted_usd', 'tokens', 'error_type')}, ensure_ascii=False), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train-job', type=Path, action='append', required=True)
    parser.add_argument('--train-run', type=Path, action='append', required=True)
    parser.add_argument('--heldout-input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--budget-usd', type=float, default=0.75)
    parser.add_argument('--interval-seconds', type=float, default=5.0)
    parser.add_argument('--api-env', type=Path)
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    result = run(args)
    return 0 if not args.call_model or result.get('status') == 'functional_certified' else 2


if __name__ == '__main__':
    raise SystemExit(main())
