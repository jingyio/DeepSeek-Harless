"""真实PyMuPDF字形回归；不调用模型，不以此代替人工视觉评审。"""
import os
from pathlib import Path
import re
import unittest

import fitz

from scenarios.research_ppt.validation import ROOT, _check_rendered_glyphs, _missing_texts


def text_pdf(text, fontname='helv', fontfile=None, render_mode=0):
    with fitz.open() as document:
        page = document.new_page()
        if fontfile is not None:
            page.insert_font(fontname='StaticFont', fontfile=str(fontfile))
            fontname = 'StaticFont'
        elif fontname == 'UnsupportedLatin':
            page.insert_font(fontname=fontname, fontbuffer=fitz.Font('helv').buffer)
        page.insert_text((30, 50), text, fontname=fontname, fontsize=16, render_mode=render_mode)
        return document.tobytes()


def preserved_unicode_missing_glyph_pdf(fontfile):
    """真实TrueType PDF保留ToUnicode的中文，CIDToGIDMap却指向.notdef。"""
    with fitz.open() as document:
        page = document.new_page()
        font_xref = page.insert_font(fontname='MissingCJK', fontfile=str(fontfile))
        page.insert_text((30, 50), 'ABCD', fontname='MissingCJK', fontsize=16)
        descendant = int(re.search(r'(\d+)\s+0\s+R', document.xref_get_key(font_xref, 'DescendantFonts')[1]).group(1))
        if document.xref_get_key(descendant, 'Subtype')[1] != '/CIDFontType2':
            raise ValueError('缺字夹具必须使用真实TrueType字体')
        cmap = (b'/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n'
            b'/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n'
            b'/CMapName /PreservedUnicode def\n/CMapType 2 def\n'
            b'1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n'
            b'4 beginbfchar\n<0001> <4E2D>\n<0002> <6587>\n<0003> <79D1>\n<0004> <7814>\nendbfchar\n'
            b'endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n')
        xref = document.get_new_xref()
        document.update_object(xref, '<<>>')
        document.update_stream(xref, cmap)
        document.xref_set_key(font_xref, 'ToUnicode', f'{xref} 0 R')
        missing = document.get_new_xref()
        document.update_object(missing, '<<>>')
        document.update_stream(missing, b'\x00\x00' * 5)
        document.xref_set_key(descendant, 'CIDToGIDMap', f'{missing} 0 R')
        document.update_stream(page.get_contents()[0],
            b'q BT /MissingCJK 16 Tf 1 0 0 1 30 792 Tm <0001000200030004> Tj ET Q')
        return document.tobytes()


class RenderedGlyphTests(unittest.TestCase):
    def check_pdf(self, contents, wanted):
        report = {'errors': [], 'warnings': []}
        with fitz.open(stream=contents, filetype='pdf') as document:
            page = document[0]
            # 实际解析并光栅化PDF，不提供mock page/get_texttrace。
            self.assertGreater(page.get_pixmap().width, 0)
            extracted = page.get_text()
            result = _check_rendered_glyphs(page, wanted, report, 1)
        return extracted, result, {row['code'] for row in report['errors']}

    def test_real_pdf_without_cjk_font_is_rejected(self):
        _, result, codes = self.check_pdf(text_pdf('中文科研', 'UnsupportedLatin'), ['中文科研'])
        self.assertGreater(result['missing_cjk_characters'], 0)
        self.assertGreater(result['visible_notdef_glyphs'], 0)
        self.assertIn('render_cjk_glyph_missing_or_collapsed', codes)
        self.assertIn('render_visible_notdef_glyph', codes)

    def test_preserved_unicode_is_not_proof_of_visible_glyphs(self):
        paths = [Path(os.environ['SSS_TEST_LATIN_FONT'])] if os.environ.get('SSS_TEST_LATIN_FONT') else [
            ROOT / '.local/toolchain/fonts/DejaVuSans.ttf',
            Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'), Path('C:/Windows/Fonts/arial.ttf')]
        font = next((path for path in paths if path.is_file()), None)
        if font is None:
            self.skipTest('没有用于真实CIDToGIDMap缺字夹具的TrueType字体，此负例未验证')
        extracted, result, codes = self.check_pdf(preserved_unicode_missing_glyph_pdf(font), ['中文科研'])
        self.assertEqual(_missing_texts(['中文科研'], extracted), [])
        self.assertGreater(result['visible_notdef_glyphs'], 0)
        self.assertIn('render_visible_notdef_glyph', codes)

    def test_builtin_cjk_real_pdf_passes_mixed_text(self):
        # MuPDF china-s实际不支持韩文和上标；完整多语言正例使用静态Noto。
        text = '中文科研 カタカナ E = mc^2; 95% CI, p < 0.05'
        _, result, codes = self.check_pdf(text_pdf(text, 'china-s'), [text])
        self.assertGreater(result['expected_cjk_characters'], 0)
        self.assertEqual(result['missing_cjk_characters'], 0)
        self.assertEqual(codes, set())

    def test_static_noto_real_pdf_passes(self):
        font = Path(os.environ.get('SSS_TEST_CJK_FONT', str(ROOT / '.local/fontconfig/NotoSansCJKsc-Regular.otf')))
        if not font.is_file():
            self.skipTest('本环境无静态Noto字体；此正例未验证，不下载依赖冒充已验证')
        text = '中文科研 カタカナ 한국어 E = mc²; Δ = 0.05'
        _, result, codes = self.check_pdf(text_pdf(text, fontfile=font), [text])
        self.assertEqual(result['missing_cjk_characters'], 0)
        self.assertEqual(result['visible_notdef_glyphs'], 0)
        self.assertEqual(codes, set())

    def test_english_formula_and_invisible_notdef_do_not_trigger_false_failure(self):
        text = 'API v9: E = mc²; 95% CI, p < 0.05, ± 0.1'
        _, result, codes = self.check_pdf(text_pdf(text), [text])
        self.assertEqual(result['expected_cjk_characters'], 0)
        self.assertEqual(codes, set())
        _, result, codes = self.check_pdf(text_pdf('中文', 'UnsupportedLatin', render_mode=3), [])
        self.assertGreater(result['ignored_invisible_spans'], 0)
        self.assertEqual(result['visible_notdef_glyphs'], 0)
        self.assertEqual(codes, set())


if __name__ == '__main__':
    unittest.main()
