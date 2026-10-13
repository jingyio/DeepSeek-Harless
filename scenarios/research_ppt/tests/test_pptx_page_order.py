"""Real OOXML package ordering and relationship diagnostics, with no model calls."""
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from PIL import Image, ImageDraw

from scenarios.research_ppt.documents import (
    P, R, PACKAGE_R, inspect_pptx, parse_document, pptx_slide_paths, safe_zip,
)

A = 'http://schemas.openxmlformats.org/drawingml/2006/main'


def package_parts(order=(2, 10, 1)):
    relationships = ''.join(
        f'<Relationship Id="rId{number}" Type="{R}/slide" Target="slides/slide{number}.xml"/>'
        for number in (1, 2, 10)
    )
    slide_ids = ''.join(f'<p:sldId id="{255 + index}" r:id="rId{number}"/>'
                        for index, number in enumerate(order, 1))
    parts = {
        '[Content_Types].xml': b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        'ppt/presentation.xml': (f'<p:presentation xmlns:p="{P}" xmlns:r="{R}">'
                                 f'<p:sldIdLst>{slide_ids}</p:sldIdLst>'
                                 '<p:sldSz cx="12192000" cy="6858000"/></p:presentation>').encode(),
        'ppt/_rels/presentation.xml.rels':
            f'<Relationships xmlns="{PACKAGE_R}">{relationships}</Relationships>'.encode(),
    }
    for number in (1, 2, 10):
        parts[f'ppt/slides/slide{number}.xml'] = (
            f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp>'
            f'<p:txBody><a:p><a:r><a:t>Original part {number}</a:t></a:r></a:p></p:txBody>'
            '</p:sp></p:spTree></p:cSld></p:sld>'
        ).encode()
    # An orphan part must not become an extra page or change editability results.
    parts['ppt/slides/slide99.xml'] = f'<p:sld xmlns:p="{P}"/>'.encode()
    return parts


def write_package(path, parts):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, content in parts.items():
            archive.writestr(name, content)


class PptxPageOrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'reordered.pptx'

    def tearDown(self):
        self.temp.cleanup()

    def test_read_and_inspect_use_presentation_order_not_part_number(self):
        write_package(self.path, package_parts())
        parsed = parse_document(self.path)
        self.assertEqual([row['page'] for row in parsed['pages']], [1, 2, 3])
        self.assertEqual([row['text'] for row in parsed['pages']],
                         ['Original part 2', 'Original part 10', 'Original part 1'])
        inspection = inspect_pptx(self.path)
        self.assertEqual(inspection['slide_count'], 3)
        self.assertTrue(inspection['each_slide_has_editable_text'])

    def test_images_keep_reordered_page_provenance_and_hidden_slides_are_pages(self):
        parts = package_parts()
        parts['ppt/slides/slide2.xml'] = parts['ppt/slides/slide2.xml'].replace(b'<p:sld ', b'<p:sld show="0" ')
        image = Image.new('RGB', (160, 120), 'white')
        ImageDraw.Draw(image).rectangle((20, 20, 120, 90), fill='blue')
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        parts['ppt/media/image1.png'] = stream.getvalue()
        parts['ppt/slides/_rels/slide10.xml.rels'] = (
            f'<Relationships xmlns="{PACKAGE_R}"><Relationship Id="img" '
            f'Type="{R}/image" Target="../media/image1.png"/></Relationships>'
        ).encode()
        write_package(self.path, parts)
        parsed = parse_document(self.path)
        self.assertEqual(parsed['page_count'], 3)
        self.assertEqual(len(parsed['images']), 1)
        self.assertEqual(parsed['images'][0]['page'], 2)

    def test_internal_absolute_and_named_parts_follow_relationships(self):
        parts = package_parts()
        parts['ppt/slides/result-page.xml'] = parts.pop('ppt/slides/slide2.xml')
        rel = 'ppt/_rels/presentation.xml.rels'
        parts[rel] = parts[rel].replace(b'Target="slides/slide2.xml"', b'Target="/ppt/slides/result-page.xml"')
        write_package(self.path, parts)
        with safe_zip(self.path) as archive:
            self.assertEqual(pptx_slide_paths(archive)[0], 'ppt/slides/result-page.xml')
        self.assertEqual(parse_document(self.path)['pages'][0]['text'], 'Original part 2')

    def test_missing_or_ambiguous_slide_relationships_are_rejected(self):
        rel = 'ppt/_rels/presentation.xml.rels'
        mutations = {
            'missing part': lambda parts: parts.pop('ppt/slides/slide2.xml'),
            'missing relationship file': lambda parts: parts.pop(rel),
            'external slide': lambda parts: parts.__setitem__(rel, parts[rel].replace(
                b'Id="rId2"', b'Id="rId2" TargetMode="External"')),
            'non-slide relationship': lambda parts: parts.__setitem__(rel, parts[rel].replace(
                f'Id="rId2" Type="{R}/slide"'.encode(), f'Id="rId2" Type="{R}/image"'.encode())),
            'duplicate target': lambda parts: parts.__setitem__(rel, parts[rel].replace(
                b'Target="slides/slide2.xml"', b'Target="slides/slide1.xml"')),
            'unsafe target': lambda parts: parts.__setitem__(rel, parts[rel].replace(
                b'Target="slides/slide2.xml"', b'Target="../../outside.xml"')),
            'duplicate ordered ID': lambda parts: parts.__setitem__('ppt/presentation.xml',
                parts['ppt/presentation.xml'].replace(b'id="257"', b'id="256"')),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                parts = package_parts()
                mutate(parts)
                write_package(self.path, parts)
                with self.assertRaises(ValueError):
                    parse_document(self.path)
                with self.assertRaises(ValueError):
                    inspect_pptx(self.path)

    def test_duplicate_package_paths_are_not_resolved_by_last_member(self):
        write_package(self.path, package_parts())
        with zipfile.ZipFile(self.path, 'a') as archive:
            archive.writestr('ppt/slides/slide2.xml', b'<replacement/>')
        with self.assertRaisesRegex(ValueError, '重复路径'):
            parse_document(self.path)


if __name__ == '__main__':
    unittest.main()
