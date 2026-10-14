"""Offline source validation and automatic delivery; legacy approval is optional."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from pdf_dependencies import compile_graph, contract_version, private_file, validate_envelope, automatic_workflow_version
from pdf_review_tools import numeric_gaps
from pdf_tools import ROOT, FIELDS, PdfScene, digest, inventory, save_private

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(private_file(path).read_text())


def capture(directory, question):
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
        raise ValueError('研究问题需要1–4000字符')
    task = {'schema_version': 1, 'question': question.strip(), 'sources': inventory(Path(directory))}
    scene = PdfScene(Path(directory), ROOT / '.local/literature-notes/pdf-cache', task)
    version_files = ['agent-support.py', 'agent.ts', 'decision-log.ts', 'pdf-task.md', 'pdf-review-task.md',
                     'review-pdf.py', 'pdf-repair-task.md', 'pdf-repair-scenario.json',
                     'pdf_repair_tools.py', 'repair-pdf.py', 'pdf_repair_recovery.py', 'recover-repair.py']
    return {'task': task, 'task_sha256': digest(task), 'parser_sha256': digest(scene.profile),
            'contract_sha256': contract_version(),
            'workflow_sha256': digest({**{n: hashlib.sha256((HERE / n).read_bytes()).hexdigest()
                                      for n in version_files}, 'completion_guard': hashlib.sha256(
                                      (ROOT / 'src/adapters/dsh_completion_guard.ts').read_bytes()).hexdigest()})}


def validate(evidence, snapshot):
    task = snapshot['task']
    if evidence['task_sha256'] != digest(task) or inventory(Path(task['sources']['root'])) != task['sources']:
        raise ValueError('来源或任务变化，需要重新处理')
    scene = PdfScene(Path(task['sources']['root']), ROOT / '.local/literature-notes/pdf-cache', task)
    for c in evidence['citation_checks']:
        pin = scene.pin_pdf_context(c['paper_id'], str(c['page']), c['start'], c['end'] - c['start'])
        if pin['source_id'] != c['source_id'] or pin['version_sha256'] != c['version_sha256']:
            raise ValueError('引文来源版本变化')
        scene.read_pinned_pdf_context(pin['source_id'])
    checked = scene.preview_research_notes(evidence['draft'])
    if checked['citation_checks'] != evidence['citation_checks'] or checked['gaps'] != evidence['gaps']:
        raise ValueError('引文或缺口记录与来源不一致')
    return checked


def package(job, evidence_path, snapshot_path, *, review_path=None):
    job = Path(job).resolve()
    if job.parent != (ROOT / '.local/literature-notes/agent-jobs').resolve() or not job.is_dir():
        raise ValueError('无效的任务目录')
    evidence, snapshot = read(evidence_path), read(snapshot_path)
    review = read(review_path) if review_path else None
    if review and review.get('revised_evidence_sha256') != digest(evidence):
        raise ValueError('自动审阅记录与候选稿不一致')
    checked = validate(evidence, snapshot)
    if evidence.get('synthesis_only') and review:
        save_private(job / 'synthesis-review.json', review)
        prior = read(job / 'evidence.json') if (job / 'evidence.json').exists() else None
        previous_review = read(job / 'model-review.json') if (job / 'model-review.json').exists() else None
        if previous_review:
            if (not prior or prior['draft']['papers'] != evidence['draft']['papers']
                    or previous_review.get('revised_evidence_sha256') != digest(prior)):
                raise ValueError('综合后的字段审阅继承不匹配')
            review = {**previous_review, 'revised_evidence_sha256': digest(evidence),
                      'runtime_preserved_fields_after_synthesis': {'original_audit_sha256': digest(previous_review),
                        'original_evidence_sha256': digest(prior), 'synthesis_audit_sha256': digest(review),
                        'facts_unchanged': True, 'new_semantic_field_decisions': False}}
        else:
            review = None
    save_private(job / 'evidence.json', evidence)
    save_private(job / 'source-snapshot.json', snapshot)
    notes = job / 'research-notes.md'
    notes.write_text('状态：智能体自动交付。来源可追溯；自动检查不能保证每项研究判断正确。\n\n'
                     + evidence['markdown'], encoding='utf-8')
    notes.chmod(0o600)
    if review:
        save_private(job / 'model-review.json', review)
    elif (job / 'model-review.json').exists():
        # The original review remains in its run directory. An edited candidate
        # must not expose that review as its own current assessment.
        (job / 'model-review.json').unlink()
    rows = []
    names = {p['paper_id']: p['filename'] for p in snapshot['task']['sources']['papers']}
    for p in evidence['draft']['papers']:
        for f in p['fields']:
            quotes = [c for c in evidence['citation_checks'] if c['paper_id'] == p['paper_id'] and c['field'] == f['name']]
            decision = next((d for d in review['decisions'] if d['paper_id'] == p['paper_id']
                             and d['name'] == f['name']), None) if review else None
            rows.append({'id': 'claim:' + p['paper_id'] + ':' + f['name'], 'paper_id': p['paper_id'],
                         'filename': names[p['paper_id']], **f, 'quotes': quotes,
                         'model_review': decision,
                         'missing_literal_numbers': numeric_gaps(f['statement'], [q['quote'] for q in quotes])})
    cards = {'evidence_sha256': digest(evidence), 'question': snapshot['task']['question'],
             'rows': rows, 'synthesis': evidence['draft']['synthesis'], 'gaps': checked['gaps'],
             'delivery_policy': 'automatic_v1', 'human_review_required': False,
             'human_review_completed': False, 'expert_blind_review_completed': False}
    save_private(job / 'review-cards.json', cards)
    return {**({'incremental_claim_ids': ['claim:' + d['paper_id'] + ':' + d['name']
               for d in evidence['incremental_audit']['decisions']],
               'incremental_synthesis_requires_review': evidence['incremental_audit'].get('synthesis_requires_review') is True
               } if 'incremental_audit' in evidence else {}),
            'evidence_sha256': digest(evidence), 'gap_count': len(checked['gaps']),
            'numeric_gap_count': sum(bool(r['missing_literal_numbers']) for r in rows),
            'claim_count': len(rows), 'research_quality':
            'automatic_model_reviewed_unverified' if review else 'automatic_source_validated_unverified',
            'delivery_policy': 'automatic_v1', 'human_review_required': False}


def resume_context(job, parent_job, evidence, snapshot, ids):
    """Freeze source-bound navigation and rejected hypotheses from actual prior receipts."""
    parent = Path(parent_job).resolve()
    if parent.parent != job.parent or parent == job:
        raise ValueError('无效续修父任务')
    if not (parent / 'model-review.json').exists(): return {}
    audit = read(parent / 'model-review.json')
    if audit.get('revised_evidence_sha256') != digest(evidence):
        raise ValueError('续修记录与当前稿不一致')
    ancestor, visited, origin = parent, set(), None
    for _ in range(32):
        if ancestor in visited: raise ValueError('父任务链循环')
        visited.add(ancestor)
        for number in (1, 2):
            candidate = ancestor / ('repair-input-' + str(number))
            if not (candidate / 'evidence.json').exists(): continue
            previous = read(candidate / 'evidence.json')
            request = read(candidate / 'repair-targets.json')
            if (digest(previous) == audit.get('input_sha256')
                    and digest(request) == audit.get('repair_request_sha256')):
                origin = candidate
                break
        if origin: break
        previous_id = read(ancestor / 'job.json').get('parent_job')
        if not previous_id: break
        following = (job.parent / previous_id).resolve()
        if following.parent != job.parent: raise ValueError('父任务链越界')
        ancestor = following
    result = {'prior_audit_sha256': digest(audit)}
    if origin:
        request = read(origin / 'repair-targets.json')
        if request.get('history_input_directory'):
            history = Path(request['history_input_directory'])
            if digest(read(history / 'evidence.json')) != request['history_input_sha256']:
                raise ValueError('续修导航历史变化')
            origin = history
        prior, old_snapshot = read(origin / 'evidence.json'), read(origin / 'pdf-input-snapshot.json')
        validate(prior, old_snapshot)
        if old_snapshot['task'] != snapshot['task']: raise ValueError('续修历史任务不同')
        frozen = job / 'repair-history'
        save_private(frozen / 'evidence.json', prior)
        save_private(frozen / 'pdf-input-snapshot.json', old_snapshot)
        result.update(history_input_directory=str(frozen), history_input_sha256=digest(prior))
    proposals = audit.get('rejected_proposals', {})
    provenance = audit.get('proposal_provenance', {})
    # Old receipts did not retain errors beside proposals. Recover from actual text
    # only when both native event bytes and the model proposal match receipt hashes.
    if not proposals and provenance.get('kind') == 'validated_model_final_json_recovery':
        import re
        native = provenance.get('native_run', '')
        if not re.fullmatch(r'[a-f0-9]{32}', native): raise ValueError('无效模型历史')
        raw = private_file(ROOT / '.local/runs' / native / 'agent-events.jsonl').read_bytes()
        if hashlib.sha256(raw).hexdigest() != provenance['native_events_sha256']:
            raise ValueError('模型历史已变化')
        events = [json.loads(line) for line in raw.splitlines()]
        messages = [e['data']['message'] for e in events if e.get('type') == 'assistant/message'
                    and e['data']['message'].get('source', {}).get('kind') == 'model']
        message = next(m for m in messages if m.get('id') == provenance['model_message_id'])
        proposal = json.loads(''.join(c['text'] for c in message['content'] if c['type'] == 'text'))
        if digest(proposal) != provenance['proposal_sha256']: raise ValueError('模型提案已变化')
        rejected = set(audit.get('runtime_gap_claim_ids', []))
        reasons = {d['claim_id']: d['reason'] for d in audit['decisions']}
        proposals = {d['claim_id']: {'proposal': d, 'validation_error': reasons.get(d['claim_id'], '')}
                     for d in proposal['decisions'] if d['claim_id'] in rejected}
    result['prior_proposals'] = {cid: value for cid, value in proposals.items() if cid in ids}
    return result


def repair_plan(job, round_number, scope=None, parent_job=None, target_claim_ids=None):
    """Offline freeze of selected claim inputs; first pass audits all, later only gaps."""
    job = Path(job).resolve()
    if job.parent != (ROOT / '.local/literature-notes/agent-jobs').resolve() or type(round_number) is not int or not 1 <= round_number <= 2:
        raise ValueError('无效任务或修复轮次')
    evidence, snapshot = read(job / 'evidence.json'), read(job / 'source-snapshot.json')
    validate(evidence, snapshot)
    if scope not in (None, 'unresolved_claims_only', 'all_claim_audit', 'support_audit'):
        raise ValueError('无效修复范围')
    known = {'claim:' + p['paper_id'] + ':' + f['name'] for p in evidence['draft']['papers'] for f in p['fields']}
    if target_claim_ids is not None and (not isinstance(target_claim_ids, list)
            or len(set(target_claim_ids)) != len(target_claim_ids) or set(target_claim_ids) - known):
        raise ValueError('局部审阅范围不匹配当前稿')
    audit_support = scope == 'support_audit'
    audit_all = round_number == 1 and scope not in ('unresolved_claims_only', 'support_audit')
    ids = []
    for p in evidence['draft']['papers']:
        for f in p['fields']:
            quotes = [c['quote'] for c in evidence['citation_checks'] if c['paper_id'] == p['paper_id'] and c['field'] == f['name']]
            cid = 'claim:' + p['paper_id'] + ':' + f['name']
            if target_claim_ids is not None and cid not in target_claim_ids: continue
            if audit_all or audit_support or f['status'] != 'evidence' or numeric_gaps(f['statement'], quotes):
                ids.append('claim:' + p['paper_id'] + ':' + f['name'])
    result = {'input_sha256': digest(evidence), 'claim_ids': ids, 'round_number': round_number,
              'review_mode': 'evidence_first_reextract' if audit_all else 'compare_existing_claim',
              'scope': ('claim_support_audit' if audit_support else 'changed_claim_audit' if target_claim_ids is not None and audit_all else
                        'all_claim_audit' if audit_all else 'unresolved_claims_only')}
    if not ids:
        return result
    directory = job / ('repair-input-' + str(round_number))
    save_private(directory / 'evidence.json', evidence)
    save_private(directory / 'pdf-input-snapshot.json', snapshot)
    if round_number > 1:
        origin = job / 'repair-input-1'
        prior = read(origin / 'evidence.json')
        validate(prior, read(origin / 'pdf-input-snapshot.json'))
        result.update(history_input_directory=str(origin), history_input_sha256=digest(prior))
    elif not audit_all and parent_job:
        result.update(resume_context(job, parent_job, evidence, snapshot, ids))
    save_private(directory / 'repair-targets.json', result)
    save_private(directory / 'input-provenance.json', {'kind': 'frozen_candidate_for_new_semantic_repair',
                 'candidate_sha256': digest(evidence), 'parent_job': str(job), 'synthetic_native_events': False})
    return {**result, 'input_directory': str(directory)}


def index_automatic(job):
    """Build an unverified per-field result cache; never issue Human/model support attestations."""
    job = Path(job).resolve()
    if job.parent != (ROOT / '.local/literature-notes/agent-jobs').resolve():
        raise ValueError('无效任务目录')
    evidence, snapshot = read(job / 'evidence.json'), read(job / 'source-snapshot.json')
    validate(evidence, snapshot)
    bound = {**evidence, 'reviewer_kind': 'Runtime', 'research_quality': 'runtime_source_bound_model_content_unverified',
             'claim_support_assessed': False, 'scientific_truth_certified': False}
    decisions = []
    for p in bound['draft']['papers']:
        for f in p['fields']:
            locators = [{'physical_page': c['page'], 'window_start': c['start'], 'quote_id': c.get('quote_id')}
                        for c in bound['citation_checks'] if c['paper_id'] == p['paper_id'] and c['field'] == f['name']]
            decisions.append({'paper_id': p['paper_id'], 'field': f['name'], 'source_binding_by': 'Runtime',
                              'source_checked_statement': f['statement'], 'source_locators': locators})
    audit = {'source_checked_by': 'Runtime', 'source_checked_evidence_sha256': digest(bound),
             'original_candidate_sha256': digest(evidence), 'decisions': decisions,
             'workflow_sha256': automatic_workflow_version(),
             'scope': 'Exact source binding of prior model output; no semantic approval, scientific truth or learned Motif.'}
    # Versioned backing files remain immutable when a newer workflow is indexed.
    directory = job / 'automatic-indexes' / digest({'evidence': bound, 'audit': audit, 'contract': contract_version()})
    for name, value in [('evidence.json', bound), ('binding.json', audit), ('snapshot.json', snapshot)]:
        path = directory / name
        if path.exists() and read(path) != value: raise ValueError('自动索引版本冲突')
        if not path.exists(): save_private(path, value)
    envelope = compile_graph(directory / 'evidence.json', directory / 'binding.json', directory / 'snapshot.json')
    save_private(job / 'automatic-dependencies.json', envelope)
    return {'automatic_dependency_graph_sha256': envelope['graph_sha256'],
            'automatic_dependency_policy': 'automatic_source_bound_unverified', 'index_model_requests': 0,
            'scientific_truth_certified': False}


def synthesis_plan(job):
    job = Path(job).resolve()
    if job.parent != (ROOT / '.local/literature-notes/agent-jobs').resolve(): raise ValueError('无效任务目录')
    evidence, snapshot = read(job / 'evidence.json'), read(job / 'source-snapshot.json')
    validate(evidence, snapshot)
    directory = job / 'synthesis-input'
    request = {'input_sha256': digest(evidence), 'claim_ids': [], 'synthesis_only': True, 'scope': 'synthesis_only'}
    save_private(directory / 'evidence.json', evidence)
    save_private(directory / 'pdf-input-snapshot.json', snapshot)
    save_private(directory / 'repair-targets.json', request)
    return {**request, 'input_directory': str(directory)}


def approve(job, expected_sha, claim_ids, synthesis_reviewed):
    job = Path(job).resolve()
    evidence, snapshot = read(job / 'evidence.json'), read(job / 'source-snapshot.json')
    validate(evidence, snapshot)
    cards = read(job / 'review-cards.json')
    originals = {'claim:' + p['paper_id'] + ':' + f['name']: f
                 for p in evidence['draft']['papers'] for f in p['fields']}
    if (len(cards['rows']) != len(originals) or {r['id'] for r in cards['rows']} != set(originals)
            or cards['synthesis'] != evidence['draft']['synthesis']
            or any(r['id'] not in originals or r['statement'] != originals[r['id']]['statement']
                   or r['status'] != originals[r['id']]['status']
                   or r['quotes'] != [c for c in evidence['citation_checks']
                                     if c['paper_id'] == r['paper_id'] and c['field'] == r['name']]
                   or r['id'] != 'claim:' + r['paper_id'] + ':' + r['name']
                   or r['missing_literal_numbers'] != numeric_gaps(r['statement'], [c['quote'] for c in r['quotes']])
                   for r in cards['rows'])):
        raise ValueError('审阅卡片与当前证据不一致')
    if (digest(evidence) != expected_sha or cards['evidence_sha256'] != expected_sha
            or not isinstance(claim_ids, list) or len(set(claim_ids)) != len(claim_ids)
            or set(claim_ids) != {r['id'] for r in cards['rows']} or synthesis_reviewed is not True):
        raise ValueError('需要核对当前稿的全部字段及综合分析')
    if evidence['gaps'] or any(r['missing_literal_numbers'] for r in cards['rows']):
        raise ValueError('仍有来源或数值缺口，先修订后批准')
    approved = {**evidence, 'research_quality': 'human_source_checked_expert_blind_review_pending',
                'reviewer_kind': 'Human', 'claim_support_assessed': True}
    decisions = [{'paper_id': r['paper_id'], 'field': r['name'],
                  'source_checked_statement': r['statement'], 'semantic_verdict_by': 'Human',
                  'source_locators': [{'physical_page': c['page'], 'window_start': c['start'],
                                      'quote_id': c.get('quote_id')} for c in r['quotes']]} for r in cards['rows']]
    audit = {'source_checked_by': 'Human', 'source_checked_evidence_sha256': digest(approved),
             'decisions': decisions, 'synthesis_reviewed': True, 'original_candidate_sha256': expected_sha,
             'expert_blind_review_completed': False,
             'scope': 'Explicit local user source comparison; not expert blind certification or a digital signature.'}
    save_private(job / 'source-checked-evidence.json', approved)
    save_private(job / 'source-check.json', audit)
    envelope = compile_graph(job / 'source-checked-evidence.json', job / 'source-check.json',
                             job / 'source-snapshot.json')
    save_private(job / 'dependencies.json', envelope)
    cards['human_review_completed'] = True
    cards['source_check_evidence_sha256'] = digest(approved)
    save_private(job / 'review-cards.json', cards)
    notes = job / 'research-notes.md'
    notes.write_text('状态：用户已逐项核对来源；未进行领域专家盲评。\n\n' + evidence['markdown'], encoding='utf-8')
    notes.chmod(0o600)
    return {'approved_evidence_sha256': digest(approved), 'dependency_graph_sha256': envelope['graph_sha256'],
            'reviewer_kind': 'Human', 'expert_blind_review_completed': False}


def revise(job, expected_sha, statements, synthesis):
    job = Path(job).resolve()
    evidence, snapshot = read(job / 'evidence.json'), read(job / 'source-snapshot.json')
    validate(evidence, snapshot)
    if digest(evidence) != expected_sha or not isinstance(statements, dict):
        raise ValueError('修订必须针对当前候选稿')
    known = {'claim:' + p['paper_id'] + ':' + f['name'] for p in evidence['draft']['papers'] for f in p['fields']}
    if set(statements) != known or any(not isinstance(s, str) or not 1 <= len(s.strip()) <= 120 for s in statements.values()):
        raise ValueError('每字段需要1–120字符的明确陈述')
    if not isinstance(synthesis, str) or len(synthesis) > 6000:
        raise ValueError('综合分析超长')
    save_private(job / ('candidate-before-edit-' + expected_sha + '.json'), evidence)
    for p in evidence['draft']['papers']:
        for f in p['fields']:
            f['statement'] = statements['claim:' + p['paper_id'] + ':' + f['name']].strip()
    evidence['draft']['synthesis'] = synthesis
    checked = validate(evidence, snapshot)
    evidence.update(markdown=checked['markdown'], research_quality='human_edited_review_pending',
                    claim_support_assessed=False, reviewer_kind='Human editor; approval pending')
    save_private(job / 'edited-evidence.json', evidence)
    return package(job, job / 'edited-evidence.json', job / 'source-snapshot.json')


def main():
    request = json.load(sys.stdin)
    operation = request.pop('operation')
    if operation == 'capture':
        result = capture(**request)
    elif operation == 'package':
        result = package(**request)
    elif operation == 'approve':
        result = approve(**request)
    elif operation == 'repair_plan':
        result = repair_plan(**request)
    elif operation == 'index_automatic':
        result = index_automatic(**request)
    elif operation == 'synthesis_plan':
        result = synthesis_plan(**request)
    elif operation == 'revise':
        result = revise(**request)
    elif operation == 'validate':
        result = validate(read(request['evidence']), read(request['snapshot']))
        if request.get('dependencies'):
            validate_envelope(read(request['dependencies']))
        result = {'source_replay': True, 'gap_count': len(result['gaps'])}
    else:
        raise ValueError('unknown scene support operation')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
