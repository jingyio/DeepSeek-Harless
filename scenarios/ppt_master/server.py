"""Read-only, versioned official skill entry. Slide authoring stays with GeneLoop."""
from pathlib import Path
import os
import io
import json
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scenarios.ppt_master.package import installation, read_lock, read_verified
from src.adapters.session_files import SessionFiles


class SourceReader(SessionFiles):
    def read(self, name, expected=None, limit=20*1024*1024):
        manifest=self.root.parent/'approved-inputs.json'
        if manifest.is_symlink(): raise ValueError('approved_source_manifest_invalid')
        self.approved=json.loads(manifest.read_text())['files']
        return super().read(name,expected,limit)

    def document(self, source_id, page=1):
        name,data,version=self.pinned(source_id)
        if type(page) is not int or page<1: raise ValueError('positive_page_required')
        if Path(name).suffix.lower()!='.pdf': raise ValueError('pdf_source_required_use_official_converter_for_other_formats')
        from pypdf import PdfReader
        pdf=PdfReader(io.BytesIO(data))
        if pdf.is_encrypted: raise ValueError('encrypted_pdf_unsupported')
        if page>len(pdf.pages): raise ValueError('page_not_in_document')
        text=pdf.pages[page-1].extract_text() or ''
        self.pinned(source_id)
        return {'source_id':source_id,'version_sha256':version,'name':name,'page':page,
                'page_count':len(pdf.pages),'text':text[:80000],'truncated':len(text)>80000,
                'visual_checked':False,'coverage':'one_page_text_only'}


class SkillReader:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else installation()
        self.lock = read_lock()
        self.version = self.lock['package_sha256']
        self.source_id = 'source-' + self.version[:32]

    def read_skill_entry(self):
        return {'source_id': self.source_id, 'version_sha256': self.version,
                'skill_dir': '/opt/geneloop/ppt-master',
                'text': read_verified(self.root, 'SKILL.md', self.lock).decode('utf-8')}

    def read_pinned_routing(self, source_id):
        if source_id != self.source_id:
            raise ValueError('ppt_master_source_version_mismatch')
        # Entry changes invalidate the continuation even after it was read.
        read_verified(self.root, 'SKILL.md', self.lock)
        read_verified(self.root, 'scripts/attribution_guard.py', self.lock)
        result = subprocess.run([sys.executable, str(self.root / 'scripts/attribution_guard.py')],
            capture_output=True, text=True, timeout=90,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE':'1', 'PYTHONUTF8':'1'})
        if result.returncode:
            raise ValueError('ppt_master_attribution_guard_failed')
        return {'source_id': source_id, 'version_sha256': self.version, 'guard_exit_code': 0,
                'text': read_verified(self.root, 'workflows/routing.md', self.lock).decode('utf-8')}


def create_server():
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.types import ToolAnnotations
    server = MCPServer('GeneLoop ppt-master')
    reader = SkillReader()
    files = SourceReader(Path(sys.argv[1]),max_files=16)

    def read_skill_entry() -> dict:
        """Read the official skill entry and guarded routing together; list this Session's approved sources. No slide authoring."""
        try:
            entry=reader.read_skill_entry()
            return {**entry,'routing':reader.read_pinned_routing(entry['source_id']),**files.list_files()}
        except (OSError, ValueError, subprocess.SubprocessError) as exc: raise ToolError(str(exc)) from None

    def pin_source(name: str, sha256: str) -> dict:
        """Pin a model-selected listed upload to its exact current version. Never choose the paper for the model."""
        try: return files.pin(name,sha256)
        except (OSError, ValueError) as exc: raise ToolError(str(exc)) from None

    def read_source_page(source_id: str, page: int = 1) -> dict:
        """Read one page of the pinned PDF, default first page for title/abstract identification. No visual or scientific certification."""
        try: return files.document(source_id,page)
        except (OSError, ValueError) as exc: raise ToolError(str(exc)) from None

    for fn in (read_skill_entry, pin_source, read_source_page):
        server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(fn)
    return server


if __name__ == '__main__':
    create_server().run(transport='stdio')
