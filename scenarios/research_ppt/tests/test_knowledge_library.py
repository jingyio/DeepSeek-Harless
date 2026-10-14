"""持久化与权限的无模型诊断；不代表科研质量、成本或多人登录验收。"""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import fitz

from scenarios.research_ppt import knowledge_library as library
from scenarios.research_ppt import documents


class PersistentLibraryTests(unittest.TestCase):
    def setUp(self):
        area = library.ROOT / '.local/research-ppt/unit-tests'
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.area = Path(self.temp.name)
        self.store = self.area / 'library'
        self.lib = library.PersistentLibrary(self.store)
        self.source = self.area / 'paper.pdf'
        self.make_pdf(self.source, 'A persistent public research paper.')
        self.public = {'confirmed': True, 'source_url': 'https://example.org/paper',
                       'license': 'CC-BY-4.0', 'consent_reference': 'owner-explicit-share-01'}

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def make_pdf(path, text):
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.insert_text((50, 70), text)
            pdf.save(path)

    def register(self, **kwargs):
        return self.lib.register_document(self.source, tenant_id='alice', job_id='job-1', **kwargs)

    def resolve(self, resource, tenant='alice', job='job-2', **kwargs):
        return self.lib.resolve_document(resource['resource_id'], tenant_id=tenant, job_id=job, **kwargs)

    def events(self):
        return [json.loads(path.read_text(encoding='utf-8')) for path in (self.store / 'events').glob('*.json')]

    def test_retains_independent_copy_across_jobs_and_restarts(self):
        resource = self.register()
        first = self.resolve(resource)
        self.source.unlink()
        restarted = library.PersistentLibrary(self.store)
        second = restarted.resolve_document(resource['resource_id'], tenant_id='alice', job_id='job-3',
                                              expected_sha256=resource['source_sha256'])
        self.assertEqual(first['path'], second['path'])
        self.assertTrue(Path(second['path']).exists())
        self.assertEqual(documents.file_hash(Path(second['path'])), resource['source_sha256'])
        rows = self.events()
        self.assertEqual({row['job_id'] for row in rows}, {'job-1', 'job-2', 'job-3'})
        for row in rows:
            sha = row.pop('event_sha256')
            self.assertEqual(sha, library._digest(row))

    def test_same_bytes_private_to_two_tenants_do_not_grant_access(self):
        resource = self.register()
        with self.assertRaises(PermissionError):
            self.resolve(resource, tenant='bob')
        self.assertEqual(self.lib.list_resources(tenant_id='bob'), [])
        with self.assertRaises(PermissionError):
            self.lib.cache_directory(resource['resource_id'], tenant_id='bob', job_id='job-2')
        other = self.lib.register_document(self.source, tenant_id='bob', job_id='job-2')
        self.assertNotEqual(resource['resource_id'], other['resource_id'])
        self.assertEqual(resource['source_sha256'], other['source_sha256'])
        self.assertNotEqual(self.resolve(resource)['path'], self.resolve(other, tenant='bob')['path'])

    def test_public_requires_explicit_consent_then_withdrawal_preserves_bytes(self):
        with self.assertRaises(ValueError):
            self.register(visibility='public')
        with self.assertRaises(PermissionError):
            self.register(visibility='public', public_consent={**self.public, 'confirmed': False})
        resource = self.register(visibility='public', public_consent=self.public)
        shared = self.resolve(resource, tenant='bob')
        self.assertEqual(len(self.lib.list_resources(tenant_id='bob')), 1)
        self.lib.set_document_sharing(resource['resource_id'], tenant_id='alice', job_id='withdraw-1',
                                       visibility='private')
        with self.assertRaises(PermissionError):
            self.resolve(resource, tenant='bob')
        with self.assertRaises(PermissionError):
            self.lib.parse_document(resource['resource_id'], tenant_id='bob', job_id='job-3')
        self.assertEqual(self.lib.list_resources(tenant_id='bob'), [])
        self.assertTrue(Path(shared['path']).exists())
        self.assertEqual(self.resolve(resource)['path'], shared['path'])

    def test_only_owner_can_share_or_revoke(self):
        resource = self.register()
        with self.assertRaises(PermissionError):
            self.lib.set_document_sharing(resource['resource_id'], tenant_id='bob', job_id='share',
                                           visibility='public', public_consent=self.public)
        with self.assertRaises(PermissionError):
            self.lib.revoke_document(resource['resource_id'], tenant_id='bob', job_id='revoke')

    def test_revocation_blocks_new_jobs_without_deleting_history(self):
        resource = self.register()
        path = Path(self.resolve(resource)['path'])
        self.lib.revoke_document(resource['resource_id'], tenant_id='alice', job_id='revoke')
        with self.assertRaises(PermissionError):
            self.resolve(resource)
        with self.assertRaises(PermissionError):
            self.register()
        self.assertTrue(path.exists())
        self.assertEqual(self.lib.list_resources(tenant_id='alice'), [])
        changed = [row for row in self.events() if row['action'] == 'access_changed']
        self.assertEqual(changed[-1]['details']['status'], 'revoked')
        self.assertTrue(changed[-1]['details']['bytes_retained'])

    def test_new_bytes_have_new_version_stale_expected_version_fails(self):
        resource = self.register()
        replacement = self.area / 'updated.pdf'
        self.make_pdf(replacement, 'A revised input with different facts.')
        self.source.write_bytes(replacement.read_bytes())
        updated = self.register()
        self.assertNotEqual(resource['resource_id'], updated['resource_id'])
        with self.assertRaisesRegex(ValueError, '版本'):
            self.resolve(updated, expected_sha256=resource['source_sha256'])
        with self.assertRaisesRegex(ValueError, '版本'):
            self.lib.parse_document(updated['resource_id'], tenant_id='alice', job_id='new',
                                      expected_sha256=resource['source_sha256'])
        with self.assertRaisesRegex(ValueError, '版本'):
            self.register(expected_sha256=resource['source_sha256'])
        self.assertEqual(self.resolve(resource)['source_sha256'], resource['source_sha256'])

    def test_actual_parser_cache_survives_job_and_store_restart(self):
        resource = self.register()
        events = []
        with patch.object(documents, 'parse_document', wraps=documents.parse_document) as parse:
            first = self.lib.parse_document(resource['resource_id'], tenant_id='alice', job_id='parse-1',
                                             expected_sha256=resource['source_sha256'], audit=events.append)
            second = library.PersistentLibrary(self.store).parse_document(
                resource['resource_id'], tenant_id='alice', job_id='parse-2', audit=events.append)
            self.assertEqual(parse.call_count, 1)
            self.assertEqual(first, second)
        self.assertEqual([row['status'] for row in events], ['miss', 'hit'])
        self.assertTrue(all(row['library_resource_id'] == resource['resource_id'] for row in events))

    def test_revoke_during_parse_never_returns_cached_payload(self):
        resource = self.register()
        original_parse = documents.parse_document

        def revoke_after_parse(path):
            payload = original_parse(path)
            self.lib.revoke_document(resource['resource_id'], tenant_id='alice', job_id='withdraw-during-parse')
            return payload

        with patch.object(documents, 'parse_document', side_effect=revoke_after_parse):
            with self.assertRaises(PermissionError):
                self.lib.parse_document(resource['resource_id'], tenant_id='alice', job_id='parse-1')

    def test_document_and_record_corruption_rejected(self):
        resource = self.register()
        path = Path(self.resolve(resource)['path'])
        path.write_bytes(path.read_bytes() + b'\n% corrupted\n')
        with self.assertRaisesRegex(ValueError, '版本'):
            self.resolve(resource)
        record_path = self.store / 'records' / (resource['resource_id'] + '.json')
        record = json.loads(record_path.read_text(encoding='utf-8'))
        record['visibility'] = 'public'
        record_path.write_text(json.dumps(record), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '完整性'):
            self.resolve(resource, tenant='bob')

    def test_repeated_registration_audited_without_resetting_visibility(self):
        first = self.register()
        second = self.register()
        self.assertEqual(first['resource_id'], second['resource_id'])
        self.assertEqual(len(list((self.store / 'objects').glob('*.pdf'))), 1)
        self.assertEqual({row['action'] for row in self.events()}, {'document_registered', 'document_reused'})
        with self.assertRaisesRegex(ValueError, '显式修改'):
            self.register(visibility='public', public_consent=self.public)

    def test_component_fixed_script_is_descriptor_only_and_version_bound(self):
        entry = self.lib.register_component({'kind': 'fixed_script', 'script_id': 'render_delivery'},
                                            tenant_id='alice', job_id='component-1')
        resolved = self.lib.resolve_component(entry['resource_id'], tenant_id='alice', job_id='component-2')
        self.assertEqual(resolved['descriptor']['script_id'], 'render_delivery')
        self.assertEqual(resolved['descriptor']['execution'], 'descriptor_only_existing_host_required')
        self.assertNotIn('code', resolved['descriptor'])
        with self.assertRaises(PermissionError):
            self.lib.resolve_component(entry['resource_id'], tenant_id='bob', job_id='component-3')
        original_hash = documents.file_hash

        def changed_hash(path):
            return '0' * 64 if str(path).endswith('delivery-adapter.ts') else original_hash(path)

        with patch.object(documents, 'file_hash', side_effect=changed_hash):
            with self.assertRaisesRegex(ValueError, '实现或认证依赖'):
                self.lib.resolve_component(entry['resource_id'], tenant_id='alice', job_id='component-4')

    def bound_job(self, *, allow_output=False, tenant='alice'):
        job = {'job_id': 'bound-job', 'allow_output': allow_output, 'persistent_library': True,
               'library_schema_version': 1, 'library_tenant': tenant,
               'library_component_schema_version': 1, 'library_components': {}}
        for script_id in library.required_job_components(job):
            entry = self.lib.register_component({'kind': 'fixed_script', 'script_id': script_id},
                                                tenant_id=tenant, job_id=job['job_id'])
            job['library_components'][script_id] = {key: entry[key] for key in ('resource_id', 'version_sha256')}
        return job

    def test_job_components_reuse_fixed_descriptors_without_loading_code(self):
        first = self.bound_job(allow_output=True)
        second = {**first, 'job_id': 'independent-job'}
        descriptors = library.validate_job_components(second, library=self.lib)
        self.assertEqual(set(descriptors), {'document_parse', 'render_delivery', 'direct_edit'})
        self.assertTrue(all(row['kind'] == 'fixed_script' and 'code' not in row for row in descriptors.values()))
        self.assertIn('scenarios/research_ppt/ts/execution-policy.ts', descriptors['render_delivery']['files'])
        self.assertNotIn('scenarios/research_ppt/cli.py', descriptors['render_delivery']['files'])
        self.assertEqual(len(self.lib.list_resources(tenant_id='alice', kind='component')), 3)
        resolved = [row for row in self.events() if row['action'] == 'component_resolved']
        self.assertEqual(len(resolved), 3)
        self.assertEqual({row['job_id'] for row in resolved}, {'independent-job'})

    def test_job_components_legacy_is_only_both_fields_absent(self):
        before = len(self.events())
        self.assertEqual(library.validate_job_components({'job_id': 'legacy'}, library=self.lib), {})
        self.assertEqual(len(self.events()), before)
        for job in ({'library_component_schema_version': 1}, {'library_components': {}},
                    {'library_component_schema_version': None, 'library_components': None}):
            with self.subTest(job=job), self.assertRaises(ValueError):
                library.validate_job_components(job, library=self.lib)

    def test_job_component_schema_and_binding_substitution_rejected(self):
        base = self.bound_job()
        mutated = []
        for schema in (True, None, 2):
            mutated.append({**base, 'library_component_schema_version': schema})
        for change in ({'persistent_library': False}, {'library_schema_version': True},
                       {'allow_output': 'false'}, {'library_tenant': '../alice'}):
            mutated.append({**base, **change})
        for bindings in ({}, {**base['library_components'], 'shell': base['library_components']['document_parse']},
                         {'document_parse': base['library_components']['document_parse']}):
            mutated.append({**base, 'library_components': bindings})
        for replacement in ({'resource_id': 'doc-' + '0' * 40, 'version_sha256': '0' * 64},
                            {**base['library_components']['document_parse'], 'version_sha256': '0' * 64},
                            {**base['library_components']['document_parse'], 'code': 'exec(input)'}):
            mutated.append({**base, 'library_components': {**base['library_components'], 'document_parse': replacement}})
        mutated.append({**base, 'library_components': {
            'document_parse': base['library_components']['render_delivery'],
            'render_delivery': base['library_components']['document_parse']}})
        for job in mutated:
            with self.subTest(job=job), self.assertRaises((ValueError, PermissionError)):
                library.validate_job_components(job, library=self.lib)

    def test_job_component_revoke_and_tenant_change_never_register_replacement(self):
        job = self.bound_job()
        with patch.object(self.lib, 'register_component', side_effect=AssertionError('不应重新登记')):
            with self.assertRaises(PermissionError):
                library.validate_job_components({**job, 'library_tenant': 'bob'}, library=self.lib)
            entry = job['library_components']['document_parse']
            self.lib.revoke_component(entry['resource_id'], tenant_id='alice', job_id='withdraw-component')
            with self.assertRaises(PermissionError):
                library.validate_job_components(job, library=self.lib)

    def test_new_component_version_cannot_rebind_old_job(self):
        old_job = self.bound_job()
        original_hash = documents.file_hash

        def changed_hash(path):
            return '0' * 64 if str(path).endswith('execution-policy.ts') else original_hash(path)

        with patch.object(documents, 'file_hash', side_effect=changed_hash):
            new_job = self.bound_job()
            self.assertNotEqual(old_job['library_components']['render_delivery'],
                                new_job['library_components']['render_delivery'])
            self.assertIn('render_delivery', library.validate_job_components(new_job, library=self.lib))
            with self.assertRaisesRegex(ValueError, '实现或认证依赖'):
                library.validate_job_components(old_job, library=self.lib)

    def test_public_fixed_component_reused_then_revoked(self):
        entry = self.lib.register_component({'kind': 'fixed_script', 'script_id': 'document_parse'},
                                            tenant_id='alice', job_id='component-1', visibility='public',
                                            public_consent={**self.public, 'license': 'repository-license'})
        descriptor = self.lib.resolve_component(entry['resource_id'], tenant_id='bob', job_id='component-2')
        self.assertEqual(descriptor['version_sha256'], entry['version_sha256'])
        self.lib.revoke_component(entry['resource_id'], tenant_id='alice', job_id='withdraw')
        with self.assertRaises(PermissionError):
            self.lib.resolve_component(entry['resource_id'], tenant_id='bob', job_id='component-3')

    def test_component_arbitrary_code_path_or_fake_certification_denied(self):
        for descriptor in ({'kind': 'fixed_script', 'script_id': 'shell'},
                           {'kind': 'fixed_script', 'script_id': 'direct_edit', 'code': 'eval(input)'},
                           {'kind': 'arbitrary_code', 'command': 'rm -rf /'},
                           {'kind': 'certified_generated_tool', 'certificate_path': str(self.source),
                            'certificate_sha256': '0' * 64}):
            with self.subTest(descriptor=descriptor), self.assertRaises((ValueError, PermissionError)):
                self.lib.register_component(descriptor, tenant_id='alice', job_id='component-1')

    def test_generated_tool_requires_existing_independent_certification(self):
        fake = self.area / 'fake-certificate.json'
        fake.write_text('{"functional_certified":true}', encoding='utf-8')
        Path(str(fake) + '.sha256').write_text(documents.file_hash(fake), encoding='ascii')
        with self.assertRaises((ValueError, KeyError)):
            self.lib.register_component({'kind': 'certified_generated_tool', 'certificate_path': str(fake),
                                         'certificate_sha256': documents.file_hash(fake)},
                                         tenant_id='alice', job_id='component-1')
        with self.assertRaises(PermissionError):
            self.lib.register_component({'kind': 'certified_generated_tool', 'certificate_path': str(fake),
                                         'certificate_sha256': documents.file_hash(fake)}, tenant_id='alice',
                                         job_id='component-1', visibility='public', public_consent=self.public)

    def test_certified_motif_uses_real_offline_compiler_and_rechecks_source_locks(self):
        # Existing synthetic trace fixture exercises the real public compiler/exporter.
        # It establishes mechanical registration, not cloud quality or RSI cost savings.
        from scenarios.research_ppt.tests.test_motif_v6 import MotifV6Tests
        fixture = MotifV6Tests('test_public_compiler_learns_unique_scoped_handle_without_written_dag')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        manifest = fixture.learn(fixture.dataset())
        descriptor = {'kind': 'certified_motif', 'manifest_path': str(manifest),
                      'manifest_sha256': documents.file_hash(manifest)}
        entry = self.lib.register_component(descriptor, tenant_id='alice', job_id='motif-train')
        resolved = self.lib.resolve_component(entry['resource_id'], tenant_id='alice', job_id='motif-new-task')
        self.assertEqual(resolved['descriptor']['manifest_sha256'], descriptor['manifest_sha256'])
        self.assertEqual(resolved['descriptor']['certification_scope'], 'independent_trace_not_quality_cost_promotion')
        self.assertEqual(resolved['descriptor']['evidence_lock_sha256'],
                         documents.file_hash(manifest.parent / 'evidence-lock.json'))
        with self.assertRaises(PermissionError):
            self.lib.register_component(descriptor, tenant_id='alice', job_id='motif-share',
                                         visibility='public', public_consent=self.public)
        fixture.code.write_bytes(fixture.code.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, '变化'):
            self.lib.resolve_component(entry['resource_id'], tenant_id='alice', job_id='motif-stale')

    def test_fake_motif_manifest_and_false_parser_cache_option_rejected(self):
        manifest = self.area / 'fake-manifest.json'
        manifest.write_text('{"manifest_digest":"fake"}', encoding='utf-8')
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.lib.register_component({'kind': 'certified_motif', 'manifest_path': str(manifest),
                                         'manifest_sha256': documents.file_hash(manifest)},
                                         tenant_id='alice', job_id='motif-fake')
        resource = self.register()
        with self.assertRaisesRegex(ValueError, 'use_cache'):
            self.lib.parse_document(resource['resource_id'], tenant_id='alice', job_id='parse', use_cache='false')

    def test_paths_ids_and_parallel_writes_fail_closed(self):
        with self.assertRaises(ValueError):
            library.PersistentLibrary(library.ROOT / 'not-private')
        with self.assertRaises(ValueError):
            self.lib.register_document(self.source, tenant_id='../bob', job_id='job-1')
        with self.assertRaises(ValueError):
            self.lib.resolve_document('../../private', tenant_id='bob', job_id='job-1')
        lock = self.store / '.write-lock'
        lock.write_text('another writer', encoding='utf-8')
        with patch.object(library, 'LOCK_WAIT_SECONDS', 0.06), self.assertRaisesRegex(RuntimeError, '写入'):
            self.register()
        self.assertEqual(lock.read_text(encoding='utf-8'), 'another writer')
        lock.unlink()

    def test_normal_writer_contention_waits_then_preserves_access(self):
        ready = threading.Event()
        def writer():
            with self.lib._lock():
                ready.set()
                time.sleep(0.12)
        worker = threading.Thread(target=writer)
        worker.start()
        self.assertTrue(ready.wait(2))
        started = time.monotonic()
        with patch.object(library, 'LOCK_WAIT_SECONDS', 1.0):
            resource = self.register()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertGreaterEqual(time.monotonic() - started, 0.08)
        self.assertFalse((self.store / '.write-lock').exists())
        self.assertEqual(self.lib.resolve_document(resource['resource_id'], tenant_id='alice',
            job_id='after-contention')['source_sha256'], documents.file_hash(self.source))

    def test_replaced_lock_is_not_removed_by_old_writer(self):
        lock = self.store / '.write-lock'
        with self.lib._lock():
            lock.write_text(json.dumps({'token':'another-writer'}), encoding='utf-8')
        self.assertEqual(json.loads(lock.read_text())['token'], 'another-writer')
        lock.unlink()


if __name__ == '__main__':
    unittest.main()
