"""固定十五工具的可靠交付 MCP 后端；沿用公共工具和权限，不注册未晋级候选。"""
from __future__ import annotations

import os
from pathlib import Path
import sys

AREA = Path(__file__).resolve().parent
ROOT = AREA.parents[1]
for directory in (ROOT,):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from scenarios.research_ppt.server import _tool_errors
from scenarios.research_ppt.recovery import CheckpointPPTService

BASE_TOOL_ORDER = (
    'list_inputs', 'list_templates', 'pin_source', 'read_source', 'read_page', 'extract_figure',
    'inspect_deck', 'deliver_deck', 'read_deck_plan', 'list_restorable_decks',
    'render_deck', 'restyle_deck', 'revise_deck', 'validate_deck', 'build_delivery',
)
def create_server(job_path: Path):
    service = CheckpointPPTService(job_path)
    server = MCPServer('SSS research PPT reliable delivery')

    def list_inputs() -> dict:
        """List approved inputs, task constraints and output permission."""
        return service.list_inputs()

    def list_templates() -> dict:
        """List supported editable layouts; scientific interpretation remains a model decision."""
        return service.list_templates()

    def pin_source(document_id: str) -> dict:
        """Pin one approved PDF/PPTX to a versioned source handle."""
        return service.pin_source(document_id)

    def read_source(source_id: str) -> dict:
        """Read pinned document text and image inventory; reject changed source versions."""
        return service.read_source(source_id)

    def read_page(source_id: str, page: int) -> dict:
        """Read actual page text and PDF geometry candidates; not scientific certification."""
        return service.read_page(source_id, page)

    def extract_figure(source_id: str, page: int, bbox: list[float] | None = None,
                       candidate_id: str | None = None) -> dict:
        """Extract source image using a read_page geometry candidate; whole page is page evidence only."""
        return service.extract_figure(source_id, page, bbox, candidate_id)

    def inspect_deck(deck_id: str) -> dict:
        """Check persisted deck integrity, slide count and editable text."""
        return service.inspect_deck(deck_id)

    def deliver_deck(validation_id: str) -> dict:
        """Deliver only a currently validated deck and current-version PDF/previews."""
        return service.deliver_deck(validation_id)

    def read_deck_plan(deck_id: str) -> dict:
        """Read the complete persisted plan before explicit local revisions."""
        return service.read_deck_plan(deck_id)

    def list_restorable_decks() -> dict:
        """List this job's restored generated deck handles and current validation status after restart."""
        return service.list_restorable_decks()

    def render_deck(plan: dict) -> dict:
        """Create a new editable PPTX from a cited plan and persist its source/plan state."""
        return service.render_deck(plan)

    def restyle_deck(source_id: str, template: str) -> dict:
        """Restyle an approved PPTX copy while preserving source text, media and page count."""
        return service.restyle_deck(source_id, template)

    def revise_deck(deck_id: str, updates: list[dict]) -> dict:
        """Revise explicit page+changes in a new copy; independently preserve every non-target page."""
        return service.revise_deck(deck_id, updates)

    def validate_deck(deck_id: str) -> dict:
        """Render real PDF/previews and verify package, geometry, notes and source versions."""
        return service.validate_deck(deck_id)

    def build_delivery(plan: dict) -> dict:
        """Ordinary render/restyle-inspect-validate-deliver script; not a learned Motif."""
        return service.build_delivery(plan)

    for fn in (list_inputs, list_templates, pin_source, read_source, read_page, extract_figure,
               inspect_deck, deliver_deck, read_deck_plan, list_restorable_decks):
        server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(
            _tool_errors(fn, service))
    for fn in (render_deck, restyle_deck, revise_deck, validate_deck, build_delivery):
        server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))(
            _tool_errors(fn, service))
    return server


if __name__ == '__main__':
    create_server(Path(os.environ['SSS_PPT_JOB'])).run(transport='stdio')
