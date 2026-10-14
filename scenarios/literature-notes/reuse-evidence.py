"""Exact-result cache baseline: revalidate an explicitly requested approved plan, no model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from uuid import uuid4

from pdf_dependencies import private_file
from pdf_tools import ROOT, digest, save_private
import importlib.util

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('evidence_cache_origin', HERE / 'compare-evidence.py')
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


def validate_request(packet, question, plan):
    if (packet['question'] != question.strip() or packet['plan'] != plan
            or plan.get('allow_deterministic_continuation') is not True):
        raise ValueError('cache miss: current question, plan or permission differs')


def reuse(directory, run, question, frozen_plan):
    started = time.monotonic()
    plan = json.loads(private_file(frozen_plan).read_text())
    # Current intent must be explicit; a prior packet is not permission to reuse
    # it for a new question or a changed selection.
    old_packet = comparison.read(Path(run) / 'evidence-packet.json')
    validate_request(old_packet, question, plan)
    output = ROOT / '.local/literature-notes' / ('evidence-cache-' + uuid4().hex)
    output.mkdir(mode=0o700, parents=True)
    packet, snapshot, _metrics, events_sha = comparison.approved_origin(
        run, directory, ROOT / '.local/literature-notes/pdf-cache', output / 'replay')
    validate_request(packet, question, plan)
    save_private(output / 'evidence-packet.json', packet)
    result = {'status': 'cache_reused', 'output': str(output), 'origin_run': Path(run).name,
              'packet_sha256': digest(packet), 'frozen_plan_sha256': digest(plan),
              'origin_native_events_sha256': events_sha, 'execution_version_sha256': packet['execution_version_sha256'],
              'source_snapshot': snapshot['task']['sources'], 'model_requests': 0,
              'accounted_usd': 0, 'source_checks': 'exact_current_source_replay',
              'elapsed_seconds': time.monotonic() - started,
              'research_quality': 'unreviewed', 'claim_support_assessed': False,
              'scope': 'identical question/approved plan/current sources only; ordinary cache, not learned RSI'}
    save_private(output / 'cache-result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--papers-dir', type=Path, default=ROOT / 'testpdf')
    parser.add_argument('--plan-run', type=Path, required=True)
    parser.add_argument('--question', required=True)
    parser.add_argument('--frozen-plan', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = reuse(args.papers_dir, args.plan_run, args.question, args.frozen_plan)
    except (ValueError, OSError, KeyError, comparison.ToolError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
