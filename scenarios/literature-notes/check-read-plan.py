"""Same real model-selected windows: parallel MCP pin/read versus guarded batch.

This measures MCP transport, not model requests or end-to-end scientific quality.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
from uuid import UUID, uuid4
from mcp import Client, StdioServerParameters
from pdf_tools import ROOT, digest, save_private
from pdf_dependencies import private_file

HERE = Path(__file__).resolve().parent


async def check(job_id):
    if str(UUID(job_id)) != job_id: raise ValueError('canonical job UUID required')
    job = ROOT / '.local/literature-notes/agent-jobs' / job_id
    metadata = json.loads(private_file(job / 'job.json').read_text())
    source_run = private_file(Path(metadata['source_run']) / 'agent-events.jsonl')
    calls = [json.loads(line)['data'] for line in source_run.read_text().splitlines()
             if json.loads(line).get('type') == 'tool/call']
    plans = [json.loads(c['arguments']) for c in calls
             if c['name'] == 'mcp__literature_pdf__read_pdf_evidence_plan']
    plan = next((p for p in plans if len(p.get('windows', [])) >= 2), None)
    if plan is None: raise ValueError('need a witnessed multi-window model plan')
    snapshot = json.loads(private_file(job / 'source-snapshot.json').read_text())
    output = ROOT / '.local/literature-notes/read-plan-checks' / uuid4().hex
    save_private(output / 'task.json', snapshot['task'])
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / 'pdf_tools.py')], cwd=ROOT,
        env={'SSS_PDF_ROOT': snapshot['task']['sources']['root'], 'SSS_PDF_TASK_FILE': str(output / 'task.json'),
             'SSS_PDF_CACHE': str(ROOT / '.local/literature-notes/pdf-cache'), 'SSS_PDF_CACHE_POLICY': 'reuse',
             'SSS_PDF_SCRIPT_READ': '0', 'SSS_PDF_DELIVERY': str(output / 'delivery')})
    async with Client(params) as client:
        async def call(name, arguments):
            result = await client.call_tool(name, arguments)
            if result.is_error: raise ValueError('native MCP operation failed: ' + name)
            return json.loads(result.content[0].text)
        prepared = await call('prepare_pdf', {'paper_id': plan['paper_id']})
        if prepared['document_version_sha256'] != plan['document_version_sha256']:
            raise ValueError('witnessed plan version changed; never force reuse')
        async def ordinary():
            pins = await asyncio.gather(*(call('pin_pdf_context', {'paper_id': plan['paper_id'], **w}) for w in plan['windows']))
            values = await asyncio.gather(*(call('read_pinned_pdf_context', {'source_id': p['source_id']}) for p in pins))
            return [{'source_id': p['source_id'], **v} for p, v in zip(pins, values)]
        async def batch():
            return (await call('read_pdf_evidence_plan', plan))['contexts']
        # Warm both paths before timing; all subsequent calls still replay guards.
        reference = await ordinary()
        if reference != await batch(): raise ValueError('batch changed the exact contexts')
        samples = []
        for round_number in range(4):
            for name, operation in ([('ordinary_parallel', ordinary), ('guarded_batch', batch)] if round_number % 2 == 0
                                    else [('guarded_batch', batch), ('ordinary_parallel', ordinary)]):
                start = time.perf_counter(); contexts = await operation()
                seconds = time.perf_counter() - start
                if contexts != reference: raise ValueError('source context changed during comparison')
                samples.append({'round': round_number + 1, 'arm': name, 'seconds': round(seconds, 6),
                                'mcp_calls': 1 if name == 'guarded_batch' else 2 * len(plan['windows'])})
    report = {'output': str(output), 'job_id': job_id, 'source_events_sha256': __import__('hashlib').sha256(source_run.read_bytes()).hexdigest(),
              'plan': plan, 'contexts_sha256': digest(reference), 'exact_contexts_equal': True, 'samples': samples,
              'paid_api_requests': 0, 'model_requests_skipped_verified': 0, 'learned_motif': False,
              'scope': 'warm native MCP transport only; not model-request or scientific-quality equivalence'}
    save_private(output / 'comparison.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(check(args.job)), ensure_ascii=False, indent=2))
