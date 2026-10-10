"""Actual image/PDF files for pixel safety diagnostics, not agent quality scores."""
import base64
import io
from pathlib import Path
import tempfile
import unittest
import fitz
from PIL import Image, ImageDraw
from scenarios.research_ppt.documents import file_hash, image_record, parse_document, pdf_page_geometry
from scenarios.research_ppt.service import ROOT


def png(image):
    stream=io.BytesIO()
    image.save(stream,format='PNG')
    return stream.getvalue()


class ImagePixelTests(unittest.TestCase):
    def test_rgba_fragment_does_not_become_an_opaque_black_rectangle(self):
        image=Image.new('RGBA',(200,120),(0,0,0,0))
        ImageDraw.Draw(image).rectangle((60,30,139,89),fill=(0,0,0,127))
        record=image_record(png(image),'alpha_fragment',1)
        self.assertIsNotNone(record)
        with Image.open(io.BytesIO(base64.b64decode(record['data'].split(',',1)[1]))) as decoded:
            self.assertEqual(decoded.getpixel((0,0)),(255,255,255))
            self.assertEqual(decoded.getpixel((100,60)),(128,128,128))

    def test_palette_transparency_is_flattened_without_losing_opaque_color(self):
        image=Image.new('P',(200,120),0)
        image.putpalette([0,0,0,0,80,220]+[0,0,0]*254)
        image.info['transparency']=0
        ImageDraw.Draw(image).rectangle((60,30,139,89),fill=1)
        record=image_record(png(image),'palette',1)
        self.assertIsNotNone(record)
        with Image.open(io.BytesIO(base64.b64decode(record['data'].split(',',1)[1]))) as decoded:
            self.assertEqual(decoded.getpixel((0,0)),(255,255,255))
            self.assertEqual(decoded.getpixel((100,60)),(0,80,220))

    def test_uniform_and_almost_uniform_assets_are_not_publishable(self):
        for color in [(0,0,0),(255,255,255),(80,80,80)]:
            with self.subTest(color=color):
                self.assertIsNone(image_record(png(Image.new('RGB',(200,120),color)),'blank',1))
        nearly_blank=Image.new('RGB',(200,120),(255,255,255))
        nearly_blank.putpixel((100,60),(0,0,0))
        self.assertIsNone(image_record(png(nearly_blank),'one_noise_pixel',1))

    def test_pdf_mask_fragment_is_hidden_but_full_geometry_remains_available(self):
        area=ROOT/'.local/research-ppt/unit-tests'
        area.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=area) as folder:
            path=Path(folder)/'masked-fragment.pdf'
            fragment=Image.new('RGBA',(200,120),(0,0,0,0))
            ImageDraw.Draw(fragment).rectangle((20,20,179,99),fill=(0,0,0,127))
            with fitz.open() as pdf:
                page=pdf.new_page(width=600,height=800)
                page.insert_image(fitz.Rect(100,150,300,300),stream=png(fragment))
                page.draw_rect(fitz.Rect(115,160,285,290),color=(0,0,0),fill=(0.8,0.9,1))
                page.insert_text((100,320),'Figure 1: This complete diagram contains a shadow image fragment.')
                pdf.save(path)
            parsed=parse_document(path)
            self.assertEqual(parsed['images'],[])
            self.assertTrue(any('遮罩' in warning for warning in parsed['warnings']))
            geometry=pdf_page_geometry(path,1,file_hash(path))
            self.assertEqual(len(geometry['figure_candidates']),1)
            self.assertFalse(geometry['figure_candidates'][0]['semantic_verified'])


if __name__=='__main__':
    unittest.main()
