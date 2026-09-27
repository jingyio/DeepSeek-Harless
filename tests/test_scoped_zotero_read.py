"""Scoped Zotero tools require explicit approval and an unchanged local item."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import Client

from src.mcp import scoped_zotero_read_server as scoped
from src.mcp.structured_research_tools import HandleStore


class ScopedZoteroTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(dir=scoped.LOCAL)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.item = {"key": "ABCD1234", "version": 7, "data": {
            "itemType": "journalArticle", "title": "A study", "abstractNote": "An abstract"}}
        self.annotation = {"key": "EFGH5678", "version": 3, "data": {
            "itemType": "annotation", "parentItem": "ABCD1234", "annotationPageLabel": "4",
            "annotationText": "Marked claim", "annotationComment": "Check this"}}
        self.items = {row["key"]: row for row in (self.item, self.annotation)}
        self.scope = {"zotero_sources": [
            self._row("paper", "item", self.item),
            self._row("margin_note", "annotation", self.annotation),
        ]}
        self.scope_file = self.root / "scope.json"
        self._write_scope()
        environment = patch.dict(os.environ, {"SSS_RESEARCH_SCOPE_FILE": str(self.scope_file)})
        environment.start()
        self.addCleanup(environment.stop)
        store = patch.object(scoped, "_HANDLE_STORE", HandleStore(self.root / "handles.sqlite3"))
        store.start()
        self.addCleanup(store.stop)
        fetch = patch.object(scoped, "_fetch_item", side_effect=lambda key: self.items[key])
        fetch.start()
        self.addCleanup(fetch.stop)

    @staticmethod
    def _row(role: str, kind: str, item: dict) -> dict:
        return {"role": role, "kind": kind, "key": item["key"],
                "version": item["version"], "data_sha256": scoped._data_digest(item),
                "external_model_excerpt_allowed": True}

    def _write_scope(self) -> None:
        self.scope_file.write_text(json.dumps(self.scope), encoding="utf-8")

    def test_pin_read_version_and_scope_invalidation(self) -> None:
        pinned = scoped.pin_scoped_zotero_source("paper")
        self.assertRegex(pinned["source_id"], r"^source-[0-9a-f]{32}$")
        self.assertEqual(scoped.read_pinned_zotero_item(pinned["source_id"])["title"], "A study")
        with self.assertRaisesRegex(ValueError, "kind changed"):
            scoped.read_pinned_zotero_annotation(pinned["source_id"])
        self.item["version"] = 8
        with self.assertRaisesRegex(ValueError, "version changed"):
            scoped.read_pinned_zotero_item(pinned["source_id"])
        self.item["version"] = 7
        self.scope["zotero_sources"][0]["external_model_excerpt_allowed"] = False
        self._write_scope()
        with self.assertRaisesRegex(ValueError, "scope or kind changed"):
            scoped.read_pinned_zotero_item(pinned["source_id"])

    def test_annotation_and_unapproved_role(self) -> None:
        pinned = scoped.pin_scoped_zotero_source("margin_note")
        result = scoped.read_pinned_zotero_annotation(pinned["source_id"])
        self.assertEqual((result["marked_text"], result["researcher_comment"],
                          result["page_label"]), ("Marked claim", "Check this", "4"))
        with self.assertRaisesRegex(ValueError, "not uniquely approved"):
            scoped.pin_scoped_zotero_source("unlisted")
        self.annotation["data"]["annotationComment"] = "Changed"
        with self.assertRaisesRegex(ValueError, "version changed"):
            scoped.read_pinned_zotero_annotation(pinned["source_id"])

    def test_annotation_attachment_is_resolved_to_approved_paper(self) -> None:
        attachment = {"key": "PDFX1234", "version": 5, "data": {
            "itemType": "attachment", "parentItem": self.item["key"],
            "title": "Private attachment title must not be returned"}}
        self.items[attachment["key"]] = attachment
        self.annotation["data"]["parentItem"] = attachment["key"]
        self.scope["zotero_sources"][1] = self._row(
            "margin_note", "annotation", self.annotation)
        self.scope["zotero_attachment_relationships"] = [{
            "key": attachment["key"], "version": attachment["version"],
            "data_sha256": scoped._data_digest(attachment),
            "parent_paper_key": self.item["key"]}]
        self._write_scope()
        pinned = scoped.pin_scoped_zotero_source("margin_note")
        result = scoped.read_pinned_zotero_annotation(pinned["source_id"])
        self.assertEqual(result["parent_relation"], {
            "status": "verified_attachment_to_paper", "attachment_key": "PDFX1234",
            "attachment_version": 5, "approved_paper_key": "ABCD1234"})
        self.assertNotIn("Private attachment title", str(result))
        self.item["version"] += 1
        with self.assertRaisesRegex(ValueError, "version changed"):
            scoped.read_pinned_zotero_annotation(pinned["source_id"])

    def test_attachment_relation_drift_is_not_reported_as_verified(self) -> None:
        attachment = {"key": "PDFX1234", "version": 5, "data": {
            "itemType": "attachment", "parentItem": self.item["key"]}}
        self.items[attachment["key"]] = attachment
        self.annotation["data"]["parentItem"] = attachment["key"]
        self.scope["zotero_sources"][1] = self._row(
            "margin_note", "annotation", self.annotation)
        self.scope["zotero_attachment_relationships"] = [{
            "key": attachment["key"], "version": attachment["version"],
            "data_sha256": scoped._data_digest(attachment),
            "parent_paper_key": self.item["key"]}]
        self._write_scope()
        pinned = scoped.pin_scoped_zotero_source("margin_note")
        attachment["version"] += 1
        relation = scoped.read_pinned_zotero_annotation(
            pinned["source_id"])["parent_relation"]
        self.assertEqual(relation["status"], "unverified")

    def test_missing_attachment_does_not_invent_a_paper_relation(self) -> None:
        self.annotation["data"]["parentItem"] = "MISSING01"
        self.scope["zotero_sources"][1] = self._row(
            "margin_note", "annotation", self.annotation)
        self._write_scope()
        pinned = scoped.pin_scoped_zotero_source("margin_note")
        relation = scoped.read_pinned_zotero_annotation(
            pinned["source_id"])["parent_relation"]
        self.assertEqual(relation["status"], "unverified")
        self.assertIsNone(relation["approved_paper_key"])


class ScopedZoteroMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_four_read_tools_are_exposed(self) -> None:
        async with Client(scoped.server) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
        self.assertEqual(names, {"list_scoped_zotero_sources", "pin_scoped_zotero_source",
                                 "read_pinned_zotero_item", "read_pinned_zotero_annotation"})


if __name__ == "__main__":
    unittest.main()
