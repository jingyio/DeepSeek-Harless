#!/usr/bin/env python3
"""Official Harness Web: dynamic tasks by default, frozen diagnostics optional."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
from secrets import token_hex

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.file_scenario import prepare_scenario
from src.adapters.file_cost_gate import State, create_server
from src.adapters.file_web_task_budget import TaskBudgetRegistry, create_control_server


def save(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)


def fixture_module():
    spec = importlib.util.spec_from_file_location('sss_public_fixture', ROOT / 'scripts/motif-example.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def demo_action(values, _event):
    for object_id in ('note:alpha', 'note:beta'):
        rows = [row for row in values if row.get('object_id') == object_id]
        pins = [row for row in rows if 'source_id' in row]
        reads = [row for row in rows if 'text' in row]
        if not pins:
            return 'mcp__demo__pin_note', {'object_id': object_id}
        if not reads:
            return 'mcp__demo__read_pinned_note', {'source_id': pins[-1]['source_id']}
    return None, {'answer': '两次试验的种子数与评测协议不同；还缺同协议下的独立复现实验。',
                  'sources': [{key: row[key] for key in ('object_id', 'source_id', 'version_sha256')}
                              for row in values if 'text' in row]}


def prepare(args, output, endpoint):
    public = json.loads((ROOT / 'config/harness-web.json').read_text())
    literature = args.scenario == 'literature-pdf'
    file_operations=args.scenario=='file-management'
    if file_operations:
        from src.adapters.continuous_rsi import load_config
        file_v2=load_config(args.rsi_config).get('adapter')=='file_operations_v2'
    scenario = ROOT / ('scenarios/file-management/web-operation-scenario-v2.json' if file_v2 else 'scenarios/file-management/web-operation-scenario.json') if file_operations else ROOT / 'scenarios/literature-notes/web-scenario.json' if literature else Path(args.scenario)
    if not scenario.is_absolute():
        scenario = ROOT / scenario
    if scenario.suffix != '.json':
        scenario = ROOT / f'scenarios/{args.scenario}/scenario.json'
    prepared = prepare_scenario(scenario, case=args.case or ('l_retrieval_persistence' if args.scenario == 'portfolio-v1' else ''))
    preset = output / 'presets/sss-task'
    preset.mkdir(parents=True, mode=0o700)
    rows = [{'id': 'sss-persona', 'name': '@deepseek-ai/dsh-persona', 'config': {
        'prefix': 'Complete the bounded task using only the permitted MCP evidence.',
        'suffix': 'Cite source IDs and versions. Do not invent evidence. Writes require tool-side preview and confirmation.'}}, *([] if literature or file_operations else prepared['mcp_rows']), *([] if literature or file_operations else prepared.get('agent_plugins', []))]
    rendered = json.dumps(rows, ensure_ascii=False, indent=2)
    for token, expression in prepared['environment_references'].items():
        rendered = rendered.replace(json.dumps(token), expression)
    (preset / 'agent.cordis.yml').write_text(rendered)
    (preset / 'agent.cordis.yml').chmod(0o600)
    save(preset / 'preset.yml', {'name': f'DeepSeek Harless {prepared["name"]}（{"真实模型" if args.real_model else "免费模拟"}）'})
    canonical_prompt_sha = hashlib.sha256(prepared['prompt'].strip().encode()).hexdigest()
    policy = {'output': str(output), 'prompt_sha256': canonical_prompt_sha,
              'allowed_tools': prepared['allowed_tools'], 'endpoint': endpoint,
              'max_output_tokens': args.max_output or public['max_output_tokens'], 'mode': args.mode,
              'embedding_endpoint': args.embedding_endpoint,
              'fixture': args.fixture}
    if (not args.frozen and args.scenario == 'portfolio-v1') or (args.frozen and args.mode != 'baseline') or args.manifest:
        bundle = ROOT / 'examples/motif-library/research-portfolio-v1'
        task = json.loads((bundle / 'task.json').read_text())
        if args.fixture == 'stale':
            task['source_versions'] = {key: '0' * 64 for key in task['source_versions']}
        save(output / 'task.json', task)
        policy.update(manifest=str(Path(args.manifest).resolve()) if args.manifest else str(bundle / 'online-manifest.json'),
                      task=str(Path(args.task).resolve()) if args.task else str(output / 'task.json'))
    if not args.frozen:
        if prepared.get('acceptance_guard'):
            policy['acceptance_guard'] = {**prepared['acceptance_guard'], 'archive_root': str(ROOT / '.local/task-acceptance')}
        resources = {}
        if args.resources:
            resource_file = Path(args.resources).resolve()
            definitions = json.loads(resource_file.read_text(encoding='utf-8'))
            if not isinstance(definitions, dict): raise ValueError('resource registry must be an object')
            for identity, definition in definitions.items():
                if (not isinstance(identity, str) or not identity or not isinstance(definition, dict)
                        or set(definition) != {'text_file'}): raise ValueError('resources require ID -> {text_file}')
                path = (resource_file.parent / definition['text_file']).resolve()
                data = path.read_bytes()
                if len(data) > 256 * 1024: raise ValueError('registered resource exceeds 256 KiB')
                resources[identity] = {'text': data.decode('utf-8'), 'version': hashlib.sha256(data).hexdigest()}
        policy.update(capability_profile=args.scenario if '/' not in args.scenario else prepared['name'],
            budget_usd=args.budget_usd, provider_mode='real' if args.real_model else 'mock',
            control_endpoint=args.control_endpoint, control_token=args.control_token,
            certified_input_sha256=canonical_prompt_sha, resources=resources,
            embedding_model=args.embedding_model)
    if literature:
        if args.frozen: raise ValueError('literature-pdf requires dynamic tasks')
        directory = Path(args.papers_dir).resolve()
        if not directory.is_dir(): raise ValueError('registered PDF directory not found')
        policy['task_binding'] = {'module': (ROOT / 'scenarios/literature-notes/web-binding.ts').as_uri(),
            'config': {'python': sys.executable, 'papers_dir': str(directory), 'presets_root': str(output / 'presets')}}
    if file_operations:
        from src.adapters.continuous_rsi import load_config,DATA,snapshot
        import shutil
        if args.frozen or args.budget_usd>5 or args.request_limit>96 or policy['max_output_tokens']>4000:
            raise ValueError('file RSI requires original dynamic task bounds')
        config_file=Path(args.rsi_config).resolve()
        cfg=load_config(config_file)
        if cfg.get('adapter') not in ('file_operations_v1','file_operations_v2') or cfg['provider_mode']!=('real' if args.real_model else 'mock'):raise ValueError('file Web/RSI provider or registered adapter mismatch')
        directory=Path(args.files_dir).resolve() if args.files_dir else Path(cfg['workspace_roots'][0])/'web-seed'
        if not args.files_dir:
            directory.mkdir(parents=True,exist_ok=True)
            if not (directory/'.experiment-copy').exists():(directory/'.experiment-copy').write_text('persistent-authorized-source')
            if not (directory/'notes.txt').exists():(directory/'notes.txt').write_text('Registered persistent Web source '+uuid4().hex+'\n')
            for name in ('brief.docx','ledger.xlsx'):
                asset=ROOT/'.local/file-management-author/assets/a'/name
                if asset.exists() and not (directory/name).exists():shutil.copyfile(asset,directory/name)
        if not directory.is_relative_to(DATA.resolve()) or not (directory/'.experiment-copy').is_file():raise ValueError('registered file directory must be an authorized experiment copy')
        registered=[{'path':n,'sha256':h} for n,h in snapshot(directory).items() if n!='.experiment-copy']
        policy['task_binding']={'module':(ROOT/'scenarios/file-management/operation_web_binding.ts').as_uri(),
             'config':{'python':sys.executable,'files_dir':str(directory),'rsi_config':str(config_file),'presets_root':str(output/'presets'),
               'registered_files':registered,'provider_mode':cfg['provider_mode'],'request_limit':args.request_limit,'max_output':policy['max_output_tokens']}}
    if file_operations and file_v2:
        policy['persistent_tasks_root']=str(Path(cfg['state_root'])/'web-tasks')
    save(output / 'policy.json', policy)
    disabled = ['llm-deepseek', 'llm-pi-ai', 'session-title-llm', 'llm-retry',
                'compaction-basic', 'command-compact', 'session-log-deepseek', 'goal', 'goal-round-driver']
    patch = [{'id': name, 'disabled': True} for name in disabled]
    patch += [{'id': 'agent-presets', 'config': {'default': 'sss-task',
        'includeShippedRoot': False, 'includeUserRoot': False,
        'roots': [{'path': str(output / 'presets'), 'trust': 'system'}]}},
        {'insert': [{'id': 'sss-web-policy', 'name': (ROOT / 'src/adapters' /
            ('dsh_web_policy.ts' if args.frozen else 'dsh_web_tasks.ts')).as_uri()}]}]
    save(output / 'host.patch.yml', patch)
    (output / 'prompt.md').write_text(prepared['prompt']); (output / 'prompt.md').chmod(0o600)
    snapshot = {**public, 'mode': args.mode, 'scenario': args.scenario,
                'budget_usd': args.budget_usd, 'request_limit': args.request_limit,
                'prompt_sha256': canonical_prompt_sha, 'raw_prompt_sha256': prepared['prompt_sha256'],
                'prompt_normalization': 'outer whitespace only (official composer trim)',
                'scenario_sha256': prepared['config_sha256'],
                'allowed_tools': prepared['allowed_tools'], 'tools_order': sorted(prepared['allowed_tools']),
                'fixture': args.fixture,
                'case': prepared['case'], 'embedding_model': args.embedding_model if args.embedding_endpoint else None,
                'dsh_version': '0.1.5-rc.3', 'python_version': sys.version.split()[0],
                'node_version': subprocess.check_output(['node', '--version'], text=True).strip(),
                'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'dirty_files': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
                'output': str(output), 'provider_mode': 'real' if args.real_model else 'mock',
                'paid_calls': None if args.real_model else 0, 'entry': 'frozen' if args.frozen else 'dynamic',
                'run_budget_usd': args.run_budget_usd, 'run_request_limit': args.run_request_limit}
    snapshot['max_output_tokens'] = policy['max_output_tokens']
    snapshot['scene_binding'] = policy.get('task_binding')
    snapshot.update(task_id=output.name, platform=platform.platform(), real_models_enabled=args.real_model,
        motif_min_similarity=0.8, motif_min_margin=0.1, disabled_host_plugins=disabled,
        git_diff_sha256=hashlib.sha256(subprocess.check_output(['git', 'diff', '--binary'], cwd=ROOT)).hexdigest())
    snapshot['host_patch_sha256'] = hashlib.sha256((output / 'host.patch.yml').read_bytes()).hexdigest()
    snapshot['files_sha256'] = {str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else 'private-scenario-config': hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [scenario, ROOT / 'config/harness-web.json', ROOT / 'src/adapters' /
                     ('dsh_web_policy.ts' if args.frozen else 'dsh_web_tasks.ts'),
                     ROOT / 'src/adapters/file_cost_gate.py', ROOT / 'scripts/harness-web.py',
                     ROOT / 'scripts/motif-example.py', ROOT / 'src/adapters/dsh_completion_guard.ts',
                     ROOT / 'src/adapters/file_acceptance_guard.ts', ROOT / 'scripts/validate-file-delivery.py', ROOT / 'package-lock.json',
                     *([ROOT / name for name in ('src/adapters/continuous_rsi.py','src/adapters/continuous_motif_learning.py',
                        'src/adapters/mcp_learning.py','src/adapters/dsh_operation_motif.ts','src/adapters/dsh_continuous_rsi.ts',
                        'src/motif_core/operation_graph_policy.ts','src/motif_core/offline/operation_graph.py',
                        'scenarios/file-management/operation_tools.py','scenarios/file-management/operation_contract.py',
                        'scenarios/file-management/operation_web_binding.py','scenarios/file-management/operation_web_binding.ts')]
                        if args.scenario=='file-management' else []),
                     *([ROOT / 'scenarios/literature-notes' / name for name in ('web-binding.ts', 'web-binding.py', 'web_pdf_tools.py', 'web-scenario.json', 'web-task.md')] if literature else []),
                     *([] if args.frozen else [ROOT / 'src/adapters/web_task_request.ts',
                       ROOT / 'src/adapters/file_web_task_budget.py', ROOT / 'src/adapters/web_task_panel.html'])]}
    if policy.get('manifest'):
        snapshot['manifest_sha256'] = hashlib.sha256(Path(policy['manifest']).read_bytes()).hexdigest()
        snapshot['task_sha256'] = hashlib.sha256(Path(policy['task']).read_bytes()).hexdigest()
    save(output / 'effective-config.json', snapshot)
    return public


def main():
    defaults = json.loads((ROOT / 'config/harness-web.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', default='example', help='scenario name or path to scenario.json (server configuration)')
    parser.add_argument('--case', default='')
    parser.add_argument('--papers-dir', default=str(ROOT / 'testpdf'), help='server-owned PDF directory for literature-pdf')
    parser.add_argument('--files-dir',default=None,help='server-owned experimental file source directory')
    parser.add_argument('--rsi-config',default=None,help='shared private certified library/learning configuration for file-management')
    parser.add_argument('--max-output', type=int, default=None, help='output token cap, 1–8000')
    parser.add_argument('--frozen', action='store_true', help='legacy single-task mock regression entry')
    parser.add_argument('--real-model', action='store_true', help='enable real DeepSeek connection; each task still requires preview confirmation')
    parser.add_argument('--manifest', help='certified online manifest for this capability profile')
    parser.add_argument('--task', help='certified task/version binding, paired with --manifest')
    parser.add_argument('--resources', help='private server-owned resource registry JSON: ID -> {text_file}')
    parser.add_argument('--embedding-endpoint', default='')
    parser.add_argument('--embedding-model', default='fixture-vectors-not-a-semantic-model')
    parser.add_argument('--mode', choices=['baseline', 'shadow', 'execute'], default='baseline')
    parser.add_argument('--port', type=int, default=defaults['port'])
    parser.add_argument('--run-id', help='optional unique 32-character hexadecimal output identity')
    parser.add_argument('--budget-usd', type=float, default=defaults['budget_usd'])
    parser.add_argument('--request-limit', type=int, default=defaults['request_limit'])
    parser.add_argument('--run-request-limit', type=int, default=256, help='whole-launch request cap across all tasks')
    parser.add_argument('--run-budget-usd', type=float, default=defaults['budget_usd'], help='whole-launch budget, never reset by a new task')
    parser.add_argument('--fixture', choices=['normal', 'stale', 'tool-failure', 'provider-failure', 'outside-tool', 'delay'],
                        default='normal', help='mock-only failure injection for diagnostics')
    args = parser.parse_args()
    if args.max_output is not None and not 1 <= args.max_output <= 8000: parser.error('max-output must be 1–8000')
    if args.scenario == 'literature-pdf' and args.max_output is None: args.max_output = 8000
    if args.scenario=='file-management' and args.max_output is None:args.max_output=4000
    if args.frozen and args.mode != 'baseline' and args.scenario != 'portfolio-v1':
        parser.error('Motif modes require the portfolio-v1 historical library scenario')
    if args.fixture in ('stale', 'tool-failure') and (args.mode != 'execute' or args.scenario != 'portfolio-v1'):
        parser.error('stale/tool-failure fixtures require portfolio-v1 execute')
    if args.scenario=='file-management' and args.fixture not in ('normal','delay'):
        parser.error('file-management supports normal/delay mock fixtures')
    if not 1024 <= args.port <= 65535 or args.request_limit < 1 or not math.isfinite(args.budget_usd) or args.budget_usd < 0:
        parser.error('invalid port, request limit or budget')
    if not math.isfinite(args.run_budget_usd) or not args.budget_usd <= args.run_budget_usd <= 100 or args.run_request_limit < 1:
        parser.error('whole-launch budget must cover task cap and be <=100; request limit must be positive')
    if bool(args.manifest) != bool(args.task): parser.error('--manifest and --task must be supplied together')
    if args.real_model and (args.frozen or args.fixture != 'normal'):
        parser.error('real provider cannot use frozen/failure fixtures')
    if args.real_model and not os.environ.get('DEEPSEEK_API_KEY', '').strip():
        parser.error('configure DEEPSEEK_API_KEY in private .env and start through npm run web')
    if args.run_id is not None and not re.fullmatch('[0-9a-f]{32}', args.run_id):
        parser.error('run-id must be 32 lowercase hexadecimal characters')
    if args.scenario=='file-management' and not args.rsi_config:
        from src.adapters.persistent_file_rsi import default_config
        args.rsi_config=str(default_config(args.real_model))
    os.umask(0o077)
    output = ROOT / '.local/web/runs' / (args.run_id or uuid4().hex)
    output.mkdir(parents=True, mode=0o700)
    (output / 'work').mkdir(mode=0o700)
    (output / 'dsh').mkdir(mode=0o700)
    for name in ('events.jsonl', 'motif-audit.jsonl', 'ledger.jsonl'):
        (output / name).touch(mode=0o600)
    module = fixture_module()
    if args.scenario == 'example':
        module.next_fixture_action = demo_action
    if args.scenario == 'literature-pdf' and not args.real_model:
        spec = importlib.util.spec_from_file_location('literature_web_fixture', ROOT / 'scenarios/literature-notes/web-fixture.py')
        fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
        module.next_fixture_action = fixture.action
    handler = module.provider_handler('event:l_retrieval_persistence:01', with_usage=True,
                                     request_limit=24 if args.frozen else args.run_request_limit)
    if args.scenario=='file-management' and not args.real_model:
        from src.adapters.continuous_rsi import load_config
        fixture_path='operation-v2-fixture.py' if load_config(args.rsi_config).get('adapter')=='file_operations_v2' else 'check-operation-rsi.py'
        spec=importlib.util.spec_from_file_location('file_operation_fixture',ROOT/'scripts'/fixture_path)
        fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
        handler=fixture.Provider;handler.calls=[];handler.embedding_calls=0;handler.failures=0;handler.response_delay=1 if args.fixture=='delay' else 0
    if args.fixture == 'outside-tool':
        original_action = module.next_fixture_action
        def outside_action(values, event):
            if len(handler.calls) == 1: return 'bash', {'command': 'echo forbidden'}
            return original_action(values, event)
        module.next_fixture_action = outside_action
    if args.fixture in ('delay', 'provider-failure') and args.scenario!='file-management':
        original_respond = handler.respond
        def respond(self):
            if args.fixture == 'delay': time.sleep(1)
            else: raise RuntimeError('injected mock provider failure')
            return original_respond(self)
        handler.respond = respond
    provider = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    if args.scenario=='file-management':provider.requests=handler.calls if hasattr(handler,'calls') else []
    upstream = f'http://127.0.0.1:{provider.server_port}'
    if not args.real_model: args.embedding_endpoint = args.embedding_endpoint or upstream + '/v1/embeddings'
    else: upstream = 'https://api.deepseek.com'
    state = State(cap_usd=args.budget_usd if args.frozen else args.run_budget_usd,
                  output_cap=args.max_output or defaults['max_output_tokens'], record=output / 'ledger.jsonl',
                  request_limit=args.request_limit if args.frozen else args.run_request_limit)
    persistent_lock=None
    if args.scenario=='file-management':
        from src.adapters.continuous_rsi import load_config,writer_lock
        cfg=load_config(args.rsi_config)
        if cfg.get('adapter')=='file_operations_v2':
            from src.adapters.persistent_web_budget import PersistentState
            persistent_root=Path(cfg['state_root']);persistent_root.mkdir(parents=True,exist_ok=True)
            persistent_lock=writer_lock(persistent_root,'web-server');persistent_lock.__enter__()
            checkpoint=persistent_root/'web-budget.json'
            if checkpoint.exists():
                original=json.loads(checkpoint.read_text())
                supplied=lambda flag:any(v==flag or v.startswith(flag+'=') for v in sys.argv[1:])
                if not supplied('--run-budget-usd'):args.run_budget_usd=original['cap_usd']
                if not supplied('--run-request-limit'):args.run_request_limit=original['request_limit']
            state=PersistentState(checkpoint=checkpoint,cap_usd=args.run_budget_usd,
                output_cap=args.max_output,record=persistent_root/'web-ledger.jsonl',request_limit=args.run_request_limit)
    servers = [] if args.real_model else [provider]
    registry = None
    if not args.frozen:
        registry = TaskBudgetRegistry(run_state=state, tasks_root=output / 'tasks',
                                     max_task_budget_usd=args.budget_usd, task_request_limit=args.request_limit)
        args.control_token = token_hex(32)
        control = create_control_server('127.0.0.1', 0, registry, control_token=args.control_token)
        args.control_endpoint = f'http://127.0.0.1:{control.server_port}'
        servers.append(control)
    gate = create_server('127.0.0.1', 0, upstream, state,
                         state_selector=registry.state_for if registry else None)
    servers.append(gate)
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    prepare(args, output, f'http://127.0.0.1:{gate.server_port}/v1')
    env = {**os.environ, 'DSH_HOME': str(Path(cfg['state_root'])/'web-dsh') if args.scenario=='file-management' and cfg.get('adapter')=='file_operations_v2' else str(output/'dsh'), 'SSS_WEB_POLICY': str(output / 'policy.json'),
           'DEEPSEEK_API_KEY': os.environ['DEEPSEEK_API_KEY'] if args.real_model else 'sss-mock-only',
           'DEEPSEEK_BASE_URL': f'http://127.0.0.1:{gate.server_port}/v1',
           'SSS_ONLINE_MOTIF_MANIFEST': '', 'SSS_ONLINE_MOTIF_TASK': ''}
    log = (output / 'startup.log').open('w')
    process = subprocess.Popen(['node', str(ROOT / 'node_modules/@deepseek-ai/dsh/lib/bin.js'),
        '--profile', 'web', '--patch', str(output / 'host.patch.yml'),
        '--host', '127.0.0.1', '--port', str(args.port), '--no-open'],
        cwd=output / 'work', env=env, stdout=log, stderr=subprocess.STDOUT)
    proc = Path(f'/proc/{os.getpid()}/stat')
    ticks = proc.read_text().rsplit(')', 1)[1].split()[19] if proc.exists() else None
    save(output / 'process.json', {'launcher_pid': os.getpid(), 'harness_pid': process.pid,
                                  'launcher_start_ticks': ticks, 'port': args.port})
    def stop(_signum, _frame):
        if process.poll() is None: process.terminate()
    for number in (signal.SIGTERM, signal.SIGINT): signal.signal(number, stop)
    def metrics():
        audit = [json.loads(line) for line in (output / 'motif-audit.jsonl').read_text().splitlines()]
        if registry:
            for file in (output / 'tasks').glob('*/motif-audit.jsonl'):
                audit.extend(json.loads(line) for line in file.read_text().splitlines())
        save(output / 'metrics.json', {'mock_requests': len(handler.calls),
            'embedding_calls': handler.embedding_calls, 'reserved_upper_usd': state.reserved_usd,
            'paid_calls': state.request_count if args.real_model else 0,
            'provider_mode': 'real' if args.real_model else 'mock', 'provider_failures': handler.failures, 'harness_exit_code': process.poll(),
            'gate_requests': state.request_count,
            'shadow_candidates': sum(row.get('kind') == 'shadow_candidate' for row in audit),
            'motif_attempts': sum(row.get('kind') == 'motif_bypass_attempt' for row in audit),
            'verified_skips': sum(row.get('kind') == 'model_request_skipped_verified' for row in audit)})
        if handler.calls:
            snapshot = json.loads((output / 'effective-config.json').read_text())
            first = handler.calls[0]
            snapshot['observed_model_request'] = {key: first.get(key) for key in ('model', 'thinking', 'max_tokens')}
            snapshot['observed_tools_order'] = [row['function']['name'] for row in first['tools']]
            snapshot['observed_tools_sha256'] = hashlib.sha256(json.dumps(first['tools'], sort_keys=True).encode()).hexdigest()
            save(output / 'effective-config.json', snapshot)
    print('DeepSeek Harless Web：' + ('真实 DeepSeek；任务须预览并确认预算。' if args.real_model else '模拟模型，实际费用为 0。'), flush=True)
    print('私有输出目录：' + str(output), flush=True)
    try:
        for _ in range(300):
            if process.poll() is not None: break
            text = (output / 'startup.log').read_text()
            match = re.search(r'http://127\.0\.0\.1:' + str(args.port) + r'/\?token=[^\s]+', text)
            if match:
                (output / 'access-url.txt').write_text(match.group(0) + '\n'); (output / 'access-url.txt').chmod(0o600)
                print('官方 Web 已启动；认证地址仅保存在 access-url.txt。' + ('冻结题面见 prompt.md。' if args.frozen else '认证后访问 /tasks 提交动态任务。'), flush=True)
                break
            time.sleep(0.1)
        if not (output / 'access-url.txt').exists(): raise RuntimeError('Web startup failed; inspect private startup.log')
        if args.scenario=='file-management' and args.real_model:
            from src.adapters.continuous_rsi import load_config,launch_worker
            cfg=load_config(args.rsi_config)
            if cfg['mode']=='learn' and cfg['auto_worker']:save(output/'resumed-worker.json',launch_worker(args.rsi_config,cfg['state_root']))
        while process.poll() is None:
            metrics()
            time.sleep(0.25)
    finally:
        stop(None, None)
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
        for server in servers: server.shutdown(); server.server_close()
        if args.real_model: provider.server_close()
        log.close()
        state_path = output / 'task-state.json'
        if state_path.exists():
            final_state = json.loads(state_path.read_text())
            if final_state['status'] in ('ready', 'running'):
                final_state.update(status='cancelled', failure='server_stopped')
                save(state_path, final_state)
        if registry:
            for task_file in (output / 'tasks').glob('*/task-state.json'):
                task_state = json.loads(task_file.read_text())
                task_state['stats'].update(registry.stats(task_state['session_id']))
                if task_state['status'] in ('awaiting_confirmation', 'running'):
                    task_state.update(status='interrupted' if args.scenario=='file-management' and cfg.get('adapter')=='file_operations_v2' else 'cancelled', failure='server_stopped')
                save(task_file, task_state)
        events = [json.loads(line) for line in (output / 'events.jsonl').read_text().splitlines()]
        metrics()
        save(output / 'mock-requests.json', handler.calls)
        answers = [event for event in events if event.get('type') == 'assistant/message']
        save(output / 'answer.json', answers[-1] if answers else None)
        text = '\n'.join(part['text'] for part in answers[-1]['data']['message']['content'] if part['type'] == 'text') if answers else ''
        (output / 'answer.md').write_text(text); (output / 'answer.md').chmod(0o600)
        if persistent_lock:persistent_lock.__exit__(None,None,None)
    if process.returncode not in (0, -signal.SIGTERM): sys.exit(1)


if __name__ == '__main__': main()
