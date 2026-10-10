"""Targeted tests for evidence/qualification failures, never the agent loop."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from audit_runs import REVIEW_CHECKS, audit_budget, formatting_issues, qualify, semantic_argument_comparison, tool_outcome_counts
from recompute_statistics import numeric_differences


class AuditTests(unittest.TestCase):
    def test_malformed_arguments_do_not_imply_local_only_failure(self):
        rows = [{'arguments': '{bad', 'success': False, 'output': None,
                 'result_text': ['Error executing tool: 2 validation errors for toolArguments']},
                {'arguments': {}, 'success': False, 'output': {'ok': False}},
                {'arguments': {}, 'success': True, 'output': {'ok': True}}]
        self.assertEqual(tool_outcome_counts(rows), {'successful_executions': 1, 'business_rejections': 1,
            'schema_error_results': 1, 'other_failed_attempts': 0, 'malformed_json_arguments': 1})

    def test_tiny_p_values_cannot_hide_under_absolute_tolerance(self):
        self.assertTrue(numeric_differences({'p_value': 1e-20}, {'p_value': 1e-30}))
        self.assertFalse(numeric_differences({'p_value': 1e-20}, {'p_value': 1.000000001e-20}))

    def test_tool_success_without_scientific_review_is_not_qualified(self):
        row = {'evidence_passed': True, 'business_delivered': True}
        self.assertIsNone(qualify(row, None)['qualified'])

    def test_figure_formatting_cannot_excuse_scientific_decimal(self):
        reference = {'kind':'figure_reference','text':'图1','labels':[1],
                     'validated_against_actual_figure_count':1,'passed':True}
        binding = {'template':'图1给出{{estimate}}。','formatting_references':[reference]}
        self.assertFalse(formatting_issues(binding, 1))
        binding['template'] = '图1显示增加了1.5倍。'
        self.assertTrue(formatting_issues(binding, 1))
        binding['template'] = '图1给出{{estimate}}。'
        self.assertTrue(formatting_issues(binding, 0))

    def test_semantic_argument_audit_only_discloses_ignored_top_level_keys(self):
        raw = {'evidence_id':'record', 'presentation':{'reason':'actual model text'}, 'extra':True}
        received = {'evidence_id':'record', 'presentation':{'reason':'actual model text'}}
        result = semantic_argument_comparison(raw, received, ['evidence_id','presentation'], ['evidence_id','presentation'])
        self.assertFalse(result['exact_match'])
        self.assertTrue(result['declared_parameters_match'])
        self.assertEqual(result['ignored_top_level'], {'extra':True})
        received['presentation'] = {'reason':'substituted prose'}
        self.assertFalse(semantic_argument_comparison(raw, received, ['evidence_id','presentation'], ['evidence_id','presentation'])['declared_parameters_match'])

    def test_review_requires_exact_final_hash_and_all_six_checks(self):
        row = {'evidence_passed': True, 'business_delivered': True,
               'report': {'sha256': 'correct'}, 'writing': {'text_id': 'current'}}
        review = {'pdf_sha256': 'correct', 'text_id': 'current', 'reviewer': 'independent AI reviewer',
                  'method': 'read actual paragraphs and page renderings',
                  'checks': {k: {'status': 'pass', 'evidence': 'specific observed artifact'} for k in REVIEW_CHECKS}}
        self.assertTrue(qualify(row, review)['qualified'])
        review['pdf_sha256'] = 'old'
        self.assertFalse(qualify(row, review)['qualified'])
        review['pdf_sha256'] = 'correct'
        review['issues'] = [{'severity': 'major', 'resolved': False}]
        self.assertFalse(qualify(row, review)['qualified'])

    def test_new_global_request_without_run_evidence_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            prior, current = root/'prior.jsonl', root/'current.jsonl'
            def entries(rid, run):
                return [{'kind':'reserve','request_id':rid,'run_id':run,'delta_cny':1},
                        {'kind':'settle','request_id':rid,'run_id':run,'delta_cny':-0.9,
                         'peak_estimate_cny':0.1,'usage':{'prompt_tokens':1}}]
            old, new = entries('old', 'old_run'), entries('new', 'new_run')
            dump = lambda rows: ''.join(json.dumps(r)+'\n' for r in rows)
            prior.write_text(dump(old),encoding='utf-8')
            current.write_text(dump(old+new),encoding='utf-8')
            self.assertFalse(audit_budget(current, {}, prior)['passed'])
            obj = SimpleNamespace(manifest={'run_id':'new_run'}, costs=[new[1]])
            self.assertTrue(audit_budget(current, {'new_run':obj}, prior)['passed'])


if __name__ == '__main__':
    unittest.main()
