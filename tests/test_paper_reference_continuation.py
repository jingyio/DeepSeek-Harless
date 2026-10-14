import importlib.util
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('continuation',ROOT/'scripts/paper-reference-continuation.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)

class BibCatalogTests(unittest.TestCase):
    def test_nested_titles_quoted_braces_and_duplicate_keys_are_preserved(self):
        text='''@article{a,
 title={A {Nested} title},
 author="A } quoted brace", year={2025}}
@article{a, title={Second}, eprint={2501.12345}}
@string{abbr = "conference"}
'''
        rows=module.bib_records(text)
        self.assertEqual([r['key'] for r in rows],['a','a'])
        self.assertIn('year={2025}',rows[0]['raw'])
        self.assertNotIn('@article{a, title={Second}',rows[0]['raw'])
    def test_unbalanced_entry_is_not_silently_truncated(self):
        with self.assertRaises(ValueError): module.bib_records('@article{k, title={incomplete}')
    def test_metadata_query_preserves_nested_title_and_leaves_tex_commands_uninterpreted(self):
        self.assertEqual(module.title_query('@article{a,title={A {Nested} title},year={2025}}'),'A Nested title')
        self.assertEqual(module.title_query('@article{a,title="Quoted title",year={2025}}'),'Quoted title')
        self.assertIsNone(module.title_query(r'@article{a,title={A \LaTeX{} title}}'))
