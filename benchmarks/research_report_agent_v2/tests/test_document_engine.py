"""Offline layout tests use geometric image fixtures, never claimed research data."""
import json
import hashlib
import re
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from benchmarks.research_report_agent_v2.document_engine import CONTENT_RECT, PAGE_WIDTH, PAGE_HEIGHT, audit_document, build_document, measure_capacity, render_document


class DocumentEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.figure = self.root / "layout-fixture.png"
        image = Image.new("RGB", (1000, 600), "white")
        pen = ImageDraw.Draw(image)
        pen.rectangle((80, 60, 950, 540), outline="#245E86", width=4)
        pen.line([(100, 470), (350, 320), (600, 360), (900, 130)], fill="#087E83", width=7)
        pen.text((120, 90), "GEOMETRIC LAYOUT FIXTURE - NOT RESEARCH DATA", fill="black")
        image.save(self.figure)

    def tearDown(self):
        self.temp.cleanup()

    def payload(self):
        return {"title": "科研报告流式排版检查", "subtitle": "离线版式测试，不是科学结论",
                "sections": [{"heading": "问题与范围", "paragraphs": ["此段文字用于验证中文内容能够完整保留，不需要模型重新撰写。"]},
                             {"heading": "证据与观察", "paragraphs": ["图形只是几何排版夹具；测试关注图注配对、内容顺序和实际生成的文件。"], "figure_indices": [0]},
                             {"heading": "解释边界", "paragraphs": ["格式通过不等于科学结论成立，需要另行审查实验设计与统计推断。"]}],
                "figures": [{"path": str(self.figure), "caption": "仅用于版式检查的几何图形，没有实验数据。", "kind": "layout_fixture"}],
                "metrics": [{"label": "测试标识", "value": "TEST-ALPHA"}],
                "requirements": {"page_mode": "max", "pages": 1, "style": "brief"}, "synthetic": True}

    def test_streams_into_one_page_and_keeps_content_and_caption(self):
        result = build_document(self.payload(), self.root / "short")
        self.assertTrue(result["quality_passed"], result["audit"])
        self.assertEqual(result["page_count"], 1)
        self.assertTrue(result["audit"]["checks"]["all_text_preserved"])
        self.assertTrue(result["audit"]["figure_checks"][0]["same_page_and_adjacent"])
        self.assertLess(result["audit"]["pages"][0]["max_internal_whitespace_pt"], 45)
        self.assertGreater(result["audit"]["pages"][0]["bbox_area_occupancy"], .18)

    def test_exact_six_does_not_invent_padding_or_extra_figures(self):
        payload = self.payload()
        payload["requirements"] = {"page_mode": "exact", "pages": 6, "style": "paper"}
        result = build_document(payload, self.root / "impossible")
        self.assertFalse(result["constraints_satisfied"])
        self.assertFalse(result["quality_passed"])
        self.assertLess(result["page_count"], 6)
        self.assertEqual(len(result["attempts"]), 4)
        self.assertEqual(sum(x["image_count"] for x in result["audit"]["pages"]), 1)
        self.assertTrue(result["audit"]["checks"]["all_text_preserved"])
        self.assertIn("without changing approved content", result["reason"])

    def test_long_paragraphs_flow_and_report_every_page_including_last(self):
        payload = self.payload()
        payload["requirements"] = {"page_mode": "auto", "pages": None, "style": "technical"}
        text = "科研解释必须限定在实际观测范围内，方法和结论不可混淆；排版引擎只调整位置和尺度，并不删减已经批准的论述。"
        payload["sections"][0]["paragraphs"] = [text * 16, "第二段保留标记：END-OF-SECTION"]
        payload["sections"][2]["paragraphs"] = [text * 11]
        result = build_document(payload, self.root / "long")
        self.assertTrue(result["quality_passed"], result["audit"])
        self.assertGreater(result["page_count"], 1)
        self.assertLessEqual(result["page_count"], 6)
        self.assertEqual(len(result["audit"]["pages"]), result["page_count"])
        self.assertTrue(result["audit"]["pages"][-1]["final_page"])
        self.assertIn("bottom_whitespace_pt", result["audit"]["pages"][-1])

    def test_independent_audit_detects_missing_source_and_pdf_tamper(self):
        result = build_document(self.payload(), self.root / "tamper")
        manifest = Path(result["manifest_path"])
        self.figure.unlink()
        audit = audit_document(result["path"], manifest)
        self.assertFalse(audit["checks"]["figure_sources_unchanged"])
        with Path(result["path"]).open("ab") as stream:
            stream.write(b"\n% modified\n")
        audit = audit_document(result["path"], manifest)
        self.assertFalse(audit["checks"]["file_hash_matches"])

    def test_audit_rejects_separated_caption_and_detects_structural_overlap(self):
        result = build_document(self.payload(), self.root / "geometry")
        manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
        caption = next(x for x in manifest["blocks"] if x["kind"] == "caption")
        caption["page"] = 2
        audit = audit_document(result["path"], manifest)
        self.assertFalse(audit["checks"]["figure_caption_pairs"])
        caption["page"] = 1
        paragraph = next(x for x in manifest["blocks"] if x["kind"] == "body")
        caption["bbox"] = list(paragraph["bbox"])
        audit = audit_document(result["path"], manifest)
        self.assertFalse(audit["checks"]["no_structural_overlap"])

    def test_capacity_wraps_full_payload_without_files_and_matches_rendered_height(self):
        payload = self.payload()
        before = set(self.root.rglob("*"))
        measurement = measure_capacity(payload)
        self.assertEqual(before, set(self.root.rglob("*")))
        self.assertTrue(measurement["fits_one_page"])
        rendered = render_document(payload, self.root / "measured.pdf", measurement["selected_config"])
        blocks = rendered["layout_manifest"]["blocks"]
        actual_height = max(x["bbox"][3] for x in blocks) - min(x["bbox"][1] for x in blocks)
        self.assertAlmostEqual(measurement["height_pt"], actual_height, places=2)
        # Before plotting, an image rectangle with its true aspect is enough
        # to measure capacity. A normal document still requires real bytes.
        payload["figures"][0].pop("path")
        payload["figures"][0]["aspect_ratio"] = 1000 / 600
        virtual = measure_capacity(payload)
        self.assertAlmostEqual(virtual["height_pt"], measurement["height_pt"], places=2)
        with self.assertRaises(ValueError):
            build_document(payload, self.root / "no-real-figure")
        payload["sections"][0]["paragraphs"] *= 80
        self.assertFalse(measure_capacity(payload)["fits_one_page"])

    def test_all_candidates_compared_before_selecting_readable_fewest_pages(self):
        payload = self.payload()
        payload["requirements"] = {"page_mode": "auto", "pages": None, "style": "brief"}
        text = "科研解释必须限定在实际观测范围内，方法和结论不可混淆；排版引擎只调整位置和尺度，并不删减已经批准的论述。"
        payload["sections"][0]["paragraphs"] = [text * 15]
        result = build_document(payload, self.root / "compare-all")
        self.assertEqual(len(result["attempts"]), 4)
        valid = [x for x in result["attempts"] if x.get("quality_passed")]
        fewest_pages = min(x["page_count"] for x in valid)
        self.assertEqual(result["page_count"], fewest_pages)
        largest_font = max(x["config"]["font_size"] for x in valid if x["page_count"] == fewest_pages)
        self.assertEqual(result["selected_config"]["font_size"], largest_font)
        self.assertTrue(result["audit"]["checks"]["all_text_preserved"])

    def test_mixed_cjk_statistical_sentence_keeps_text_inside_unchanged_frame(self):
        payload = self.payload()
        sentence = "斜率=0.80323，95% CI [0.7532, 0.85325]；双侧p=3.2966e-34。R²=0.95597。达到预设显著性阈值，仍需评估实际重要性。"
        payload["sections"][0]["paragraphs"] = [sentence]
        rendered = render_document(payload, self.root / "mixed-cjk.pdf", {"font_size": 9.4, "leading": 14})
        audit = audit_document(rendered["path"], rendered["layout_manifest"])
        self.assertTrue(audit["checks"]["no_content_overflow"], audit["overflow"])
        self.assertTrue(audit["checks"]["all_text_preserved"], audit["missing_text"])
        self.assertAlmostEqual(rendered["layout_manifest"]["content_rect"][2], 551.275590551)

    def _margin_fixture(self, overhang, footer=""):
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.pdfbase.pdfmetrics import stringWidth
        path = self.root / f"margin-{overhang}.pdf"
        canvas = Canvas(str(path), pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
        text = "SCIENTIFIC VALUE = 0.6849"
        canvas.setFont("Helvetica", 12)
        canvas.drawString(CONTENT_RECT[2] + overhang - stringWidth(text, "Helvetica", 12), PAGE_HEIGHT-100, text)
        if footer:
            canvas.drawString(44, 20, footer)
        canvas.save()
        manifest = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "requirements": {"page_mode": "auto", "pages": None},
                    "content_rect": list(CONTENT_RECT), "figures": [],
                    "blocks": [{"id": "body", "kind": "body", "page": 1,
                                "bbox": [44, 80, CONTENT_RECT[2], 110]}],
                    "expected_text": [{"id": "body", "text": text}]}
        return path, manifest

    def test_minor_margin_deviation_is_soft_but_larger_overflow_remains_hard(self):
        path, manifest = self._margin_fixture(2.324)
        audit = audit_document(path, manifest)
        self.assertTrue(audit["quality_passed"], audit)
        self.assertEqual(audit["acceptance_status"], "accepted_with_warnings")
        self.assertTrue(any(x["type"] == "minor_text_frame_overhang" for x in audit["soft_warnings"]))
        path, manifest = self._margin_fixture(7)
        audit = audit_document(path, manifest)
        self.assertFalse(audit["quality_passed"])
        self.assertFalse(audit["checks"]["no_content_overflow"])

    def test_soft_glyph_extension_cannot_intersect_another_tracked_block(self):
        path, manifest = self._margin_fixture(2.324)
        manifest["blocks"].append({"id": "neighbor", "kind": "body", "page": 1,
                                   "bbox": [CONTENT_RECT[2]+1, 80, CONTENT_RECT[2]+3, 110]})
        audit = audit_document(path, manifest)
        self.assertFalse(audit["quality_passed"])
        self.assertFalse(audit["checks"]["no_content_overflow"])
        self.assertTrue(audit["checks"]["no_structural_overlap"])
        self.assertEqual(audit["overflow"][0]["colliding_blocks"], ["neighbor"])

    def test_footer_cannot_satisfy_missing_body_text(self):
        path, manifest = self._margin_fixture(0, footer="MISSING BODY TEXT")
        manifest["expected_text"][0]["text"] = "MISSING BODY TEXT"
        audit = audit_document(path, manifest)
        self.assertFalse(audit["checks"]["all_text_preserved"])
        self.assertEqual(audit["missing_text"], ["body"])

    def test_split_paragraph_excludes_footer_but_rejects_actual_deleted_or_replaced_middle(self):
        import fitz
        payload = self.payload()
        payload["requirements"] = {"page_mode": "auto", "pages": None, "style": "technical"}
        # Every line differs: a repeated sentence elsewhere cannot conceal loss.
        paragraph = " ".join(f"Observation {i:03d} preserves measured value {i}.314 and its interpretation." for i in range(100))
        payload["sections"][0]["paragraphs"] = [paragraph]
        rendered = render_document(payload, self.root / "split.pdf")
        manifest = rendered["layout_manifest"]
        paragraph_id = "section-0-paragraph-0"
        splits = [b for b in manifest["blocks"] if b["id"] == paragraph_id]
        self.assertGreater(len({b["page"] for b in splits}), 1)
        audit = audit_document(rendered["path"], manifest)
        self.assertTrue(audit["checks"]["all_text_preserved"], audit["missing_text"])
        with fitz.open(rendered["path"]) as original:
            full_text = re.sub(r"\s+", "", "".join(page.get_text() for page in original))
            self.assertNotIn(re.sub(r"\s+", "", paragraph), full_text)
        # Delete a real interior line, then separately replace it with other
        # text. Refresh only the hash to isolate content checking from tampering.
        for replacement in ("", "WRONG REPLACEMENT VALUE = 999"):
            with fitz.open(rendered["path"]) as changed:
                split = splits[0]
                page = changed[split["page"]-1]
                lines = [line for block in page.get_text("dict")["blocks"] if block["type"] == 0
                         for line in block["lines"]
                         if split["bbox"][1]+30 < line["bbox"][1] < split["bbox"][3]-30]
                rectangle = fitz.Rect(lines[len(lines)//2]["bbox"])
                page.add_redact_annot(rectangle, fill=(1, 1, 1))
                page.apply_redactions(images=0)
                if replacement:
                    page.insert_text((rectangle.x0, rectangle.y1-2), replacement, fontsize=9)
                edited = self.root / ("replaced.pdf" if replacement else "deleted.pdf")
                changed.save(edited)
            altered_manifest = dict(manifest, sha256=hashlib.sha256(edited.read_bytes()).hexdigest())
            check = audit_document(edited, altered_manifest)
            self.assertTrue(check["checks"]["file_hash_matches"])
            self.assertFalse(check["checks"]["all_text_preserved"])
            self.assertIn(paragraph_id, check["missing_text"])

    def test_actual_page_edge_clipping_remains_rejected(self):
        path, manifest = self._margin_fixture(60)
        audit = audit_document(path, manifest)
        self.assertFalse(audit["quality_passed"])
        self.assertFalse(audit["checks"]["all_text_preserved"])


if __name__ == "__main__":
    unittest.main()
