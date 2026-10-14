"""Launch evidence-bound semantic repair through the existing Harness runner."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from pdf_tools import ROOT, digest, save_private
from pdf_review_tools import ReviewScene
HERE = Path(__file__).resolve().parent
REVIEW_TOOL = 'mcp__literature_pdf_review__submit_claim_review'


def review_contracts():
    sys.path.insert(0, str(ROOT))
    from src.adapters.tool_contract_loader import parse_tool_contracts
    return parse_tool_contracts({REVIEW_TOOL: {'required_params': ['review'], 'read_only': True, 'replay_stable': False}})


def collect_review(model_run, output, run, input_digest, *, tool_name=REVIEW_TOOL,
                   contracts=None, validator=ReviewScene):
    """Collect only a tool-witnessed hash receipt; safe to retry offline after a collector failure."""
    contracts = contracts if contracts is not None else review_contracts()
    from src.adapters.dsh_trajectory import extract_dsh_trace
    model_run, output, run = Path(model_run).resolve(), Path(output).resolve(), Path(run).resolve()
    if not model_run.is_relative_to(ROOT / '.local/runs') or not output.is_relative_to(ROOT / '.local'):
        raise ValueError('unexpected review directory')
    events = [json.loads(x) for x in (model_run / 'agent-events.jsonl').read_text().splitlines()]
    trace = extract_dsh_trace(events, contracts, trace_id=model_run.name)
    receipts = [r.observation for r in trace.records if r.name == tool_name and r.observation and 'artifact' in r.observation]
    if not receipts: return None
    receipt = receipts[-1]; artifact = Path(receipt['artifact'])
    if artifact.is_symlink() or artifact.resolve() != output / 'revised-evidence.json':
        raise ValueError('unexpected review artifact')
    revised = json.loads(artifact.read_text())
    if (digest(revised) != receipt['artifact_sha256'] or receipt['input_sha256'] != input_digest
            or digest(json.loads((run / 'evidence.json').read_text())) != input_digest):
        raise ValueError('review receipt or original input changed')
    if tool_name != REVIEW_TOOL:
        audit_path = Path(receipt['audit'])
        if audit_path.is_symlink() or audit_path.resolve() != output / 'claim-review.json':
            raise ValueError('unexpected repair audit')
        audit = json.loads(audit_path.read_text())
        if (digest(audit) != receipt['audit_sha256'] or audit['input_sha256'] != input_digest
                or audit['revised_evidence_sha256'] != digest(revised)):
            raise ValueError('repair audit receipt changed')
    # Source changes after the tool ran must also invalidate collection.
    checked = validator(run, output)
    if tool_name != REVIEW_TOOL and (audit['target_claim_ids'] != checked.targets
                                    or audit['repair_request_sha256'] != checked.request_digest):
        raise ValueError('repair targets changed after execution')
    notes = output / 'revised-research-notes.md'; notes.write_text(revised['markdown']); notes.chmod(0o600)
    return {'receipt': receipt, 'notes': str(notes)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--budget-usd', type=float, default=100)
    args = parser.parse_args(argv)
    review_contracts()  # Validate the collector contract before a paid call.
    run = args.run.resolve()
    output = ROOT / '.local/literature-notes/claim-reviews' / uuid4().hex
    scene = ReviewScene(run, output)  # Revalidate input before any paid launch.
    snapshot = {'original_run': str(run), 'input_sha256': scene.input_digest,
                'events_sha256': hashlib.sha256((run / 'agent-events.jsonl').read_bytes()).hexdigest(),
                'task_sha256': digest(scene.task), 'model_review_is_not_human_certification': True}
    runtime_spec = importlib.util.spec_from_file_location('pdf_review_runtime', HERE / 'run-pdf.py')
    runtime = importlib.util.module_from_spec(runtime_spec); runtime_spec.loader.exec_module(runtime)
    snapshot['runtime'] = runtime.runtime_snapshot()
    save_private(output / 'input-snapshot.json', snapshot)
    scenario = json.loads((HERE / 'pdf-review-scenario.json').read_text())
    prompt = (HERE / 'pdf-review-task.md').read_text() + '\n本轮选定论文 ID：\n' + json.dumps(
        [p['paper_id'] for p in scene.evidence['draft']['papers']], ensure_ascii=False) + '\n'
    prompt_path = output / 'prompt.md'; prompt_path.write_text(prompt); prompt_path.chmod(0o600)
    scenario['prompt'] = str(prompt_path); save_private(output / 'scenario.json', scenario)
    env = os.environ.copy()
    env.update(SSS_PDF_REVIEW_RUN=str(run), SSS_PDF_REVIEW_OUTPUT=str(output), SSS_PDF_SCRIPT_READ='0')
    if args.call_model:
        spec = importlib.util.spec_from_file_location('pdf_review_key', HERE / 'run-live.py')
        key = importlib.util.module_from_spec(spec); spec.loader.exec_module(key)
        env['DEEPSEEK_API_KEY'] = key.load_key(key.KEY_FILE, env)
    command = [sys.executable, str(ROOT / 'scripts/run-scenario.py'), '--scenario', str(output / 'scenario.json'),
               '--budget-usd', str(args.budget_usd), '--max-output', '6000', '--max-steps', '24']
    if args.call_model: command.append('--call-model')
    print(json.dumps({'review_directory': str(output), 'input_sha256': scene.input_digest,
                      'model_call_enabled': args.call_model, 'user_file_writes_enabled': False}), flush=True)
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    print(result.stdout, end='', flush=True)
    if result.stderr: print(result.stderr, file=sys.stderr, end='')
    if not args.call_model: return result.returncode
    # Accept only a submit receipt witnessed in original tool events, not a file or final assertion alone.
    summaries = []
    for line in result.stdout.splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict) and 'output_dir' in row: summaries.append(row)
        except ValueError: pass
    if not summaries: return result.returncode or 2
    model_run = Path(summaries[-1]['output_dir']).resolve()
    if not model_run.is_relative_to(ROOT / '.local/runs'): raise ValueError('unexpected runner directory')
    collected = collect_review(model_run, output, run, scene.input_digest)
    if collected is None:
        save_private(output / 'outcome.json', {'status': 'missing_review', 'run': summaries[-1]})
        return result.returncode or 2
    receipt = collected['receipt']
    save_private(output / 'outcome.json', {'receipt': receipt, 'run': summaries[-1], 'input': snapshot})
    print(json.dumps({'claim_review': str(output), 'status': receipt['status'], 'gap_count': receipt['gap_count'],
                      'notes': collected['notes'], 'research_quality': receipt['research_quality']}, ensure_ascii=False))
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
