"""Offline, predeclared acceptance checks. Verdict changes do not certify entailment."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from pdf_tools import digest, save_private
from pdf_dependencies import private_file, validate_envelope


def freeze_calibration(run, reference):
    run = Path(run).resolve()
    evidence = json.loads(private_file(run / 'evidence.json').read_text())
    reference = json.loads(private_file(reference).read_text())
    if reference.get('original_evidence_sha256') != digest(evidence):
        raise ValueError('reference is not bound to this original draft')
    originals = {(p['paper_id'], f['name']): f for p in evidence['draft']['papers'] for f in p['fields']}
    cases, seen = [], set()
    for d in reference['decisions']:
        key = d['paper_id'], d['field']
        if key not in originals or key in seen or d['original_statement'] != originals[key]['statement']:
            raise ValueError('reference decisions differ from original fields')
        seen.add(key)
        cases.append({'paper_id': key[0], 'field': key[1], 'original': originals[key],
                      'support_issue': d['support_issue'], 'expected_issue': bool(d['support_issue'])})
    if seen != set(originals):
        raise ValueError('reference must cover every original field')
    return {'schema_version': 1, 'run': str(run), 'input_sha256': digest(evidence),
            'reference_sha256': digest(reference), 'cases': cases,
            'scope': 'known-error calibration; not held-out or expert-blind evaluation',
            'gold_visible_to_model': False, 'automatic_semantic_certification': False}


def score_calibration(manifest, audit, revised, adjudication=None):
    if (audit['input_sha256'] != manifest['input_sha256']
            or audit['revised_evidence_sha256'] != digest(revised)
            or revised['original_evidence_sha256'] != manifest['input_sha256']):
        raise ValueError('review is not bound to the frozen calibration input/output')
    expected = {(c['paper_id'], c['field']): c for c in manifest['cases']}
    decisions = {(d['paper_id'], d['name']): d for d in audit['decisions']}
    fields = {(p['paper_id'], f['name']): f for p in revised['draft']['papers'] for f in p['fields']}
    if len(decisions) != len(audit['decisions']) or set(decisions) != set(expected) or set(fields) != set(expected):
        raise ValueError('review decisions must cover frozen cases exactly once')
    rows = []
    for key, c in expected.items():
        d, f = decisions[key], fields[key]
        verdict = d['verdict']
        if (d['original_statement'] != c['original']['statement']
                or d['statement'] != f['statement'] or d['citations'] != f['citations']
                or f['status'] != ('evidence' if verdict in ('supported', 'revised') else verdict)
                or verdict not in ('supported', 'revised', 'needs_review', 'not_extracted')):
            raise ValueError('review decision and delivered field differ')
        if verdict == 'supported' and (d['statement'] != c['original']['statement']
                                     or d['citations'] != c['original']['citations']):
            raise ValueError('supported decision changed original content')
        rows.append({'paper_id': key[0], 'field': key[1], 'expected_issue': c['expected_issue'],
                     'verdict': verdict, 'issue_flagged_by_verdict': verdict != 'supported',
                     'delivered_gap': f['status'] != 'evidence'})
    report = {'calibration_sha256': digest(manifest), 'review_sha256': digest(audit),
              'revised_evidence_sha256': digest(revised), 'cases': rows,
              'known_issue_count': sum(r['expected_issue'] for r in rows),
              'issues_flagged_by_verdict': sum(r['expected_issue'] and r['issue_flagged_by_verdict'] for r in rows),
              'controls_preserved': sum(not r['expected_issue'] and not r['issue_flagged_by_verdict'] for r in rows),
              'control_count': sum(not r['expected_issue'] for r in rows),
              'delivered_gap_count': sum(r['delivered_gap'] for r in rows),
              'semantic_quality': 'pending_independent_source_comparison', 'quality_passed': False,
              'scope': manifest['scope']}
    if adjudication is not None:
        if (adjudication['calibration_sha256'] != digest(manifest)
                or adjudication['review_sha256'] != digest(audit)
                or adjudication['revised_evidence_sha256'] != digest(revised)):
            raise ValueError('independent comparison is bound to different artifacts')
        judgments = {(d['paper_id'], d['field']): d for d in adjudication['decisions']}
        if len(judgments) != len(adjudication['decisions']) or set(judgments) != set(expected):
            raise ValueError('independent comparison must cover all cases')
        for key, j in judgments.items():
            if (type(j['supported_after_review']) is not bool or type(j['original_issue_addressed']) is not bool
                    or not isinstance(j['reason'], str) or not j['reason'].strip()):
                raise ValueError('independent comparison needs explicit support decisions and reasons')
        if (type(adjudication.get('synthesis_supported')) is not bool
                or not isinstance(adjudication.get('synthesis_reason'), str)
                or not adjudication['synthesis_reason'].strip()):
            raise ValueError('independent comparison must assess synthesis too')
        report.update(semantic_quality='independent_source_comparison_expert_blind_review_pending',
                      unsupported_after_review=sum(not j['supported_after_review'] for j in judgments.values()),
                      known_issues_unresolved=sum(c['expected_issue'] and not judgments[k]['original_issue_addressed']
                                                  for k, c in expected.items()),
                      adjudication_sha256=digest(adjudication),
                      synthesis_supported=adjudication['synthesis_supported'],
                      quality_passed=all(j['supported_after_review'] and
                                        (not expected[k]['expected_issue'] or j['original_issue_addressed'])
                                        for k, j in judgments.items()) and report['delivered_gap_count'] == 0
                                        and adjudication['synthesis_supported'])
    return report


def check_revocation(envelope, revoked, plan, payload):
    graph = validate_envelope(envelope)
    revoked = set(revoked['revoked_claim_ids'])
    expected = set(graph['fields']) - revoked
    audit = payload['incremental_audit']
    if (audit['graph_sha256'] != envelope['graph_sha256'] or audit['plan_sha256'] != plan['plan_sha256']
            or audit['task_sha256'] != digest(graph['task']) or payload['task_sha256'] != digest(graph['task'])
            or set(plan['invalidated_claim_ids']) != revoked or set(plan['retained_claim_ids']) != expected
            or set(audit['retained_claim_ids']) != expected or audit['reviewed_field_count'] != len(revoked)
            or not plan['synthesis_requires_review']):
        raise ValueError('revocation did not invalidate exactly the declared claims and synthesis')
    actual = {'claim:' + p['paper_id'] + ':' + f['name']: f
              for p in payload['draft']['papers'] for f in p['fields']}
    if set(actual) != set(graph['fields']):
        raise ValueError('updated delivery dropped or added unexpected fields')
    for cid in expected:
        if actual[cid] != graph['fields'][cid]['field']:
            raise ValueError('retained field was modified')
        old = graph['fields'][cid]['citation_checks']
        new = [c for c in payload['citation_checks'] if c['paper_id'] == graph['fields'][cid]['paper_id']
               and c['field'] == actual[cid]['name']]
        if new != old:
            raise ValueError('retained evidence changed')
    decisions = {'claim:' + d['paper_id'] + ':' + d['name'] for d in audit['decisions']}
    if decisions != revoked or audit['update_quality'] != 'model_draft_pending_independent_support_review':
        raise ValueError('revoked claims need fresh decisions with pending support review')
    return {'status': 'structural_acceptance_passed', 'retained_fields': len(expected),
            'reprocessed_fields': len(revoked), 'retained_fields_identical': True,
            'retained_citations_identical': True, 'synthesis_reprocessed': True,
            'scientific_quality': 'pending_independent_source_comparison',
            'learned_motif': False, 'revocation_means': 'withdrawal of prior approval, not an assertion of falsity'}


def load(path):
    return json.loads(private_file(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare-review')
    prepare.add_argument('--run', type=Path, required=True)
    prepare.add_argument('--reference', type=Path, required=True)
    prepare.add_argument('--output', type=Path, required=True)
    score = sub.add_parser('score-review')
    score.add_argument('--calibration', type=Path, required=True)
    score.add_argument('--review', type=Path, required=True)
    score.add_argument('--adjudication', type=Path)
    score.add_argument('--output', type=Path, required=True)
    revoke = sub.add_parser('check-revocation')
    for name in ('dependencies', 'revoked', 'run', 'output'):
        revoke.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    from pdf_tools import ROOT
    if not output.is_relative_to(ROOT / '.local') or output.exists():
        parser.error('output must be a new file in .local')
    if args.command == 'prepare-review':
        report = freeze_calibration(args.run, args.reference)
    elif args.command == 'score-review':
        report = score_calibration(load(args.calibration), load(args.review / 'claim-review.json'),
            load(args.review / 'revised-evidence.json'), load(args.adjudication) if args.adjudication else None)
    else:
        payload = load(args.run / 'incremental-evidence.json')
        outcome = load(args.run / 'outcome.json')
        if not outcome.get('receipt') or outcome['receipt']['artifact_sha256'] != digest(payload):
            raise ValueError('missing collected tool receipt or changed delivery')
        report = check_revocation(load(args.dependencies), load(args.revoked), load(args.run / 'plan.json'), payload)
    save_private(output, report)
    print(json.dumps({'report': str(output), 'command': args.command}, ensure_ascii=False))


if __name__ == '__main__':
    main()
