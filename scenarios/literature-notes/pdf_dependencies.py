"""Offline evidence dependency compiler and bridge to the scene TypeScript guard."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
from pdf_tools import ROOT, FIELDS, PdfScene, digest, inventory, save_private

HERE = Path(__file__).resolve().parent
POLICY = HERE / 'pdf-incremental-policy.ts'


def private_file(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT / '.local'):
        raise ValueError('dependency evidence must be a private regular file')
    return path.resolve()


def contract_version():
    # Conservative local contract: includes actual reader and incremental publication code.
    names = ['pdf_layout.py', 'claim_coverage.py', 'pdf_read_plan.py', 'pdf-scenario.json', 'pdf-incremental-scenario.json', 'pdf-repair-scenario.json', 'pdf_tools.py', 'pdf-contracts.json', 'pdf-version-fields.json',
             'pdf_incremental_tools.py', 'pdf_review_tools.py', 'pdf-incremental-policy.ts', 'pdf_dependencies.py',
             'research-checklist.md']
    return digest({**{name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in names},
                   'completion_guard': hashlib.sha256((ROOT / 'src/adapters/dsh_completion_guard.ts').read_bytes()).hexdigest()})


def automatic_workflow_version():
    names = ['agent.ts', 'decision-log.ts', 'agent-support.py', 'pdf-task.md', 'pdf-incremental-task.md', 'pdf-repair-task.md',
             'pdf_repair_tools.py', 'repair-pdf.py', 'review-pdf.py', 'pdf_repair_recovery.py', 'run-incremental.py']
    return digest({name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in names})


def inputs(scene, review_digest, *, automatic=False):
    versions = {'parser': digest(scene.profile), 'contract': contract_version(),
                'question': digest(scene.task['question']), 'selection': digest(sorted(scene.rows)),
                'review_attestation': review_digest}
    versions.update({'pdf:' + pid: row['pdf_sha256'] for pid, row in scene.rows.items()})
    if automatic: versions['workflow'] = automatic_workflow_version()
    return versions


def compile_graph(evidence_path, audit_path, snapshot_path, *, _baseline_versions=None):
    evidence_path, audit_path, snapshot_path = map(private_file, (evidence_path, audit_path, snapshot_path))
    evidence = json.loads(evidence_path.read_text()); audit = json.loads(audit_path.read_text())
    task = json.loads(snapshot_path.read_text())['task']
    reviewer = evidence.get('reviewer_kind')
    qualities = {'Codex': 'codex_source_checked_expert_blind_review_pending',
                 'Human': 'human_source_checked_expert_blind_review_pending',
                 'Runtime': 'runtime_source_bound_model_content_unverified'}
    automatic = reviewer == 'Runtime'
    if (digest(evidence) != audit.get('source_checked_evidence_sha256')
            or evidence.get('task_sha256') != digest(task)
            or reviewer not in qualities or evidence.get('research_quality') != qualities[reviewer]
            or audit.get('source_checked_by') != reviewer
            or (reviewer == 'Human' and audit.get('synthesis_reviewed') is not True)):
        raise ValueError('source-checked artifact and explicit review attestation required')
    decisions = {(d['paper_id'], d['field']): d for d in audit['decisions']}
    if len(decisions) != len(audit['decisions']):
        raise ValueError('duplicate support decisions')
    if _baseline_versions is None:
        scene = PdfScene(Path(task['sources']['root']), ROOT / '.local/literature-notes/pdf-cache', task)
        for c in evidence['citation_checks']:
            pin = scene.pin_pdf_context(c['paper_id'], str(c['page']), c['start'], c['end'] - c['start'])
            if pin['source_id'] != c['source_id'] or pin['version_sha256'] != c['version_sha256']:
                raise ValueError('baseline evidence source changed')
            scene.read_pinned_pdf_context(pin['source_id'])
        verified = scene.preview_research_notes(evidence['draft'])
        if verified['citation_checks'] != evidence['citation_checks'] or (verified['gaps'] and not automatic):
            raise ValueError('baseline citations or completeness differ')
        versions = inputs(scene, digest(audit), automatic=automatic)
        if automatic and versions['workflow'] != audit.get('workflow_sha256'):
            raise ValueError('automatic source index workflow changed')
    else:
        # Validation must work after the original PDFs change. The graph was compiled
        # while original citations were live; publication rechecks each retained span.
        versions = dict(_baseline_versions)
        expected = {'question': digest(task['question']),
                    'selection': digest(sorted(p['paper_id'] for p in task['sources']['papers'])),
                    'review_attestation': digest(audit)}
        expected.update({'pdf:' + p['paper_id']: p['pdf_sha256'] for p in task['sources']['papers']})
        if automatic: expected['workflow'] = audit['workflow_sha256']
        if (set(versions) != set(expected) | {'parser', 'contract'}
                or any(versions.get(k) != v for k, v in expected.items())):
            raise ValueError('baseline version provenance differs')
    nodes = [{'id': k, 'kind': 'input', 'deps': [], 'version': v} for k, v in versions.items()]
    seen, fields, notes = set(), {}, []
    for paper in evidence['draft']['papers']:
        pid = paper['paper_id']; parse = 'parse:' + pid
        nodes.append({'id': parse, 'kind': 'parse', 'deps': ['pdf:' + pid, 'parser']})
        claim_ids = []
        for f in paper['fields']:
            cid = 'claim:' + pid + ':' + f['name']; deps = []
            for c in evidence['citation_checks']:
                if c['paper_id'] != pid or c['field'] != f['name']: continue
                qid = 'citation:' + c['source_id'] + ':' + c['quote_id']
                if qid not in seen:
                    nodes.append({'id': qid, 'kind': 'citation', 'deps': [parse, 'contract']}); seen.add(qid)
                deps.append(qid)
            decision = decisions.get((pid, f['name']), {})
            actual_locators = [{'physical_page': c['page'], 'window_start': c['start'],
                                'quote_id': c.get('quote_id')} for c in evidence['citation_checks']
                               if c['paper_id'] == pid and c['field'] == f['name']]
            approved = (bool(deps) and f['status'] == 'evidence'
                        and all('quote_id' in c for c in evidence['citation_checks']
                                if c['paper_id'] == pid and c['field'] == f['name'])
                        and decision.get('source_binding_by' if automatic else 'semantic_verdict_by') == reviewer
                        and decision.get('source_locators') == actual_locators
                        and decision.get('source_checked_statement') == f['statement'])
            if automatic:
                from pdf_review_tools import numeric_gaps
                approved = approved and not numeric_gaps(f['statement'], [c['quote'] for c in evidence['citation_checks']
                    if c['paper_id'] == pid and c['field'] == f['name']])
            if not approved and not automatic: raise ValueError('missing per-claim support review')
            nodes.append({'id': cid, 'kind': 'claim', 'deps': sorted(set(deps)) +
                          ([parse, 'contract', 'question', 'review_attestation', 'workflow'] if automatic else
                           ['question', 'selection', 'review_attestation']),
                          **({'source_bound': approved} if automatic else {'reviewed': approved})})
            fields[cid] = {'paper_id': pid, 'field': f, 'citation_checks': [
                c for c in evidence['citation_checks'] if c['paper_id'] == pid and c['field'] == f['name']]}
            claim_ids.append(cid)
        nid = 'note:' + pid; nodes.append({'id': nid, 'kind': 'note', 'deps': claim_ids}); notes.append(nid)
    nodes.append({'id': 'synthesis', 'kind': 'synthesis', 'deps': notes + ['question', 'selection']})
    graph = {'schema_version': 1, 'nodes': nodes, 'fields': fields, 'task': task,
             'synthesis': evidence['draft']['synthesis'], 'baseline_evidence_sha256': digest(evidence),
             'audit_path': str(audit_path), 'evidence_path': str(evidence_path),
             'snapshot_path': str(snapshot_path), 'review_attestation_sha256': digest(audit),
             'quality_authority': ('Runtime exact source binding; inherited model content remains scientifically unverified'
                                  if automatic else reviewer + ' source comparison; human expert blind review pending'),
             **({'reuse_policy': 'automatic_source_bound_unverified'} if automatic else {}),
             'builder': 'explicit evidence dependencies; not a learned Motif'}
    return {'graph': graph, 'graph_sha256': digest(graph)}


def evaluate(envelope, current):
    result = subprocess.run(['node', str(POLICY), '--stdio'], input=json.dumps({**envelope, 'current': current},
        ensure_ascii=False), text=True, capture_output=True, timeout=20)
    if result.returncode: raise ValueError('dependency guard rejected input: ' + result.stderr.strip())
    return json.loads(result.stdout)


def validate_envelope(envelope):
    if not isinstance(envelope, dict) or set(envelope) != {'graph', 'graph_sha256'}:
        raise ValueError('invalid dependency envelope')
    graph = envelope['graph']
    if digest(graph) != envelope['graph_sha256']:
        raise ValueError('dependency graph digest mismatch')
    # Recompile from the independently checked original; graph fields cannot invent approvals.
    versions = {n['id']: n['version'] for n in graph['nodes'] if n['kind'] == 'input'}
    fresh = compile_graph(graph['evidence_path'], graph['audit_path'], graph['snapshot_path'],
                          _baseline_versions=versions)
    if fresh != envelope:
        raise ValueError('dependency graph or support attestation changed; recompile')
    return graph


def current_scene(graph, directory, question=None):
    task = {'schema_version': 1, 'question': question if question is not None else graph['task']['question'],
            'sources': inventory(Path(directory))}
    return PdfScene(Path(directory), ROOT / '.local/literature-notes/pdf-cache', task)
