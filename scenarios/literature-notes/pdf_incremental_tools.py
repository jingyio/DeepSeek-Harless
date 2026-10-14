"""Scene MCP operations; dependency control is delegated to the TypeScript policy."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pdf_tools import ROOT, FIELDS, PdfScene, digest, inventory, save_private
from pdf_dependencies import inputs, evaluate, private_file, validate_envelope
from pdf_review_tools import numeric_gaps
from claim_coverage import technical_name_gaps
from bibliography_tools import preview_bibliography


class IncrementalScene(PdfScene):
    def __init__(self, envelope_path, directory, task, output, *, revoked_path=None):
        self.envelope_path = private_file(envelope_path)
        self.envelope = json.loads(self.envelope_path.read_text())
        self.graph = validate_envelope(self.envelope)
        self.revoked_path = private_file(revoked_path) if revoked_path else None
        self.output = Path(output).resolve()
        if not self.output.is_relative_to(ROOT / '.local'):
            raise ValueError('incremental output must remain private')
        super().__init__(Path(directory), ROOT / '.local/literature-notes/pdf-cache', task)
        self.plan_read = False
        self.read_retained = set()
        self.initial_plan = self._plan()

    def _plan(self):
        if json.loads(self.envelope_path.read_text()) != self.envelope:
            raise ToolError('dependency envelope changed during execution')
        if inventory(self.root) != self.task['sources']:
            raise ToolError('current PDF inventory changed during execution')
        audit = json.loads(private_file(self.graph['audit_path']).read_text())
        evidence = json.loads(private_file(self.graph['evidence_path']).read_text())
        snapshot = json.loads(private_file(self.graph['snapshot_path']).read_text())
        if (digest(evidence) != self.graph['baseline_evidence_sha256']
                or snapshot['task'] != self.graph['task']):
            raise ToolError('baseline evidence or snapshot changed')
        revoked = []
        if self.revoked_path:
            value = json.loads(private_file(self.revoked_path).read_text())
            if set(value) != {'revoked_claim_ids'}:
                raise ToolError('revocation file requires revoked_claim_ids')
            revoked = value['revoked_claim_ids']
        return evaluate(self.envelope, {'inputs': inputs(self, digest(audit),
            automatic=self.graph.get('reuse_policy') == 'automatic_source_bound_unverified'), 'revoked_claim_ids': revoked})

    def read_update_plan(self) -> dict:
        """Read a fresh dependency plan; no source version can certify scientific truth."""
        plan = self._plan()
        self.plan_read = True
        retained = set(plan['retained_claim_ids'])
        work = []
        for pid, row in self.rows.items():
            names = [name for name in FIELDS if 'claim:' + pid + ':' + name not in retained]
            if names:
                old = [self.graph['fields'][cid] for cid in self.graph['fields']
                       if self.graph['fields'][cid]['paper_id'] == pid
                       and self.graph['fields'][cid]['field']['name'] in names]
                work.append({'paper_id': pid, 'filename': row['filename'], 'fields_to_review': names,
                             'previous_claims': old,
                             'warning': 'Previous quotes are stale navigation data. Read current PDF evidence before using any citation.'})
        removed = sorted(set(self.graph['task']['sources']['papers'][i]['paper_id']
                             for i in range(len(self.graph['task']['sources']['papers']))) - set(self.rows))
        synthesis = next(n for n in plan['nodes'] if n['id'] == 'synthesis')
        return {'question': self.task['question'], 'task_sha256': digest(self.task),
                'plan_sha256': digest(plan), 'retained_claim_ids': plan['retained_claim_ids'],
                'invalidated_claim_ids': plan['invalidated_claim_ids'], 'work': work,
                'removed_paper_ids': removed, 'synthesis_requires_review': not synthesis['reusable_candidate'],
                'previous_synthesis': self.graph['synthesis'], 'scientific_truth_certified': False,
                'learned_motif': False, 'authority': self.graph['quality_authority']}

    def read_previous_claims(self, paper_id: str) -> dict:
        """Expose only dependency-valid previously source-checked claims; preserve their review limits."""
        if not self.plan_read or paper_id not in self.rows:
            raise ToolError('read the plan first and choose a current paper')
        plan = self._plan()
        fields = []
        for cid in plan['retained_claim_ids']:
            value = self.graph['fields'][cid]
            if value['paper_id'] == paper_id:
                fields.append(copy.deepcopy(value))
                self.read_retained.add(cid)
        return {'paper_id': paper_id, 'retained_fields': fields,
                'review_status': self.graph['quality_authority'], 'scientific_truth_certified': False}

    def _retain(self, retained):
        """Recheck exact raw spans mechanically; this does not reread them with a model."""
        for cid in retained:
            for c in self.graph['fields'][cid]['citation_checks']:
                pin = self.pin_pdf_context(c['paper_id'], str(c['page']), c['start'], c['end'] - c['start'])
                if pin['source_id'] != c['source_id'] or pin['version_sha256'] != c['version_sha256']:
                    raise ToolError('retained citation changed')
                self.read_pinned_pdf_context(pin['source_id'])

    def publish(self, update, *, automatic=False, persist=True):
        plan = self._plan()
        if automatic:
            if plan['invalidated_claim_ids'] or set(self.rows) != {
                    p['paper_id'] for p in self.graph['task']['sources']['papers']}:
                raise ToolError('automatic delivery requires a fully unchanged dependency plan')
        elif not self.plan_read:
            raise ToolError('read update plan before submission')
        if not isinstance(update, dict) or set(update) != {'papers', 'synthesis_hypothesis'}:
            raise ToolError('update requires papers and synthesis_hypothesis')
        retained = set(plan['retained_claim_ids'])
        expected = {'claim:' + pid + ':' + name for pid in self.rows for name in FIELDS} - retained
        changes, decisions = {}, []
        if not isinstance(update['papers'], list):
            raise ToolError('papers must be a list of changed fields')
        seen_papers = set()
        for p in update['papers']:
            if (not isinstance(p, dict) or set(p) != {'paper_id', 'fields'} or p['paper_id'] not in self.rows
                    or p['paper_id'] in seen_papers or not isinstance(p['fields'], list) or not p['fields']):
                raise ToolError('unknown, duplicate or empty changed paper')
            pid = p['paper_id']; seen_papers.add(pid)
            for f in p['fields']:
                if not isinstance(f, dict) or set(f) != {'name', 'verdict', 'reason', 'statement', 'citations'}:
                    raise ToolError('field requires name/verdict/reason/statement/citations')
                if not isinstance(f['name'], str) or f['name'] not in FIELDS:
                    raise ToolError('unknown evidence field')
                cid = 'claim:' + pid + ':' + f['name']
                if cid not in expected or cid in changes:
                    raise ToolError('cannot replace retained or duplicate fields')
                if (f['verdict'] not in ('revised', 'not_extracted', 'needs_review')
                        or not isinstance(f['reason'], str) or not 1 <= len(f['reason']) <= 400
                        or not isinstance(f['statement'], str) or not 1 <= len(f['statement']) <= 120
                        or not isinstance(f['citations'], list) or len(f['citations']) > 3):
                    issues = []
                    for candidate in p['fields']:
                        if not isinstance(candidate, dict): continue
                        label = 'claim:' + pid + ':' + str(candidate.get('name'))
                        for key, lower, upper in [('statement', 1, 120), ('reason', 1, 400)]:
                            value = candidate.get(key)
                            if not isinstance(value, str) or not lower <= len(value) <= upper:
                                issues.append({'claim_id': label, 'parameter': key,
                                               'actual_characters': len(value) if isinstance(value, str) else None,
                                               'allowed_characters': [lower, upper]})
                        if candidate.get('verdict') not in ('revised', 'not_extracted', 'needs_review'):
                            issues.append({'claim_id': label, 'parameter': 'verdict',
                                           'allowed': ['revised', 'not_extracted', 'needs_review']})
                        citations = candidate.get('citations')
                        if not isinstance(citations, list) or len(citations) > 3:
                            issues.append({'claim_id': label, 'parameter': 'citations', 'maximum': 3})
                    raise ToolError('invalid bounded reviewer decision: ' + json.dumps(
                        {'issues': issues, 'action': 'Correct only these parameters; do not drop required fields or relax source checks.'},
                        ensure_ascii=False))
                quotes = []
                for c in f['citations']:
                    if not isinstance(c, dict) or set(c) != {'source_id', 'quote_id'}:
                        raise ToolError('use current source_id and quote_id')
                    if c['source_id'] not in self.delivered:
                        raise ToolError('changed claims require current evidence read in this session')
                    context = self.read_pinned_pdf_context(c['source_id'])
                    span = next((s for s in context['quote_spans'] if s['quote_id'] == c['quote_id']), None)
                    if context['paper_id'] != pid or span is None:
                        raise ToolError('unknown or cross-paper quote span')
                    quotes.append(context['text'][span['start']:span['end']])
                if f['verdict'] == 'revised' and (not quotes or numeric_gaps(f['statement'], quotes)):
                    raise ToolError('revised fact requires citations containing its literal numbers: ' + json.dumps(
                        {'claim_id': cid, 'missing_literal_numbers': numeric_gaps(f['statement'], quotes),
                         'citation_count': len(quotes), 'semantic_support_certified': False}, ensure_ascii=False))
                names = technical_name_gaps(f['statement'], quotes) if f['verdict'] == 'revised' else []
                if names:
                    raise ToolError('selected quotes lack technical names: ' + json.dumps(
                        {'claim_id': cid, 'missing_technical_names': names, 'semantic_support_certified': False,
                         'action': 'Read/choose actual source spans or remove the unsupported named detail.'}, ensure_ascii=False))
                changes[cid] = {'name': f['name'], 'status': 'evidence' if f['verdict'] == 'revised'
                                else f['verdict'], 'statement': f['statement'], 'citations': copy.deepcopy(f['citations'])}
                decisions.append({'paper_id': pid, **copy.deepcopy(f)})
        if set(changes) != expected:
            raise ToolError('review every invalidated or new field exactly once: ' + json.dumps(
                {'missing_claim_ids': sorted(expected - set(changes)),
                 'unexpected_claim_ids': sorted(set(changes) - expected)}, ensure_ascii=False))
        hypothesis = update['synthesis_hypothesis']
        if not isinstance(hypothesis, str) or len(hypothesis) > 600:
            raise ToolError('use a bounded project hypothesis')
        synthesis_state = next(n for n in plan['nodes'] if n['id'] == 'synthesis')
        if synthesis_state['reusable_candidate']:
            if hypothesis: raise ToolError('unchanged synthesis must be retained')
            synthesis = self.graph['synthesis']
        else:
            if not hypothesis.strip(): raise ToolError('changed synthesis requires a new bounded hypothesis')
            synthesis = '本项目假设（尚未被本实验验证）：' + hypothesis
        self._retain(retained)
        papers = [{'paper_id': pid, 'fields': [copy.deepcopy(self.graph['fields']['claim:' + pid + ':' + name]['field'])
                  if 'claim:' + pid + ':' + name in retained else changes['claim:' + pid + ':' + name]
                  for name in FIELDS]} for pid in self.rows]
        payload = self.preview_research_notes({'papers': papers, 'synthesis': synthesis})
        if self._plan() != plan:
            raise ToolError('dependency plan changed before publication')
        audit = {'graph_sha256': self.envelope['graph_sha256'], 'plan_sha256': digest(plan),
                 'task_sha256': digest(self.task), 'retained_claim_ids': sorted(retained),
                 'synthesis_requires_review': not synthesis_state['reusable_candidate'],
                 'reviewed_field_count': len(changes), 'decisions': decisions,
                 'submitted_update': copy.deepcopy(update),
                 'authority': self.graph['quality_authority'], 'learned_motif': False,
                 'scientific_truth_certified': False, 'human_expert_blind_review_completed': False,
                 'reused_without_model_field_count': len(retained),
                 'verified_motif_model_requests_skipped': 0,
                 'update_quality': 'model_draft_pending_independent_support_review' if changes else
                     'inherited_model_content_unverified' if self.graph.get('reuse_policy') == 'automatic_source_bound_unverified'
                     else 'inherited_source_check_expert_review_pending'}
        payload.update(research_quality=audit['update_quality'], reviewer_kind='incremental',
                       incremental_audit=audit, claim_support_assessed=False)
        payload['markdown'] = ('增量整理：复用 ' + str(len(retained)) + ' 个来源未变化的字段，重新处理 '
                               + str(len(changes)) + ' 个字段；自动检查不能保证科研判断正确。\n\n' + payload['markdown'])
        if not persist:
            return payload
        save_private(self.output / 'incremental-evidence.json', payload)
        save_private(self.output / 'incremental-audit.json', audit)
        return {'status': payload['status'], 'artifact': str(self.output / 'incremental-evidence.json'),
                'artifact_sha256': digest(payload), 'plan_sha256': digest(plan),
                'task_sha256': digest(self.task), 'retained_field_count': len(retained),
                'reviewed_field_count': len(changes), 'gap_count': len(payload['gaps']),
                'research_quality': payload['research_quality'], 'application_enabled': False}

    def submit_incremental_update(self, update: dict) -> dict:
        """Validate changed-only decisions, merge immutable retained fields and save a private preview."""
        return self.publish(update)


def make_server(scene):
    server = MCPServer('Incremental local PDF evidence')
    for fn in (scene.list_pdfs, scene.prepare_pdf, scene.search_pdf_text, scene.pin_pdf_context,
               scene.read_pinned_pdf_context, scene.read_pdf_evidence_plan, scene.read_update_plan, scene.read_previous_claims,
               scene.submit_incremental_update, preview_bibliography):
        server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(fn)
    return server


if __name__ == '__main__':
    task = json.loads(Path(os.environ['SSS_PDF_TASK_FILE']).read_text())
    make_server(IncrementalScene(os.environ['SSS_PDF_DEPENDENCIES'], os.environ['SSS_PDF_ROOT'], task,
                os.environ['SSS_PDF_INCREMENTAL_OUTPUT'], revoked_path=os.environ.get('SSS_PDF_REVOKED') or None)).run(transport='stdio')
