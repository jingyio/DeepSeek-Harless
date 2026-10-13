"""V6 编译边界诊断：合成事件只测守卫，不作真实模型质量/收益证据。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from scenarios.research_ppt import motif_v6
from tests.test_trace_compiled_read_motif import event_pair

ROOT = Path(__file__).resolve().parents[3]
PIN = 'mcp__ppt__pin_figure_catalog'
READ = 'mcp__ppt__read_pinned_model_catalog'


def freezer():
    path = ROOT / 'scripts/freeze-dsh-task-identity.py'
    spec = importlib.util.spec_from_file_location('v6_test_freezer', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False) + '\n', encoding='utf-8')


class MotifV6Tests(unittest.TestCase):
    def setUp(self):
        (ROOT / '.local').mkdir(exist_ok=True)
        self.temp = TemporaryDirectory(dir=ROOT / '.local')
        self.area = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.contracts = {
            PIN: {'required_params': ['document_id'], 'read_only': True,
                  'replay_stable': True, 'description': 'Pin a real PDF figure inventory scope.',
                  'output_fields': ['source_id', 'version_sha256']},
            READ: {'required_params': ['source_id'], 'provenance_params': ['source_id'],
                   'read_only': True, 'replay_stable': True,
                   'description': 'Read real figure candidates of the pinned inventory.',
                   'output_fields': ['source_id', 'version_sha256', 'figures']},
        }
        self.contracts_path = self.area / 'contracts.json'
        self.versions_path = self.area / 'version-fields.json'
        self.schema_path = self.area / 'schema.json'
        self.code = self.area / 'generated-code.json'
        write(self.contracts_path, self.contracts)
        write(self.versions_path, {PIN: 'version_sha256', READ: 'version_sha256'})
        write(self.schema_path, {'tools': [
            {'name': name, 'description': contract['description'],
             'inputSchema': {'type': 'object', 'required': contract['required_params'],
                             'properties': {key: {'type': 'string'}
                                            for key in contract['required_params']}}}
            for name, contract in self.contracts.items()]})
        write(self.code, {'code_digest': 'a' * 64, 'status': 'test_fixture_not_real_tool'})

    def dataset(self, *, barrier=False, duplicate_question=False, interleaved=False):
        directories = []
        for index, label in enumerate(('alpha', 'beta', 'gamma'), 1):
            folder = self.area / label
            folder.mkdir()
            handle = 'source-' + str(index) * 32
            version = str(index) * 64
            events = event_pair(1, PIN, {'document_id': 'doc_' + str(index)},
                                {'source_id': handle, 'version_sha256': version})
            if interleaved:
                if index == 2:
                    events = event_pair(1, 'mcp__ppt__list_sources', {}, {'count': 1}) + event_pair(
                        2, PIN, {'document_id': 'doc_' + str(index)},
                        {'source_id': handle, 'version_sha256': version})
                else:
                    events += event_pair(2, 'mcp__ppt__list_sources', {}, {'count': 1})
            if barrier:
                events += event_pair(2, 'mcp__ppt__extract_figure', {'source_id': handle},
                                     {'image_id': 'actual-file-fixture'})
            events += event_pair(3 if barrier or interleaved else 2, READ, {'source_id': handle},
                                 {'source_id': handle, 'version_sha256': version, 'figures': []})
            write(folder / 'manifest.json', {'task_id': label,
                  'question': 'Same decision' if duplicate_question else 'Decision for ' + label})
            (folder / 'agent-events.jsonl').write_text(
                ''.join(json.dumps(row) + '\n' for row in events), encoding='utf-8')
            freezer().freeze(folder, 'decision-' + label, 'agent-events.jsonl')
            directories.append(str(folder))
        path = self.area / 'dataset.json'
        write(path, {'train': directories[:2], 'heldout': directories[2:]})
        return path

    def learn(self, dataset):
        return motif_v6.learn(dataset, contracts_path=self.contracts_path,
                              version_fields_path=self.versions_path,
                              tool_schema_path=self.schema_path, generated_tool=READ,
                              guard_paths=(self.code,), out_dir=self.area / 'compiled')

    def test_public_compiler_learns_unique_scoped_handle_without_written_dag(self):
        manifest = self.learn(self.dataset())
        report = motif_v6.validate_compilation(manifest)
        self.assertEqual(len(report['new_tool_artifacts']), 1)
        self.assertEqual(report['new_tool_structural_candidates'][0]['from_tool'], PIN)
        self.assertFalse(report['real_bypass_observed'])
        self.assertEqual(report['quality'], 'not_reviewed')
        library = motif_v6.read(manifest.parent / 'library.json')
        edge = library['artifacts'][0]['transfer_evidence'][0]
        self.assertEqual((edge['from_tool'], edge['to_tool']), (PIN, READ))
        self.assertEqual(edge['from_field'], 'source_id')
        self.assertEqual(len(library['task_identity_evidence']), 3)

    def test_write_or_unapproved_tool_is_a_barrier_not_a_skipped_connector(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.learn(self.dataset(barrier=True))
        failure = motif_v6.read(self.area / 'compiled/learning-failure.json')
        self.assertEqual(failure['status'], 'not_promoted')
        self.assertFalse((self.area / 'compiled/online-manifest.json').exists())

    def test_same_research_question_cannot_be_renamed_to_independent_tasks(self):
        with self.assertRaisesRegex(ValueError, 'identical research questions'):
            self.learn(self.dataset(duplicate_question=True))
        self.assertFalse((self.area / 'compiled').exists())

    def test_generated_code_and_tool_schema_changes_invalidate_frozen_learning(self):
        manifest = self.learn(self.dataset())
        original = self.code.read_bytes()
        write(self.code, {'code_digest': 'b' * 64})
        with self.assertRaisesRegex(ValueError, '重新认证'):
            motif_v6.validate_compilation(manifest)
        self.code.write_bytes(original)
        schema = motif_v6.read(self.schema_path)
        schema['tools'][0]['description'] += ' changed'
        write(self.schema_path, schema)
        with self.assertRaisesRegex(ValueError, '重新认证'):
            motif_v6.validate_compilation(manifest)

    def test_actual_mcp_schema_must_match_approved_parameters(self):
        dataset = self.dataset()
        schema = motif_v6.read(self.schema_path)
        schema['tools'][1]['inputSchema']['required'].append('page')
        schema['tools'][1]['inputSchema']['properties']['page'] = {'type': 'integer'}
        write(self.schema_path, schema)
        with self.assertRaisesRegex(ValueError, 'schema does not match'):
            self.learn(dataset)
        self.assertFalse((self.area / 'compiled').exists())

    def test_full_ordered_schema_snapshot_keeps_harness_tool_names(self):
        raw = motif_v6.read(self.schema_path)['tools'][0]
        converted = motif_v6.schema_tools({'ordered_allowed_mcp_schemas': [
            {'harness_tool_name': PIN, 'mcp_tool': {**raw, 'name': 'pin_figure_catalog'}}]})
        self.assertEqual(converted['tools'][0]['name'], PIN)

    def test_public_witnessed_edges_learn_across_unrelated_read_interleaving(self):
        extra = 'mcp__ppt__list_sources'
        self.contracts[extra] = {'required_params': [], 'read_only': True,
                                'replay_stable': True, 'output_fields': ['count'],
                                'description': 'List this task sources without selecting any material.'}
        write(self.contracts_path, self.contracts)
        schema = motif_v6.read(self.schema_path)
        schema['tools'].append({'name': extra, 'description': self.contracts[extra]['description'],
                                'inputSchema': {'type': 'object', 'properties': {}, 'required': []}})
        write(self.schema_path, schema)
        manifest = motif_v6.learn(self.dataset(interleaved=True), contracts_path=self.contracts_path,
                                  version_fields_path=self.versions_path, tool_schema_path=self.schema_path,
                                  generated_tool=READ, guard_paths=(self.code,),
                                  out_dir=self.area / 'witnessed', mining='witnessed_edges')
        report = motif_v6.validate_compilation(manifest)
        self.assertEqual(report['mining'], 'witnessed_edges')
        self.assertEqual(len(report['new_tool_artifacts']), 1)
        self.assertFalse(report['product_registered'])
        self.assertFalse(report['quality_cost_promoted'])
        library = motif_v6.read(manifest.parent / 'library.json')
        self.assertEqual(library['artifacts'][0]['mining_basis'], 'witnessed_parameter_edge')
        self.assertEqual(library['artifacts'][0]['tools'], [PIN, READ])
        self.assertEqual(len(library['task_identity_evidence']), 3)
        evidence = motif_v6.read(manifest.parent / 'evidence-lock.json')
        self.assertTrue(any(row['path'].endswith('compile-witnessed-read-chains.py')
                            for row in evidence['sources']))


if __name__ == '__main__':
    unittest.main()
