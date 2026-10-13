"""条件协议/离线边界诊断；固定夹具不是正常 DeepSeek 训练或实际收益证据。"""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scenarios.research_ppt import conditional_learning as learning

PIN, READ, INSPECT = learning.PIN, learning.READ, 'mcp__ppt__inspect_deck'


def fixture():
    string = {'type': 'string', 'minLength': 1, 'maxLength': 500}
    def schema(properties, required):
        return {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}
    candidate = {'schema_version': 1, 'primitive_version': 'ppt-conditional-read-v1', 'candidate_id': 'offline-protocol-fixture',
        'origin': 'manual', 'anchor': {'tool': INSPECT, 'input_version_field': 'input_version',
            'predicate': {'op': 'field_equals', 'field': 'each_slide_has_editable_text', 'value': True}},
        'branches': {'on_equal': [
            {'id': 'pin', 'tool': PIN, 'bindings': {'deck_id': {'from': 'task', 'field': 'deck_id'}, 'pages_csv': {'from': 'task', 'field': 'pages_csv'}}, 'output_contract': 'pinned_pages'},
            {'id': 'read', 'tool': READ, 'bindings': {'source_id': {'from': 'node', 'node_id': 'pin', 'field': 'source_id'}}, 'output_contract': 'read_pages'}], 'on_unequal': []},
        'contracts': {INSPECT: {'read_only': True, 'replay_stable': True, 'input_schema': schema({'deck_id': string}, ['deck_id'])},
            PIN: {'read_only': True, 'replay_stable': True, 'input_schema': schema({'deck_id': string, 'pages_csv': {'type': 'string', 'minLength': 1, 'maxLength': 89, 'pattern': '^[1-9][0-9]?(?:,[1-9][0-9]?){0,29}$'}}, ['deck_id', 'pages_csv'])},
            READ: {'read_only': True, 'replay_stable': True, 'input_schema': schema({'source_id': string}, ['source_id'])}},
        'dependencies': {'backend': 'a' * 64}, 'training': {'task_fingerprints': [], 'trace_sha256': []}}
    candidate['candidate_digest'] = learning.digest(candidate)
    task = {'schema_version': 1, 'session_id': 'fixture-only', 'task_fingerprint': 'not-real-training', 'input_version': 'b' * 64,
        'deck_id': 'fixture-deck', 'deck_sha256': 'c' * 64, 'pages_csv': '1,3', 'job_sha256': 'd' * 64,
        'permission_sha256': 'e' * 64, 'dependencies': copy.deepcopy(candidate['dependencies']), 'allowed_tools': [INSPECT, PIN, READ]}
    anchor = {'name': INSPECT, 'callId': 'fixture-anchor', 'ok': True, 'arguments': {'deck_id': task['deck_id']},
        'output': {'deck_id': task['deck_id'], 'input_version': task['input_version'], 'file_sha256': task['deck_sha256'], 'each_slide_has_editable_text': True}}
    pinned = {'name': PIN, 'ok': True, 'arguments': {'deck_id': task['deck_id'], 'pages_csv': task['pages_csv']},
        'output': {'source_id': 'source-' + '1' * 32, 'deck_id': task['deck_id'], 'version_sha256': task['input_version'],
            'file_sha256': task['deck_sha256'], 'pages_csv': task['pages_csv'], 'scope': 'explicit_pages_from_current_persisted_plan'}}
    read = {'name': READ, 'ok': True, 'arguments': {'source_id': pinned['output']['source_id']},
        'output': {'source_id': pinned['output']['source_id'], 'deck_id': task['deck_id'], 'version_sha256': task['input_version'],
            'file_sha256': task['deck_sha256'], 'total_slides': 4, 'scope': 'explicit_pages_only_no_semantic_selection',
            'slides': [{'page': 1, 'slide': {'title': 'First'}}, {'page': 3, 'slide': {'title': 'Third'}}]}}
    offered = [[name, {'parameters': value['input_schema'], 'annotations': {'readOnlyHint': True}}] for name, value in candidate['contracts'].items()]
    return candidate, task, anchor, pinned, read, offered


class ConditionalLearningTests(unittest.TestCase):
    def test_python_and_ts_protocol_digests_and_sequential_decisions(self):
        c, t, anchor, pin, read, offered = fixture()
        self.assertTrue(learning.probe({'op': 'validate', 'candidate': c, 'guard': t})['valid'])
        self.assertEqual(learning.compare(c, t, t, [anchor], offered)['proposals'][0]['tool'], PIN)
        self.assertEqual(learning.compare(c, t, t, [anchor, pin], offered)['proposals'][0]['arguments'], read['arguments'])
        self.assertEqual(learning.compare(c, t, t, [anchor, pin, read], offered)['kind'], 'abstain')

    def test_missing_false_conflicting_and_guard_boundaries_agree(self):
        for kind in ('missing', 'false', 'conflict', 'permission', 'dependency', 'schema', 'barrier'):
            c, t, anchor, _, _, offered = fixture()
            history, live = [anchor], copy.deepcopy(t)
            if kind == 'missing':
                anchor['output'].pop('each_slide_has_editable_text')
            elif kind == 'false':
                anchor['output']['each_slide_has_editable_text'] = False
            elif kind == 'conflict':
                anchor['arguments']['deck_id'] = 'another-deck'
            elif kind == 'permission':
                live['permission_sha256'] = '0' * 64
            elif kind == 'dependency':
                live['dependencies']['backend'] = '0' * 64
            elif kind == 'schema':
                offered[1][1]['parameters'] = {'type': 'null'}
            else:
                history.append({'name': 'write', 'ok': True, 'barrier': True, 'arguments': {}, 'output': {}})
            self.assertEqual(learning.compare(c, t, live, history, offered)['kind'], 'abstain', kind)

    def test_result_scope_change_and_failed_read_are_independently_rejected(self):
        c, t, anchor, pin, read, offered = fixture()
        for key, wrong in [('file_sha256', '0' * 64), ('pages_csv', '2'), ('source_id', '')]:
            changed = copy.deepcopy(pin); changed['output'][key] = wrong
            self.assertEqual(learning.compare(c, t, t, [anchor, changed], offered)['kind'], 'abstain')
        wrong = copy.deepcopy(read); wrong['output']['slides'].reverse()
        self.assertEqual(learning.compare(c, t, t, [anchor, pin, wrong], offered)['kind'], 'abstain')

    def parsed_run(self):
        _, _, anchor, pin, read, _ = fixture()
        records = []
        for index, row in enumerate((anchor, pin, read)):
            records.append({'name': row['name'], 'arguments': row['arguments'], 'observation': row['output'],
                'eligible': True, 'reason': 'eligible_read', 'event_seq': index,
                'parameter_sources': {'source_id': {'from_tool': PIN, 'from_field': 'source_id'}} if row['name'] == READ else None})
        return {'records': records, 'identity': {'question_sha256': 'f' * 64, 'research_decision_id': 'diagnostic-only'}}

    def test_discovery_requires_actual_parameter_result_version_evidence(self):
        run = self.parsed_run()
        found = learning.opportunities(run)
        self.assertEqual(len(found), 2)  # inspect→pin→read 与 pin→read 是观测机会，尚非候选。
        self.assertEqual(found[0]['scope']['pages_csv'], '1,3')
        for alter in (lambda r: r['records'][2].update(parameter_sources=None),
                      lambda r: r['records'][2]['observation'].update(file_sha256='0' * 64),
                      lambda r: r['records'][1]['arguments'].update(pages_csv='2')):
            changed = copy.deepcopy(run); alter(changed)
            self.assertEqual(learning.opportunities(changed), [])

    def test_discovery_never_crosses_write_or_failed_barrier(self):
        run = self.parsed_run()
        run['records'].insert(2, {'name': 'mcp__ppt__revise_deck', 'eligible': False, 'observation': None})
        self.assertEqual(learning.opportunities(run), [])

    def test_unpaid_or_simulated_manifest_cannot_claim_normal_training(self):
        (learning.ROOT / '.local').mkdir(exist_ok=True)
        with TemporaryDirectory(dir=learning.ROOT / '.local') as name:
            area = Path(name)
            manifest = {'task_id': 'diagnostic', 'question': 'Fixture only', 'mode': 'baseline', 'reasoning_effort': 'off', 'model_call_enabled': False}
            raw = json.dumps(manifest).encode(); events = b''
            (area / 'manifest.json').write_bytes(raw); (area / 'agent-events.jsonl').write_bytes(events)
            (area / 'task-identity.json').write_text(json.dumps({'schema_version': 1, 'research_decision_id': 'diagnostic-only',
                'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'events_sha256': hashlib.sha256(events).hexdigest()}), encoding='utf-8')
            (area / 'metrics.json').write_text(json.dumps({'status': 'done', 'upstream_requests': 0}), encoding='utf-8')
            (area / 'cost-ledger.jsonl').write_text('', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '模拟/旁路/预览'):
                learning.load_run(area, area / 'unused-schema.json')

    def test_private_scope_duplicate_json_and_wrong_dependencies_fail_closed(self):
        with self.assertRaises(ValueError):
            learning.private(learning.ROOT / 'README.md', True)
        with self.assertRaises(ValueError):
            learning.dependencies([learning.ROOT / '.local'])
        (learning.ROOT / '.local').mkdir(exist_ok=True)
        with TemporaryDirectory(dir=learning.ROOT / '.local') as name:
            path = Path(name) / 'duplicate.json'; path.write_text('{"status":false,"status":true}', encoding='utf-8')
            with self.assertRaises(ValueError):
                learning.read(path)

    def test_certificate_checks_are_harness_computed_not_candidate_claims(self):
        certifier = learning.Certifier(None)
        with self.assertRaisesRegex(ValueError, 'both_actual_branches'):
            certifier.check('both_actual_branches', False, {'branches': ['on_equal']})
        self.assertFalse(certifier.checks[0]['passed'])
        self.assertEqual(set(learning.NEGATIVES), {'missing_state', 'conflicting_arguments', 'permission_changed',
            'dependency_changed', 'source_changed', 'schema_changed', 'tool_failure', 'result_scope_changed'})


if __name__ == '__main__':
    unittest.main()
