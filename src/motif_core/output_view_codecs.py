"""Conservative, reversible presentation views for certified tool outputs.

A codec may remove presentation markup, but never select evidence by relevance.
The original result is kept by the projection proxy and can be restored exactly.
"""

from __future__ import annotations

import json
import re
import hashlib
import unicodedata
from html.parser import HTMLParser
from typing import Any, Mapping


_METADATA = "SSS_STRUCTURED_METADATA_V1 "
_OPEN = "<untrusted-tool-output>\n"
_CLOSE = "</untrusted-tool-output>"
_SPACE = re.compile(r"\s+")
_BLOCKS = {"address", "article", "blockquote", "br", "div", "h1", "h2", "h3",
           "h4", "h5", "h6", "li", "p", "section", "table", "td", "th", "tr"}


class _VisibleHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.visible_fragments: list[str] = []
        self.suppressed: list[str] = []
        self.invalid = False
        self.body_seen = False
        self.content_images_without_alt = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "body":
            self.body_seen = True
        if tag in {"script", "noscript", "iframe", "svg"}:
            self.invalid = True
        if tag == "style":
            self.suppressed.append(tag)
        if self.suppressed:
            return
        if tag in _BLOCKS:
            self.parts.append("\n")
        if tag == "img":
            alt = attributes.get("alt") or ""
            if alt.strip():
                self.visible_fragments.append(alt.strip())
                self.parts.append(alt.strip())
            elif attributes.get("width") != "1" or attributes.get("height") != "1":
                self.content_images_without_alt += 1
        if attributes.get("hidden") is not None or attributes.get("aria-hidden") == "true":
            # CSS visibility requires a renderer; do not make a visibility
            # claim for mail containing explicitly hidden elements.
            self.invalid = True

    def handle_endtag(self, tag: str) -> None:
        if self.suppressed:
            if tag == self.suppressed[-1]:
                self.suppressed.pop()
            return
        if tag in _BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.suppressed:
            if "content:" in data.lower():
                self.invalid = True
            return
        clean = _SPACE.sub(" ", data).strip()
        if clean:
            self.visible_fragments.append(clean)
            self.parts.append(clean)

    def handle_entityref(self, name: str) -> None:
        self.invalid = True

    def handle_charref(self, name: str) -> None:
        self.invalid = True


def marked_html_visible_text_v1(raw: str) -> tuple[str, dict[str, int]]:
    """Keep every visible text fragment and header in a marked HTML result.

    URLs and markup are omitted from the view; the caller must provide exact
    restoration. Malformed or unfamiliar messages fail closed.
    """
    first, separator, rest = raw.partition("\n")
    if not separator or not first.startswith(_METADATA) or not rest.startswith(_OPEN):
        raise ValueError("marked HTML result is missing its trusted envelope")
    metadata = json.loads(first[len(_METADATA):])
    if (not isinstance(metadata, dict)
            or not all(isinstance(metadata.get(key), str) and metadata[key]
                       for key in ("message_id", "thread_id", "source_version"))
            or metadata["message_id"] != metadata["source_version"]):
        raise ValueError("marked HTML result lacks a verified source version")
    if not rest.rstrip().endswith(_CLOSE) or rest.count(_OPEN) != 1:
        raise ValueError("marked HTML result has an invalid untrusted envelope")
    content = rest[len(_OPEN):rest.rfind(_CLOSE)].rstrip()
    starts = list(re.finditer(r"<html(?:\s|>)", content, re.IGNORECASE))
    ends = list(re.finditer(r"</html\s*>", content, re.IGNORECASE))
    if len(starts) != 1 or len(ends) != 1 or starts[0].start() >= ends[0].start():
        raise ValueError("marked result does not contain one complete HTML document")
    header = content[:starts[0].start()].rstrip()
    html = content[starts[0].start():ends[0].end()]
    if content[ends[0].end():].strip() or not header.startswith("Thread ID: "):
        raise ValueError("marked HTML result has unrecognized surrounding content")
    parser = _VisibleHTML()
    parser.feed(html)
    parser.close()
    if (parser.invalid or parser.suppressed or not parser.body_seen
            or parser.content_images_without_alt or not parser.visible_fragments):
        raise ValueError("HTML contains evidence requiring original presentation")
    visible = "".join(parser.parts)
    visible = re.sub(r"[ \t]*\n[ \t]*", "\n", visible)
    visible = re.sub(r"\n{3,}", "\n\n", visible).strip()
    # Check each text or alt fragment survived in source order. The view may
    # add line breaks but cannot silently discard a paper title or abstract.
    cursor = 0
    flattened = _SPACE.sub(" ", visible)
    for fragment in parser.visible_fragments:
        index = flattened.find(fragment, cursor)
        if index < 0:
            raise ValueError("visible evidence fragment was lost")
        cursor = index + len(fragment)
    view = (first + "\n" + _OPEN + header + "\n\n"
            + "[SSS visible-text view; HTML markup and link URLs omitted. "
            + "Recover the exact original before using omitted details.]\n"
            + visible + "\n" + _CLOSE)
    return view, {"visible_fragments": len(parser.visible_fragments),
                  "original_bytes": len(raw.encode("utf-8")),
                  "view_bytes": len(view.encode("utf-8"))}


CODECS = {"marked_html_visible_text_v1": marked_html_visible_text_v1}


def _normalized_with_offsets(raw: str) -> tuple[str, list[int]]:
    """Mirror the PDF locator normalization and retain positions in raw text."""
    characters: list[str] = []
    offsets: list[int] = []
    for index, source in enumerate(raw):
        for character in unicodedata.normalize("NFKC", source).casefold():
            if character.isspace():
                if characters and characters[-1] != " ":
                    characters.append(" ")
                    offsets.append(index)
            else:
                characters.append(character)
                offsets.append(index)
    if characters and characters[-1] == " ":
        characters.pop()
        offsets.pop()
    rendered = "".join(characters)
    expected = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", raw)).strip().casefold()
    if rendered != expected:
        raise ValueError("PDF text normalization cannot preserve quote offsets")
    return rendered, offsets


def pdf_match_quote_window_v1(
    raw: str, context: Mapping[str, Any], *, radius: int = 500,
) -> tuple[str, dict[str, int]]:
    """Show a witnessed exact quote and nearby PDF text for quote checks only.

    The caller must gate this on a certified locator->read parameter edge and
    an explicit quote-verification task scope. This codec alone does not decide
    that other content on the PDF page is irrelevant to scientific judgment.
    """
    value = json.loads(raw)
    locator = context.get("locator")
    quote = context.get("quote")
    if (not isinstance(value, dict) or not isinstance(locator, dict)
            or not isinstance(quote, str) or not 12 <= len(quote) <= 500
            or locator.get("status") != "unique" or locator.get("match_count") != 1
            or value.get("match_id") != context.get("match_id")
            or value.get("match_id") != locator.get("match_id")
            or not isinstance(value.get("match_id"), str)
            or re.fullmatch(r"match-[0-9a-f]{32}", value["match_id"]) is None
            or value.get("sha256") != locator.get("sha256")
            or not isinstance(value.get("source_id"), str)
            or not isinstance(value.get("role"), str) or not value["role"]
            or not isinstance(value.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is None
            or type(value.get("pdf_page_count")) is not int
            or value["pdf_page_count"] < 1
            or not isinstance(value.get("pages"), list) or len(value["pages"]) != 1
            or not isinstance(locator.get("matches"), list)
            or len(locator["matches"]) != 1):
        raise ValueError("PDF quote view lacks one versioned locator match")
    needle = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", quote)).strip().casefold()
    if (len(needle) < 12 or locator.get("quote_sha256")
            != hashlib.sha256(needle.encode()).hexdigest()):
        raise ValueError("PDF quote does not match the locator's quote hash")
    page = value["pages"][0]
    match = locator["matches"][0]
    if (not isinstance(page, dict) or not isinstance(match, dict)
            or type(page.get("pdf_page")) is not int
            or page["pdf_page"] != match.get("pdf_page")
            or not isinstance(page.get("text"), str)
            or type(page.get("total_chars")) is not int
            or page["total_chars"] < len(page["text"])
            or type(page.get("truncated")) is not bool
            or page.get("low_text") is True
            or not isinstance(match.get("page_text_sha256"), str)):
        # read_pinned_pdf_match verifies the complete page hash before returning
        # a page excerpt. The excerpt may be truncated by the reader's limit.
        raise ValueError("PDF page does not match the locator's witnessed page")
    normalized, offsets = _normalized_with_offsets(page["text"])
    if normalized.count(needle) != 1:
        raise ValueError("PDF quote is absent or ambiguous in the returned page")
    position = normalized.find(needle)
    first = offsets[max(0, position - radius)]
    last = offsets[min(len(offsets) - 1, position + len(needle) + radius - 1)] + 1
    excerpt = page["text"][first:last]
    result = {
        "source_id": value["source_id"], "role": value.get("role"),
        "sha256": value["sha256"], "match_id": value["match_id"],
        "pdf_page_count": value.get("pdf_page_count"),
        "pdf_page": page["pdf_page"], "quote": quote,
        "quote_context": excerpt, "page_total_chars": page.get("total_chars"),
        "page_truncated_by_tool": page.get("truncated"),
        "view_scope": "verify_this_quote_only",
        "notice": "Other page text is omitted. Restore the original result before broader scientific claims.",
    }
    view = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    return view, {"visible_fragments": 2,
                  "original_bytes": len(raw.encode("utf-8")),
                  "view_bytes": len(view.encode("utf-8"))}


CONTEXT_CODECS = {"pdf_match_quote_window_v1": pdf_match_quote_window_v1}
