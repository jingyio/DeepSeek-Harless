"""Per-session PDF reading, bounded automatic support review and delivery via MCP."""
from __future__ import annotations
import json
import os
from functools import wraps
from pathlib import Path
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pdf_tools import ROOT, PdfScene, digest, save_private
from pdf_repair_tools import RepairScene, claim_id, WITHDRAWN, NOT_EXTRACTED
from pdf_review_tools import numeric_gaps


class WebPdfScene:
    def __init__(self, directory: Path, *, cache: Path | None = None):
        self.directory = directory.resolve()
        self.task = json.loads((self.directory / 'task.json').read_text())
        self.snapshot = json.loads((self.directory / 'input-snapshot.json').read_text())
        self.scene = PdfScene(Path(self.task['sources']['root']),
                              cache if cache is not None else ROOT / '.local/literature-notes/pdf-cache', self.task,
                              delivery=self.directory / 'reading')
        self.phase = 'reading'
        self.round = 0
        self.repair = None
        self.evidence = None

    def _require(self, *phases):
        if self.phase not in phases:
            raise ToolError('task phase is ' + self.phase + '; inspect workflow before submitting')

    def _round(self, targets, *, synthesis=False, prior_proposals=None):
        source = self.directory / ('synthesis-input' if synthesis else 'review-input-' + str(self.round))
        save_private(source / 'evidence.json', self.evidence)
        save_private(source / 'pdf-input-snapshot.json', self.snapshot)
        request = {'input_sha256': digest(self.evidence), 'claim_ids': targets,
            'scope': 'claim_support_audit' if self.round == 1 and not synthesis else 'unresolved_claims_only',
            'review_mode': 'compare_existing_claim', 'synthesis_only': synthesis}
        if self.round == 2 and not synthesis:
            origin = self.directory / 'review-input-1'
            request.update(history_input_directory=str(origin),
                           history_input_sha256=digest(json.loads((origin / 'evidence.json').read_text())),
                           prior_proposals={cid: value for cid, value in (prior_proposals or {}).items() if cid in targets})
        save_private(source / 'repair-targets.json', request)
        self.repair = RepairScene(source, self.directory / ('synthesis' if synthesis else 'review-' + str(self.round)))
        self.phase = 'synthesis' if synthesis else 'review'

    def workflow(self):
        return {'phase': self.phase, 'review_round': self.round,
                'target_claim_ids': self.repair.targets if self.repair else [],
                'next_action': {'reading': 'preview_research_notes', 'review': 'read_claim_repair_packet then submit_claim_repair',
                                'synthesis': 'read_final_synthesis then deliver_research_notes', 'delivered': 'complete'}[self.phase],
                'human_review_required': False, 'research_quality': 'automatic_model_reviewed_unverified'}

    def preview_research_notes(self, draft: dict) -> dict:
        """Submit the complete reading draft and start automatic claim review; this is not final delivery."""
        self._require('reading')
        receipt = self.scene.preview_research_notes(draft)
        self.evidence = json.loads(Path(receipt['artifact']).read_text())
        self.round = 1
        targets = [claim_id(p['paper_id'], f['name']) for p in self.evidence['draft']['papers'] for f in p['fields']]
        self._round(targets)
        return {'status': 'pending_automatic_review', 'reading_receipt': receipt, **self.workflow()}

    def read_claim_repair_packet(self, claim_id: str) -> dict:
        """Read a selected claim and issued quotes before reviewing its support."""
        self._require('review')
        return {**self.repair.read_claim_repair_packet(claim_id),
                'gap_statements': {'withdrawn': WITHDRAWN, 'not_extracted': NOT_EXTRACTED}}

    def search_claim_evidence(self, claim_id: str, query: str) -> dict:
        """Search literally within the selected claim's frozen paper; no support approval."""
        self._require('review')
        return self.repair.search_claim_evidence(claim_id, query)

    def read_claim_evidence_plan(self, claim_id: str, document_version_sha256: str, windows: list[dict]) -> dict:
        """Actually read a bounded plan within a claim's existing evidence budget."""
        self._require('review')
        return self.repair.read_claim_evidence_plan(claim_id, document_version_sha256, windows)

    def submit_claim_repair(self, decisions: list[dict], synthesis_hypothesis: str) -> dict:
        """Validate selected model decisions; accepted decisions persist. At most two review rounds."""
        self._require('review')
        receipt = self.repair.submit_claim_repair(decisions, synthesis_hypothesis)
        if receipt['status'] == 'pending_claim_decisions':
            return receipt
        self.evidence = json.loads(Path(receipt['artifact']).read_text())
        targets = []
        for paper in self.evidence['draft']['papers']:
            for field in paper['fields']:
                quotes = [c['quote'] for c in self.evidence['citation_checks']
                          if c['paper_id'] == paper['paper_id'] and c['field'] == field['name']]
                if field['status'] != 'evidence' or numeric_gaps(field['statement'], quotes):
                    targets.append(claim_id(paper['paper_id'], field['name']))
        if targets and self.round < 2:
            self.round += 1
            self._round(targets, prior_proposals=self.repair.rejected_proposals)
        else:
            self._round([], synthesis=True)
        return {'status': 'pending_final_delivery', 'review_receipt': receipt, **self.workflow()}

    def read_final_synthesis(self) -> dict:
        """Read the entire revised table and actual final quotes before synthesizing the research question."""
        self._require('synthesis')
        return self.repair.read_claim_repair_packet('synthesis')

    def deliver_research_notes(self, synthesis_hypothesis: str) -> dict:
        """Publish source-replayed model-reviewed notes with explicit gaps; no human review or PDF writes."""
        self._require('synthesis')
        receipt = self.repair.submit_claim_repair([], synthesis_hypothesis)
        self.evidence = json.loads(Path(receipt['artifact']).read_text())
        save_private(self.directory / 'evidence.json', self.evidence)
        notes = self.directory / 'research-notes.md'
        notes.write_text(self.evidence['markdown'], encoding='utf-8'); notes.chmod(0o600)
        final = {**receipt, 'status': 'delivered_with_gaps' if self.evidence['gaps'] else 'delivered',
                 'artifact': str(self.directory / 'evidence.json'), 'artifact_sha256': digest(self.evidence),
                 'task_sha256': digest(self.task), 'question': self.task['question'],
                 'research_quality': 'automatic_model_reviewed_unverified', 'human_review_required': False,
                 'citation_count': len(self.evidence['citation_checks']),
                 'claim_count': sum(len(p['fields']) for p in self.evidence['draft']['papers']),
                 'gap_count': len(self.evidence['gaps'])}
        save_private(self.directory / 'delivery-receipt.json', final)
        self.phase = 'delivered'
        return final


def make_server(scene):
    server = MCPServer('Session-bound local PDF research')
    def reading_gate(method):
        @wraps(method)
        def guarded(*args, **kwargs):
            scene._require('reading')
            return method(*args, **kwargs)
        return guarded
    for method in (scene.scene.prepare_pdf, scene.scene.search_pdf_text, scene.scene.pin_pdf_context,
                   scene.scene.read_pinned_pdf_context, scene.scene.read_pdf_evidence_plan):
        server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(reading_gate(method))
    for method in (scene.scene.list_pdfs, scene.preview_research_notes, scene.read_claim_repair_packet, scene.search_claim_evidence,
                   scene.read_claim_evidence_plan, scene.submit_claim_repair, scene.read_final_synthesis,
                   scene.deliver_research_notes):
        server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(method)
    return server


if __name__ == '__main__':
    make_server(WebPdfScene(Path(os.environ['SSS_PDF_WEB_TASK']))).run(transport='stdio')
