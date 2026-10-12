"""Server-only, trace-derived local proofs; not a full paper quality benchmark."""
from __future__ import annotations
import argparse
from collections import Counter
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading
import time
from uuid import uuid4
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.parameter_motif_compiler import compile_parameter_library
from src.adapters.native_motif_compiler import digest
from src.adapters.deepseek_cost_gate import State, create_server
from src.adapters.harness_runtime import create_harness

spec = importlib.util.spec_from_file_location('reference', ROOT / 'scripts/paper-reference-experiment.py')
reference = importlib.util.module_from_spec(spec); spec.loader.exec_module(reference)
sha, save = reference.sha, reference.save
ORIGIN = 'paper-reference-five-native-two-motif-20261010-v5'
EXPERIMENT = 'parameter-motif-proof-20261010-v1'
OUTPUT_CAP = 4096


def prepare(exp):
    source = ROOT / '.local/paper-reference' / ORIGIN
    library = compile_parameter_library(source)
    save(exp / 'library.json', library)
    # Prototype/schema choices are frozen from training; heldout is not a selector.
    request = next((source / 'runs/baseline-01/requests').glob('*.json'))
    tools = json.loads(request.read_text())['tools']
    contracts = {'order': [t['function']['name'] for t in tools],
                 'hashes': {t['function']['name']: digest(t['function']['parameters']) for t in tools}}
    save(exp / 'contracts.json', contracts)
    summary = [{'motif_id': m['motif_id'], 'tool': m['prototype']['tool'],
                'training_instances': len(m['training_witnesses']),
                'training_runs': sorted({w['run_id'] for w in m['training_witnesses']}),
                'heldout_instances': len(m['heldout_witnesses']),
                'heldout_runs': sorted({w['run_id'] for w in m['heldout_witnesses']}),
                'historical_parallel_batches': len(m['parallel_witnesses'])} for m in library['motifs']]
    save(exp / 'compile-summary.json', {'motifs': summary, 'historical_requests_saved': None,
         'scope': 'explicit_input_continuation_proof', 'selection_not_learned': True})
    return library, contracts


def inputs(exp, work, case, library, variant):
    origin = ROOT / '.local/paper-reference' / ORIGIN
    shutil.copyfile(origin / 'runs/baseline-01/work/submission.zip', work / 'submission.zip')
    # Vary paths and item order; keep source bytes and selected input set fixed.
    nested = 'inputs/' + variant
    with zipfile.ZipFile(work / 'submission.zip') as z:
        for name in ['main.tex', 'extended_abstract.tex', 'references.bib']:
            entry = next(n for n in z.namelist() if n == name or n.endswith('/' + name))
            p = work / nested / name; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(z.read(entry)); p.chmod(0o600)
    motif = next(m for m in library['motifs'] if m['prototype']['tool'] == ('read' if case == 'read' else 'web_fetch'))
    sources = [{'path': nested + '/' + n, 'sha256': sha(work / nested / n)}
               for n in ['main.tex', 'extended_abstract.tex', 'references.bib']]
    if case == 'read':
        items = [{'item_id': n, 'file_path': nested + '/' + n, 'sha256': sha(work / nested / n)}
                 for n in ['main.tex', 'extended_abstract.tex']]
    else:
        bib = (work / nested / 'references.bib').read_text()
        ids = []
        for w in motif['training_witnesses']:
            value = w['dependency']['id']
            if value in bib and value not in ids: ids.append(value)
        if len(ids) < 2: raise ValueError('two source-witnessed training identifiers required')
        items = [{'item_id': i, 'id': i, 'source_path': nested + '/references.bib'} for i in ids[:2]]
    if variant == 'renamed': items.reverse()
    binding = {'schema_version': 1, 'library_digest': library['manifest_digest'],
               'motif_id': motif['motif_id'], 'operation': 'read_files' if case == 'read' else 'fetch_arxiv_pages',
               'items': items, 'sources': sources,
               'scope': 'collect selected evidence; scientific interpretation remains with the model'}
    save(work / 'binding.json', binding)
    return binding


def run(exp, library, contracts, case, mode, cap, suffix='', scenario=None, library_path=None):
    library_path = Path(library_path) if library_path is not None else exp / 'library.json'
    label = case + '-' + mode + suffix
    out = exp / 'runs' / label
    if out.exists(): raise ValueError('preserve existing run; no overwrite or budget reset')
    work = out / 'work'; work.mkdir(parents=True, mode=0o700)
    if json.loads(library_path.read_text()) != library: raise ValueError('selected library changed before task')
    shutil.copyfile(library_path, out / 'library-snapshot.json')
    selected_library_path = library_path
    library_path = out / 'library-snapshot.json'
    binding = inputs(exp, work, case, library, 'renamed') if scenario is None else scenario.prepare(work, library)
    prompt = '''这是局部证据收集测试，不是完整论文评审。首先用原生 read 工具读取当前工作区的 binding.json。
对 operation=read_files，用原生 read 工具完整读取 items 列出的每个 file_path；
对 operation=fetch_arxiv_pages，用原生 web_fetch 工具获取每个 id 对应的 https://arxiv.org/abs/{id} 页面。
items 中的相对路径均相对当前工作区。必须覆盖全部 item，独立读取或查询可以并行。
只使用实际工具结果，不写入文件、不启动子 Agent、不重复查询已成功的 item。
最后用中文简短列出每个 item 的关键证据与获取状态。文件证据给首个文档声明或标题；网页给页面论文标题。
获取失败时如实说明，不能用记忆补齐。不判断会议合规、文献著录正确性或科研结论。'''
    if scenario is not None: prompt = scenario.prompt
    session = 'parameter-proof-' + uuid4().hex
    save(out / 'prompt.md', prompt)
    save(out / 'native.patch.yml', reference.POLICY)
    patches = [str(out / 'native.patch.yml')]
    env = {'DSH_HOME': str(out / 'dsh'), 'DSH_TELEMETRY_MODE': 'none',
           'DSH_MAX_TOKENS_AS_SUCCESS': 'false', 'DSH_PERMISSION_MODE': 'danger-full-access',
           'SSS_ONLINE_MOTIF_MANIFEST': '', 'SSS_NATIVE_MOTIF_MANIFEST': ''}
    if mode != 'baseline':
        config = {'library_path': str(library_path), 'work': str(work), 'session_id': session,
                  'binding_path': 'binding.json' if scenario is None else 'selection.json',
                  'binding_hash': sha(work / 'binding.json') if scenario is None else None,
                  'schema_hashes': contracts['hashes'], 'tool_order': contracts['order'],
                  'mode': mode, 'prompt_sha256': digest(prompt)}
        if scenario is not None:
            config.update(catalog_path='catalog.json', catalog_hash=sha(work / 'catalog.json'))
        # Lifecycle gate uses SHA-256 of literal prompt text, not JSON encoding.
        import hashlib
        config['prompt_sha256'] = hashlib.sha256(prompt.encode()).hexdigest()
        save(out / 'parameter-config.json', config)
        save(out / 'motif.patch.yml', '- insert:\n    - id: parameter-motif\n      name: ' + json.dumps((ROOT / 'src/adapters/dsh_parameter_motif.ts').as_uri()) + '\n')
        patches.append(str(out / 'motif.patch.yml'))
        env['SSS_PARAMETER_CONFIG'] = str(out / 'parameter-config.json')
    rows, prior, ledgers = reference.budget.account(exp)
    if prior >= cap: raise ValueError('cumulative authorized budget exhausted')
    class Recorded(State):
        def book(self, body):
            row = super().book(body)
            if row: save(out / f'requests/{row[0]:04d}.json', body.decode())
            return row
    state = Recorded(cap_usd=cap, output_cap=OUTPUT_CAP, request_limit=None, record=out / 'cost-ledger.jsonl')
    state.request_count = len(rows); state.reserved_usd = prior
    gate = create_server('127.0.0.1', 0, 'https://api.deepseek.com', state)
    thread = threading.Thread(target=gate.serve_forever, daemon=True); thread.start()
    env.update(DEEPSEEK_BASE_URL=f'http://127.0.0.1:{gate.server_port}/v1', SSS_BUDGET_GATE_ACTIVE='1',
               SSS_BUDGET_CAP_USD=str(cap), SSS_BUDGET_LEDGER=str(out / 'cost-ledger.jsonl'))
    save(out / 'manifest.json', {'model': 'deepseek-flash', 'reasoning_effort': 'off', 'mode': mode,
         'case': case, 'session_id': session, 'prompt_sha256': __import__('hashlib').sha256(prompt.encode()).hexdigest(),
         'output_cap': OUTPUT_CAP, 'request_limit': None, 'compression': False,
         'sandbox': 'danger-full-access', 'approval': 'never',
         'cumulative_cap_usd': cap, 'prior_usd': prior,
         'library_sha256': sha(library_path), 'binding_sha256': sha(work / 'binding.json') if scenario is None else None,
         'library_manifest_digest': library['manifest_digest'], 'library_source_path': str(selected_library_path.relative_to(ROOT)),
         'catalog_sha256': sha(work / 'catalog.json') if scenario is not None else None,
         'input_source_sha256': sha(work / 'submission.zip'), 'tool_order': contracts['order'],
         'schema_hashes': contracts['hashes'], 'python': platform.python_version(),
         'node': subprocess.check_output(['node', '--version'], text=True).strip(),
         'dsh_version': json.loads((ROOT / 'node_modules/@deepseek-ai/dsh/package.json').read_text())['version'],
         'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
         'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)),
         'patch_sha256': {str(Path(p).relative_to(ROOT)): sha(p) for p in patches},
         'code_sha256': {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT / 'src/adapters/parameter_motif_compiler.py', ROOT / 'src/adapters/dsh_parameter_motif.ts', ROOT / 'src/adapters/dsh_online_motif.mjs', ROOT / 'src/adapters/harness_runtime.py', ROOT / 'src/adapters/deepseek_cost_gate.py', ROOT / 'src/motif_core/online_skill_runtime.mjs', ROOT / 'package-lock.json', *([Path(scenario.__file__), ROOT / 'scenarios/paper-submission/checks.py', ROOT / 'schemas/parameter-motif-selection.schema.json'] if scenario is not None else [])]},
         'scope': 'selected_input_probe_not_full_audit' if scenario is None else 'cited_arxiv_version_triage', 'quality_review': 'not_reviewed'})
    calls = []
    def observe(n):
        if n.method == 'session.event' and isinstance(n.payload.get('event'), dict):
            e = n.payload['event']
            with (out / 'session-events.jsonl').open('a') as f:
                f.write(json.dumps({'session_id': n.payload.get('sessionId'), 'event': e}, ensure_ascii=False) + '\n')
            if e['type'] == 'tool/call': calls.append(e['data']['name'])
    start = time.monotonic()
    print(json.dumps({'starting': label, 'prior_usd': prior, 'cap_usd': cap}), flush=True)
    try:
        with create_harness(root=ROOT, patches=tuple(patches), env=env, provider='deepseek-official',
                            model='deepseek-flash', max_tokens=OUTPUT_CAP, cwd=str(work), runtime_cwd=str(work),
                            request_timeout_seconds=600) as h:
            result = h.run(prompt, session_id=session, on_notification=observe)
        save(out / 'answer.md', result.final_response)
        status = result.finish_reason
    except Exception as e:
        save(out / 'error-private.txt', repr(e)); status = 'error'
    finally:
        gate.shutdown(); gate.server_close(); thread.join(timeout=5)
    audits = [json.loads(x) for x in (out / 'work/../parameter-motif/audit.jsonl').read_text().split('\n') if x.strip()] if (out / 'parameter-motif/audit.jsonl').exists() else []
    metrics = {'status': status, 'actual_requests': state.request_count - len(rows),
               'new_estimated_usd': state.reserved_usd - prior, 'cumulative_estimated_usd': state.reserved_usd,
               'elapsed_seconds': time.monotonic() - start, 'tool_calls': dict(Counter(calls)),
               'verified_skips': sum(r['kind'] == 'model_request_skipped_verified' for r in audits),
               'unverified_bypasses': sum(r['kind'] == 'bypass_result_unverified' for r in audits),
               'shadow_matches': sum(r['kind'] == 'shadow_result' and r.get('verified') for r in audits),
               'selected_batches': sum(r['kind'] == 'selection_accepted' for r in audits),
               'scope': 'local_continuation_only' if scenario is None else 'cited_arxiv_version_triage', 'full_report_quality': 'not_evaluated'}
    save(out / 'metrics.json', metrics)
    print(json.dumps({'finished': label, **metrics}), flush=True)
    return metrics


def main():
    p = argparse.ArgumentParser(); p.add_argument('--phase', choices=['compile', 'preview', 'run'], default='preview')
    p.add_argument('--call-model', action='store_true')
    p.add_argument('--case', choices=['read', 'query'])
    p.add_argument('--mode', choices=['baseline', 'shadow', 'execute'])
    p.add_argument('--run-suffix', default='')
    args = p.parse_args()
    import re
    if args.run_suffix and not re.fullmatch(r'-[a-z0-9-]{1,32}', args.run_suffix): p.error('invalid run suffix')
    exp = ROOT / '.local/paper-reference' / EXPERIMENT; exp.mkdir(parents=True, exist_ok=True)
    if args.phase == 'compile':
        if (exp / 'library.json').exists():
            print((exp / 'compile-summary.json').read_text()); return
        library, _ = prepare(exp); print((exp / 'compile-summary.json').read_text()); return
    rows, prior, _ = reference.budget.account(exp)
    if args.phase == 'preview':
        frozen_budget = exp / 'effective-budget.json'
        cap = json.loads(frozen_budget.read_text())['cap_usd'] if frozen_budget.exists() else min(5, prior + 1)
        print(json.dumps({'prior_usd': prior, 'cumulative_cap_usd': cap, 'paid_enabled': False,
                          'cases': ['read', 'query'], 'modes': ['baseline', 'shadow', 'execute'],
                          'model': 'deepseek-flash', 'reasoning_effort': 'off', 'output_cap': OUTPUT_CAP, 'request_limit': None})); return
    if not args.call_model or not os.environ.get('DEEPSEEK_API_KEY'): raise ValueError('explicit server API authorization/config required')
    with (ROOT / '.local/paper-motif/.budget.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        library = json.loads((exp / 'library.json').read_text()); contracts = json.loads((exp / 'contracts.json').read_text())
        frozen_budget = exp / 'effective-budget.json'
        if frozen_budget.exists():
            cap = json.loads(frozen_budget.read_text())['cap_usd']
        else:
            cap = min(5, prior + 1)
            save(frozen_budget, {'prior_usd': prior, 'cap_usd': cap, 'incremental_cap_usd': 1})
        for case in [args.case] if args.case else ['read', 'query']:
            for mode in [args.mode] if args.mode else ['baseline', 'shadow', 'execute']:
                if mode == 'execute':
                    shadow_run = exp / 'runs' / (case + '-shadow' + args.run_suffix)
                    if not shadow_run.exists(): shadow_run = exp / 'runs' / (case + '-shadow')
                    shadow = json.loads((shadow_run / 'metrics.json').read_text())
                    if shadow['shadow_matches'] != 2: raise ValueError('successful shadow required before execute')
                metrics = run(exp, library, contracts, case, mode, cap, args.run_suffix)
                if metrics['status'] != 'completed': raise ValueError('incomplete proof; inspect before retry')
                if mode == 'shadow' and metrics['shadow_matches'] != 2:
                    raise ValueError('shadow did not verify every selected item; do not execute')

if __name__ == '__main__': main()
