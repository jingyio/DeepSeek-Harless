"""A trial Agent may read only approved, unchanged Obsidian notes."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

from mcp import Client
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from src.mcp import scoped_obsidian_read_server as scoped
from src.mcp.structured_research_tools import HandleStore


class ScopedObsidianTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(dir=scoped.LOCAL)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.note = self.root / "selected.md"
        self.note.write_text("approved research note", encoding="utf-8")
        self.scope = {"obsidian_vault_root": str(self.root), "sources": [{
            "role": "current_state", "vault_path": "selected.md",
            "path": str(self.note),
            "sha256": hashlib.sha256(self.note.read_bytes()).hexdigest(),
            "external_model_excerpt_allowed": False,
        }]}
        self.scope_patch = patch.object(scoped, "_scope", return_value=self.scope)
        self.scope_patch.start()
        self.addCleanup(self.scope_patch.stop)

    def test_approval_and_exact_version_are_required(self) -> None:
        self.assertEqual(scoped.list_scoped_notes()["count"], 0)
        with self.assertRaisesRegex(ValueError, "not approved"):
            scoped._approved_note("current_state")
        self.scope["sources"][0]["external_model_excerpt_allowed"] = True
        self.assertEqual(scoped._approved_note("current_state")[1], "selected.md")
        self.note.write_text("changed research note", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "version changed"):
            scoped._approved_note("current_state")

    def test_unlisted_note_is_rejected(self) -> None:
        self.scope["sources"][0]["external_model_excerpt_allowed"] = True
        with self.assertRaisesRegex(ValueError, "not approved"):
            scoped._approved_note("other_note")

    def test_approved_note_excerpt_rejects_outside_lines_before_mcp(self) -> None:
        self.scope["sources"][0]["external_model_excerpt_allowed"] = True
        self.scope["sources"][0]["allowed_line_ranges"] = [[2, 4]]
        with self.assertRaisesRegex(ValueError, "outside approved excerpt"):
            import asyncio
            asyncio.run(scoped.read_scoped_note("current_state", start_line=1, max_lines=2))

    def test_scoped_local_text_and_pdf(self) -> None:
        text = self.root / "week6.md"
        text.write_text("first\nsecond\nthird\n", encoding="utf-8")
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buffer = BytesIO()
        writer.write(buffer)
        pdf = self.root / "week7.pdf"
        pdf.write_bytes(buffer.getvalue())
        for role, path in (("model_rsi_week6", text), ("model_rsi_week7", pdf)):
            self.scope["sources"].append({"role": role, "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "external_model_excerpt_allowed": True})
        read = scoped.read_scoped_text("model_rsi_week6", start_line=2, max_lines=120)
        self.assertIn("2: second", read["numbered_text"])
        self.assertEqual(read["returned_max_lines"], 100)
        self.assertEqual(scoped.read_scoped_pdf_pages("model_rsi_week7")["pdf_page_count"], 1)
        text.write_text("modified", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "version changed"):
            scoped.read_scoped_text("model_rsi_week6")

    def test_pdf_pages_must_stay_in_approved_ranges(self) -> None:
        writer = PdfWriter()
        for _ in range(4):
            writer.add_blank_page(width=200, height=200)
        pdf = self.root / "paper.pdf"
        with pdf.open("wb") as stream:
            writer.write(stream)
        row = {"role": "paper", "path": str(pdf),
               "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
               "allowed_page_ranges": [[2, 3]],
               "external_model_excerpt_allowed": True}
        self.scope["sources"].append(row)
        self.assertEqual(len(scoped.read_scoped_pdf_pages("paper", 2, 2)["pages"]), 2)
        with self.assertRaisesRegex(ValueError, "outside approved excerpt"):
            scoped.read_scoped_pdf_pages("paper", 1, 2)
        clipped = scoped.read_scoped_pdf_pages("paper", 3, 3)
        self.assertEqual([page["pdf_page"] for page in clipped["pages"]], [3])
        self.assertTrue(clipped["clipped_to_tool_limit"])
        self.assertTrue(clipped["clipped_to_approved_excerpt"])
        self.assertIsNone(clipped["next_page"])
        row["allowed_page_ranges"] = [[0, 3]]
        with self.assertRaisesRegex(ValueError, "Invalid approved PDF page ranges"):
            scoped.read_scoped_pdf_pages("paper", 2, 1)


class ScopedObsidianMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_read_tools_are_exposed(self) -> None:
        async with Client(scoped.server) as client:
            names = {item.name for item in (await client.list_tools()).tools}
        self.assertEqual(names, {"list_scoped_notes", "read_scoped_note",
                                 "list_scoped_local_sources", "read_scoped_text",
                                 "read_scoped_pdf_pages"})

    async def test_handle_mode_exposes_only_pinned_reads(self) -> None:
        async with Client(scoped.create_server(handle_mode=True)) as client:
            names = {item.name for item in (await client.list_tools()).tools}
        self.assertEqual(names, {"list_scoped_notes", "list_scoped_local_sources",
                                 "pin_scoped_source", "read_pinned_note",
                                 "read_pinned_approved_note_excerpt",
                                 "read_pinned_text", "read_pinned_pdf_pages",
                                 "locate_pinned_pdf_quote", "read_pinned_pdf_match"})

    async def test_notes_only_mode_hides_local_file_tools(self) -> None:
        async with Client(scoped.create_server(handle_mode=True, notes_only=True)) as client:
            names = {item.name for item in (await client.list_tools()).tools}
        self.assertEqual(names, {"list_scoped_notes", "pin_scoped_note",
                                 "read_pinned_approved_note_excerpt"})


class ScopedSourceHandleTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(dir=scoped.LOCAL)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.note = self.root / "note.md"
        self.note.write_text("one\ntwo\n", encoding="utf-8")
        self.data = self.root / "data.txt"
        self.data.write_text("alpha\nbeta\n", encoding="utf-8")
        scope = {"obsidian_vault_root": str(self.root), "sources": [
            {"role": "note", "vault_path": "note.md", "path": str(self.note),
             "sha256": hashlib.sha256(self.note.read_bytes()).hexdigest(),
             "external_model_excerpt_allowed": True},
            {"role": "data", "path": str(self.data),
             "sha256": hashlib.sha256(self.data.read_bytes()).hexdigest(),
             "external_model_excerpt_allowed": True},
        ]}
        self.scope_file = self.root / "scope.json"
        self.scope_file.write_text(json.dumps(scope), encoding="utf-8")
        self.env_patch = patch.dict(os.environ, {"SSS_RESEARCH_SCOPE_FILE": str(self.scope_file)})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.store_patch = patch.object(scoped, "_HANDLE_STORE",
                                        HandleStore(self.root / "handles.sqlite3"))
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)

    def test_handle_binds_scope_source_version_and_type(self) -> None:
        pinned = scoped.pin_scoped_source("data")
        self.assertRegex(pinned["source_id"], r"^source-[0-9a-f]{32}$")
        self.assertEqual(scoped.read_pinned_text(pinned["source_id"], start_line=2)["numbered_text"],
                         "2: beta")
        with self.assertRaisesRegex(ValueError, "type changed"):
            scoped.read_pinned_pdf_pages(pinned["source_id"])
        self.data.write_text("modified", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "version changed"):
            scoped.read_pinned_text(pinned["source_id"])

    def test_note_only_pin_rejects_local_text_role(self) -> None:
        with self.assertRaises(ValueError):
            scoped.pin_scoped_note("data")

    def test_approved_note_overlong_request_is_clipped_without_exposure(self) -> None:
        self.assertEqual(scoped._approved_note_read_limit([[120, 175]], 120, 60),
                         (56, 175))
        with self.assertRaisesRegex(ValueError, "outside approved excerpt"):
            scoped._approved_note_read_limit([[120, 175]], 1, 80)

    def test_permission_change_invalidates_existing_handle(self) -> None:
        pinned = scoped.pin_scoped_source("note")
        scope = json.loads(self.scope_file.read_text(encoding="utf-8"))
        scope["sources"][0]["external_model_excerpt_allowed"] = False
        self.scope_file.write_text(json.dumps(scope), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "scope or type changed"):
            scoped._resolve_pinned(pinned["source_id"], "note")

    def test_approved_note_excerpt_uses_scope_ranges_without_model_line_choice(self) -> None:
        import asyncio

        scope = json.loads(self.scope_file.read_text(encoding="utf-8"))
        scope["sources"][0]["allowed_line_ranges"] = [[2, 2]]
        self.scope_file.write_text(json.dumps(scope), encoding="utf-8")
        source = scoped.pin_scoped_source("note")["source_id"]
        result = {"sha256": scope["sources"][0]["sha256"],
                  "numbered_text": "2: two"}
        with patch.object(scoped, "read_scoped_note", new_callable=AsyncMock,
                          return_value=result) as read:
            excerpt = asyncio.run(scoped.read_pinned_approved_note_excerpt(source))
        read.assert_awaited_once_with("note", start_line=2, max_lines=1)
        self.assertEqual(excerpt["segments"], [{"start_line": 2,
                                                "end_line": 2,
                                                "numbered_text": "2: two"}])
        scope["sources"][0]["allowed_line_ranges"] = [[1, 200]]
        self.scope_file.write_text(json.dumps(scope), encoding="utf-8")
        source = scoped.pin_scoped_source("note")["source_id"]
        with self.assertRaisesRegex(ValueError, "exceeds 120 lines"):
            asyncio.run(scoped.read_pinned_approved_note_excerpt(source))

    def _pdf_with_text(self, pages: list[str]) -> Path:
        writer = PdfWriter()
        font = writer._add_object(DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }))
        for text in pages:
            page = writer.add_blank_page(width=400, height=400)
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 40 350 Td ({text}) Tj ET".encode("ascii"))
            page[NameObject("/Contents")] = writer._add_object(stream)
        target = self.root / "paper.pdf"
        with target.open("wb") as output:
            writer.write(output)
        scope = json.loads(self.scope_file.read_text(encoding="utf-8"))
        scope["sources"].append({"role": "paper", "path": str(target),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "allowed_page_ranges": [[2, 3]],
            "external_model_excerpt_allowed": True})
        self.scope_file.write_text(json.dumps(scope), encoding="utf-8")
        return target

    def test_quote_locator_unique_ambiguous_unapproved_and_stale(self) -> None:
        pdf = self._pdf_with_text([
            "Outside scope anchor only appears on page one.",
            "An exact annotation quotation appears here.",
            "A different result appears here.",
            "Outside scope anchor only appears on page four.",
        ])
        source = scoped.pin_scoped_source("paper")["source_id"]
        found = scoped.locate_pinned_pdf_quote(source, "annotation quotation appears")
        self.assertEqual(found["status"], "unique")
        self.assertEqual([item["pdf_page"] for item in found["matches"]], [2])
        self.assertEqual(scoped.read_pinned_pdf_match(found["match_id"])["pages"][0]["pdf_page"], 2)
        self.assertEqual(scoped.locate_pinned_pdf_quote(source, "Outside scope anchor")["status"],
                         "not_found")
        with self.assertRaisesRegex(ValueError, "too short|12–500"):
            scoped.locate_pinned_pdf_quote(source, "result")
        with self.assertRaisesRegex(ValueError, "Expected a match handle"):
            scoped.read_pinned_pdf_match(source)
        pdf.write_bytes(pdf.read_bytes() + b"\n% changed")
        with self.assertRaisesRegex(ValueError, "version changed"):
            scoped.read_pinned_pdf_match(found["match_id"])

    def test_quote_locator_does_not_choose_between_two_pages(self) -> None:
        self._pdf_with_text([
            "Outside approved range.",
            "The same exact quoted sentence appears here.",
            "The same exact quoted sentence appears here again.",
        ])
        source = scoped.pin_scoped_source("paper")["source_id"]
        found = scoped.locate_pinned_pdf_quote(source, "same exact quoted sentence")
        self.assertEqual(found["status"], "ambiguous")
        self.assertEqual([item["pdf_page"] for item in found["matches"]], [2, 3])
        self.assertNotIn("match_id", found)


if __name__ == "__main__":
    unittest.main()
