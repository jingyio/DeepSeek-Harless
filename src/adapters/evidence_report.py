"""Opt-in experimental rendering: reuse frozen implementations in isolated modules.

No production module is patched. This variant has its own recorded hashes and
is not covered by the existing production Motif certificate.
"""
from pathlib import Path
import importlib.util
import hashlib
import re
from contextvars import ContextVar

ROOT=Path(__file__).resolve().parents[2]
def isolated(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def _fallback_font(primary_font: str):
    """Embed fallback glyphs missing from either a CID or configured TTF font."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    name = "ResearchFallbackSans"
    if name not in pdfmetrics.getRegisteredFontNames():
        try:
            from matplotlib import get_data_path
            path = Path(get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
        except ImportError:
            import reportlab
            path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
        pdfmetrics.registerFont(TTFont(name, str(path)))
    fallback = pdfmetrics.getFont(name)
    if primary_font == "STSong-Light":
        return fallback
    from types import SimpleNamespace
    primary = pdfmetrics.getFont(primary_font)
    coverage = getattr(primary.face, "charToGlyph", None)
    if coverage is None:
        return None  # No trustworthy glyph coverage for an unknown font type.
    return SimpleNamespace(fontName=fallback.fontName, face=SimpleNamespace(charToGlyph={
        code: glyph for code, glyph in fallback.face.charToGlyph.items() if not coverage.get(code, 0)}))


engine=isolated('_evidence_document_engine','benchmarks/research_report_agent_v2/document_engine.py')
engine._fallback_font=_fallback_font
build_document=engine.build_document
base=isolated('_evidence_session_report','src/adapters/session_report.py')
render_result=ContextVar('current_evidence_render',default=None)
def captured_build(*args,**kwargs):
    result=build_document(*args,**kwargs);render_result.set(result);return result
base.build_document=captured_build

class SessionReport(base.SessionReport):
    def export(self,title,sections,source_versions):
        token=render_result.set(None)
        try:
            response=super().export(title,sections,source_versions)
            result=render_result.get()
            if response.get('exported') or result is None:return response
            issues=[]
            for block in result.get('audit',{}).get('missing_text',[])[:32]:
                match=re.fullmatch(r'section-(\d+)-(?:paragraph-(\d+)|(heading))',block)
                pointer=value=None
                if block=='title':pointer,value='/title',title
                elif match and int(match[1])<len(sections):
                    i=int(match[1]);section=sections[i]
                    if match[3]:pointer,value=f'/sections/{i}/heading',section['heading']
                    elif int(match[2])<len(section['paragraphs']):
                        j=int(match[2]);pointer,value=f'/sections/{i}/paragraphs/{j}',section['paragraphs'][j]
                if pointer is not None:issues.append({'pointer':pointer,'value_sha256':hashlib.sha256(value.encode()).hexdigest(),'check':'all_text_preserved','block_id':block})
            return {**response,'failed_checks':response.get('failed_checks') or [e['check'] for e in result.get('hard_errors',[]) if 'check' in e],
                    'argument_issues':issues,'diagnostic_scope':'current_render_preservation_not_cause_or_scientific_judgment',
                    'next_step':'Use current argument_issues to inspect failed fields; preserve other content and source versions. This may be a rendering/glyph failure, not an incorrect scientific statement. No rejected draft is downloadable.'}
        finally:render_result.reset(token)
