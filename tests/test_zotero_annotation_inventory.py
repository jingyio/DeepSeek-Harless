"""Do not infer absence of annotations from empty PDF /children responses."""

from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlsplit

from src.adapters.zotero_annotation_inventory import collection_annotation_inventory


class ZoteroAnnotationInventoryTests(unittest.TestCase):
    def test_collection_filter_finds_annotations_when_attachment_children_are_empty(self) -> None:
        empty_attachment_children = []
        self.assertEqual(empty_attachment_children, [])
        called_urls = []

        def fetch(url):
            called_urls.append(url)
            query = parse_qs(urlsplit(url).query)
            self.assertEqual(query["itemType"], ["annotation"])
            self.assertEqual(query["start"], ["0"])
            return ([{"key": "SJ42P7L9", "data": {
                "itemType": "annotation", "parentItem": "M6LCRZ6L",
                "annotationPageLabel": "636", "annotationText": "source quote",
                "annotationComment": "researcher note",
                "dateModified": "2026-09-11T12:55:32Z",
            }}], 1)

        rows = collection_annotation_inventory("EUUDL6NQ", fetch_page=fetch)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["parent_item"], "M6LCRZ6L")
        self.assertTrue(rows[0]["has_comment"])
        self.assertNotIn("source quote", str(rows))
        self.assertTrue(all("/collections/EUUDL6NQ/items?" in url for url in called_urls))
        self.assertTrue(all("/children" not in url for url in called_urls))

    def test_pagination_refuses_truncated_inventory(self) -> None:
        def fetch(_url):
            return [], 6

        with self.assertRaisesRegex(ValueError, "ended early"):
            collection_annotation_inventory("EUUDL6NQ", fetch_page=fetch)


if __name__ == "__main__":
    unittest.main()
