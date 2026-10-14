"""Replay source and native grants before learning; no scientific review or model call."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from pdf_tools import ROOT, digest, save_private
from pdf_dependencies import private_file
from pdf_evidence_tools import continuation_policy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.adapters.dsh_trajectory import extract_dsh_trace, infer_dsh_provenance
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.motif_core.offline.continuation_policy import valid_granted_record, same_grant

spec = importlib.util.spec_from_file_location('review_evidence_origin', HERE / 'compare-evidence.py')
origin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(origin)


def audit_chain(trace, receipt):
    policy = continuation_policy()
    names = [step['tool'] for step in policy['steps']]
    # Select the chain that actually delivered this packet, not an unrelated success.
    ends = [i for i, r in enumerate(trace.records) if r.name == names[-1] and r.observation == receipt]
    if len(ends) != 1 or ends[0] < 2:
        raise ValueError('ambiguous or missing native packet chain')
    chain = trace.records[ends[0] - 2:ends[0] + 1]
    if ([r.name for r in chain] != names or not all(r.eligible for r in chain)
            or not all(valid_granted_record(r, policy) for r in chain)
            or not all(same_grant(chain[0], r) for r in chain[1:])):
        raise ValueError('failed, interleaved or mismatched continuation grant chain')
    if (chain[1].arguments.get('extraction_id') != chain[0].observation.get('extraction_id')
            or chain[2].arguments.get('verification_id') != chain[1].observation.get('verification_id')):
        raise ValueError('native successor arguments do not use successful predecessor receipts')
    return chain


def review(run):
    run = Path(run).resolve()
    if not run.is_relative_to(ROOT / '.local/runs'):
        raise ValueError('review requires original private shared-run events')
    snapshot = origin.read(run / 'evidence-input-snapshot.json')
    opts = snapshot['execution_options']
    if (opts.get('mode') != 'baseline' or opts.get('script_chain') is not False
            or opts.get('model_call_enabled') is not True):
        raise ValueError('learning review requires a real-model normal baseline, not a script, Motif or simulated run')
    packet, _snapshot, metrics, event_sha = origin.approved_origin(
        run, Path(snapshot['task']['sources']['root']), ROOT / '.local/literature-notes/pdf-cache',
        run / 'structural-replay')
    events = [json.loads(line) for line in private_file(run / 'agent-events.jsonl').read_text().splitlines()]
    contracts = parse_tool_contracts(json.loads((HERE / 'pdf-evidence-contracts.json').read_text()))
    trace = extract_dsh_trace(events, contracts, trace_id=run.name,
                             provenance_by_call_id=infer_dsh_provenance(events, contracts))
    receipt = origin.read(run / 'evidence-packet-receipt.json')
    chain = audit_chain(trace, receipt)
    result = {'packet_sha256': digest(packet), 'events_sha256': event_sha,
              'contracts_sha256': hashlib.sha256((HERE / 'pdf-evidence-contracts.json').read_bytes()).hexdigest(),
              'execution_version_sha256': packet['execution_version_sha256'],
              'structural_chain_safe': True, 'scientific_quality_assessed': False,
              'review_method': 'current exact source replay + contiguous native successful grant and argument checks',
              'chain_tools': [r.name for r in chain], 'window_count': len(packet['windows']),
              'prior_upstream_requests': metrics['upstream_requests'],
              'review_model_requests': 0, 'review_paid_usd': 0,
              'scope': 'source preparation mechanics only; no semantic approval or relevance certification'}
    destination = run / 'evidence-structural-review.json'
    if destination.exists() and origin.read(destination) != result:
        raise ValueError('existing different review preserved; use a fresh run')
    save_private(destination, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(review(args.run), ensure_ascii=False))
