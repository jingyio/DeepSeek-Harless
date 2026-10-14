"""Launch one claim-scoped repair stage through the existing Harness and budget runner."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from pdf_tools import ROOT, digest, save_private
from pdf_repair_tools import RepairScene, POLICY

HERE = Path(__file__).resolve().parent
REPAIR_TOOL = 'mcp__literature_pdf_repair__submit_claim_repair'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def repair_contracts(synthesis_only=False):
    sys.path.insert(0, str(ROOT))
    from src.adapters.tool_contract_loader import parse_tool_contracts
    return parse_tool_contracts({REPAIR_TOOL: {'required_params': ['synthesis_hypothesis'] if synthesis_only else ['decisions', 'synthesis_hypothesis'],
                                             'read_only': True, 'replay_stable': False}})


def collect_repair(model_run, output, run, input_digest):
    scene = RepairScene(Path(run), Path(output))
    result = module('repair_receipt_collector', 'review-pdf.py').collect_review(
        model_run, output, run, input_digest, tool_name=REPAIR_TOOL,
        contracts=repair_contracts(scene.synthesis_only), validator=RepairScene)
    if result and scene.synthesis_only:
        published = json.loads(Path(result['receipt']['artifact']).read_text())
        if published['draft']['papers'] != scene.evidence['draft']['papers']:
            raise ValueError('synthesis receipt changed a fact field')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--budget-usd', type=float, default=100)
    parser.add_argument('--model', choices=['deepseek-flash', 'deepseek-pro', 'deepseek-v4-pro'])
    parser.add_argument('--source-feedback', type=Path, help='private independent source-check diagnostics; not a truth certificate')
    parser.add_argument('--entry-policy', type=Path, help='independently certified task-entry read Motif')
    parser.add_argument('--terminal-policy', type=Path, help='independently certified successful receipt -> finish Motif')
    args = parser.parse_args(argv)
    if args.entry_policy and args.terminal_policy:
        parser.error('entry and terminal combination needs separate certification')
    repair_contracts()
    run = args.run.resolve()
    output = ROOT / '.local/literature-notes/claim-repairs' / uuid4().hex
    scene = RepairScene(run, output)
    entry_path = None
    terminal_path = None
    if args.terminal_policy:
        from terminal_entry import private_policy, entry_task as terminal_task
        terminal_policy = private_policy(args.terminal_policy)
        terminal_path = output / 'terminal-task.json'
        save_private(terminal_path, terminal_task(scene, output.name))
    if args.entry_policy:
        from pdf_dependencies import private_file
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location('entry_task_loader', HERE / 'learn-entry.py')
        loader = module_from_spec(spec); spec.loader.exec_module(loader)
        policy = json.loads(private_file(args.entry_policy).read_text())
        if (policy['policy_digest'] != digest({k:v for k,v in policy.items() if k!='policy_digest'})
                or policy['execution_version_sha256'] != loader.execution_version()):
            raise ValueError('entry reader execution version changed')
        entry_path = output / 'entry-task.json'; save_private(entry_path, loader.entry_task(scene))
    feedback = None
    if args.source_feedback:
        from pdf_dependencies import private_file
        raw = private_file(args.source_feedback).read_bytes()
        if len(raw) > 16000:
            raise ValueError('source feedback exceeds diagnostic limit')
        feedback = json.loads(raw)
        if (set(feedback) != {'schema_version', 'origin', 'input_sha256', 'issues'}
                or feedback['schema_version'] != 1 or feedback['origin'] != 'independent_source_check'
                or feedback['input_sha256'] != scene.input_digest or not isinstance(feedback['issues'], list)
                or not 1 <= len(feedback['issues']) <= len(scene.targets)
                or any(not isinstance(i, dict) or set(i) != {'claim_id', 'issue'}
                       or i['claim_id'] not in scene.targets or not isinstance(i['issue'], str)
                       or not 1 <= len(i['issue']) <= 2000 for i in feedback['issues'])
                or len({i['claim_id'] for i in feedback['issues']}) != len(feedback['issues'])):
            raise ValueError('source feedback must bind the current candidate and selected claims')
    model = args.model or 'deepseek-flash'
    if model == 'deepseek-pro': model = 'deepseek-v4-pro'
    active_policy = {**POLICY, 'max_statement_characters': scene.statement_limit}
    snapshot = {'original_input': str(run), 'input_sha256': scene.input_digest,
                'repair_request_sha256': scene.request_digest, 'task_sha256': digest(scene.task), 'target_claim_ids': scene.targets,
                'model': model, 'reasoning_effort': 'off', 'policy': active_policy, 'runtime': module('repair_runtime_snapshot', 'run-pdf.py').runtime_snapshot(),
                'model_repair_is_not_truth_certification': True}
    from terminal_entry import execution_version as terminal_execution_version
    snapshot['terminal_execution_version_sha256'] = terminal_execution_version()
    if feedback:
        snapshot['source_feedback_sha256'] = digest(feedback)
    if entry_path:
        snapshot['entry_policy_digest'] = policy['policy_digest']
    if terminal_path:
        snapshot['terminal_policy_digest'] = terminal_policy['policy_digest']
    save_private(output / 'input-snapshot.json', snapshot)
    scenario = json.loads((HERE / 'pdf-repair-scenario.json').read_text())
    prompt = (HERE / 'pdf-repair-task.md').read_text() + '\n本轮冻结 synthesis_only=' + str(scene.synthesis_only).lower() + '\n本轮冻结目标 claim_id：\n' + json.dumps(scene.targets, ensure_ascii=False)
    if feedback:
        prompt += ('\n独立自动原文核对的诊断意见（不是Runtime拒绝记录，也不是事实或答案；必须再次用实际原文核对）：\n'
                   + json.dumps(feedback, ensure_ascii=False)
                   + '\n软件Agent直接交付结果，不要求用户人工审阅；综合建议也遵循这个要求。')
    prompt_path = output / 'prompt.md'; prompt_path.write_text(prompt); prompt_path.chmod(0o600)
    scenario['prompt'] = str(prompt_path); save_private(output / 'scenario.json', scenario)
    env = os.environ.copy()
    env.update(SSS_PDF_REPAIR_RUN=str(run), SSS_PDF_REPAIR_OUTPUT=str(output), SSS_PDF_SCRIPT_READ='0')
    if args.call_model:
        key = module('repair_private_key_loader', 'run-live.py')
        env['DEEPSEEK_API_KEY'] = key.load_key(key.KEY_FILE, env)
    command = [sys.executable, str(ROOT / 'scripts/run-scenario.py'), '--scenario', str(output / 'scenario.json'),
               '--model', model, '--budget-usd', str(args.budget_usd), '--max-output', '6500', '--max-steps', '48']
    if entry_path: command.extend(['--entry-policy', str(args.entry_policy), '--entry-task', str(entry_path)])
    if terminal_path: command.extend(['--terminal-policy', str(args.terminal_policy), '--terminal-task', str(terminal_path)])
    if args.call_model: command.append('--call-model')
    print(json.dumps({'repair_directory': str(output), 'input_sha256': scene.input_digest,
                      'target_count': len(scene.targets), 'model': model, 'policy': active_policy,
                      'model_call_enabled': args.call_model, 'user_file_writes_enabled': False}), flush=True)
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    print(result.stdout, end='', flush=True)
    if result.stderr: print(result.stderr, file=sys.stderr, end='')
    if not args.call_model: return result.returncode
    summaries = []
    for line in result.stdout.splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict) and 'output_dir' in row: summaries.append(row)
        except ValueError: pass
    if not summaries: return result.returncode or 2
    collected = collect_repair(summaries[-1]['output_dir'], output, run, scene.input_digest)
    if collected is None:
        from pdf_repair_recovery import recover_final_proposal
        collected = recover_final_proposal(model_run=summaries[-1]['output_dir'], output=output, run=run, input_digest=scene.input_digest)
    if collected is None:
        save_private(output / 'outcome.json', {'status': 'missing_repair_receipt', 'run': summaries[-1]})
        return result.returncode or 2
    receipt = collected['receipt']
    save_private(output / 'outcome.json', {'receipt': receipt, 'run': summaries[-1], 'input': snapshot, 'receipt_origin': collected.get('receipt_origin', 'native_tool_submission')})
    print(json.dumps({'claim_repair': str(output), 'receipt': receipt, 'receipt_origin': collected.get('receipt_origin', 'native_tool_submission'), 'notes': collected['notes']}, ensure_ascii=False))
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
