"""Free real MCP/Harness acceptance of changed-only work; no scientific interpretation."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer
from uuid import uuid4
from pdf_tools import ROOT, digest, inventory, save_private
from pdf_incremental_tools import IncrementalScene
from runpy import run_path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from mcp import Client, StdioServerParameters
from src.adapters.deepseek_cost_gate import State, create_server
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard
from src.adapters.scenario import prepare_scenario

PREFIX = 'mcp__literature_pdf__'


def protocol_action(values):
    plan = next((v for v in values if 'work' in v and 'retained_claim_ids' in v), None)
    if plan is None: return PREFIX + 'read_update_plan', {}
    for w in plan['work']:
        pid = w['paper_id']
        if not any(v.get('paper_id') == pid and 'coverage' in v for v in values):
            return PREFIX + 'prepare_pdf', {'paper_id': pid}
        pin = next((v for v in values if v.get('paper_id') == pid and 'source_id' in v), None)
        if pin is None: return PREFIX + 'pin_pdf_context', {'paper_id': pid, 'page': '1'}
        if not any(v.get('paper_id') == pid and 'text' in v for v in values):
            return PREFIX + 'read_pinned_pdf_context', {'source_id': pin['source_id']}
    receipt = next((v for v in values if 'retained_field_count' in v and 'artifact_sha256' in v), None)
    if receipt: return None, {'status': receipt['status'], 'scope': 'protocol_only'}
    papers = [{'paper_id': w['paper_id'], 'fields': [{'name': name, 'verdict': 'not_extracted',
               'reason': 'Protocol provider does not assess scientific meaning.',
               'statement': '协议检查未执行论文理解，此字段尚未提取。', 'citations': []}
               for name in w['fields_to_review']]} for w in plan['work']]
    return PREFIX + 'submit_incremental_update', {'update': {'papers': papers,
        'synthesis_hypothesis': '协议检查不提供科研判断，后续需要独立语义审阅。' if plan['synthesis_requires_review'] else ''}}


async def mcp_check(env, expected):
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / 'pdf_incremental_tools.py')], cwd=ROOT, env=env)
    async with Client(params) as client:
        tools = (await client.list_tools()).tools
        assert {PREFIX + t.name for t in tools} == set(expected)
        assert all(t.annotations.read_only_hint for t in tools)
        result = await client.call_tool('read_update_plan', {})
        assert not result.is_error
        plan = json.loads(result.content[0].text)
        bad = await client.call_tool('read_pinned_pdf_context', {'source_id': 'unissued'})
        assert bad.is_error
        bib = await client.call_tool('preview_bibliography', {'bibtex': '@article{a,title={A {Nested} Title},author={Smith},year={2024}}'})
        assert not bib.is_error
        return {'tool_count': len(tools), 'unknown_source_rejected': True,
                'retained_field_count': len(plan['retained_claim_ids']),
                'fields_to_review': sum(len(w['fields_to_review']) for w in plan['work']),
                'offline_bibliography_tool_checked': True}


def check(dependencies, directory):
    runner = run_path(str(HERE / 'run-incremental.py'))
    graph = json.loads(Path(dependencies).read_text())['graph']
    task = {'schema_version': 1, 'question': graph['task']['question'], 'sources': inventory(directory)}
    output = ROOT / '.local/literature-notes/incremental-checks' / uuid4().hex
    save_private(output / 'revoked-claims.json', {'revoked_claim_ids': []})
    scene = IncrementalScene(dependencies, directory, task, output, revoked_path=output / 'revoked-claims.json')
    plan = scene.read_update_plan()
    if not 1 <= len(plan['work']) <= 3:
        raise ValueError('protocol check requires 1–3 affected papers; unchanged reuse uses the normal launcher')
    save_private(output / 'task.json', task)
    scenario = json.loads((HERE / 'pdf-incremental-scenario.json').read_text())
    scenario['prompt'] = str(HERE / 'pdf-incremental-task.md'); save_private(output / 'scenario.json', scenario)
    env = {'SSS_PDF_ROOT': str(Path(directory).resolve()), 'SSS_PDF_TASK_FILE': str(output / 'task.json'),
           'SSS_PDF_DEPENDENCIES': str(Path(dependencies).resolve()), 'SSS_PDF_INCREMENTAL_OUTPUT': str(output),
           'SSS_PDF_REVOKED': str(output / 'revoked-claims.json'), 'SSS_PDF_SCRIPT_READ': '0'}
    prepared = prepare_scenario(output / 'scenario.json')
    report = {'status': 'passed', 'scope': 'real_pdf_protocol_only', 'paid_api_requests': 0,
              'mcp': asyncio.run(mcp_check(env, prepared['allowed_tools']))}
    protocol = runner['load_entry']('incremental_protocol_provider', 'check-pdf.py')
    protocol.protocol_action = protocol_action
    handler = type('IncrementalProvider', (protocol.Provider,), {'calls': [], 'failures': []})
    state = State(cap_usd=0.25, output_cap=4000, record=output / 'cost-ledger.jsonl')
    provider = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    gate = create_server('127.0.0.1', 0, f'http://127.0.0.1:{provider.server_port}', state)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (provider, gate)]
    for t in threads: t.start()
    try:
        child_env = {**env, 'DSH_HOME': str(output / 'dsh'), 'DEEPSEEK_API_KEY': 'loopback-protocol-only',
                     'DEEPSEEK_BASE_URL': f'http://127.0.0.1:{gate.server_port}/v1',
                     'SSS_SCENARIO_TOOLS': json.dumps(prepared['allowed_tools']),
                     'SSS_ONLINE_MOTIF_MANIFEST': '', 'SSS_ONLINE_MOTIF_TASK': '',
                     'SSS_BUDGET_GATE_ACTIVE': '1', 'SSS_BUDGET_CAP_USD': '0.25', 'SSS_BUDGET_LEDGER': str(state.record)}
        guard = NativeBudgetGuard(max_model_requests=20, max_observed_input_tokens=150000)
        with create_harness(root=ROOT, patches=(prepared['patch'],), env=child_env, cwd=str(output),
                            runtime_cwd=str(output), provider='deepseek-official', model='deepseek-flash',
                            max_tokens=4000, request_timeout_seconds=30) as client:
            result = client.run(prepared['prompt'], session_id='incremental-check-' + uuid4().hex,
                                on_notification=guard.on_notification)
        assert result.finish_reason == 'completed' and not handler.failures
        events = output / 'agent-events.jsonl'
        events.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in result.events)); events.chmod(0o600)
        receipt = runner['collect_incremental'](output, scene)
        assert receipt and receipt['gap_count'] == sum(len(w['fields_to_review']) for w in plan['work'])
        assert len(handler.calls) == state.request_count
        assert all({t['function']['name'] for t in b['tools']} == set(prepared['allowed_tools']) for b in handler.calls)
        report['harness'] = {'model_requests': state.request_count,
                             'budget_ledger_rows': len(state.record.read_text().splitlines()),
                             'receipt': receipt, 'usage': 'synthetic; not scientific quality or paid savings'}
        report['notes'] = runner['save_notes'](scene)
    finally:
        for s in (gate, provider): s.shutdown(); s.server_close()
        for t in threads: t.join(timeout=5)
    save_private(output / 'acceptance.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dependencies', type=Path, required=True)
    parser.add_argument('--papers-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.dependencies, args.papers_dir), ensure_ascii=False, indent=2))
