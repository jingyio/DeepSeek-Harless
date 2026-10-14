"""合成夹具诊断；不代表真实模型质量或自然语言等价认证。"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('trace_control_audit', ROOT / 'scripts/audit-trace-control-text.py')
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class TraceControlTextAuditTests(unittest.TestCase):
    def fixture(self, directory, text='', extra=False, result=None, verified=True):
        run = Path(directory) / 'private-fixture'
        (run / 'work').mkdir(parents=True)
        (run / 'requests').mkdir()
        self.save(run / 'config.json', {'mode':'shadow', 'session_id':'private-session-secret'})
        self.save(run / 'metrics.json', {'actual_requests':2, 'actual_model_skips':0})
        call = {'type':'tool-call', 'id':'check-call', 'name':'private-tool-secret',
                'arguments':{'input_id':'private-handle-secret'}}
        blocks = ([{'type':'text', 'text':text}] if text else []) + [call]
        if extra:
            blocks.append({'type':'tool-call', 'id':'read-call', 'name':'read', 'arguments':{}})
        message = {'role':'assistant', 'id':'message-one', 'content':blocks}
        second = {'role':'assistant', 'id':'message-two',
                  'content':[{'type':'text', 'text':'Private final reasoning secret.'}]}
        value = {'output': {'passed':True}, 'report_sha256':'private-report-hash-secret'}
        actual_result = value if result is None else result
        events = [
            self.event('assistant/message', {'message':message}),
            self.event('assistant/message', {'message':second}, sid='child'),
            self.event('tool/result', {'message':{'content':[{
                'type':'tool-result', 'toolCallId':'check-call', 'isError':False,
                'content':[{'type':'text', 'text':json.dumps(actual_result)}]}]}}),
            self.event('assistant/message', {'message':second}),
        ]
        self.lines(run / 'events.jsonl', events)
        predictions = [
            {'kind':'prediction', 'request_ordinal':1, 'session_id':'private-session-secret',
             'execution_authorized':False, 'prediction':{
                'expected_tools':[{'tool':call['name'], 'arguments':call['arguments']}],
                'expected_result':value, 'execution_authorized':False}},
            {'kind':'shadow_result', 'request_ordinal':1, 'session_id':'private-session-secret',
             'call_id':call['id'], 'verified':verified, 'execution_authorized':False},
            {'kind':'deferred', 'request_ordinal':2, 'session_id':'private-session-secret',
             'execution_authorized':False},
        ]
        self.lines(run / 'work/shadow.jsonl', predictions)
        self.save(run / 'requests/17.json', {'messages':[{'role':'user','content':'Private source secret.'}]})
        saved = {'role':'assistant','content':text, 'tool_calls':[
            {'id':b['id'], 'type':'function', 'function':{'name':b['name'],
             'arguments':json.dumps(b['arguments'])}} for b in blocks if b['type']=='tool-call']}
        self.save(run / 'requests/18.json', {'messages':[saved]})
        return run

    def save(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def lines(self, path, rows):
        path.write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in rows)+'\n', encoding='utf-8')

    def event(self, kind, data, sid='private-session-secret'):
        return {'sessionId':sid, 'event':{'type':kind, 'data':data}}

    def read(self, run, reviews=None):
        return audit.audit_run(run, reviews)[0]

    def test_exact_tool_only_request_remains_shadow_opportunity(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.read(self.fixture(tmp))
            self.assertEqual(result['strict_whole_request'], 1)
            self.assertEqual(result['actual_requests'], 2)
            self.assertEqual(result['actual_model_skips'], 0)
            self.assertTrue(result['request_history_chain_verified'])
            self.assertFalse(result['prospective_timing_independently_proven'])

    def test_control_review_never_removes_text_or_upgrades_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.fixture(tmp, text='Let me check. Private source secret.')
            row = self.read(run)['rows'][0]
            result = self.read(run, {audit.review_key(row):'schedule_only'})
            self.assertEqual(result['strict_whole_request'], 0)
            self.assertEqual(result['matching_local_operation'], 1)
            self.assertEqual(result['matched_manual_categories'], {'schedule_only':1})
            self.assertEqual(result['deterministic_text_certified'], 0)
            self.assertTrue(result['rows'][0]['has_text'])

    def test_extra_operation_or_changed_boolean_result_is_not_whole_match(self):
        for args, expected in [({'extra':True}, 'different_next_operation'),
                               ({'result':{'output':{'passed':1}, 'report_sha256':'private-report-hash-secret'}},
                                'different_result_or_version')]:
            with self.subTest(args=args), tempfile.TemporaryDirectory() as tmp:
                result = self.read(self.fixture(tmp, **args))
                self.assertEqual(result['rows'][0]['outcome'], expected)
                self.assertEqual(result['matching_local_operation'], 0)

    def test_unknown_block_is_preserved_as_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.fixture(tmp)
            events = audit.read_jsonl(run / 'events.jsonl')
            events[0]['event']['data']['message']['content'].insert(0, {'type':'private-type-secret'})
            self.lines(run / 'events.jsonl', events)
            result = self.read(run)
            self.assertEqual(result['rows'][0]['outcome'], 'local_match_text_requires_review')
            self.assertEqual(result['rows'][0]['other_block_count'], 1)
            self.assertNotIn('private-type-secret', json.dumps(result))

    def test_missing_verified_result_or_result_after_next_request_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.fixture(tmp, verified=False)
            self.assertEqual(self.read(run)['rows'][0]['outcome'], 'live_result_unverified')
        with tempfile.TemporaryDirectory() as tmp:
            run = self.fixture(tmp)
            events = audit.read_jsonl(run / 'events.jsonl')
            events.append(events.pop(2))
            self.lines(run / 'events.jsonl', events)
            self.assertEqual(self.read(run)['rows'][0]['outcome'], 'different_result_or_version')

    def test_all_paid_requests_stay_in_denominator_when_boundaries_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.fixture(tmp)
            self.save(run / 'metrics.json', {'actual_requests':3, 'actual_model_skips':0})
            result = self.read(run)
            self.assertEqual(result['actual_requests'], 3)
            self.assertFalse(result['complete_request_boundaries'])
            self.assertEqual(result['strict_whole_request'], 0)
            self.assertEqual(result['rows'][0]['outcome'], 'local_match_incomplete_request_boundary')

    def test_request_history_text_drift_blocks_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.fixture(tmp)
            request = audit.read_json(run / 'requests/18.json')
            request['messages'][0]['content'] = 'Omitted semantic judgment.'
            self.save(run / 'requests/18.json', request)
            result = self.read(run)
            self.assertFalse(result['request_history_chain_verified'])
            self.assertEqual(result['strict_whole_request'], 0)

    def test_unicode_record_separators_and_child_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.read(self.fixture(tmp, text='Private\u2028source\u2029secret.'))
            self.assertEqual(result['root_messages'], 2)
            self.assertEqual(result['matching_local_operation'], 1)

    def test_prospective_ordinal_and_cross_session_audit_fail_closed(self):
        for field, value in [('request_ordinal',4), ('session_id','foreign-session')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                run = self.fixture(tmp)
                rows = audit.read_jsonl(run / 'work/shadow.jsonl')
                rows[0][field] = value
                self.lines(run / 'work/shadow.jsonl', rows)
                with self.assertRaises(ValueError):
                    self.read(run)

    def test_cli_is_private_safe_read_only_and_rejects_review_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.fixture(tmp, text='Private source secret.')
            before = {str(p):audit.file_sha(p) for p in run.rglob('*') if p.is_file()}
            command = [sys.executable, str(ROOT / 'scripts/audit-trace-control-text.py'), str(run)]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            self.assertNotIn('Private', result.stdout)
            self.assertNotIn('private-', result.stdout)
            self.assertNotIn(str(run), result.stdout)
            self.assertEqual(before, {str(p):audit.file_sha(p) for p in run.rglob('*') if p.is_file()})
            row = self.read(run)['rows'][0]
            review = {k:row[k] for k in audit.REVIEW_FIELDS if k != 'category'}
            review.update(category='schedule_only', text_sha256='0'*64)
            review_path = Path(tmp) / 'reviews.json'
            self.save(review_path, {'schema_version':1, 'reviews':[review]})
            result = subprocess.run(command + ['--reviews', str(review_path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)['error'], 'audit_input_or_evidence_invalid')


if __name__ == '__main__':
    unittest.main()
