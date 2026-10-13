"""Deterministic, streaming PDF layout; no model calls or scientific rewriting.

``build_document(payload, output_dir)`` preserves supplied content, measures the
actual PDF, and makes at most four bounded layout attempts. Page constraints are
reported honestly: exact six pages is not permission to pad a short report.
"""
from __future__ import annotations

import copy
import hashlib
import html
import io
import json
import re
import shutil
from functools import partial
from pathlib import Path
from typing import Any

ENGINE_VERSION = "streaming-pdf-v2.2"
AUDIT_POLICY_VERSION = "layout-audit-v2.2"
# A frame is a planned text area, not the physical paper edge. Small glyph
# overhangs into its otherwise empty margin are reportable, not lost content.
SOFT_TEXT_OVERHANG_PT = 3.0
PAGE_WIDTH, PAGE_HEIGHT = 595.275590551, 841.88976378
CONTENT_RECT = (44.0, 43.0, PAGE_WIDTH - 44.0, PAGE_HEIGHT - 49.0)
STYLES = {
    "brief": {"font_size": 10.0, "leading": 15.2, "title_size": 20.0, "figure_height": 194.0,
              "paragraph_gap": 5.5, "section_gap": 9.0, "accent": "#087E83"},
    "technical": {"font_size": 10.0, "leading": 15.5, "title_size": 21.0, "figure_height": 216.0,
                  "paragraph_gap": 6.0, "section_gap": 10.0, "accent": "#245E86"},
    "paper": {"font_size": 10.2, "leading": 16.0, "title_size": 20.5, "figure_height": 226.0,
              "paragraph_gap": 6.0, "section_gap": 11.0, "accent": "#303E4B"},
}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _validate(payload: dict, *, virtual_figures: bool = False) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Document payload must be an object.")
    result = copy.deepcopy(payload)
    if not isinstance(result.get("title"), str) or not result["title"].strip():
        raise ValueError("A nonempty document title is required.")
    sections = result.get("sections", [])
    if not isinstance(sections, list) or not sections:
        raise ValueError("Supply at least one content section; the engine does not invent content.")
    for i, section in enumerate(sections):
        if not isinstance(section, dict) or not isinstance(section.get("heading"), str):
            raise ValueError(f"Section {i} requires heading and paragraphs.")
        paragraphs = section.get("paragraphs", [])
        if not isinstance(paragraphs, list) or any(not isinstance(x, str) or not x.strip() for x in paragraphs):
            raise ValueError(f"Section {i} paragraphs must be nonempty strings.")
        if not paragraphs and not section.get("figure_indices"):
            raise ValueError(f"Section {i} is empty.")
    figures = result.setdefault("figures", [])
    if not isinstance(figures, list):
        raise ValueError("figures must be a list.")
    for i, figure in enumerate(figures):
        path = Path(figure.get("path", ""))
        if virtual_figures and not path.is_file():
            ratio = figure.get("aspect_ratio", 7.4 / 4.5)
            if not isinstance(ratio, (int, float)) or not .1 <= ratio <= 10:
                raise ValueError("Virtual figure aspect_ratio must be within 0.1..10.")
            figure["aspect_ratio"] = float(ratio)
        elif not path.is_file() or path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            raise ValueError(f"Figure {i} needs an existing PNG or JPEG; no simulated images are created.")
        if not isinstance(figure.get("caption"), str) or not figure["caption"].strip():
            raise ValueError(f"Figure {i} needs a nonempty caption.")
        if len(figure["caption"]) > 650:
            raise ValueError(f"Figure {i} caption is too long for an inseparable image-caption pair.")
        figure["path"] = str(path.resolve())
    seen = []
    for section in sections:
        ids = section.get("figure_indices", [])
        if not isinstance(ids, list) or any(type(x) is not int or not 0 <= x < len(figures) for x in ids):
            raise ValueError("figure_indices must be zero-based indexes into figures.")
        seen.extend(ids)
    if len(set(seen)) != len(seen):
        raise ValueError("Each figure may appear once; duplicate insertion is not extra evidence.")
    metrics = result.setdefault("metrics", [])
    if not isinstance(metrics, list) or any(not isinstance(x, dict) or "label" not in x or "value" not in x for x in metrics):
        raise ValueError("metrics must contain label/value objects.")
    req = result.setdefault("requirements", {})
    req.setdefault("style", "technical")
    req.setdefault("page_mode", "auto")
    req.setdefault("pages", None)
    if req["style"] not in STYLES or req["page_mode"] not in ("auto", "max", "exact"):
        raise ValueError("style: brief|technical|paper; page_mode: auto|max|exact.")
    if req["pages"] is not None and (type(req["pages"]) is not int or not 1 <= req["pages"] <= 6):
        raise ValueError("A page constraint must be an integer from 1 to 6.")
    if req["page_mode"] != "auto" and req["pages"] is None:
        raise ValueError("max/exact page mode requires pages.")
    return result


def _font(style: str) -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    name = "ResearchBodySerif" if style == "paper" else "ResearchBodySans"
    candidates = ([Path("C:/Windows/Fonts/simsun.ttc")] if style == "paper" else []) + [
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"), Path("/usr/share/fonts/truetype/arphic/ukai.ttc")]
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    for path in candidates:
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=0))
                return name
            except Exception:
                pass
    if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def _configuration(payload: dict, overrides: dict | None = None) -> dict:
    config = dict(STYLES[payload["requirements"]["style"]])
    config.update(overrides or {})
    # Readability bounds apply even to caller-provided configurations.
    bounds = {"font_size": (9.4, 11.0), "leading": (13.8, 17.5), "title_size": (18, 24),
              "figure_height": (164, 256), "paragraph_gap": (3.5, 9), "section_gap": (7, 15)}
    for key, (low, high) in bounds.items():
        if not isinstance(config[key], (float, int)) or not low <= config[key] <= high:
            raise ValueError(f"Layout {key} must be within {low}..{high}; content is never shrunk without bounds.")
    return config


def render_document(payload: dict, pdf_path: Path | None, config: dict | None = None,
                    *, _measure_only: bool = False) -> dict:
    """Render once without page padding; return a persisted block-level manifest.

    A section's figure_indices place real figures immediately after that section.
    Images remain inseparable from captions; sections and paragraphs flow freely.
    The caller's words, figure bytes and metric strings are not rewritten.
    """
    from PIL import Image as PILImage
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image, KeepTogether,
                                   PageTemplate, Paragraph, Spacer, Table, TableStyle)
    from reportlab.pdfgen.canvas import Canvas
    payload = _validate(payload, virtual_figures=_measure_only)
    config = _configuration(payload, config)
    if not _measure_only:
        pdf_path = Path(pdf_path).resolve()
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
    style, font = payload["requirements"]["style"], _font(payload["requirements"]["style"])
    left, top, right, bottom = CONTENT_RECT
    usable = right - left
    accent = colors.HexColor(config["accent"])
    ink = colors.HexColor("#243546")
    styles = {
        "title": ParagraphStyle("title", fontName=font, fontSize=config["title_size"], leading=config["title_size"] * 1.30,
                                spaceAfter=9, textColor=ink, wordWrap="CJK", keepWithNext=True),
        "heading": ParagraphStyle("heading", fontName=font, fontSize=config["font_size"] + 2.2, leading=config["leading"] + 2,
                                  spaceBefore=config["section_gap"], spaceAfter=5, textColor=accent, wordWrap="CJK", keepWithNext=True),
        "body": ParagraphStyle("body", fontName=font, fontSize=config["font_size"], leading=config["leading"],
                               spaceAfter=config["paragraph_gap"], textColor=ink, wordWrap="CJK", allowWidows=0, allowOrphans=0),
        "small": ParagraphStyle("small", fontName=font, fontSize=8.2, leading=12.0, spaceAfter=6,
                                textColor=colors.HexColor("#61707D"), wordWrap="CJK"),
        "caption": ParagraphStyle("caption", fontName=font, fontSize=8.5, leading=12.8, spaceBefore=5,
                                  spaceAfter=7, textColor=ink, wordWrap="CJK"),
        "cell": ParagraphStyle("cell", fontName=font, fontSize=9.0, leading=13.1, textColor=ink, wordWrap="CJK"),
    }
    # Mixed CJK/Latin runs can have extraction glyph extents slightly wider
    # than ReportLab's line advance (observed with WenQuanYi MicroHei). Wrap
    # inside a real 6 pt safety inset, keeping the audit's original frame.
    # Capacity preflight uses these exact styles, not a character-count proxy.
    for paragraph_style in styles.values():
        paragraph_style.rightIndent = 6.0
    blocks: list[dict] = []
    expected: list[dict] = []

    class Tracked(Flowable):
        def __init__(self, child, block_id, kind, content="", figure_index=None):
            Flowable.__init__(self)
            self.child, self.block_id, self.kind = child, block_id, kind
            self.content, self.figure_index = content, figure_index
            self.spaceBefore, self.spaceAfter = child.getSpaceBefore(), child.getSpaceAfter()
            self.keepWithNext = child.getKeepWithNext()

        def wrap(self, avail_width, avail_height):
            self.width, self.height = self.child.wrap(avail_width, avail_height)
            return self.width, self.height

        def split(self, avail_width, avail_height):
            parts = self.child.split(avail_width, avail_height)
            return [Tracked(part, self.block_id, self.kind, self.content, self.figure_index) for part in parts]

        def draw(self):
            x, y = self.canv.absolutePosition(0, 0)
            self.child.drawOn(self.canv, 0, 0)
            record = {"id": self.block_id, "kind": self.kind, "page": self.canv.getPageNumber(),
                      "bbox": [round(x, 3), round(PAGE_HEIGHT-y-self.height, 3), round(x+self.width, 3), round(PAGE_HEIGHT-y, 3)]}
            if self.figure_index is not None:
                record["figure_index"] = self.figure_index
            blocks.append(record)

    def paragraph(text, kind, block_id, figure_index=None):
        text = str(text)
        expected.append({"id": block_id, "text": text})
        return Tracked(Paragraph(html.escape(text).replace("\n", "<br/>"), styles[kind]), block_id, kind, text, figure_index)

    story = []
    if style == "brief":
        story.append(paragraph("研究简报", "small", "kicker"))
    elif style == "technical":
        story.append(paragraph("RESEARCH ANALYSIS / 技术报告", "small", "kicker"))
    story.append(paragraph(payload["title"], "title", "title"))
    if payload.get("subtitle"):
        story.append(paragraph(payload["subtitle"], "small", "subtitle"))

    def metrics_table():
        pairs = []
        for i, item in enumerate(payload["metrics"]):
            label, value = str(item["label"]), str(item["value"])
            pairs.append([Paragraph(html.escape(label), styles["cell"]), Paragraph(html.escape(value), styles["cell"])])
            expected.extend([{"id": f"metric-{i}-label", "text": label}, {"id": f"metric-{i}-value", "text": value}])
        if style == "brief":
            rows = [[Paragraph(label, styles["cell"]) for label in ("统计量", "计算结果", "统计量", "计算结果")]]
            rows.extend(pairs[i] + (pairs[i + 1] if i + 1 < len(pairs) else ["", ""]) for i in range(0, len(pairs), 2))
            widths = [usable * .25] * 4
        else:
            rows = [[Paragraph("统计量", styles["cell"]), Paragraph("计算结果", styles["cell"])]] + pairs
            widths = [usable * .56, usable * .44]
        table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table_commands = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                          ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, 0), .7, accent)]
        if style != "paper":
            table_commands += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F4")),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8FA")])]
        else:
            table_commands += [("LINEABOVE", (0, 0), (-1, 0), .9, accent), ("LINEBELOW", (0, -1), (-1, -1), .7, accent)]
        table.setStyle(TableStyle(table_commands))
        table.spaceBefore, table.spaceAfter = 6, 8
        return Tracked(table, "metrics-table", "table")

    def figure(index):
        item = payload["figures"][index]
        if _measure_only and not Path(item["path"]).is_file():
            ratio = item["aspect_ratio"]
        else:
            with PILImage.open(item["path"]) as source:
                ratio = source.width / source.height
        image_height = min(config["figure_height"], usable / ratio)
        image_width = image_height * ratio
        image = (Spacer(image_width, image_height) if _measure_only else
                 Image(item["path"], width=image_width, height=image_height))
        # Table gives explicit centering while the tracked image keeps its true bbox.
        tracked = Tracked(image, f"figure-{index}", "figure", figure_index=index)
        row = Table([[tracked]], colWidths=[usable], hAlign="LEFT")
        row.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 3),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        caption = paragraph(f"图 {index + 1} | {item['caption']}", "caption", f"caption-{index}", index)
        return KeepTogether([row, caption])

    referenced = set()
    for i, section in enumerate(payload["sections"]):
        heading = f"{i + 1}  {section['heading']}" if style == "paper" else section["heading"]
        story.append(paragraph(heading, "heading", f"section-{i}-heading"))
        for j, text in enumerate(section.get("paragraphs", [])):
            story.append(paragraph(text, "body", f"section-{i}-paragraph-{j}"))
        # Metrics stay near the first result-bearing part instead of an isolated page.
        if payload["metrics"] and i == min(1, len(payload["sections"]) - 1):
            story.append(metrics_table())
        for index in section.get("figure_indices", []):
            story.append(figure(index))
            referenced.add(index)
    remaining = [i for i in range(len(payload["figures"])) if i not in referenced]
    if remaining:
        story.append(paragraph("数据与效应图", "heading", "additional-figures"))
        story.extend(figure(i) for i in remaining)
    if payload.get("provenance"):
        story.append(paragraph(payload["provenance"], "small", "provenance"))

    if _measure_only:
        from reportlab.platypus.flowables import _listWrapOn

        def flatten(flowables):
            for flowable in flowables:
                if isinstance(flowable, KeepTogether):
                    yield from flatten(flowable._content)
                else:
                    yield flowable

        # Use the same ReportLab wrapping and space-collapsing implementation
        # as the renderer. Flatten only page-break constraints: fitting the
        # complete stack on one page then satisfies all such constraints.
        memory_canvas = Canvas(io.BytesIO(), pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
        _, height = _listWrapOn(list(flatten(story)), usable, memory_canvas)
        return {"height_pt": float(height), "available_height_pt": bottom - top,
                "font": font, "config": config, "engine_version": ENGINE_VERSION}

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(2.0 if style == "brief" else .7)
        canvas.line(left, PAGE_HEIGHT - 28, right, PAGE_HEIGHT - 28)
        canvas.setFont(font, 7.6)
        canvas.setFillColor(colors.HexColor("#667684"))
        footer = "合成数据 / Synthetic data" if payload.get("synthetic") else "科研数据分析报告"
        canvas.drawString(left, 28, footer)
        canvas.drawRightString(right, 28, str(doc.page))
        canvas.restoreState()

    doc = BaseDocTemplate(str(pdf_path), pagesize=(PAGE_WIDTH, PAGE_HEIGHT), title=payload["title"],
                          author="Research Report Agent", leftMargin=left, rightMargin=PAGE_WIDTH-right,
                          topMargin=top, bottomMargin=PAGE_HEIGHT-bottom)
    frame = Frame(left, PAGE_HEIGHT-bottom, usable, bottom-top, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id="stream", frames=frame, onPage=decorate))
    doc.build(story, canvasmaker=partial(Canvas, invariant=1))
    manifest = {"engine_version": ENGINE_VERSION, "path": str(pdf_path), "sha256": _hash(pdf_path), "font": font,
                "config": config, "requirements": payload["requirements"], "content_rect": list(CONTENT_RECT),
                "blocks": blocks, "expected_text": expected,
                "figures": [{"index": i, "path": x["path"], "sha256": _hash(Path(x["path"])), "kind": x.get("kind")}
                            for i, x in enumerate(payload["figures"])]}
    manifest_path = pdf_path.with_suffix(".layout.json")
    _write_json(manifest_path, manifest)
    return {"path": str(pdf_path), "manifest_path": str(manifest_path), "manifest_sha256": _hash(manifest_path),
            "layout_manifest": manifest, "config": config}


def _interval_union(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return merged


def _rect_union_area(rectangles):
    xs = sorted({v for box in rectangles for v in (box[0], box[2])})
    area = 0.0
    for x0, x1 in zip(xs, xs[1:]):
        intervals = [(b[1], b[3]) for b in rectangles if b[0] < x1 and b[2] > x0]
        area += (x1 - x0) * sum(b - a for a, b in _interval_union(intervals))
    return area


def audit_document(pdf_path: Path, layout_manifest: dict | Path, requirements: dict | None = None) -> dict:
    """Reopen PDF and audit actual spans/images plus tracked structural blocks.

    Density is bbox occupancy, not literal colored-pixel coverage: text uses the
    extracted span boxes and figures use full image boxes including chart margins.
    Both final-page and nonfinal-page whitespace are reported; only nonfinal tail
    gaps enter the density repair preference. No scientific validity is asserted.
    """
    import fitz
    if isinstance(layout_manifest, (str, Path)):
        layout_manifest = json.loads(Path(layout_manifest).read_text(encoding="utf-8"))
    pdf_path = Path(pdf_path)
    req = requirements or layout_manifest["requirements"]
    left, top, right, bottom = layout_manifest["content_rect"]
    content_area = (right-left)*(bottom-top)
    pages, overflow, overlaps, texts = [], [], [], []
    frame_deviations, page_clipping, body_spans = [], [], {}
    with fitz.open(pdf_path) as document:
        for number, page in enumerate(document, 1):
            content = []
            body_spans[number] = []
            for block in page.get_text("dict")["blocks"]:
                if block["type"] == 0:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            center_y = (span["bbox"][1] + span["bbox"][3]) / 2
                            if span["text"].strip() and top - SOFT_TEXT_OVERHANG_PT <= center_y <= bottom + SOFT_TEXT_OVERHANG_PT:
                                body_spans[number].append(span)
                            if span["text"].strip() and span["bbox"][1] < bottom + 2 and span["bbox"][3] > top - 2:
                                content.append({"type": "text", "bbox": list(span["bbox"])})
                elif block["type"] == 1:
                    content.append({"type": "image", "bbox": list(block["bbox"])})
            boxes = [x["bbox"] for x in content]
            for item in content:
                a, b, c, d = item["bbox"]
                clipped = a < -.05 or b < -.05 or c > page.rect.width + .05 or d > page.rect.height + .05
                if clipped:
                    page_clipping.append({"page": number, **item})
                excess = max(left - a, top - b, c - right, d - bottom, 0.0)
                if excess > .05:
                    soft = item["type"] == "text" and excess <= SOFT_TEXT_OVERHANG_PT and not clipped
                    deviation = {"page": number, **item, "max_overhang_pt": round(excess, 4),
                                 "severity": "soft" if soft else "hard"}
                    frame_deviations.append(deviation)
                    if not soft:
                        overflow.append(deviation)
            structural = [b for b in layout_manifest["blocks"] if b["page"] == number]
            # A tiny extension into unused paper margin is harmless only when
            # the actual glyph box does not intrude into a different flowable.
            # Planned boxes alone cannot catch a glyph extending past its own
            # box into a neighboring block.
            for deviation in frame_deviations:
                if deviation["page"] != number or deviation["severity"] != "soft":
                    continue
                a, b, c, d = deviation["bbox"]
                owners = [block for block in structural
                          if block["bbox"][0] - .5 <= a <= block["bbox"][2] + .5
                          and block["bbox"][1] - .05 <= (b+d)/2 <= block["bbox"][3] + .05]
                collisions = [block["id"] for block in structural if block not in owners
                              and min(c, block["bbox"][2])-max(a, block["bbox"][0]) > .05
                              and min(d, block["bbox"][3])-max(b, block["bbox"][1]) > .05]
                if collisions:
                    deviation.update(severity="hard", reason="glyph_overhang_intersects_other_block",
                                     colliding_blocks=collisions)
                    overflow.append(deviation)
            for i, a in enumerate(structural):
                for b in structural[i+1:]:
                    x_overlap = min(a["bbox"][2], b["bbox"][2]) - max(a["bbox"][0], b["bbox"][0])
                    y_overlap = min(a["bbox"][3], b["bbox"][3]) - max(a["bbox"][1], b["bbox"][1])
                    if x_overlap > 2 and y_overlap > 2:
                        overlaps.append({"page": number, "first": a["id"], "second": b["id"],
                                         "intersection": [round(x_overlap, 2), round(y_overlap, 2)]})
            vertical = _interval_union([(b[1], b[3]) for b in boxes])
            gaps = [b[0]-a[1] for a, b in zip(vertical, vertical[1:])]
            bbox = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)] if boxes else None
            page_text = page.get_text()
            texts.append(page_text)
            pages.append({"page": number, "final_page": number == len(document), "characters": len(page_text.strip()),
                          "content_bbox": [round(v, 2) for v in bbox] if bbox else None,
                          "bbox_area_occupancy": round(_rect_union_area(boxes) / content_area, 4),
                          "vertical_occupancy": round(sum(b-a for a, b in vertical)/(bottom-top), 4),
                          "top_whitespace_pt": round(max(0, bbox[1]-top), 2) if bbox else round(bottom-top, 2),
                          "bottom_whitespace_pt": round(max(0, bottom-bbox[3]), 2) if bbox else round(bottom-top, 2),
                          "max_internal_whitespace_pt": round(max(gaps, default=0), 2),
                          "image_count": sum(x["type"] == "image" for x in content),
                          "content_boxes": content})
    figure_checks = []
    for figure in layout_manifest["figures"]:
        image = [b for b in layout_manifest["blocks"] if b.get("figure_index") == figure["index"] and b["kind"] == "figure"]
        caption = [b for b in layout_manifest["blocks"] if b.get("figure_index") == figure["index"] and b["kind"] == "caption"]
        pair_ok = (len(image) == len(caption) == 1 and image[0]["page"] == caption[0]["page"]
                   and -1 <= caption[0]["bbox"][1]-image[0]["bbox"][3] <= 18)
        figure_checks.append({"index": figure["index"], "same_page_and_adjacent": pair_ok,
                              "source_hash_matches": Path(figure["path"]).exists() and _hash(Path(figure["path"])) == figure["sha256"]})
    def normalize(text):
        # Do not normalize signs, digits or punctuation: changing a scientific
        # value or relation must remain a hard preservation failure.
        return re.sub(r"\s+", "", text)

    def block_text(blocks):
        parts = []
        for block in sorted(blocks, key=lambda row: (row["page"], row["bbox"][1], row["bbox"][0])):
            x0, y0, x1, y1 = block["bbox"]
            for span in body_spans.get(block["page"], []):
                a, b, c, d = span["bbox"]
                # Centers assign each line to its actual laid-out paragraph;
                # font ascenders/descenders may exceed the line's advance box.
                if y0 - .05 <= (b + d) / 2 <= y1 + .05 and c > x0 and a < x1:
                    parts.append(span["text"])
        return "".join(parts)

    normalized = normalize("".join(span["text"] for spans in body_spans.values() for span in spans))
    text_verification, missing_text = [], []
    for item in layout_manifest["expected_text"]:
        blocks = [block for block in layout_manifest["blocks"] if block["id"] == item["id"]]
        # Table cells in existing manifests share one tracked table. All other
        # text is checked at its own location, so a duplicate elsewhere cannot
        # conceal a deleted paragraph. Split paragraphs concatenate across
        # pages without the page number / synthetic-data footer in between.
        if not blocks and item["id"].startswith("metric-"):
            blocks = [block for block in layout_manifest["blocks"] if block["id"] == "metrics-table"]
        actual = normalize(block_text(blocks))
        matched = normalize(item["text"]) in actual
        if not matched:
            missing_text.append(item["id"])
        text_verification.append({"id": item["id"], "matched": matched,
                                  "pages": sorted({block["page"] for block in blocks}),
                                  "method": "tracked_body_spans_without_decorations"})
    page_count = len(pages)
    within_engine_limit = 1 <= page_count <= 6
    constraint_met = within_engine_limit and (req["page_mode"] == "auto" or
                    (page_count <= req["pages"] if req["page_mode"] == "max" else page_count == req["pages"]))
    checks = {"file_hash_matches": _hash(pdf_path) == layout_manifest["sha256"], "no_content_overflow": not overflow,
              "no_actual_page_clipping": not page_clipping,
              "no_structural_overlap": not overlaps, "all_text_preserved": not missing_text,
              "figure_caption_pairs": all(x["same_page_and_adjacent"] for x in figure_checks),
              "figure_sources_unchanged": all(x["source_hash_matches"] for x in figure_checks),
              "figure_count_matches": sum(p["image_count"] for p in pages) == len(layout_manifest["figures"]),
              "no_empty_pages": all(p["content_bbox"] is not None for p in pages),
              "no_replacement_glyphs": "\ufffd" not in normalized,
              "page_constraint_satisfied": constraint_met}
    warnings = []
    warnings.extend({"page": row["page"], "type": "minor_text_frame_overhang",
                     "points": row["max_overhang_pt"], "bbox": row["bbox"],
                     "reason": "Glyphs remain within the physical page; up to 3 pt of planned frame overhang is accepted only with all hard checks passing."}
                    for row in frame_deviations if row["severity"] == "soft")
    for page in pages:
        if page["max_internal_whitespace_pt"] > 90:
            warnings.append({"page": page["page"], "type": "large_internal_gap", "points": page["max_internal_whitespace_pt"]})
        if not page["final_page"] and page["bottom_whitespace_pt"] > 180:
            warnings.append({"page": page["page"], "type": "large_nonfinal_tail", "points": page["bottom_whitespace_pt"]})
        if page["final_page"] and page["vertical_occupancy"] < .15 and page_count > 1:
            warnings.append({"page": page["page"], "type": "very_sparse_final_page", "occupancy": page["vertical_occupancy"]})
    passed = all(checks.values())
    hard_errors = [{"check": name} for name, value in checks.items() if not value]
    return {"quality_passed": passed, "constraints_satisfied": constraint_met, "page_count": page_count,
            "checks": checks, "pages": pages, "overflow": overflow, "overlaps": overlaps,
            "missing_text": missing_text, "figure_checks": figure_checks, "warnings": warnings,
            "text_verification": text_verification, "frame_deviations": frame_deviations,
            "actual_page_clipping": page_clipping, "hard_errors": hard_errors, "soft_warnings": warnings,
            "acceptance_status": ("accepted_with_warnings" if warnings else "accepted") if passed else "rejected",
            "policy_version": AUDIT_POLICY_VERSION,
            "acceptance_policy": {"soft_text_overhang_pt": SOFT_TEXT_OVERHANG_PT,
                                  "page_constraints_are_hard": True,
                                  "content_loss_and_actual_clipping_are_hard": True,
                                  "soft_warnings_require_all_hard_checks_to_pass": True},
            "density_definition": "Union area of actual text-span boxes plus full embedded image boxes / printable content area. Figure margins count within image boxes; this is not colored-pixel density. All pages, including the final page, are reported.",
            "scope": "Deterministic layout/content-preservation checks; scientific review and human visual inspection remain separate."}


def _candidate_configs(payload):
    base = _configuration(payload)
    compact = dict(base, font_size=max(9.6, base["font_size"]-.2), leading=max(14.2, base["leading"]-.8),
                   figure_height=max(178, base["figure_height"]-24), paragraph_gap=4.5, section_gap=8)
    dense = dict(base, font_size=9.4, leading=14.0, figure_height=164, paragraph_gap=3.5, section_gap=7)
    roomy = dict(base, font_size=min(10.7, base["font_size"]+.4), leading=min(17.2, base["leading"]+1),
                 figure_height=min(252, base["figure_height"]+26), paragraph_gap=7.5, section_gap=12)
    return [base, compact, dense, roomy]


def measure_capacity(payload: dict) -> dict:
    """Measure a supplied one-page document without writing or rendering a PDF.

    The real title, paragraphs, metrics, captions and style are wrapped with
    the renderer's own flowables. Figures may omit path before plotting and
    supply aspect_ratio (default 7.4/4.5). This is an admission preflight, not
    PDF QA: glyph bounds, hashes and actual figure geometry still need audit.
    No universal character limit is inferred from this specific document.
    """
    payload = _validate(payload, virtual_figures=True)
    trials = []
    for number, config in enumerate(_candidate_configs(payload), 1):
        measured = render_document(payload, None, config, _measure_only=True)
        spare = measured["available_height_pt"] - measured["height_pt"]
        trials.append(dict(measured, attempt=number, spare_height_pt=spare,
                           fits_one_page=spare >= 2.0))
    fitting = [trial for trial in trials if trial["fits_one_page"]]
    selected = min(fitting or trials, key=lambda trial: (
        0 if trial["fits_one_page"] else max(0, -trial["spare_height_pt"]),
        -trial["config"]["font_size"], -trial["config"]["figure_height"], trial["attempt"]))
    return {"engine_version": ENGINE_VERSION, "fits_one_page": bool(fitting),
            "height_pt": selected["height_pt"], "available_height_pt": selected["available_height_pt"],
            "spare_height_pt": selected["spare_height_pt"], "safety_reserve_pt": 2.0,
            "selected_config": selected["config"], "trials": trials,
            "reason": "Full supplied content fits with a 2 pt vertical reserve." if fitting else
                      "Approved content exceeds one-page capacity within readability bounds; revise content or page constraint.",
            "scope": "Read-only flowable measurement; final PDF audit remains mandatory."}


def build_document(payload: dict, output_dir: Path, repair: bool = True) -> dict:
    """Build a PDF with preserved content and at most four logged layout attempts.

    requirements: page_mode=auto|max|exact, pages=1..6 or null for auto,
    style=brief|technical|paper. Auto uses the natural document length, capped at
    six pages. Max/exact limits cannot authorize content loss, padding, extra
    figures or invented prose. Unsatisfied requirements return false with the
    best readable PDF for inspection. A wrapper must not label that a success.
    """
    payload = _validate(payload)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    attempts_dir = output_dir / "layout_attempts"
    attempts_dir.mkdir(exist_ok=True)
    candidates = _candidate_configs(payload) if repair else [_configuration(payload)]
    attempts, successful = [], []
    for number, config in enumerate(candidates, 1):
        path = attempts_dir / f"attempt-{number}.pdf"
        try:
            rendered = render_document(payload, path, config)
            audit = audit_document(path, rendered["layout_manifest"], payload["requirements"])
            _write_json(path.with_suffix(".audit.json"), audit)
            entry = {"attempt": number, "config": config, "path": str(path), "sha256": _hash(path),
                     "page_count": audit["page_count"], "quality_passed": audit["quality_passed"],
                     "constraints_satisfied": audit["constraints_satisfied"], "warnings": audit["warnings"],
                     "failed_checks": [k for k, v in audit["checks"].items() if not v]}
            attempts.append(entry)
            # Inspect all bounded candidates: an acceptable default can still
            # leave an avoidable near-empty last page. Preserve safety/content
            # before page compliance; among valid layouts prefer fewer pages,
            # then the largest type and figures. Do not shrink to hide failure.
            unsafe = [name for name in entry["failed_checks"] if name != "page_constraint_satisfied"]
            page_preference = audit["page_count"] if payload["requirements"]["page_mode"] != "exact" else 0
            score = (len(unsafe), not audit["constraints_satisfied"], page_preference,
                     -config["font_size"], -config["figure_height"], -config["leading"],
                     len(audit["warnings"]), number)
            successful.append((score, rendered, audit, entry))
        except Exception as error:
            attempts.append({"attempt": number, "config": config, "path": str(path),
                             "quality_passed": False, "error_type": type(error).__name__, "error": str(error)})
    if not successful:
        result = {"engine_version": ENGINE_VERSION, "path": None, "quality_passed": False,
                  "constraints_satisfied": False, "attempts": attempts, "reason": "No bounded readable layout could be built.",
                  "acceptance_status": "rejected", "policy_version": AUDIT_POLICY_VERSION,
                  "hard_errors": [{"check": "readable_layout_built"}], "soft_warnings": []}
        _write_json(output_dir / "layout_result.json", result)
        return result
    _, selected, audit, entry = min(successful, key=lambda x: x[0])
    final_path = output_dir / "research_report.pdf"
    shutil.copyfile(selected["path"], final_path)
    manifest = selected["layout_manifest"]
    manifest["path"], manifest["sha256"] = str(final_path), _hash(final_path)
    manifest_path = final_path.with_suffix(".layout.json")
    _write_json(manifest_path, manifest)
    audit_path = final_path.with_suffix(".audit.json")
    _write_json(audit_path, audit)
    result = {"engine_version": ENGINE_VERSION, "path": str(final_path), "sha256": _hash(final_path),
              "page_count": audit["page_count"], "quality_passed": audit["quality_passed"],
              "constraints_satisfied": audit["constraints_satisfied"], "audit": audit,
              "acceptance_status": audit["acceptance_status"], "policy_version": audit["policy_version"],
              "hard_errors": audit["hard_errors"], "soft_warnings": audit["soft_warnings"],
              "selected_config": selected["config"], "selected_attempt": entry["attempt"],
              "attempts": attempts, "manifest_path": str(manifest_path), "manifest_sha256": _hash(manifest_path),
              "audit_path": str(audit_path), "audit_sha256": _hash(audit_path)}
    if not audit["constraints_satisfied"]:
        result["reason"] = "Page constraint cannot be satisfied within readability bounds without changing approved content; request semantic revision or a different page limit."
    _write_json(output_dir / "layout_result.json", result)
    return result
