"""Exact Zotero identifier lookup does not expose fuzzy search hits."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from mcp import Client

from src.mcp import zotero_identifier_server as lookup


class ZoteroIdentifierTests(unittest.TestCase):
    def test_exact_match_filters_unrelated_search_hits(self) -> None:
        items = [
            {"key": "ABCD1234", "version": 3, "data": {
                "itemType": "journalArticle", "title": "Target",
                "DOI": "10.1234/EXAMPLE"}},
            {"key": "EFGH5678", "version": 1, "data": {
                "itemType": "journalArticle", "title": "Fuzzy hit",
                "DOI": "10.5678/other"}},
        ]
        with patch.object(lookup, "_search_page", return_value=(items, 2)):
            result = lookup.lookup_zotero_identifier("https://doi.org/10.1234/example")
        self.assertEqual((result["status"], result["match_count"], result["item_key"]),
                         ("unique_match", 1, "ABCD1234"))
        self.assertNotIn("Fuzzy hit", str(result))

    def test_no_exact_match_is_bounded_to_personal_index(self) -> None:
        item = {"key": "ABCD1234", "version": 3, "data": {
            "itemType": "journalArticle", "title": "Fuzzy hit"}}
        with patch.object(lookup, "_search_page", return_value=([item], 1)):
            result = lookup.lookup_zotero_identifier("2409.07429")
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["search_scope"], "indexed_personal_library")
        self.assertNotIn("Fuzzy hit", str(result))

    def test_ambiguous_exact_matches_are_not_selected(self) -> None:
        items = [{"key": key, "version": 1, "data": {
            "itemType": "journalArticle", "DOI": "10.1234/example"}}
                 for key in ("ABCD1234", "EFGH5678")]
        with patch.object(lookup, "_search_page", return_value=(items, 2)):
            result = lookup.lookup_zotero_identifier("10.1234/example")
        self.assertEqual(result["status"], "multiple_exact_matches")
        self.assertNotIn("ABCD1234", str(result))

    def test_arxiv_doi_relation_requires_exact_version(self) -> None:
        item = {"key": "ABCD1234", "version": 3, "data": {
            "itemType": "journalArticle", "DOI": "10.48550/arXiv.2409.07429"}}
        with patch.object(lookup, "_search_page", return_value=([item], 1)):
            self.assertEqual(lookup.lookup_zotero_identifier("2409.07429")
                             ["status"], "unique_match")
            self.assertEqual(lookup.lookup_zotero_identifier("2409.07429v2")
                             ["status"], "not_found")


class ZoteroIdentifierMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_exact_read_tool_is_exposed(self) -> None:
        async with Client(lookup.server) as client:
            tools = (await client.list_tools()).tools
        self.assertEqual([tool.name for tool in tools], ["lookup_zotero_identifier"])


if __name__ == "__main__":
    unittest.main()
