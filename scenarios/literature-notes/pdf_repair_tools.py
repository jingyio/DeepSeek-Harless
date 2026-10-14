"""Claim-scoped semantic repair; bounded local evidence tools, no model loop."""
from __future__ import annotations

import copy
import json
import os
import re
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pdf_dependencies import private_file
from pdf_review_tools import ReviewScene, numeric_gaps
from pdf_tools import digest, save_private, normalized
from claim_coverage import technical_name_gaps

WITHDRAWN = '当前证据不足，原结论已撤回。'
NOT_EXTRACTED = '当前未提取到足够证据。'
POLICY = {'schema_version': 9, 'adjacent_spans_per_side': 1, 'validation_attempts_per_claim': 3, 'searches_per_claim': 2, 'reads_per_claim': 3,
          'window_chars': 6000, 'search_hits': 3, 'max_targets': 100}


def claim_id(pid, name):
    return 'claim:' + pid + ':' + name


class RepairScene(ReviewScene):
    def __init__(self, run: Path, output: Path):
        # Reject symlinks before the inherited source replay.
        for name in ('evidence.json', 'pdf-input-snapshot.json', 'repair-targets.json'):
            private_file(Path(run) / name)
        super().__init__(run, output)
        request = json.loads((self.run / 'repair-targets.json').read_text())
        self.claims = {claim_id(p['paper_id'], f['name']): (p['paper_id'], f)
                       for p in self.evidence['draft']['papers'] for f in p['fields']}
        ids = request.get('claim_ids')
        self.synthesis_only = request.get('synthesis_only') is True
        if (request.get('input_sha256') != self.input_digest or not isinstance(ids, list)
                or not (len(ids) == 0 if self.synthesis_only else 1 <= len(ids) <= POLICY['max_targets'])
                or not all(isinstance(i, str) and i in self.claims for i in ids) or len(set(ids)) != len(ids)):
            raise ValueError('repair targets must uniquely bind the current candidate')
        self.statement_limit = 80 if request.get('scope') == 'claim_support_audit' else 120
        self.targets = ids
        self.request_digest = digest(request)
        self.evidence_first = request.get('review_mode') == 'evidence_first_reextract'
        self.read_claims, self.claim_allowed = set(), {i: set() for i in ids}
        self.usage = {i: {'searches': 0, 'reads': 0} for i in ids}
        self.batch_contexts = {}
        self.completed = False
        self.synthesis_read = False
        self.proposal_provenance = {'kind': 'native_tool_submission'}
        self.runtime_gap_claim_ids = []
        self.rejected_proposals = {}
        self.prior_proposals = request.get('prior_proposals', {})
        if (not isinstance(self.prior_proposals, dict) or set(self.prior_proposals) - set(ids)
                or len(json.dumps(self.prior_proposals)) > 200_000):
            raise ValueError('prior proposal diagnostics must bind selected claims')
        self.accepted, self.validation_attempts = {}, {i: 0 for i in ids}
        self.history = None
        if request.get('history_input_directory'):
            origin = Path(request['history_input_directory'])
            private_file(origin / 'evidence.json')
            private_file(origin / 'pdf-input-snapshot.json')
            self.history = ReviewScene(origin, output)
            if (self.history.input_digest != request.get('history_input_sha256')
                    or digest(self.history.task) != digest(self.task)):
                raise ValueError('repair history does not bind current sources and task')
            # Replay old navigation windows against the current frozen source.
            for c in self.history.evidence['citation_checks']:
                pin = self.scene.pin_pdf_context(c['paper_id'], str(c['page']), c['start'], c['end'] - c['start'])
                if pin['source_id'] != c['source_id'] or pin['version_sha256'] != c['version_sha256']:
                    raise ValueError('repair history source changed')
                self.sources[c['source_id']] = self.scene.read_pinned_pdf_context(c['source_id'])

    def _claim(self, cid, *, read=False):
        if cid not in self.targets or (read and cid not in self.read_claims):
            raise ToolError('read a selected claim packet first; targets cannot be widened')
        return self.claims[cid]

    def _neighbours(self, cid, quotes):
        adjacent, issued = [], {(c['source_id'], c['quote_id']) for c in quotes}
        for quote in quotes:
            sid = quote['source_id']
            context = self.sources[sid]
            spans = context['quote_spans']
            index = next(i for i, span in enumerate(spans) if span['quote_id'] == quote['quote_id'])
            for span in spans[max(0, index - 1):index + 2]:
                key = (sid, span['quote_id'])
                if key in issued: continue
                issued.add(key)
                adjacent.append({'source_id': sid, 'quote_id': span['quote_id'], 'citation_id': span['citation_id'], 'page': context['page'],
                                 'quote': context['text'][span['start']:span['end']]})
                self.claim_allowed[cid].add(key)
        return adjacent

    def read_claim_repair_packet(self, claim_id: str) -> dict:
        """Read one claim and its actual quotes; prior model verdicts are not support evidence."""
        if self.synthesis_only and claim_id == 'synthesis':
            self.synthesis_read = True
            return {'scope': 'synthesis_only', 'input_sha256': self.input_digest, 'question': self.task['question'],
                    'draft': self.evidence['draft'], 'quotes': self.evidence['citation_checks'],
                    'note': 'All source locations replayed. Model statements remain unverified; only write a project hypothesis across the whole question, never revise fields.'}
        pid, field = self._claim(claim_id)
        self.read_claims.add(claim_id)
        quotes = [c for c in self.evidence['citation_checks'] if c['paper_id'] == pid and c['field'] == field['name']]
        quotes = [{**c, 'citation_id': next(s['citation_id'] for s in self.sources[c['source_id']]['quote_spans']
                    if s['quote_id'] == c['quote_id'])} if 'quote_id' in c else dict(c) for c in quotes]
        self.claim_allowed[claim_id].update((c['source_id'], c['quote_id']) for c in quotes)
        previous = None
        if self.history:
            old = next(p for p in self.history.evidence['draft']['papers'] if p['paper_id'] == pid)
            original = next(f for f in old['fields'] if f['name'] == field['name'])
            old_quotes = [c for c in self.history.evidence['citation_checks']
                          if c['paper_id'] == pid and c['field'] == field['name']]
            self.claim_allowed[claim_id].update((c['source_id'], c['quote_id']) for c in old_quotes)
            previous = {'field': original, 'quotes': old_quotes,
                        'note': 'Previous withdrawn hypothesis, not a support verdict. Quotes replayed against current PDF.'}
        metadata = self.scene.prepare_pdf(pid)
        return {'claim_id': claim_id, 'paper_id': pid, 'question': self.task['question'],
                'input_sha256': self.input_digest,
                'review_mode': 'evidence_first_reextract' if self.evidence_first else 'compare_existing_claim',
                'field': ({'name': field['name'], 'note': 'Old wording withheld. Independently extract this field from actual quotes.'}
                          if self.evidence_first else copy.deepcopy(field)), 'quotes': quotes,
                'adjacent_quotes': self._neighbours(claim_id, quotes + (previous['quotes'] if previous else [])),
                'previous_claim_context': previous, 'page_count': len(metadata['pages']),
                'document_version_sha256': metadata['document_version_sha256'],
                'section_navigation': metadata['section_navigation'],
                'prior_rejected_proposal': self.prior_proposals.get(claim_id),
                'diagnostic_note': 'Rejected model hypotheses and validation errors are navigation only; they grant no citation permission or support verdict.',
                'missing_literal_numbers': [] if self.evidence_first else numeric_gaps(field['statement'], [c['quote'] for c in quotes]),
                'policy': {**POLICY, 'max_statement_characters': self.statement_limit, 'support_anchor_required': self.statement_limit == 80}, 'note': 'Assess this field only. Tool checks do not establish semantic support.'}

    def search_claim_evidence(self, claim_id: str, query: str) -> dict:
        """Search this claim's paper literally; hits are navigation, never citations or absence proof."""
        pid, _ = self._claim(claim_id, read=True)
        if self.usage[claim_id]['searches'] >= POLICY['searches_per_claim']:
            raise ToolError('claim search limit reached; narrow or withdraw the unsupported claim')
        self.usage[claim_id]['searches'] += 1
        if not isinstance(query, str) or not 2 <= len(query.strip()) <= 80:
            raise ToolError('use a literal source-language query of 2–80 characters')
        return {'claim_id': claim_id, **self.scene.search_pdf_text(pid, query, limit=POLICY['search_hits'])}

    def read_claim_evidence(self, claim_id: str, page: str, start: int = 0) -> dict:
        """Read a bounded same-paper window with enough preceding text to recover subject/conditions."""
        pid, _ = self._claim(claim_id, read=True)
        if self.usage[claim_id]['reads'] >= POLICY['reads_per_claim']:
            raise ToolError('claim evidence read limit reached; narrow or withdraw the unsupported claim')
        self.usage[claim_id]['reads'] += 1
        pin = self.scene.pin_pdf_context(pid, page, start=start, length=POLICY['window_chars'])
        context = self.scene.read_pinned_pdf_context(pin['source_id'])
        self.sources[pin['source_id']] = context
        self.claim_allowed[claim_id].update((pin['source_id'], s['quote_id']) for s in context['quote_spans'])
        return {'claim_id': claim_id, 'source_id': pin['source_id'], **context}

    def read_claim_evidence_plan(self, claim_id: str, document_version_sha256: str, windows: list[dict]) -> dict:
        """Execute same-claim windows atomically validated against version and remaining read allowance."""
        from pdf_read_plan import validate_windows
        pid, _ = self._claim(claim_id, read=True)
        keys = validate_windows(self.scene, pid, document_version_sha256, windows,
                                maximum=POLICY['reads_per_claim'], total_chars=18000,
                                window_chars=POLICY['window_chars'])
        cache = self.batch_contexts.setdefault(claim_id, {})
        fresh = [key for key in keys if key not in cache]
        if self.usage[claim_id]['reads'] + len(fresh) > POLICY['reads_per_claim']:
            raise ToolError('claim evidence read limit reached; narrow or withdraw the unsupported claim')
        # Charge attempted fresh reads before execution; failed/partial batches cannot reset the allowance.
        self.usage[claim_id]['reads'] += len(fresh)
        if fresh:
            # Keys have already been normalized with this claim's narrower bound.
            # Recompiling with the ordinary reader's 12000 limit could merge
            # them again and silently misalign keys with citation permissions.
            contexts = self.scene._read_validated_windows(pid, document_version_sha256, fresh)
            for key, context in zip(fresh, contexts, strict=True):
                sid = context['source_id']
                cache[key] = context
                self.sources[sid] = context
                self.claim_allowed[claim_id].update((sid, q['quote_id']) for q in context['quote_spans'])
        if document_version_sha256 != self.scene.document_version(pid):
            raise ToolError('source changed during batch; discard this plan')
        return {'claim_id': claim_id, 'contexts': [cache[key] for key in keys],
                'reused_windows': len(keys) - len(fresh), 'remaining_reads': POLICY['reads_per_claim'] - self.usage[claim_id]['reads'],
                'scientific_truth_certified': False, 'learned_motif': False}

    def _number_candidates(self, cid, decision, error):
        """Suggest already-read spans for a literal failure, never certify their relevance."""
        if not error.startswith('selected quotes lack literal numbers:'): return []
        chosen = []
        for c in decision.get('citations', []):
            key = (c.get('source_id'), c.get('quote_id'))
            if key not in self.claim_allowed[cid]: continue
            context = self.sources[key[0]]
            span = next(s for s in context['quote_spans'] if s['quote_id'] == key[1])
            chosen.append(context['text'][span['start']:span['end']])
        missing = numeric_gaps(decision.get('statement', ''), chosen)
        candidates = []
        for sid, qid in sorted(self.claim_allowed[cid]):
            context = self.sources[sid]
            span = next(s for s in context['quote_spans'] if s['quote_id'] == qid)
            quote = context['text'][span['start']:span['end']]
            if any(not numeric_gaps(number, [quote]) for number in missing):
                candidates.append({'source_id': sid, 'quote_id': qid, 'quote': quote,
                                   'note': 'Literal match only; assess subject, version, conditions and support before choosing.'})
                if len(candidates) == 3: break
        return candidates

    def submit_claim_repair(self, decisions: list[dict], synthesis_hypothesis: str) -> dict:
        """Merge exactly the selected decisions; preserve untouched fields and publish a hash receipt."""
        if self.completed:
            raise ToolError('repair already published')
        if (not isinstance(decisions, list) or
                (bool(decisions) or not self.synthesis_read if self.synthesis_only else not 1 <= len(decisions) <= len(self.targets))):
            raise ToolError('submit a nonempty batch within selected targets')
        if not isinstance(synthesis_hypothesis, str) or not 1 <= len(synthesis_hypothesis) <= 600:
            raise ToolError('give a bounded project hypothesis, without relying on withdrawn claims')
        issues, seen_batch = [], set()
        for decision in decisions:
            cid = decision.get('claim_id') if isinstance(decision, dict) else None
            if not isinstance(cid, str) or cid not in self.targets or cid in seen_batch:
                raise ToolError('unknown or duplicate claim; targets cannot be widened')
            seen_batch.add(cid)
            if cid in self.accepted:
                # A repeated accepted decision is a no-op, never another semantic attempt.
                continue
            try:
                if self.validation_attempts[cid] >= POLICY['validation_attempts_per_claim']:
                    if decision.get('verdict') not in ('withdrawn', 'not_extracted'):
                        raise ToolError('validation limit reached; explicitly withdraw or leave not_extracted')
                self.validation_attempts[cid] += 1
                checked = self._validate_decision(decision)
                self.accepted[cid] = checked
            except ToolError as error:
                self.rejected_proposals[cid] = {'proposal': copy.deepcopy(decision), 'validation_error': str(error)}
                issues.append({'claim_id': cid, 'error': str(error),
                               'literal_number_candidates': self._number_candidates(cid, decision, str(error)),
                               'allowed_citations': [{'source_id': sid, 'quote_id': qid}
                                                     for sid, qid in sorted(self.claim_allowed[cid])],
                               'validation_attempts': self.validation_attempts[cid],
                               'remaining_attempts': max(0, POLICY['validation_attempts_per_claim'] - self.validation_attempts[cid])})
        pending = [cid for cid in self.targets if cid not in self.accepted]
        if pending:
            return {'status': 'pending_claim_decisions', 'published': False,
                    'accepted_claim_ids': list(self.accepted), 'pending_claim_ids': pending, 'issues': issues,
                    'instruction': 'Only retry pending claims. Accepted claims are retained, not withdrawn by another claim error.'}
        merged = copy.deepcopy(self.evidence['draft'])
        fields = {claim_id(p['paper_id'], f['name']): f for p in merged['papers'] for f in p['fields']}
        audit_decisions = []
        for cid in self.targets:
            pid, original = self.claims[cid]
            decision = self.accepted[cid]
            verdict = decision['verdict']
            fields[cid].update(status='evidence' if verdict in ('supported', 'revised') else
                               'needs_review' if verdict == 'withdrawn' else 'not_extracted',
                               statement=decision['statement'], citations=copy.deepcopy(decision['citations']))
            audit_decisions.append({'paper_id': pid, 'name': original['name'], **copy.deepcopy(decision),
                                    'original_statement': original['statement']})
        merged['synthesis'] = '本项目假设（尚未被本实验验证）：' + synthesis_hypothesis
        # Replays the current full source inventory, including untouched claims.
        revised = self.scene.preview_research_notes(merged)
        changed = [cid for cid in self.targets if fields[cid] != self.claims[cid][1]]
        unresolved = [cid for cid in self.targets if fields[cid]['status'] != 'evidence']
        revised.update(research_quality='model_synthesis_unverified' if self.synthesis_only else 'model_repaired_unverified', reviewer_kind='model',
                       claim_support_assessed=not self.synthesis_only, semantic_assessment_scope=self.targets,
                       synthesis_assessed=True, synthesis_only=self.synthesis_only,
                       original_evidence_sha256=self.input_digest, proposal_origin=self.proposal_provenance['kind'])
        revised['markdown'] = '智能体自动逐论断复核与修复稿；未解决项明确留缺口，自动审阅可能漏检。\n\n' + revised['markdown']
        audit = {'schema_version': 1, 'input_sha256': self.input_digest, 'task_sha256': digest(self.task),
                 'decisions': audit_decisions, 'revised_evidence_sha256': digest(revised),
                 'target_claim_ids': self.targets, 'repair_request_sha256': self.request_digest, 'untouched_claim_ids': [i for i in self.claims if i not in self.targets],
                 'changed_claim_ids': changed, 'unresolved_claim_ids': unresolved,
                 'policy': {**POLICY, 'max_statement_characters': self.statement_limit, 'support_anchor_required': self.statement_limit == 80}, 'evidence_operations': self.usage, 'validation_attempts': self.validation_attempts,
                 'human_blind_review_completed': False, 'quality_equivalence_established': False,
                 'proposal_provenance': self.proposal_provenance, 'runtime_gap_claim_ids': self.runtime_gap_claim_ids,
                 'rejected_proposals': self.rejected_proposals}
        save_private(self.output / 'revised-evidence.json', revised)
        save_private(self.output / 'claim-review.json', audit)
        self.completed = True
        return {'status': revised['status'], 'input_sha256': self.input_digest,
                'artifact': str(self.output / 'revised-evidence.json'), 'artifact_sha256': digest(revised),
                'audit': str(self.output / 'claim-review.json'), 'audit_sha256': digest(audit),
                'research_quality': revised['research_quality'], 'target_count': len(self.targets),
                'changed_claim_count': len(changed), 'unresolved_claim_ids': unresolved,
                'withdrawn_claim_count': sum(d['verdict'] == 'withdrawn' for d in audit_decisions),
                'gap_count': len(revised['gaps'])}

    def _validate_decision(self, decision):
        cid = decision['claim_id']
        pid, original = self._claim(cid, read=True)
        if (set(decision) - {'claim_id', 'verdict', 'reason', 'statement', 'citations', 'support_anchor'}
                or not {'claim_id', 'verdict', 'reason'} <= set(decision)):
            raise ToolError('requires claim_id/verdict/reason; revised also requires statement/citations')
        value = copy.deepcopy(decision)
        verdict = value['verdict']
        if verdict not in ('supported', 'revised', 'withdrawn', 'not_extracted'):
            raise ToolError('invalid verdict')
        if verdict == 'supported' and self.evidence_first:
            raise ToolError('evidence-first mode requires independently written revised fact or explicit gap, never copying supported')
        if verdict == 'supported':
            value.setdefault('statement', original['statement'])
            value.setdefault('citations', copy.deepcopy(original['citations']))
        elif verdict in ('withdrawn', 'not_extracted'):
            value.setdefault('statement', WITHDRAWN if verdict == 'withdrawn' else NOT_EXTRACTED)
            value.setdefault('citations', [])
        statement, citations = value.get('statement'), value.get('citations')
        if (not isinstance(statement, str) or not 1 <= len(statement) <= self.statement_limit
                or not isinstance(value['reason'], str) or not 1 <= len(value['reason']) <= 400
                or not isinstance(citations, list) or len(citations) > 3):
            raise ToolError(f'statement must be 1–{self.statement_limit} characters (actual: {len(statement) if isinstance(statement, str) else None}); reason 1–400, citations at most three. Narrow to one fact; never truncate automatically.')
        citations = [self.scene.resolve_citation(c) if isinstance(c, dict) and set(c) == {'citation_id'} else c
                     for c in citations]
        value['citations'] = citations
        if verdict == 'supported' and (statement != original['statement'] or citations != original['citations']
                                       or original['status'] != 'evidence'):
            raise ToolError('supported must preserve current evidence exactly; changed or withdrawn claims require revised')
        if verdict in ('supported', 'revised') and not citations:
            raise ToolError('supported/revised requires evidence')
        if verdict in ('withdrawn', 'not_extracted') and (
                citations or statement != (WITHDRAWN if verdict == 'withdrawn' else NOT_EXTRACTED)):
            raise ToolError('gap verdict must use the canonical gap text and no citations')
        quotes = []
        for c in citations:
            if not isinstance(c, dict) or set(c) != {'source_id', 'quote_id'}:
                raise ToolError('use only an issued citation_id or source_id and quote_id')
            sid, qid = c['source_id'], c['quote_id']
            if not isinstance(sid, str) or not isinstance(qid, str) or (sid, qid) not in self.claim_allowed[cid]:
                raise ToolError('evidence was not read for this claim; use its allowed_citations')
            context = self.sources[sid]
            if context['paper_id'] != pid:
                raise ToolError('cross-paper evidence rejected')
            span = next(s for s in context['quote_spans'] if s['quote_id'] == qid)
            quotes.append(context['text'][span['start']:span['end']])
        if self.statement_limit == 80 and verdict in ('supported', 'revised'):
            anchor = value.get('support_anchor')
            if not isinstance(anchor, str) or not 30 <= len(anchor) <= 1600:
                raise ToolError('support audit requires support_anchor: 30–1600 verbatim source characters supporting the entire short fact, from FINAL selected citations only')
            groups = {}
            for c in citations:
                context = self.sources[c['source_id']]
                span = next(q for q in context['quote_spans'] if q['quote_id'] == c['quote_id'])
                groups.setdefault(c['source_id'], []).append(span)
            blocks = []
            for sid, spans in groups.items():
                ordered = sorted(spans, key=lambda q: q['start'])
                begin, end = ordered[0]['start'], ordered[0]['end']
                for span in ordered[1:]:
                    if span['start'] != end:
                        blocks.append(self.sources[sid]['text'][begin:end]); begin = span['start']
                    end = span['end']
                blocks.append(self.sources[sid]['text'][begin:end])
            if not any(normalized(anchor) in normalized(block) for block in blocks):
                raise ToolError('support_anchor is outside FINAL selected continuous quote spans; adjacent/context-only evidence requires revised with its actual citation, never supported unchanged')
            if not re.search(r'[.!?。！？][\s\)\]\}"\u201d\u2019]*$', anchor):
                raise ToolError('support_anchor ends mid-sentence; cite its actual continuation or choose a complete shorter sentence. Sentence punctuation is only a mechanical boundary, not semantic certification.')
            if numeric_gaps(statement, [anchor]) or technical_name_gaps(statement, [anchor]):
                raise ToolError('support_anchor lacks the stated literal numbers or technical names; narrow the fact or choose a complete supporting source sentence; semantic support remains unverified')
        missing = numeric_gaps(statement, quotes) if verdict in ('supported', 'revised') else []
        if missing:
            raise ToolError('selected quotes lack literal numbers: ' + ', '.join(missing)
                            + '; read/choose actual support or narrow this claim only')
        names = technical_name_gaps(statement, quotes) if verdict in ('supported', 'revised') else []
        if names:
            raise ToolError('selected quotes lack technical names: ' + ', '.join(names)
                            + '; read/choose actual source spans or remove the unsupported named detail; this is not semantic certification')
        return value


class DecisionBase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    claim_id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=400)


class CitationId(BaseModel):
    model_config = ConfigDict(extra='forbid')
    citation_id: str = Field(min_length=1)


class QuoteCitation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: str = Field(min_length=1)
    quote_id: str = Field(min_length=1)


class SupportedDecision(DecisionBase):
    verdict: Literal['supported']
    statement: str | None = Field(default=None, min_length=1, max_length=120,
        description='Usually omit: runtime preserves original. If supplied it must equal the original exactly.')
    citations: list[CitationId | QuoteCitation] | None = Field(default=None, min_length=1, max_length=3,
        description='Usually omit: runtime preserves original. If supplied they must equal original citations exactly.')


class AuditSupportedDecision(SupportedDecision):
    statement: str | None = Field(default=None, min_length=1, max_length=80)
    support_anchor: str = Field(min_length=30, max_length=1600)


class RevisedDecision(DecisionBase):
    verdict: Literal['revised']
    statement: str = Field(min_length=1, max_length=120)
    citations: list[CitationId | QuoteCitation] = Field(min_length=1, max_length=3)


class AuditRevisedDecision(RevisedDecision):
    statement: str = Field(min_length=1, max_length=80)
    support_anchor: str = Field(min_length=30, max_length=1600)


class GapDecision(DecisionBase):
    verdict: Literal['withdrawn', 'not_extracted']


NormalDecision = Annotated[SupportedDecision | RevisedDecision | GapDecision, Field(discriminator='verdict')]
AuditDecision = Annotated[AuditSupportedDecision | AuditRevisedDecision | GapDecision, Field(discriminator='verdict')]


def make_server(scene):
    server = MCPServer('Bounded claim repair')
    for fn in (scene.read_claim_repair_packet, scene.search_claim_evidence,
               scene.read_claim_evidence, scene.read_claim_evidence_plan):
        server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(fn)
    def submit_audit(decisions: list[AuditDecision], synthesis_hypothesis: str) -> dict:
        """Support audit: supported needs a verbatim anchor; revised also needs a short fact and final citations. Gap verdicts need only claim_id, verdict, reason. Source/semantic checks still run."""
        return scene.submit_claim_repair([d.model_dump(exclude_none=True) for d in decisions], synthesis_hypothesis)
    def submit_normal(decisions: list[NormalDecision], synthesis_hypothesis: str) -> dict:
        """Repair: supported preserves the original fact and citations; revised supplies both; gap verdicts need only claim_id, verdict, reason."""
        return scene.submit_claim_repair([d.model_dump(exclude_none=True) for d in decisions], synthesis_hypothesis)
    server.tool(name='submit_claim_repair', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(
        submit_audit if scene.statement_limit == 80 else submit_normal)
    return server


if __name__ == '__main__':
    make_server(RepairScene(Path(os.environ['SSS_PDF_REPAIR_RUN']),
                            Path(os.environ['SSS_PDF_REPAIR_OUTPUT']))).run(transport='stdio')
