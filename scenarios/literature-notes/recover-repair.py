"""Offline recovery of a typed native model proposal; zero new model requests."""
import argparse
import json
from pathlib import Path
from uuid import uuid4
from pdf_repair_recovery import recover_final_proposal
from pdf_repair_tools import RepairScene
from pdf_tools import ROOT, save_private


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--model-run', required=True, type=Path)
    parser.add_argument('--native-receipt', action='store_true')
    args = parser.parse_args()
    output = ROOT / '.local/literature-notes/proposal-recoveries' / uuid4().hex
    scene = RepairScene(args.run, output)
    if args.native_receipt:
        import importlib.util
        from pdf_dependencies import private_file
        spec = importlib.util.spec_from_file_location('native_repair_collector', Path(__file__).with_name('repair-pdf.py'))
        launcher = importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
        if not scene.synthesis_only: raise ValueError('native recapture requires synthesis-only input')
        native = args.model_run.resolve()
        if not native.is_relative_to(ROOT / '.local/runs'): raise ValueError('invalid native history')
        events = [json.loads(line) for line in private_file(native / 'agent-events.jsonl').read_text().splitlines()]
        calls = {e['data']['callId']: e['data'] for e in events if e['type'] == 'tool/call'}
        artifacts = []
        for e in events:
            if e['type'] != 'tool/result': continue
            for b in e['data']['message']['content']:
                call = calls.get(b.get('toolCallId'))
                if b.get('isError') or not call or call['name'] != launcher.REPAIR_TOOL: continue
                if json.loads(call['arguments']).get('decisions') != []: continue
                value = json.loads(''.join(c.get('text', '') for c in b['content']))
                if 'artifact' in value: artifacts.append(private_file(value['artifact']).parent)
        result = launcher.collect_repair(native, artifacts[-1], args.run, scene.input_digest) if artifacts else None
        if result:
            output = artifacts[-1]
            result['receipt_origin'] = 'native_tool_submission_recaptured'
    else:
        result = recover_final_proposal(args.model_run, output, args.run, scene.input_digest)
    if not result:
        print(json.dumps({'status': 'no_recoverable_proposal', 'model_call_enabled': False}));return 2
    evidence = json.loads(Path(result['receipt']['artifact']).read_text())
    notes = output / 'revised-research-notes.md';notes.write_text(evidence['markdown']);notes.chmod(0o600)
    result['notes'] = str(notes)
    record_path = output / ('native-recapture-' + uuid4().hex + '.json') if args.native_receipt else output / 'outcome.json'
    save_private(record_path, {**result, 'scope': 'offline_native_receipt_recapture' if args.native_receipt else 'offline_typed_proposal_validation',
        'model_call_enabled': False, 'model_requests': 0, 'budget_accounted_usd': 0})
    print(json.dumps({'claim_repair': str(output), **result, 'model_call_enabled': False,
                      'model_requests': 0, 'budget_accounted_usd': 0}, ensure_ascii=False));return 0


if __name__ == '__main__': raise SystemExit(main())
