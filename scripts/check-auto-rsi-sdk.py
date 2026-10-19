"""Actual SDK/MCP automatic seed retrieval; local rejecting provider, never training."""
from __future__ import annotations
import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT));sys.path.insert(0, str(ROOT / 'scenarios/file-management'))
import auto_rsi as rsi
from common import save, digest
from src.adapters.file_scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard


class NoModel(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.server.requests += 1
        self.send_response(500)
        self.end_headers()
        self.wfile.write(b'free selection check must not require a model')


def check(exp, case, p):
    out, spec, env, _ = rsi.h.instantiate(exp, case, p, True)
    registry = Path(rsi.read(exp / 'seed-lock.json')['registry_file'])
    rsi.experience_binding(exp, case, p, out, spec, env, registry)
    prepared = prepare_scenario(Path(case['task_dir']) / 'scenario.json')
    with ThreadingHTTPServer(('127.0.0.1', 0), NoModel) as server:
        server.requests = 0
        worker = threading.Thread(target=server.serve_forever, daemon=True);worker.start()
        env.update(DEEPSEEK_API_KEY='mock-no-key', DEEPSEEK_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1',
                   DSH_HOME=str(out / 'dsh'), SSS_SCENARIO_PRESENTATION='native', SSS_SCENARIO_TOOLS=json.dumps(prepared['allowed_tools']))
        guard = NativeBudgetGuard(max_model_requests=96, max_observed_input_tokens=None)
        try:
            with create_harness(root=ROOT, patches=(prepared['patch'], str(exp / 'control.patch.yml')), env=env,
                                cwd=str(out), runtime_cwd=str(out), provider='deepseek-official', model='deepseek-flash',
                                max_tokens=4000, request_timeout_seconds=15) as client:
                result = client.run(prepared['prompt'], session_id='rsi-free-' + uuid4().hex, on_notification=guard.on_notification)
            report = rsi.read(out / 'delivery/report.json')
            receipt = rsi.h.receipt_from(guard.events)
            review = rsi.h.verify_workflow(spec, report, out / 'delivery', guard.events)
            assert result.finish_reason == 'completed' and review['passed']
            assert receipt['artifact_sha256'] == digest(report) and server.requests == 0
            audit = [json.loads(l) for l in (out / 'experience-audit.jsonl').read_text().splitlines()]
            assert sum(row['kind'] == 'experience_selected' for row in audit) == 1
            assert not any(row['kind'] == 'experience_deferred' for row in audit)
            value = {'task_id': case['task_id'], 'status': 'passed', 'actual_sdk_and_mcp': True,
                     'model_requests': 0, 'not_training': True, 'output': str(out)}
        except BaseException as error:
            value = {'task_id': case['task_id'], 'status': 'failed', 'error': str(error), 'output': str(out),
                     'real_api_requests': 0, 'mock_requests': server.requests}
            save(out / 'free-outcome.json', value);save(out / 'events.json', guard.events)
            raise
        finally:
            server.shutdown();worker.join(timeout=5)
        save(out / 'events.json', guard.events);save(out / 'free-outcome.json', value)
        return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('--experiment', type=Path, required=True);args = parser.parse_args()
    exp = args.experiment.resolve();p = rsi.read(exp / 'protocol.json');results = []
    for case in p['probes']:
        results.append(check(exp, case, p));print(json.dumps(results[-1]), flush=True)
    save(exp / 'free-sdk-summary.json', {'checks': len(results), 'passed': len(results), 'real_api_requests': 0, 'results': results})
