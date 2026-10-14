"""Free actual Harness/MCP dispatch; protocol fixture is not a learned library."""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import sys
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from uuid import uuid4
from pdf_tools import ROOT, digest, save_private
from pdf_dependencies import private_file
from pdf_repair_tools import RepairScene
from terminal_entry import TOOL, entry_task, execution_version
sys.path.insert(0, str(ROOT))
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.deepseek_cost_gate import State, create_server
from src.adapters.native_budget import NativeBudgetGuard

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def check(run, decision_path, policy_path=None, tamper=False):
    out = ROOT / '.local/terminal-checks' / uuid4().hex; out.mkdir(parents=True, mode=0o700)
    scene = RepairScene(run, out / 'delivery')
    learner = load('terminal_schema_probe', HERE / 'learn-terminal.py')
    actual = asyncio.run(learner.schema(scene))
    if policy_path:
        policy = json.loads(private_file(policy_path).read_text())
    else:
        a = {'kind': 'task_terminal_receipt', 'status': 'trace_validated_read_only', 'schema_sha256': digest(actual),
            'source_task_fingerprints': ['fixture-one', 'fixture-two'], 'validation_task_fingerprint': 'fixture-heldout', 'tools': [TOOL],
            'terminal': {'kind': 'receipt_then_finish', 'receipt_contract': 'claim_repair_v1', 'tool': TOOL,
                'statuses': ['preview'], 'max_targets': 100, 'output': 'verified_status_json', 'provider_requests': 0}}
        a['certified_digest'] = digest(a)
        policy = {'schema_version': 1, 'format': 'sss-terminal-receipt-v1', 'source_library_digest': 'a' * 64,
            'execution_version_sha256': execution_version(), 'artifact': a, 'fixture_only_not_learned': True}
        policy['policy_digest'] = digest(policy)
    save_private(out / 'policy.json', policy)
    prompt = '复核这一条已选事实，提交后简短返回收据状态。此为免费协议诊断。'
    task = {**entry_task(scene, out.name), 'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()}
    save_private(out / 'task.json', task)
    (out / 'prompt.md').write_text(prompt); (out / 'prompt.md').chmod(0o600)
    config = json.loads((HERE / 'pdf-repair-scenario.json').read_text()); config['prompt'] = str(out / 'prompt.md')
    if tamper:
        proxy = out / 'fault-tools.py'
        proxy.write_text("import sys,os,json\nfrom pathlib import Path\nsys.path.insert(0," + repr(str(HERE)) + ")\n"
            "from pdf_repair_tools import RepairScene,make_server\nfrom pdf_tools import save_private\n"
            "scene=RepairScene(Path(os.environ['SSS_PDF_REPAIR_RUN']),Path(os.environ['SSS_PDF_REPAIR_OUTPUT']))\n"
            "original=scene.submit_claim_repair\ndef faulty(decisions,synthesis_hypothesis):\n"
            " r=original(decisions,synthesis_hypothesis)\n if r.get('artifact'):\n"
            "  p=Path(r['artifact']);v=json.loads(p.read_text());v['fault_test_corruption']=True;save_private(p,v)\n"
            " return r\nscene.submit_claim_repair=faulty\nmake_server(scene).run(transport='stdio')\n")
        proxy.chmod(0o600)
        config['servers'][0]['args'] = [str(proxy)]
    save_private(out / 'scenario.json', config)
    prepared = prepare_scenario(out / 'scenario.json', entry_motif=True)
    decision = json.loads(private_file(decision_path).read_text())
    fake = load('terminal_mock', ROOT / 'scripts/motif-example.py')
    def action(obs, _case):
        if not obs: return 'mcp__literature_pdf_repair__read_claim_repair_packet', {'claim_id': scene.targets[0]}
        if not any(v.get('artifact') for v in obs): return TOOL, {'decisions': [decision], 'synthesis_hypothesis': '协议诊断假设，未认证科研支持。'}
        return None, {'scope': 'mock-provider-final-fallback'}
    fake.next_fixture_action = action
    handler = fake.provider_handler('terminal-fixture', with_usage=True, request_limit=8)
    provider = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    state = State(cap_usd=1, output_cap=2000, record=out / 'mock-ledger.jsonl', request_limit=8)
    gate = create_server('127.0.0.1', 0, f'http://127.0.0.1:{provider.server_port}', state)
    for s in (provider, gate): threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        with create_harness(root=ROOT, patches=(prepared['patch'],), env={
            'DSH_HOME': str(out / 'dsh'), 'DEEPSEEK_API_KEY': 'mock-no-key', 'DEEPSEEK_BASE_URL': f'http://127.0.0.1:{gate.server_port}/v1',
            'SSS_SCENARIO_TOOLS': json.dumps(prepared['allowed_tools']), 'SSS_SCENARIO_PRESENTATION': 'native',
            'SSS_PDF_REPAIR_RUN': str(run), 'SSS_PDF_REPAIR_OUTPUT': str(scene.output), 'SSS_PDF_SCRIPT_READ': '0',
            'SSS_TERMINAL_MOTIF_POLICY': str(out / 'policy.json'), 'SSS_TERMINAL_MOTIF_TASK': str(out / 'task.json'),
            'SSS_ENTRY_MOTIF_POLICY': '', 'SSS_ENTRY_MOTIF_TASK': '', 'SSS_ONLINE_MOTIF_MANIFEST': '', 'SSS_ONLINE_MOTIF_TASK': '',
            'SSS_BUDGET_GATE_ACTIVE': '1', 'SSS_BUDGET_CAP_USD': '1', 'SSS_BUDGET_LEDGER': str(state.record)},
            cwd=str(out), runtime_cwd=str(out), provider='deepseek-official', model='deepseek-flash',
            max_tokens=2000, request_timeout_seconds=120) as client:
            try:
                result = client.run(prompt, session_id=task['session_id'], on_notification=NativeBudgetGuard(max_model_requests=8, max_observed_input_tokens=None).on_notification)
            except Exception:
                if not tamper: raise
                result = None
        if tamper:
            audit_path = out / '.local/online-motif' / (hashlib.sha256(task['session_id'].encode()).hexdigest() + '.jsonl')
            audits = [json.loads(l) for l in audit_path.read_text().splitlines()]
            save_private(out / 'audits.json', audits)
            assert len(handler.calls) >= 3
            if result:
                save_private(out / 'events.json', result.events)
                assert 'certified_terminal_runtime' not in result.final_response
            assert sum(a['kind'] == 'terminal_model_request_bypassed_verified' for a in audits) == 0
            assert any(a.get('reason') == 'receipt_or_source_unverified' for a in audits)
            report = {'directory': str(out), 'tampered_receipt_rejected': True, 'artifact_delivered': False,
                'mock_provider_requests': len(handler.calls), 'real_api_requests': 0, 'verified_terminal_batches': 0,
                'sdk_finish_reason': result.finish_reason if result else 'exception'}
            save_private(out / 'outcome.json', report); print(json.dumps(report)); return
        save_private(out / 'events.json', result.events)
        audit_path = out / '.local/online-motif' / (hashlib.sha256(task['session_id'].encode()).hexdigest() + '.jsonl')
        audits = [json.loads(l) for l in audit_path.read_text().splitlines()]
        save_private(out / 'audits.json', audits)
        summary = json.loads(result.final_response)
        assert result.finish_reason == 'completed' and summary['producer'] == 'certified_terminal_runtime'
        assert summary['target_count'] == 1 and summary['gap_count'] == 0 and len(handler.calls) == 2
        assert sum(a['kind'] == 'terminal_model_request_bypassed_verified' for a in audits) == 1
        report = {'directory': str(out), 'mock_provider_requests': len(handler.calls), 'real_api_requests': 0,
            'verified_terminal_batches': 1, 'actual_tool_calls': 2, 'artifact_delivered': True,
            'scope': 'protocol fixture only; not training or scientific quality'}
        save_private(out / 'outcome.json', report); print(json.dumps(report))
    finally:
        for s in (provider, gate): s.shutdown(); s.server_close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--run', type=Path, required=True); p.add_argument('--decision', type=Path, required=True)
    p.add_argument('--policy', type=Path); p.add_argument('--tamper-receipt', action='store_true')
    a = p.parse_args(); check(a.run.resolve(), a.decision.resolve(), a.policy.resolve() if a.policy else None, a.tamper_receipt)
