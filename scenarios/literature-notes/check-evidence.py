"""Free actual-PDF/MCP/Harness evidence preparation acceptance; no cloud key."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer
from uuid import uuid4

from pdf_tools import DEFAULT_QUESTION, ROOT, digest, inventory, save_private
from pdf_evidence_tools import PREFIX

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from mcp import Client, StdioServerParameters
from src.adapters.deepseek_cost_gate import State, create_server
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard
from src.adapters.scenario import prepare_scenario
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.tool_schema_contracts import bind_mcp_descriptions

import importlib.util


def module(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def protocol_action(values, *, window_limit=6, frozen_plan=None):
    """Fixed page fixture validates dispatch, not model page selection or science."""
    selected = next((v for v in values if 'papers' in v and 'page_numbering' in v), None)
    if selected is None:
        return PREFIX + 'list_pdfs', {}
    for row in ([] if frozen_plan is not None else selected['papers']):
        if not any(v.get('paper_id') == row['paper_id'] and 'coverage' in v for v in values):
            return PREFIX + 'prepare_pdf', {'paper_id': row['paper_id']}
    ready = next((v for v in values if v.get('status') == 'packet_ready'
                  or v.get('script_packet', {}).get('status') == 'packet_ready'), None)
    if ready:
        return None, {'status': 'packet_ready', 'scope': 'protocol_only'}
    extraction = next((v for v in values if v.get('status') == 'extracted'), None)
    if extraction is None:
        registered = next((v for v in values if v.get('status') == 'plan_approved'), None)
        if registered:
            return PREFIX + 'extract_evidence_windows', {'plan': registered['plan_id']}
        plan = {'schema_version': 1, 'task_sha256': selected['task_sha256'],
                'allow_deterministic_continuation': True,
                'windows': [{'paper_id': row['paper_id'], 'page': '1', 'start': 0, 'length': 1200,
                             'purpose': 'Protocol-only first-page fixture; not a relevance decision.'}
                            for row in selected['papers'][:window_limit]]}
        return PREFIX + 'register_reading_plan', {'plan': json.dumps(frozen_plan or plan)}
    verified = next((v for v in values if v.get('status') == 'verified'), None)
    if verified is None:
        return PREFIX + 'verify_evidence_windows', {'extraction_id': extraction['extraction_id']}
    return PREFIX + 'build_evidence_packet', {'verification_id': verified['verification_id']}


async def check_mcp(env, output):
    async with Client(StdioServerParameters(command=sys.executable, args=[str(HERE / 'pdf_evidence_tools.py')],
                                            env=env, cwd=ROOT)) as client:
        tools = (await client.list_tools()).tools
        schemas = [{**tool.model_dump(mode='json', by_alias=True), 'name': PREFIX + tool.name} for tool in tools]
        contracts = parse_tool_contracts(json.loads((HERE / 'pdf-evidence-contracts.json').read_text()))
        bound = bind_mcp_descriptions(contracts, schemas)
        assert set(bound) == set(json.loads((HERE / 'pdf-evidence-scenario.json').read_text())['allowed_tools'])
        assert all(tool.annotations.read_only_hint is True for tool in tools)
        result = await client.call_tool('verify_evidence_windows', {'extraction_id': 'extraction-invented'})
        assert result.is_error
    save_private(output / 'mcp-schemas.json', schemas)
    return {'schema_checked': True, 'unknown_receipt_rejected': True, 'tool_count': len(schemas)}


def check(directory, *, manifest=None, frozen_plan=None, question=DEFAULT_QUESTION):
    runner = module('run-evidence.py', 'free_evidence_runner')
    provider_module = module('check-pdf.py', 'free_evidence_provider')
    # Reuse the existing SSE fixture transport, replace only its diagnostic policy.
    provider_module.protocol_action = lambda values: protocol_action(values, frozen_plan=frozen_plan)
    output = ROOT / '.local/literature-notes' / ('evidence-check-' + uuid4().hex)
    output.mkdir(mode=0o700, parents=True)
    original = inventory(directory)
    rows, packets = [], []
    approved = bool(manifest and any(a.get('continuation_policy_digest') for a in
                    json.loads(Path(manifest).read_text())['artifacts']))
    execute_arm = 'execute_approved_plan' if approved else 'execute_gate_unavailable'
    for arm in (('baseline', 'script', execute_arm) if manifest else ('baseline', 'script')):
        task_dir, env = runner.prepare_task(directory, question, script_chain=arm == 'script',
                                           frozen_plan=frozen_plan)
        mcp = asyncio.run(check_mcp(env, task_dir))
        prepared = prepare_scenario(task_dir / 'scenario.json')
        handler = type('EvidenceProtocolProvider', (provider_module.Provider,), {'calls': [], 'failures': []})
        state = State(cap_usd=0.25, output_cap=2000, record=task_dir / 'cost-ledger.jsonl')
        guard = NativeBudgetGuard(max_model_requests=20, max_observed_input_tokens=150000)
        provider = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        gate = create_server('127.0.0.1', 0, f'http://127.0.0.1:{provider.server_port}', state)
        workers = [threading.Thread(target=server.serve_forever, daemon=True) for server in (provider, gate)]
        for worker in workers:
            worker.start()
        embedding_server = embedding_worker = None
        try:
            env.update(DSH_HOME=str(task_dir / 'dsh'), DEEPSEEK_API_KEY='local-protocol-only',
                       DEEPSEEK_BASE_URL=f'http://127.0.0.1:{gate.server_port}/v1',
                       SSS_SCENARIO_TOOLS=json.dumps(prepared['allowed_tools']),
                       SSS_ONLINE_MOTIF_MANIFEST='', SSS_ONLINE_MOTIF_TASK='',
                       SSS_BUDGET_GATE_ACTIVE='1', SSS_BUDGET_CAP_USD='0.25', SSS_BUDGET_LEDGER=str(state.record))
            patches = [prepared['patch']]
            session_id = 'evidence-check-' + uuid4().hex
            if arm == execute_arm and manifest:
                snapshot = json.loads((task_dir / 'input-snapshot.json').read_text())
                save_private(task_dir / 'motif-task.json', {'schema_version': 1, 'task_id': task_dir.name,
                    'session_id': session_id, 'intent': question, 'input_version': digest(snapshot['task']),
                    'bindings': {}, 'source_versions': {PREFIX + name: [snapshot['execution_version_sha256']]
                     for name in ('extract_evidence_windows', 'verify_evidence_windows', 'build_evidence_packet')},
                    **({'continuation_policy_digests': [digest(module('pdf_evidence_tools.py',
                       'evidence_check_policy').continuation_policy())]} if approved else {})})
                online = module(ROOT / 'scripts/prepare-online-motif.py', 'free_evidence_online').prepare(
                    manifest, task_dir / 'motif-task.json')
                patches.append(online['patch'])
                embedding_handler = type('UnavailableEvidenceEmbeddings',
                    (module('compare-pdf.py', 'evidence_no_embeddings').ClosedReadOnly,), {'calls': 0})
                embedding_server = ThreadingHTTPServer(('127.0.0.1', 0), embedding_handler)
                embedding_worker = threading.Thread(target=embedding_server.serve_forever, daemon=True)
                embedding_worker.start()
                env.update(SSS_ONLINE_MOTIF_MANIFEST=online['manifest'], SSS_ONLINE_MOTIF_TASK=online['task'],
                           SSS_ONLINE_MOTIF_MODE='execute', SSS_ONLINE_MOTIF_PROMPT_SHA256=prepared['prompt_sha256'],
                           SSS_MOTIF_EMBEDDING_ENDPOINT=f'http://127.0.0.1:{embedding_server.server_port}/v1/embeddings',
                           SSS_MOTIF_EMBEDDING_MODEL='disabled-no-fake-vectors')
            with create_harness(root=ROOT, patches=tuple(patches), env=env, cwd=str(task_dir),
                                runtime_cwd=str(task_dir), provider='deepseek-official', model='deepseek-flash',
                                max_tokens=2000, request_timeout_seconds=30) as client:
                result = client.run(prepared['prompt'], session_id=session_id,
                                    on_notification=guard.on_notification)
            event_path = task_dir / 'agent-events.jsonl'
            event_path.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in result.events))
            event_path.chmod(0o600)
            assert result.finish_reason == 'completed' and not handler.failures
            delivery = runner.collect_packet(task_dir, task_dir)
            assert delivery['status'] == 'packet_ready'
            assert state.request_count == len(handler.calls)
            assert all({t['function']['name'] for t in body['tools']} == set(prepared['allowed_tools'])
                       for body in handler.calls)
            ledger = [json.loads(line) for line in state.record.read_text().splitlines()]
            assert len(ledger) == state.request_count
            body = json.loads((task_dir / 'evidence-packet.json').read_text())
            packets.append(body)
            rows.append({'arm': arm, 'task_directory': str(task_dir), 'mcp': mcp,
                         'model_requests': state.request_count, 'budget_ledger_rows': len(ledger),
                         'packet_sha256': digest(body), 'delivery': delivery})
            if embedding_server:
                audit_path = task_dir / '.local/online-motif' / (hashlib.sha256(session_id.encode()).hexdigest() + '.jsonl')
                audit = [json.loads(line) for line in audit_path.read_text().splitlines()]
                skips = sum(row.get('kind') == 'model_request_skipped_verified' for row in audit)
                if approved:
                    assert skips == 2 and embedding_handler.calls == 0
                    assert state.request_count == rows[0]['model_requests'] - 2
                    assert all(row['selection_bases'] == ['closed_approved_plan_continuation']
                               for row in audit if row.get('kind') == 'motif_bypass_attempt')
                else:
                    assert skips == 0 and embedding_handler.calls > 0
                    assert any(row.get('kind') == 'motif_deferred' for row in audit)
                    assert state.request_count == rows[0]['model_requests']
                rows[-1].update(verified_skips=skips, unavailable_embedding_requests=embedding_handler.calls,
                                semantic_fallback_verified=not approved)
        finally:
            for server in (gate, provider):
                server.shutdown()
                server.server_close()
            for worker in workers:
                worker.join(timeout=5)
            if embedding_server:
                embedding_server.shutdown()
                embedding_server.server_close()
                embedding_worker.join(timeout=5)
    assert all(body == packets[0] for body in packets) and inventory(directory) == original
    report = {'status': 'passed', 'output': str(output), 'arms': rows,
              'identical_packets': True, 'sources_unchanged': True, 'paid_api_requests': 0,
              'selected_windows_per_packet': len(packets[0]['windows']),
              'usage': 'synthetic; not actual fees or performance evidence',
              'frozen_plan_sha256': digest(frozen_plan) if frozen_plan is not None else None,
              'limits': ['fixed page protocol fixture', 'mechanical continuation only',
                         'no relevance, semantic-support or complete scientific quality assessment']}
    save_private(output / 'acceptance.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--papers-dir', type=Path, default=ROOT / 'testpdf')
    parser.add_argument('--manifest', type=Path, help='also check real learned library with unavailable semantic matching')
    args = parser.parse_args()
    print(json.dumps(check(args.papers_dir, manifest=args.manifest), ensure_ascii=False))
