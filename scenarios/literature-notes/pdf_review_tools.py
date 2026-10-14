"""Evidence-bound semantic review tools; no model loop or automatic truth certification."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pdf_tools import FIELDS, ROOT, PdfScene, digest, save_private


def numeric_gaps(statement, quotes):
    """A warning about literal numbers, never an entailment decision."""
    digits = {'零': '0', '〇': '0', '一': '1', '二': '2', '两': '2', '三': '3', '四': '4',
              '五': '5', '六': '6', '七': '7', '八': '8', '九': '9'}

    def decimal(match):
        left, right = match.group().split('点')
        if '十' in left:
            tens, ones = left.split('十')
            integer = str(int(digits.get(tens, '1')) * 10 + int(digits.get(ones, '0')))
        else:
            integer = ''.join(digits[c] for c in left)
        return integer + '.' + ''.join(digits[c] for c in right)

    # Keep this narrow: scientific decimals such as 三点七 / 八十四点二.
    # Do not turn ordinary words such as 一致/一并 into numeric claims.
    def values(text):
        normalized = re.sub(r'(?:[一二两三四五六七八九]?十[零〇一二两三四五六七八九]?|[零〇一二两三四五六七八九]{1,3})点[零〇一二两三四五六七八九]+', decimal, text)
        return set(re.findall(r'\d+(?:\.\d+)?', normalized))

    numbers = values(statement)
    available = values('\n'.join(quotes))
    return sorted(numbers - available)


class ReviewScene:
    def __init__(self, run: Path, output: Path):
        self.run, self.output = run.resolve(), output.resolve()
        for path in (self.run, self.output):
            if not path.is_relative_to(ROOT / '.local'):
                raise ValueError('review inputs and outputs must remain private')
        self.evidence = json.loads((self.run / 'evidence.json').read_text())
        snapshot = json.loads((self.run / 'pdf-input-snapshot.json').read_text())
        self.task = snapshot['task']
        if self.evidence['task_sha256'] != digest(self.task):
            raise ValueError('evidence and frozen task differ')
        # Freeze reviewed input. A later process checks this digest too.
        self.input_digest = digest(self.evidence)
        self.scene = PdfScene(Path(self.task['sources']['root']), ROOT / '.local/literature-notes/pdf-cache', self.task)
        self.sources, self.allowed, self.packets_read = {}, set(), set()
        # Reconstruct only original cited windows; exact identity and original quotes must match.
        for citation in self.evidence['citation_checks']:
            sid = citation['source_id']
            if sid not in self.sources:
                pin = self.scene.pin_pdf_context(citation['paper_id'], str(citation['page']),
                    start=citation['start'], length=max(1, citation['end'] - citation['start']))
                if pin['source_id'] != sid or pin['version_sha256'] != citation['version_sha256']:
                    raise ValueError('original source window is stale or inconsistent')
                self.sources[sid] = self.scene.read_pinned_pdf_context(sid)
        verified = self.scene.preview_research_notes(self.evidence['draft'])
        if verified['citation_checks'] != self.evidence['citation_checks']:
            raise ValueError('original citation checks differ from current source')

    def read_review_packet(self, paper_id: str) -> dict:
        """Read original statements and their exact selected quotes; no implicit support approval."""
        paper = next((p for p in self.evidence['draft']['papers'] if p['paper_id'] == paper_id), None)
        if paper is None:
            raise ToolError('paper is outside this frozen draft')
        self.packets_read.add(paper_id)
        cards = []
        for field in paper['fields']:
            quotes = [c for c in self.evidence['citation_checks']
                      if c['paper_id'] == paper_id and c['field'] == field['name']]
            for quote in quotes:
                if 'quote_id' in quote:
                    self.allowed.add((quote['source_id'], quote['quote_id']))
            cards.append({'field': field['name'], 'status': field['status'], 'statement': field['statement'],
                          'quotes': quotes, 'missing_literal_numbers': numeric_gaps(field['statement'], [c['quote'] for c in quotes])})
        return {'paper_id': paper_id, 'question': self.task['question'], 'input_sha256': self.input_digest,
                'claims': cards, 'available_source_ids': [sid for sid, c in self.sources.items() if c['paper_id'] == paper_id],
                'note': 'Quotes are literal evidence, not certified facts. Read a named window to repair truncated evidence.'}

    def read_review_evidence(self, paper_id: str, source_id: str = '', page: str = '', start: int = 0) -> dict:
        """Read an issued window or explicitly selected page of this frozen paper to repair missing evidence."""
        if paper_id not in self.packets_read or bool(source_id) == bool(page):
            raise ToolError('read the paper packet first, then supply exactly one source_id or decimal page')
        if page:
            pin = self.scene.pin_pdf_context(paper_id, page, start=start)
            source_id = pin['source_id']
            self.sources[source_id] = self.scene.read_pinned_pdf_context(source_id)
        elif source_id not in self.sources or start != 0:
            raise ToolError('unknown source_id or conflicting window offset')
        context = self.sources[source_id]
        if context['paper_id'] != paper_id:
            raise ToolError('cross-paper source rejected')
        context = self.scene.read_pinned_pdf_context(source_id)
        self.allowed.update((source_id, span['quote_id']) for span in context['quote_spans'])
        return {'source_id': source_id, **context}

    def submit_claim_review(self, review: dict) -> dict:
        """Validate complete reviewer decisions and fresh citations; save a model-reviewed derivative, never overwrite the draft."""
        if not isinstance(review, dict) or set(review) != {'papers', 'synthesis_hypothesis'}:
            raise ToolError('review requires papers and synthesis_hypothesis')
        expected = {p['paper_id']: p for p in self.evidence['draft']['papers']}
        if self.packets_read != set(expected) or not isinstance(review['papers'], list) or len(review['papers']) != len(expected):
            raise ToolError('read and review every selected paper')
        hypothesis = review['synthesis_hypothesis']
        if not isinstance(hypothesis, str) or not 1 <= len(hypothesis) <= 600:
            raise ToolError('hypothesis must be a bounded project proposal, not a new paper fact')
        draft, decisions, seen = {'papers': [], 'synthesis': '本项目假设（尚未被本实验验证）：' + hypothesis}, [], set()
        for paper in review['papers']:
            if not isinstance(paper, dict) or set(paper) != {'paper_id', 'fields'}:
                raise ToolError('paper requires paper_id and fields')
            pid = paper['paper_id']
            if pid not in expected or pid in seen:
                raise ToolError('unknown or duplicate paper')
            seen.add(pid)
            originals = {f['name']: f for f in expected[pid]['fields']}
            if not isinstance(paper['fields'], list) or len(paper['fields']) != len(FIELDS):
                raise ToolError('review all five fields')
            fields, names = [], set()
            for field in paper['fields']:
                if not isinstance(field, dict) or set(field) != {'name', 'verdict', 'reason', 'statement', 'citations'}:
                    raise ToolError('field requires name/verdict/reason/statement/citations')
                name, verdict = field['name'], field['verdict']
                if name not in FIELDS or name in names or verdict not in ('supported', 'revised', 'not_extracted', 'needs_review'):
                    raise ToolError('invalid field/verdict')
                names.add(name)
                if (not isinstance(field['reason'], str) or not 1 <= len(field['reason']) <= 400
                        or not isinstance(field['statement'], str) or not 1 <= len(field['statement']) <= 120
                        or not isinstance(field['citations'], list) or len(field['citations']) > 3):
                    raise ToolError('use one short fact and a bounded reviewer reason')
                if verdict == 'supported' and (field['statement'] != originals[name]['statement']
                        or field['citations'] != originals[name]['citations']):
                    raise ToolError('supported must preserve the original claim and citations; changes require revised')
                if verdict in ('supported', 'revised') and not field['citations']:
                    raise ToolError('supported/revised fact requires evidence')
                quotes = []
                for citation in field['citations']:
                    if not isinstance(citation, dict) or set(citation) != {'source_id', 'quote_id'}:
                        raise ToolError('use only source_id and quote_id')
                    sid, qid = citation['source_id'], citation['quote_id']
                    if not isinstance(sid, str) or not isinstance(qid, str) or (sid, qid) not in self.allowed:
                        raise ToolError('reviewer has not read this evidence span')
                    context = self.sources[sid]
                    if context['paper_id'] != pid:
                        raise ToolError('cross-paper citation rejected')
                    span = next(s for s in context['quote_spans'] if s['quote_id'] == qid)
                    quotes.append(context['text'][span['start']:span['end']])
                if verdict in ('supported', 'revised') and numeric_gaps(field['statement'], quotes):
                    raise ToolError('claim contains numbers absent from its selected quotes; revise or mark needs_review')
                status = 'evidence' if verdict in ('supported', 'revised') else verdict
                fields.append({'name': name, 'status': status, 'statement': field['statement'], 'citations': field['citations']})
                decisions.append({'paper_id': pid, **copy.deepcopy(field), 'original_statement': originals[name]['statement']})
            draft['papers'].append({'paper_id': pid, 'fields': fields})
        # Recheck files and parser versions at final publication, including spans exposed earlier.
        revised = self.scene.preview_research_notes(draft)
        revised.update(research_quality='model_reviewed_human_unverified', claim_support_assessed=True,
                       reviewer_kind='model', original_evidence_sha256=self.input_digest)
        revised['markdown'] = revised['markdown'].replace('模型草稿，尚未审阅', '自动语义审阅后的项目假设')
        revised['markdown'] = '自动语义审阅修订稿；模型审阅不等于人类专家验收。\n\n' + revised['markdown']
        audit = {'input_sha256': self.input_digest, 'task_sha256': digest(self.task), 'decisions': decisions,
                 'revised_evidence_sha256': digest(revised), 'human_blind_review_completed': False,
                 'quality_equivalence_established': False, 'review': review}
        save_private(self.output / 'revised-evidence.json', revised)
        save_private(self.output / 'claim-review.json', audit)
        return {'status': revised['status'], 'input_sha256': self.input_digest,
                'artifact': str(self.output / 'revised-evidence.json'), 'artifact_sha256': digest(revised),
                'research_quality': revised['research_quality'], 'decisions': len(decisions), 'gap_count': len(revised['gaps'])}


def make_server(scene):
    server = MCPServer('PDF claim support review')
    for fn in (scene.read_review_packet, scene.read_review_evidence, scene.submit_claim_review):
        server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(fn)
    return server


if __name__ == '__main__':
    make_server(ReviewScene(Path(os.environ['SSS_PDF_REVIEW_RUN']), Path(os.environ['SSS_PDF_REVIEW_OUTPUT']))).run(transport='stdio')
