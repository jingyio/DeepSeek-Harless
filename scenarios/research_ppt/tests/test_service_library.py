"""长期库接入的实际 PDF/MCP 后端诊断；服务器执行，无云模型调用。"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fitz

from scenarios.research_ppt import cli, documents, knowledge_library as library
from scenarios.research_ppt.service import PPTService
from scenarios.research_ppt.recovery import CheckpointPPTService, CheckpointRejected


class ServiceLibraryTests(unittest.TestCase):
    def setUp(self):
        area = library.ROOT / '.local/research-ppt/unit-tests'
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.area = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.source = self.area / 'source.pdf'
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.insert_text((50, 70), 'The retained paper source is frozen for this job.')
            page.draw_rect(fitz.Rect(100, 150, 300, 300), color=(0, 0, 0))
            page.insert_text((100, 320), 'Figure 1: A vector diagram.')
            pdf.save(self.source)
        self.store = self.area / 'library'
        self.addCleanup(patch.stopall)
        patch.object(library, 'DEFAULT_STORE', self.store).start()
        patch.object(cli, 'ROOT', self.area).start()

    def service(self, *, cache=False, tenant='alice', checkpoint=False):
        job = cli.prepare([self.source], '长期资料库独立授权诊断', 1, tenant_id=tenant,
                          document_cache=cache)
        return CheckpointPPTService(job) if checkpoint else PPTService(job)

    @staticmethod
    def cache_events(service):
        return [row for row in (json.loads(line) for line in
            (service.job_path.parent / 'feedback.jsonl').read_text(encoding='utf-8').splitlines())
            if row['kind'] == 'document_cache']

    def test_prepare_default_retains_source_with_trusted_identity_and_version(self):
        service = self.service()
        row = service.job['inputs'][0]
        self.assertTrue(service.job['persistent_library'])
        self.assertEqual(service.job['library_tenant'], 'alice')
        self.assertIn('library_resource_id', row)
        self.assertNotEqual(Path(row['path']), self.source)
        self.assertEqual(row['version_sha256'], documents.file_hash(self.source))
        self.source.unlink()
        pinned = service.pin_source('doc_1')
        self.assertIn('retained paper', service.read_source(pinned['source_id'])['pages'][0]['text'])

    def test_prepare_binds_and_reuses_actual_fixed_components_with_real_parser(self):
        with patch.object(documents, 'parse_document', wraps=documents.parse_document) as parser:
            first, second = self.service(), self.service()
            first_pin = first.pin_source('doc_1')
            second_pin = second.pin_source('doc_1')
            self.assertEqual(parser.call_count, 2)  # 缓存仍关闭，不把组件登记冒充解析降本。
        self.assertEqual(first.job['library_component_schema_version'], 1)
        bindings = first.job['library_components']
        self.assertEqual(set(bindings), {'document_parse', 'render_delivery'})
        self.assertEqual(bindings, second.job['library_components'])
        self.assertIn('retained paper', first.read_source(first_pin['source_id'])['pages'][0]['text'])
        self.assertIn('retained paper', second.read_source(second_pin['source_id'])['pages'][0]['text'])
        store = first.library
        records = store.list_resources(tenant_id='alice', kind='component')
        self.assertEqual(len(records), 2)
        events = [json.loads(p.read_text(encoding='utf-8')) for p in (self.store / 'events').glob('*.json')]
        used = {row['job_id'] for row in events if row['action'] == 'component_resolved'}
        self.assertEqual(used, {first.job['job_id'], second.job['job_id']})

    def test_output_enabled_job_also_binds_direct_edit(self):
        job = cli.prepare([self.source], '授权局部改页', 1, allow_output=True, tenant_id='alice')
        data = json.loads(job.read_text(encoding='utf-8'))
        self.assertEqual(set(data['library_components']), {'document_parse', 'render_delivery', 'direct_edit'})
        descriptors = library.validate_job_components(data, library=library.PersistentLibrary(self.store))
        self.assertEqual(descriptors['direct_edit']['execution'], 'descriptor_only_existing_host_required')

    def test_component_revoke_blocks_retained_handles_and_checkpoint_restart(self):
        service = self.service(checkpoint=True)
        pinned = service.pin_source('doc_1')
        self.assertIn('retained paper', service.read_source(pinned['source_id'])['pages'][0]['text'])
        component = service.job['library_components']['document_parse']
        service.library.revoke_component(component['resource_id'], tenant_id='alice', job_id='withdraw-component')
        for operation in (lambda: PPTService.current(service, service.job['inputs'][0]),
                          lambda: PPTService.pin_source(service, 'doc_1'),
                          lambda: PPTService.read_source(service, pinned['source_id'])):
            with self.assertRaises(PermissionError):
                operation()
        # 组件权限在基类初始化阶段核验，恢复checkpoint之前即可明确拒绝。
        with self.assertRaises(PermissionError):
            CheckpointPPTService(service.job_path)

    def test_component_change_blocks_memory_read_without_auto_register(self):
        service = self.service()
        pinned = service.pin_source('doc_1')
        original_hash = documents.file_hash

        def changed_hash(path):
            return '0' * 64 if str(path).endswith('execution-policy.ts') else original_hash(path)

        with patch.object(documents, 'file_hash', side_effect=changed_hash), \
                patch.object(service.library, 'register_component', side_effect=AssertionError('不能自动升级')):
            with self.assertRaisesRegex(ValueError, '实现或认证依赖'):
                service.read_source(pinned['source_id'])

    def test_old_job_without_component_fields_keeps_legacy_read_but_partial_binding_rejected(self):
        service = self.service()
        data = dict(service.job)
        data.pop('library_component_schema_version')
        data.pop('library_components')
        cli.save(service.job_path, data)
        legacy = PPTService(service.job_path)
        self.assertEqual(library.validate_job_components(legacy.job, library=legacy.library), {})
        pinned = legacy.pin_source('doc_1')
        self.assertIn('retained paper', legacy.read_source(pinned['source_id'])['pages'][0]['text'])
        data['library_component_schema_version'] = 1
        cli.save(service.job_path, data)
        with self.assertRaisesRegex(ValueError, '绑定协议'):
            partial = PPTService(service.job_path)
            partial.pin_source('doc_1')

    def test_cross_job_cache_hit_keeps_each_job_pin_and_read_requirements(self):
        first = self.service(cache=True)
        pinned = first.pin_source('doc_1')
        first.read_source(pinned['source_id'])
        second = self.service(cache=True)
        self.assertNotEqual(first.job['job_id'], second.job['job_id'])
        self.assertEqual(first.job['inputs'][0]['library_resource_id'], second.job['inputs'][0]['library_resource_id'])
        with self.assertRaisesRegex(ValueError, '未知 source_id'):
            second.read_source(pinned['source_id'])
        repinned = second.pin_source('doc_1')
        self.assertFalse(second.handles[repinned['source_id']]['read'])
        self.assertEqual(self.cache_events(first)[-1]['status'], 'miss')
        self.assertEqual(self.cache_events(second)[-1]['status'], 'hit')

    def test_document_cache_false_is_uncached_in_each_new_job(self):
        with patch.object(documents, 'parse_document', wraps=documents.parse_document) as parser:
            first, second = self.service(), self.service()
            first.pin_source('doc_1')
            second.pin_source('doc_1')
            self.assertEqual(parser.call_count, 2)
        self.assertEqual(self.cache_events(first), [])
        self.assertEqual(self.cache_events(second), [])
        resource = first.job['inputs'][0]['library_resource_id']
        self.assertFalse((self.store / 'caches' / resource).exists())

    def test_retained_version_change_refuses_memory_read_pin_and_page_geometry(self):
        service = self.service(cache=True)
        pinned = service.pin_source('doc_1')
        row = service.job['inputs'][0]
        path = Path(row['path'])
        path.write_bytes(path.read_bytes() + b'\n% modified persistent source\n')
        for read in (lambda: service.read_source(pinned['source_id']),
                     lambda: service.pin_source('doc_1'), lambda: service.page_geometry(row, 1)):
            with self.assertRaisesRegex(ValueError, '版本'):
                read()

    def test_acl_revoke_refuses_memory_handles_geometry_new_pin_and_checkpoint_restart(self):
        service = self.service(cache=True, checkpoint=True)
        pinned = service.pin_source('doc_1')
        service.read_source(pinned['source_id'])
        row = service.job['inputs'][0]
        service.library.revoke_document(row['library_resource_id'], tenant_id='alice', job_id='withdraw')
        with self.assertRaises(PermissionError):
            PPTService.current(service, row)
        with self.assertRaises(PermissionError):
            PPTService.pin_source(service, 'doc_1')
        with self.assertRaises(PermissionError):
            PPTService.page_geometry(service, row, 1)
        with self.assertRaises(PermissionError):
            PPTService.read_source(service, pinned['source_id'])
        with self.assertRaises(CheckpointRejected):
            CheckpointPPTService(service.job_path)

    def test_library_identity_and_path_substitution_do_not_bypass_acl(self):
        service = self.service()
        job_data = dict(service.job)
        job_data['library_tenant'] = 'bob'
        cli.save(service.job_path, job_data)
        with self.assertRaises(PermissionError):
            impostor = PPTService(service.job_path)
            impostor.pin_source('doc_1')
        job_data['library_tenant'] = 'alice'
        job_data['inputs'][0]['path'] = str(self.source)
        cli.save(service.job_path, job_data)
        substituted = PPTService(service.job_path)
        with self.assertRaisesRegex(ValueError, '绑定'):
            substituted.pin_source('doc_1')
        job_data['persistent_library'] = False
        cli.save(service.job_path, job_data)
        with self.assertRaisesRegex(ValueError, '绕过'):
            PPTService(service.job_path)

    def test_live_source_opt_out_preserves_existing_source_version_guard(self):
        service = PPTService(cli.prepare([self.source], '原始来源版本守卫', 1, persistent_library=False))
        self.assertIsNone(service.library)
        self.assertEqual(service.job['inputs'][0]['path'], str(self.source))
        self.source.write_bytes(self.source.read_bytes() + b'\n% changed original\n')
        with self.assertRaisesRegex(ValueError, '输入版本已变化'):
            service.pin_source('doc_1')

    def test_prepare_execution_policy_is_frozen_and_rejects_unknown_values(self):
        for strategy in ('baseline_steps', 'host_delivery'):
            path = cli.prepare([self.source], '固定执行策略', 1, execution_policy=strategy)
            job = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(job['execution_policy'], {'schema_version': 1, 'strategy': strategy})
        with self.assertRaisesRegex(ValueError, 'execution_policy'):
            cli.prepare([self.source], '未知执行策略', 1, execution_policy='unrestricted')


if __name__ == '__main__':
    unittest.main()
