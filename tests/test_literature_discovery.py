"""Behavior checks for research discovery and bounded article access."""

from __future__ import annotations

import unittest
import json
from io import BytesIO
import xml.etree.ElementTree as ET
from unittest.mock import patch

from pypdf import PdfWriter

from src.mcp import literature_discovery_server as discovery


ARTICLE = ET.fromstring("""<article><front><article-meta>
<abstract><p>Abstract evidence and caveat.</p></abstract>
</article-meta></front><body><sec><title>Methods</title>
<p>Sample collection.</p><sec><title>Analysis</title><p>Statistical test.</p></sec>
</sec></body></article>""")
SOURCE = {"sha256": "a" * 64, "retrieved_at": "2026-09-25T00:00:00+00:00",
          "source_url": "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC123/fullTextXML",
          "cache_hit": True, "article_url": "https://europepmc.org/articles/PMC123"}
ARXIV_FEED = ET.fromstring("""<feed xmlns="http://www.w3.org/2005/Atom"
 xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
 xmlns:arxiv="http://arxiv.org/schemas/atom">
 <opensearch:totalResults>1</opensearch:totalResults><entry>
 <id>http://arxiv.org/abs/1706.03762v7</id><title>Attention Is All You Need</title>
 <summary>Neural attention.</summary><author><name>A. Researcher</name></author>
 <published>2017-06-12T00:00:00Z</published><arxiv:primary_category term="cs.CL"/>
 <link title="pdf" href="https://arxiv.org/pdf/1706.03762"/>
 </entry></feed>""")


class DiscoveryEntrypointTest(unittest.TestCase):
    def test_arxiv_search_uses_plain_words_without_doi(self) -> None:
        with patch.object(discovery, "_arxiv_feed", return_value=(ARXIV_FEED, "https://arxiv.org/api", False)) as feed:
            result = discovery.search_arxiv("attention transformer", limit=2)
        self.assertEqual(feed.call_args.args[0]["search_query"], "all:attention AND all:transformer")
        self.assertEqual(result["total_matches"], 1)
        self.assertEqual(result["papers"][0]["arxiv_id"], "1706.03762v7")
        self.assertIsNone(result["papers"][0]["doi"])

    def test_arxiv_id_validation_and_lookup(self) -> None:
        with patch.object(discovery, "_arxiv_feed", return_value=(ARXIV_FEED, "https://arxiv.org/api", True)):
            self.assertEqual(discovery.get_arxiv_paper("1706.03762")["paper"]["title"],
                             "Attention Is All You Need")
        with self.assertRaisesRegex(ValueError, "arXiv ID"):
            discovery.get_arxiv_paper("../private-file")

    def test_arxiv_provider_rejection_returns_explicit_partial_result(self) -> None:
        with patch.object(discovery, "_arxiv_feed", side_effect=[
            RuntimeError("arXiv returned HTTP 406"),
            (ARXIV_FEED, "https://arxiv.org/api?max_results=3", False),
        ]) as feed:
            result = discovery.search_arxiv("persistent memory transformer", limit=5)
        self.assertTrue(result["partial_due_to_provider_error"])
        self.assertEqual(result["requested_limit"], 5)
        self.assertEqual(feed.call_args.args[0]["max_results"], "3")
        self.assertEqual(len(result["papers"]), 1)

    def test_arxiv_provider_failure_is_not_reported_as_zero_matches(self) -> None:
        with patch.object(discovery, "_arxiv_feed", side_effect=RuntimeError("arXiv returned HTTP 406")):
            result = discovery.search_arxiv("test time learning", limit=3)
            paper = discovery.get_arxiv_paper("1706.03762")
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["total_matches"])
        self.assertEqual(result["papers"], [])
        self.assertEqual(paper["status"], "unavailable")

    def test_arxiv_pdf_page_read_is_bounded_and_versioned(self) -> None:
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.add_blank_page(width=200, height=200)
        out = BytesIO()
        writer.write(out)
        with patch.object(discovery, "_arxiv_pdf", return_value=(
            out.getvalue(), {"arxiv_id": "1706.03762v7", "sha256": "a" * 64})):
            result = discovery.read_arxiv_pdf_pages("1706.03762v7", start_page=2)
            self.assertEqual(result["pdf_page_count"], 2)
            self.assertEqual([row["pdf_page"] for row in result["pages"]], [2])
            self.assertTrue(result["pages"][0]["low_text"])
            with self.assertRaisesRegex(ValueError, "Start page"):
                discovery.read_arxiv_pdf_pages("1706.03762v7", start_page=3)
        with self.assertRaisesRegex(ValueError, "Page request"):
            discovery.read_arxiv_pdf_pages("1706.03762v7", max_pages=20)

    def test_arxiv_pdf_rejects_invalid_id_before_download(self) -> None:
        with self.assertRaisesRegex(ValueError, "arXiv ID"):
            discovery._arxiv_pdf("../private-file")

    def test_scholar_requires_key_and_budget(self) -> None:
        with patch.dict(discovery.os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SerpAPI key"):
                discovery.search_google_scholar("attention transformer")

    def test_scholar_response_is_bounded_and_does_not_expose_key(self) -> None:
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return None
            def read(self, *_):
                return json.dumps({"organic_results": [{"title": "Paper", "link": "https://example.org/p",
                                                         "snippet": "a" * 1500}]}).encode()
        with patch.dict(discovery.os.environ, {"SERPAPI_API_KEY": "private-test-key",
                                               "SERPAPI_MONTHLY_SEARCH_BUDGET": "3"}), \
             patch.object(discovery, "_reserve_scholar_search", return_value=(1, 3)), \
             patch.object(discovery.urllib.request, "urlopen", return_value=Response()):
            result = discovery.search_google_scholar("attention transformer")
        self.assertEqual(result["papers"][0]["title"], "Paper")
        self.assertEqual(len(result["papers"][0]["snippet"]), 1000)
        self.assertNotIn("private-test-key", str(result))


class EuropePMCTest(unittest.TestCase):
    def test_exact_doi_match_and_open_fulltext_gate(self) -> None:
        response = {"resultList": {"result": [
            {"doi": "10.1234/different", "pmcid": "PMC999", "isOpenAccess": "Y"},
            {"doi": "10.1234/example", "pmcid": "PMC123", "isOpenAccess": "Y",
             "title": "Paper", "license": "cc by"},
        ]}}
        with patch.object(discovery, "_request", return_value=(response, "https://example.org/query")):
            result = discovery.find_europe_pmc_fulltext("https://doi.org/10.1234/example")
        self.assertTrue(result["fulltext_candidate"])
        self.assertEqual(result["pmcid"], "PMC123")
        self.assertEqual(result["license"], "cc by")

    def test_sections_are_bounded_and_nested_content_is_separate(self) -> None:
        with patch.object(discovery, "_article_xml", return_value=(ARTICLE, SOURCE)):
            listing = discovery.list_europe_pmc_sections("PMC123")
            self.assertEqual([item["id"] for item in listing["sections"]],
                             ["abstract", "s1", "s1.1"])
            self.assertEqual(listing["sections"][1]["chars"], len("Sample collection."))
            excerpt = discovery.read_europe_pmc_section("PMC123", "abstract", max_chars=500)
            self.assertEqual(excerpt["total_chars"], len("Abstract evidence and caveat."))
            self.assertIsNone(excerpt["next_offset"])
            with self.assertRaisesRegex(ValueError, "max_chars"):
                discovery.read_europe_pmc_section("PMC123", "abstract", max_chars=9000)
        with self.assertRaisesRegex(ValueError, "PMCID"):
            discovery.list_europe_pmc_sections("../PMC123")


if __name__ == "__main__":
    unittest.main()
