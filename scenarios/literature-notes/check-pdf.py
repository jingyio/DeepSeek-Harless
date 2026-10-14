"""Free PDF/MCP/Harness acceptance using actual files and a loopback protocol provider."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

from pdf_tools import DEFAULT_QUESTION, FIELDS, ROOT, PdfScene, digest, inventory, save_private

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from mcp import Client, StdioServerParameters
from src.adapters.deepseek_cost_gate import State, create_server
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard
from src.adapters.scenario import prepare_scenario
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.tool_schema_contracts import bind_mcp_descriptions

PREFIX = 'mcp__literature_pdf__'


def entry():
    spec = importlib.util.spec_from_file_location('pdf_entry', HERE / 'run-pdf.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observations(messages):
    values = []
    for message in messages:
        if message.get('role') != 'tool':
            continue
        try:
            row = json.loads(message.get('content', ''))
            if isinstance(row, dict):
                values.append(row)
        except (TypeError, ValueError):
            pass
    return values


def protocol_action(values):
    """Navigation fixture; no research interpretation and no learned structure."""
    selected = next((v for v in values if 'papers' in v and 'page_numbering' in v), None)
    if selected is None:
        return PREFIX + 'list_pdfs', {}
    for row in selected['papers']:
        paper_id = row['paper_id']
        if not any(v.get('paper_id') == paper_id and 'coverage' in v for v in values):
            return PREFIX + 'prepare_pdf', {'paper_id': paper_id}
        pinned = next((v for v in values if v.get('paper_id') == paper_id and 'source_id' in v), None)
        if pinned is None:
            return PREFIX + 'pin_pdf_context', {'paper_id': paper_id, 'page': '1', 'start': 0, 'length': 1200}
        if not any(v.get('paper_id') == paper_id and 'text' in v for v in values):
            return PREFIX + 'read_pinned_pdf_context', {'source_id': pinned['source_id']}
    preview = next((v for v in values if ('citation_checks' in v and 'markdown' in v)
                    or ('artifact_sha256' in v and v.get('status') in ('preview', 'needs_review'))), None)
    if preview is not None:
        return None, {'status': preview['status'], 'scope': 'protocol_only', 'research_quality': 'unreviewed'}
    papers = []
    for row in selected['papers']:
        paper_id = row['paper_id']
        pinned = next(v for v in values if v.get('paper_id') == paper_id and 'source_id' in v)
        context = next(v for v in values if v.get('paper_id') == paper_id and 'text' in v)
        quote = context['text'].strip()[:120]
        fields = [{'name': name, 'status': 'not_extracted',
                   'statement': '协议检查不执行科研内容理解，此字段尚未提取。', 'citations': []}
                  for name in FIELDS]
        if len(quote) >= 12:
            fields[0] = {'name': FIELDS[0], 'status': 'evidence',
                         'statement': '协议测试：以下是原文片段，不是对研究目标的解释。',
                         'citations': [{'source_id': pinned['source_id'], 'quote': quote}]}
        papers.append({'paper_id': paper_id, 'fields': fields})
    return PREFIX + 'preview_research_notes', {'draft': {'papers': papers,
           'synthesis': '本输出只验证真实 PDF 的工具和引文链路，不提供论文比较或科研结论。'}}


class Provider(BaseHTTPRequestHandler):
    calls = None
    failures = None

    def log_message(self, *_args):
        pass

    def do_POST(self):
        try:
            if self.path != '/v1/chat/completions' or len(self.calls) >= 20:
                raise ValueError('unexpected protocol request')
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.calls.append(body)
            tool, payload = protocol_action(observations(body['messages']))
            delta = {'role': 'assistant'}
            if tool:
                delta['tool_calls'] = [{'index': 0, 'id': 'pdf-fixture-' + str(len(self.calls)),
                    'type': 'function', 'function': {'name': tool, 'arguments': json.dumps(payload)}}]
            else:
                delta['content'] = json.dumps(payload)
            base = {'id': 'pdf-fixture', 'created': 1, 'model': body['model'], 'object': 'chat.completion.chunk'}
            chunks = [{**base, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                      {**base, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls' if tool else 'stop'}]},
                      {**base, 'choices': [], 'usage': {'prompt_tokens': 100,
                       'prompt_cache_hit_tokens': 50, 'prompt_cache_miss_tokens': 50,
                       'completion_tokens': 20, 'total_tokens': 120}}]
            response = (''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks)
                        + 'data: [DONE]\n\n').encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        except Exception as exc:
            self.failures.append(type(exc).__name__)
            self.send_error(500)


async def check_mcp(env, output):
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / 'pdf_tools.py')], cwd=ROOT, env=env)
    async with Client(params) as client:
        tools = (await client.list_tools()).tools
        schemas = [{**tool.model_dump(mode='json', by_alias=True), 'name': PREFIX + tool.name} for tool in tools]
        contracts = parse_tool_contracts(json.loads((HERE / 'pdf-contracts.json').read_text(encoding='utf-8')))
        bound = bind_mcp_descriptions(contracts, schemas)
        assert set(bound) == set(json.loads((HERE / 'pdf-scenario.json').read_text())['allowed_tools'])
        assert all(tool.annotations.read_only_hint is True for tool in tools)
        listing = await client.call_tool('list_pdfs', {})
        assert not listing.is_error
        rows = json.loads(listing.content[0].text)['papers']
        for row in rows:
            prepared = await client.call_tool('prepare_pdf', {'paper_id': row['paper_id']})
            assert not prepared.is_error
            index = json.loads(prepared.content[0].text)
            save_private(output / (row['paper_id'].split(':')[-1] + '-page-index.json'), index)
            pin = await client.call_tool('pin_pdf_context', {'paper_id': row['paper_id'], 'page': '1'})
            source = json.loads(pin.content[0].text)['source_id']
            read = await client.call_tool('read_pinned_pdf_context', {'source_id': source})
            assert not read.is_error
            batch = await client.call_tool('read_pdf_evidence_plan', {'paper_id': row['paper_id'],
                'document_version_sha256': index['document_version_sha256'],
                'windows': [{'page': '1', 'start': 0, 'length': 1200}]})
            assert not batch.is_error
            assert json.loads(batch.content[0].text)['contexts'][0]['quote_spans']
        rejected = await client.call_tool('read_pinned_pdf_context', {'source_id': 'source-' + '0' * 32})
        assert rejected.is_error
    save_private(output / 'mcp-schemas.json', schemas)
    return {'schema_checked': True, 'paper_count': len(rows), 'unknown_handle_rejected': True}


def check(directory: Path, *, harness=True):
    runner = entry()
    output, env = runner.prepare_task(directory, DEFAULT_QUESTION)
    task = json.loads((output / 'task.json').read_text(encoding='utf-8'))
    # Isolated fresh cache makes cold/warm checks interpretable, independent of earlier runs.
    env['SSS_PDF_CACHE'] = str(output / 'cache')
    cold = PdfScene(directory, Path(env['SSS_PDF_CACHE']), task)
    started = time.monotonic()
    indexes = [cold.prepare_pdf(row['paper_id']) for row in task['sources']['papers']]
    cold_seconds = time.monotonic() - started
    warm = PdfScene(directory, Path(env['SSS_PDF_CACHE']), task)
    started = time.monotonic()
    warm_indexes = [warm.prepare_pdf(row['paper_id']) for row in task['sources']['papers']]
    warm_seconds = time.monotonic() - started
    assert [{k: v for k, v in row.items() if k != 'cache_stats'} for row in indexes] == [
        {k: v for k, v in row.items() if k != 'cache_stats'} for row in warm_indexes]
    assert cold.stats['parser_runs'] == len(indexes) and warm.stats['parser_runs'] == 0
    report = {'status': 'passed', 'scope': 'actual_pdf_protocol_only', 'paid_api_requests': 0,
              'task_directory': str(output), 'research_quality': 'unreviewed',
              'parser_profile': cold.profile, 'cold': {**cold.stats, 'seconds': round(cold_seconds, 3)},
              'warm': {**warm.stats, 'seconds': round(warm_seconds, 3)},
              'mcp': asyncio.run(check_mcp(env, output)),
              'source_unchanged': inventory(directory) == task['sources'],
              'limitations': ['No scientific interpretation', 'No OCR or figure/table validation',
                              'No learned PDF Motif', 'Synthetic provider usage, no cost-savings claim']}
    if harness:
        handler = type('PdfProvider', (Provider,), {'calls': [], 'failures': []})
        prepared = prepare_scenario(output / 'scenario.json')
        state = State(cap_usd=0.25, output_cap=4000, record=output / 'cost-ledger.jsonl')
        guard = NativeBudgetGuard(max_model_requests=20, max_observed_input_tokens=150000)
        provider = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        gate = create_server('127.0.0.1', 0, f'http://127.0.0.1:{provider.server_port}', state)
        workers = [threading.Thread(target=server.serve_forever, daemon=True) for server in (provider, gate)]
        for worker in workers:
            worker.start()
        try:
            child_env = {**env, 'DSH_HOME': str(output / 'dsh'), 'DEEPSEEK_API_KEY': 'local-protocol-only',
                         'DEEPSEEK_BASE_URL': f'http://127.0.0.1:{gate.server_port}/v1',
                         'SSS_SCENARIO_TOOLS': json.dumps(prepared['allowed_tools']),
                         'SSS_ONLINE_MOTIF_MANIFEST': '', 'SSS_ONLINE_MOTIF_TASK': '',
                         'SSS_BUDGET_GATE_ACTIVE': '1', 'SSS_BUDGET_CAP_USD': '0.25',
                         'SSS_BUDGET_LEDGER': str(state.record)}
            with create_harness(root=ROOT, patches=(prepared['patch'],), env=child_env, cwd=str(output),
                                runtime_cwd=str(output), provider='deepseek-official', model='deepseek-flash',
                                max_tokens=4000, request_timeout_seconds=30) as client:
                result = client.run(prepared['prompt'], session_id='pdf-check-' + uuid4().hex,
                                    on_notification=guard.on_notification)
            assert result.finish_reason == 'completed' and not handler.failures
            events = ''.join(json.dumps(event, ensure_ascii=False) + '\n' for event in result.events)
            event_path = output / 'agent-events.jsonl'
            event_path.write_text(events, encoding='utf-8'); event_path.chmod(0o600)
            delivery = runner.collect_preview(output, output)
            assert delivery['status'] == 'needs_review' and delivery['citation_count'] == len(indexes)
            assert state.request_count == len(handler.calls)
            assert all({t['function']['name'] for t in body['tools']} == set(prepared['allowed_tools'])
                       for body in handler.calls)
            ledger = [json.loads(line) for line in state.record.read_text().splitlines()]
            assert len(ledger) == state.request_count
            report['harness'] = {'model_requests': state.request_count,
                                 'tool_calls': sum(event.get('type') == 'tool/call' for event in result.events),
                                 'budget_ledger_rows': len(ledger), 'usage': 'synthetic', 'delivery': delivery}
        finally:
            for server in (gate, provider):
                server.shutdown(); server.server_close()
            for worker in workers:
                worker.join(timeout=5)
    save_private(output / 'acceptance.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--papers-dir', type=Path, default=ROOT / 'testpdf')
    parser.add_argument('--skip-harness', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check(args.papers_dir, harness=not args.skip_harness), ensure_ascii=False, indent=2))
