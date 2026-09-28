"""Conservative, reversible presentation views for certified tool outputs.

A codec may remove presentation markup, but never select evidence by relevance.
The original result is kept by the projection proxy and can be restored exactly.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser


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
