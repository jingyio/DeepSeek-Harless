"""Session-scoped paper evidence, reusing the existing static checker."""
from pathlib import Path
import hashlib
import io
import json
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.adapters.session_files import SessionFiles
from src.adapters import paper_static_checks
from mcp.server import MCPServer
from mcp.types import ToolAnnotations


class PaperEvidence(SessionFiles):
    def scope_version(self):
        rows = self.list_files()['files']
        return hashlib.sha256(json.dumps({'files': rows, 'checker': hashlib.sha256(
            Path(paper_static_checks.__file__).read_bytes()).hexdigest()}, sort_keys=True).encode()).hexdigest()

    def pin_sources(self, main):
        if Path(main).suffix.lower() != '.tex': raise ValueError('latex_main_required')
        self.read(main, limit=256*1024)
        version = self.scope_version()
        handle = 'source-' + uuid4().hex
        self.handles[handle] = (main, version, 'latex')
        return {'source_id': handle, 'main': main, 'version_sha256': version}

    def read_sources(self, source_id):
        row = self.handles.get(source_id)
        if not row or len(row) != 3 or row[2] != 'latex': raise ValueError('wrong_or_unknown_source_view')
        main, version, _ = row
        if self.scope_version() != version: raise ValueError('paper_scope_version_changed')
        bbl_path = self.root / (Path(main).stem + '.bbl')
        bbl = self.read(bbl_path.name, limit=256*1024)[0].decode('utf-8') if bbl_path.exists() else None
        diagnostic = paper_static_checks.source_diagnostics(self.root, main, bbl)
        logs = []
        for entry in self.list_files()['files']:
            if Path(entry['name']).suffix.lower() == '.log':
                text = self.read(entry['name'], entry['sha256'], limit=256*1024)[0].decode('utf-8')
                logs.append({'name': entry['name'], 'diagnostic': paper_static_checks.build_diagnostics(text, None)})
        if self.scope_version() != version: raise ValueError('paper_scope_version_changed')
        return {'source_id': source_id, 'version_sha256': version, 'diagnostic': diagnostic,
                'existing_logs': logs, 'compiled_by_this_task': False}

    def document(self, source_id, page):
        row = self.handles.get(source_id)
        if not row or len(row) != 2: raise ValueError('wrong_or_unknown_source_view')
        name, data, version = self.pinned(source_id)
        if type(page) is not int or page < 1: raise ValueError('positive_page_required')
        if Path(name).suffix.lower() == '.pdf':
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted: raise ValueError('encrypted_pdf_unsupported')
            if len(reader.pages) > 200: raise ValueError('paper_page_limit')
            if page > len(reader.pages): raise ValueError('page_not_in_document')
            text = reader.pages[page - 1].extract_text() or ''
            count = len(reader.pages)
        else:
            if page != 1: raise ValueError('text_has_one_logical_page')
            if len(data) > 256*1024: raise ValueError('paper_text_limit')
            text, count = data.decode('utf-8'), 1
        if len(text) > 100000: raise ValueError('paper_page_text_limit')
        self.pinned(source_id)
        return {'source_id': source_id, 'version_sha256': version, 'name': name, 'page': page,
                'page_count': count, 'text': text, 'visual_checked': False,
                'coverage': 'extracted_text_for_model_review_not_fact_or_venue_certification'}


def create_server(directory):
    files = PaperEvidence(directory)
    server = MCPServer('Harless uploaded paper evidence')
    annotation = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @server.tool(annotations=annotation)
    def list_inputs() -> dict:
        """List only the approved files in this Session, with exact SHA256."""
        return files.list_files()

    @server.tool(annotations=annotation)
    def pin_document(name: str, sha256: str) -> dict:
        """Pin a listed PDF or UTF-8 paper file to a fresh Session-local handle; no host paths."""
        if Path(name).suffix.lower() not in ('.pdf', '.tex', '.bib', '.bbl', '.log', '.md', '.txt'):
            raise ValueError('paper_document_format_unsupported')
        return files.pin(name, sha256)

    @server.tool(annotations=annotation)
    def read_pinned_document(source_id: str, page: int = 1) -> dict:
        """Read one exact PDF page or one bounded text file for proofreading; do not claim visual or factual verification."""
        return files.document(source_id, page)

    @server.tool(annotations=annotation)
    def pin_paper_sources(main: str) -> dict:
        """Pin the uploaded literal LaTeX main and all current source files to a versioned scope."""
        return files.pin_sources(main)

    @server.tool(annotations=annotation)
    def read_pinned_paper_sources(source_id: str) -> dict:
        """Use the existing static checker for literal citations, duplicate labels, floats and supplied logs; no compilation or authenticity claim."""
        return files.read_sources(source_id)

    return server


if __name__ == '__main__': create_server(Path(sys.argv[1])).run(transport='stdio')
