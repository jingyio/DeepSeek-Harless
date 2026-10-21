"""Lifecycle protocol diagnostics; local fixture servers never call a model."""
import importlib.util
from contextlib import nullcontext
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location('geneloop_service', SCRIPTS / 'geneloop_service.py')
service = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(service)

FIXTURE = r'''
import os,sys,json
from http.server import BaseHTTPRequestHandler,HTTPServer
from uuid import uuid4
role,config=sys.argv[1:]
c=json.load(open(config));port=c['ownerPort'] if role=='owner' else c['port']
if os.environ.get('FAIL_SERVICE')==role:sys.exit(3)
token=uuid4().hex+uuid4().hex
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if role=='gateway':self.send_response(200 if self.path=='/login' else 404)
  elif self.path=='/?token='+token:
   self.send_response(303);self.send_header('Set-Cookie','dsh-auth-test='+token+'; HttpOnly');self.send_header('Location','/')
  else:self.send_response(200 if self.path=='/' and self.headers.get('Cookie')=='dsh-auth-test='+token else 401)
  self.end_headers();self.wfile.write(b'fixture protocol diagnostic')
 def log_message(self,*args):pass
server=HTTPServer(('127.0.0.1',port),Handler)
if role=='owner':print('dsh web: http://127.0.0.1:%s/?token=%s'%(port,token),flush=True)
server.serve_forever()
'''


def port():
    with socket.socket() as connection:
        connection.bind(('127.0.0.1', 0))
        return connection.getsockname()[1]


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = self.root / 'gateway.json'
        self.policy = self.root / 'policy.json'
        self.output = self.root / 'tasks'
        self.output.mkdir()
        self.members = self.root / 'members'
        self.members.mkdir()
        service.save(self.policy, {'output': str(self.output)})
        service.save(self.config, {'ownerPort': port(), 'port': port(), 'membersDir': str(self.members),
                                  'dataDir': str(self.root / 'accounts'), 'ownerTokenFile': str(self.root / 'access.txt')})
        self.fixture = self.root / 'fixture.py'
        self.fixture.write_text(FIXTURE, encoding='utf-8')
        env = {**os.environ, 'SSS_WEB_POLICY': str(self.policy), 'DSH_HOME': str(self.root / 'home')}
        self.plan = {'version': 1, 'state_dir': str(self.root / 'service'), 'gateway_config': str(self.config),
                     'owner_output': str(self.output), 'owner': {'argv': [sys.executable, str(self.fixture), 'owner', str(self.config)],
                         'cwd': str(self.root), 'env': env},
                     'gateway': {'argv': [sys.executable, str(self.fixture), 'gateway', str(self.config)],
                         'cwd': str(self.root), 'env': env.copy()}}
        self.plan_file = self.root / 'service.json'
        self.pointer = self.root / 'runtime.json'
        service.save(self.pointer, {'budget': {'requests': 19, 'spent': .25}, 'kept_receipt': 'previous',
                                    'owner_pid': 0, 'gateway_pid': 0})
        self.plan['runtime_pointer'] = str(self.pointer)
        service.save(self.plan_file, self.plan)

    def test_plan_validates_private_files_and_output(self):
        self.assertEqual(service.load_plan(self.plan_file), self.plan)
        value = service.read(self.policy)
        value['output'] = str(self.root / 'different')
        service.save(self.policy, value)
        with self.assertRaises(RuntimeError):
            service.load_plan(self.plan_file)

    def test_snapshot_keeps_digest_and_is_independent_of_original_files(self):
        lifecycle = service.Lifecycle(self.plan)
        destination = self.root / 'snapshot'
        destination.mkdir(mode=0o700)
        frozen = lifecycle.snapshot(self.plan, destination)
        digest = service.plan_digest(frozen)
        self.assertEqual(digest, service.plan_digest(self.plan))
        service.save(self.config, {**service.read(self.config), 'marker': 'changed'})
        self.assertEqual(digest, service.plan_digest(frozen))
        self.assertNotEqual(digest, service.plan_digest(self.plan))

    def test_start_prepared_recovery_only_after_both_managed_processes_exit(self):
        lifecycle=service.Lifecycle(self.plan)
        old=json.loads(json.dumps(self.plan))
        old['owner']['env']['RECOVERY_VARIANT']='old'
        record={'plan':old,'digest':service.plan_digest(old),'rollback_plan':str(self.plan_file)}
        with mock.patch.object(lifecycle,'lock',return_value=nullcontext()), \
                mock.patch.object(lifecycle,'current',return_value=record), \
                mock.patch.object(lifecycle,'inspect',return_value={'owner':None,'gateway':None}), \
                mock.patch.object(service,'assert_idle') as idle, \
                mock.patch.object(lifecycle,'start',return_value={'already_running':False}) as start:
            result=lifecycle.run('start')
        idle.assert_called_once_with(old)
        start.assert_called_once_with(self.plan)
        self.assertTrue(result['recovered_stopped_deployment'])

    def test_prepared_recovery_refuses_a_surviving_process(self):
        lifecycle=service.Lifecycle(self.plan)
        old=json.loads(json.dumps(self.plan));old['owner']['env']['RECOVERY_VARIANT']='old'
        record={'plan':old,'digest':service.plan_digest(old),'rollback_plan':str(self.plan_file)}
        with mock.patch.object(lifecycle,'lock',return_value=nullcontext()), \
                mock.patch.object(lifecycle,'current',return_value=record), \
                mock.patch.object(lifecycle,'inspect',return_value={'owner':{'pid':1},'gateway':None}), \
                mock.patch.object(lifecycle,'start') as start:
            with self.assertRaisesRegex(RuntimeError,'different release'):
                lifecycle.run('start')
        start.assert_not_called()

    def test_prepared_recovery_keeps_active_task_guard(self):
        lifecycle=service.Lifecycle(self.plan)
        old=json.loads(json.dumps(self.plan));old['owner']['env']['RECOVERY_VARIANT']='old'
        record={'plan':old,'digest':service.plan_digest(old),'rollback_plan':str(self.plan_file)}
        with mock.patch.object(lifecycle,'lock',return_value=nullcontext()), \
                mock.patch.object(lifecycle,'current',return_value=record), \
                mock.patch.object(lifecycle,'inspect',return_value={'owner':None,'gateway':None}), \
                mock.patch.object(service,'assert_idle',side_effect=RuntimeError('Active task')), \
                mock.patch.object(lifecycle,'start') as start:
            with self.assertRaisesRegex(RuntimeError,'Active task'):
                lifecycle.run('start')
        start.assert_not_called()

    def test_polling_plan_does_not_allocate_native_watches(self):
        self.plan['owner']['env']['CHOKIDAR_USEPOLLING']='1'
        with mock.patch.object(service.ctypes,'CDLL') as library:
            service.assert_watch_capacity(self.plan)
        library.assert_not_called()

    def test_exhausted_native_watch_is_closed_and_refuses_before_stop(self):
        self.plan['owner']['env']['CHOKIDAR_USEPOLLING']='0'
        library=mock.Mock()
        library.inotify_init1.return_value=41
        library.inotify_add_watch.return_value=-1
        with mock.patch.object(service.sys,'platform','linux'), \
                mock.patch.object(service.ctypes,'CDLL',return_value=library), \
                mock.patch.object(service.os,'O_CLOEXEC',524288,create=True), \
                mock.patch.object(service.os,'close') as close:
            with self.assertRaisesRegex(RuntimeError,'capacity exhausted'):
                service.assert_watch_capacity(self.plan)
        close.assert_called_once_with(41)
        lifecycle=service.Lifecycle(self.plan)
        record={'plan':self.plan,'digest':service.plan_digest(self.plan),
                'processes':{'owner':{'pid':1},'gateway':{'pid':2}}}
        with mock.patch.object(lifecycle,'current',return_value=record), \
                mock.patch.object(lifecycle,'inspect'),mock.patch.object(service,'same_data'), \
                mock.patch.object(service,'assert_idle'), \
                mock.patch.object(service,'assert_watch_capacity',side_effect=RuntimeError('capacity exhausted')), \
                mock.patch.object(lifecycle,'stop_record') as stop:
            with self.assertRaisesRegex(RuntimeError,'capacity exhausted'):
                lifecycle.restart()
        stop.assert_not_called()

    def test_persistent_data_migration_is_rejected(self):
        second = json.loads(json.dumps(self.plan))
        other = self.root / 'different-config.json'
        service.save(other, {**service.read(self.config), 'membersDir': str(self.root / 'other-members')})
        second['gateway_config'] = str(other)
        with self.assertRaises(RuntimeError):
            service.same_data(self.plan, second)

    def test_unknown_and_member_active_states_refuse_restart(self):
        member = self.members / 'one' / 'tasks' / 'tasks' / 'task'
        member.mkdir(parents=True)
        for status in ('running', 'unexpected'):
            service.save(member / 'task-state.json', {'status': status})
            with self.assertRaises(RuntimeError):
                service.assert_idle(self.plan)
        service.save(member / 'task-state.json', {'status': 'completed'})
        service.assert_idle(self.plan)

    def test_active_comparison_lane_is_not_treated_as_idle(self):
        service.save(self.output / 'comparisons.json', {'turns': [{'status': 'completed', 'lanes': {
            'baseline': {'status': 'completed'}, 'motif': {'status': 'running'}}}]})
        with self.assertRaises(RuntimeError):
            service.assert_idle(self.plan)

    def file_state(self, base, name='task'):
        path = base / 'file-management' / 'accounts' / 'diagnostic-scope' / 'tasks' / name / 'state.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def bind_gateway_source(self, root):
        source = root / 'src'
        source.mkdir(parents=True)
        entry = root / 'scripts' / 'harless_gateway.mjs'
        entry.parent.mkdir()
        entry.write_text('// Source identity fixture; never executed.\n', encoding='utf-8')
        service.save(self.config, {**service.read(self.config), 'sourceDir': str(source)})
        self.plan['gateway']['cwd'] = str(root)
        self.plan['gateway']['argv'] = [sys.executable, str(entry), str(self.config)]

    def test_member_sdk_file_active_and_unknown_states_refuse_restart(self):
        path = self.file_state(self.members / 'one' / 'tasks')
        for status in ('running', 'queued', 'preparing', 'awaiting_confirmation', 'unexpected', None, []):
            with self.subTest(status=status):
                service.save(path, {'status': status})
                with self.assertRaisesRegex(RuntimeError, 'Active or unknown File task'):
                    service.assert_idle(self.plan)

    def test_file_terminal_states_allow_restart_and_do_not_modify_records(self):
        for status in ('completed', 'failed', 'cancelled', 'interrupted'):
            for output in (self.output, self.members / 'one' / 'tasks', self.members / 'two' / 'tasks'):
                path = self.file_state(output, status)
                service.save(path, {'status': status, 'retained': 'original'})
        before = {path: path.read_bytes() for path in self.root.rglob('state.json')}
        service.assert_idle(self.plan)
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_owner_sdk_file_uses_running_gateway_source_not_output(self):
        running = self.root / 'running-checkout'
        self.bind_gateway_source(running)
        path = self.file_state(running / '.local' / 'web')
        service.save(path, {'status': 'running'})
        with self.assertRaisesRegex(RuntimeError, 'Active or unknown File task'):
            service.assert_idle(self.plan)
        service.save(path, {'status': 'interrupted'})
        service.assert_idle(self.plan)

    def test_mismatched_owner_file_source_cannot_hide_active_old_tasks(self):
        running = self.root / 'running-checkout'
        self.bind_gateway_source(running)
        path = self.file_state(running / '.local' / 'web')
        service.save(path, {'status': 'running'})
        other = self.root / 'candidate-checkout' / 'src'
        other.mkdir(parents=True)
        service.save(self.config, {**service.read(self.config), 'sourceDir': str(other)})
        with self.assertRaisesRegex(RuntimeError, 'Owner File source root differs'):
            service.assert_idle(self.plan)

    def test_invalid_owner_file_source_is_not_silently_skipped(self):
        for source in ('relative/src', str(self.root / 'missing' / 'src'), str(self.output)):
            with self.subTest(source=source):
                service.save(self.config, {**service.read(self.config), 'sourceDir': source})
                with self.assertRaisesRegex(RuntimeError, 'Unknown owner File source root'):
                    service.assert_idle(self.plan)

    def test_corrupt_or_nonobject_file_state_refuses_restart(self):
        path = self.file_state(self.members / 'one' / 'tasks')
        for raw in ('{', '[]', 'null', '"completed"'):
            with self.subTest(raw=raw):
                path.write_text(raw, encoding='utf-8')
                with self.assertRaisesRegex(RuntimeError, 'Unknown File task state'):
                    service.assert_idle(self.plan)

    def test_restart_refuses_active_file_before_stopping_any_process(self):
        path = self.file_state(self.members / 'one' / 'tasks')
        service.save(path, {'status': 'running'})
        lifecycle = service.Lifecycle(self.plan)
        record = {'plan': self.plan, 'digest': 'same-intent', 'processes': {'owner': {'pid': 1}, 'gateway': {'pid': 2}}}
        with mock.patch.object(lifecycle, 'current', return_value=record), \
                mock.patch.object(service, 'plan_digest', return_value='same-intent'), \
                mock.patch.object(lifecycle, 'inspect'), \
                mock.patch.object(lifecycle, 'stop_record') as stop, \
                mock.patch.object(lifecycle, 'start') as start:
            with self.assertRaisesRegex(RuntimeError, 'Active or unknown File task'):
                lifecycle.restart()
        stop.assert_not_called()
        start.assert_not_called()

    def test_completed_file_spawn_receipt_blocks_restart_before_learning_lock_is_written(self):
        path = self.file_state(self.output)
        service.save(path, {'status': 'completed', 'metrics': {'continuous_rsi': {'worker': {'pid': 12345}}}})
        before = path.read_bytes()
        with mock.patch.object(service, 'file_worker_running', return_value=True) as probe:
            with self.assertRaisesRegex(RuntimeError, 'Active File background learning'):
                service.assert_idle(self.plan)
        probe.assert_called_once_with(12345, path.parents[2], None)
        self.assertEqual(path.read_bytes(), before)

    def test_member_learning_lock_uses_the_member_namespace_scope_and_retains_dead_lock(self):
        home = self.members / 'one' / 'tasks' / 'file-management' / 'accounts' / 'scope'
        lock = home / 'rsi' / 'daily' / 'worker.lock'
        lock.parent.mkdir(parents=True)
        service.save(lock, {'pid': 42, 'created': 1})
        policy = self.members / 'one' / 'config' / 'policy.json'
        policy.parent.mkdir()
        namespace_output = self.root / 'sandbox-output'
        service.save(policy, {'output': str(namespace_output)})
        before = lock.read_bytes()
        with mock.patch.object(service, 'file_worker_running', return_value=True) as probe:
            with self.assertRaisesRegex(RuntimeError, 'Active File background learning'):
                service.assert_idle(self.plan)
        probe.assert_called_once_with(42, home, namespace_output / 'file-management' / 'accounts' / 'scope')
        with mock.patch.object(service, 'file_worker_running', return_value=False):
            service.assert_idle(self.plan)
        self.assertEqual(lock.read_bytes(), before, 'A dead worker check never steals or removes its lock')

    def test_unknown_learning_receipts_and_locks_refuse_restart(self):
        path = self.file_state(self.output)
        for metrics in ('bad', {'continuous_rsi': []}, {'continuous_rsi': {'worker': []}}, {'continuous_rsi': {'worker': {'pid': True}}}):
            with self.subTest(metrics=metrics):
                service.save(path, {'status': 'completed', 'metrics': metrics})
                with self.assertRaisesRegex(RuntimeError, 'Unknown File background worker'):
                    service.assert_idle(self.plan)
        service.save(path, {'status': 'completed'})
        lock = path.parents[2] / 'rsi' / 'daily' / 'worker.lock'
        lock.parent.mkdir(parents=True)
        for raw in ('{', '[]', '{}', '{"pid":0}', '{"pid":"42"}'):
            with self.subTest(raw=raw):
                lock.write_text(raw, encoding='utf-8')
                with self.assertRaisesRegex(RuntimeError, 'Unknown File background worker'):
                    service.assert_idle(self.plan)


class FileWorkerIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.proc = self.root / 'proc'
        self.proc.mkdir()
        self.home = self.root / 'account'
        self.home.mkdir()

    def process(self, host_pid, namespace_pid, config, command='rsi-worker.py'):
        process = self.proc / str(host_pid)
        process.mkdir()
        (process / 'status').write_text(f'State:\tS (sleeping)\nNSpid:\t{host_pid}\t{namespace_pid}\n', encoding='utf-8')
        argv = [sys.executable, command, '--config', str(config), '--drain']
        (process / 'cmdline').write_bytes(b'\0'.join(os.fsencode(value) for value in argv) + b'\0')
        return process

    def test_dead_and_reused_host_pids_do_not_false_positive_or_signal(self):
        with mock.patch.object(service.os, 'kill', side_effect=AssertionError('Must not signal any process')):
            self.assertFalse(service.file_worker_running(100, self.home, proc_root=self.proc))
            self.process(100, 100, self.home / 'rsi' / 'config.json', command='other.py')
            self.assertFalse(service.file_worker_running(100, self.home, proc_root=self.proc))

    def test_live_host_worker_requires_its_own_account_config(self):
        process = self.process(100, 100, self.home / 'rsi' / 'config.json')
        self.assertTrue(service.file_worker_running(100, self.home, proc_root=self.proc))
        (process / 'cmdline').write_bytes(b'python\0rsi-worker.py\0--config\0/other-account/rsi/config.json\0')
        self.assertFalse(service.file_worker_running(100, self.home, proc_root=self.proc))

    def kernel_process(self, host_pid, namespace_pid, *, flags=0x208040, name='scsi_eh_5', kthread=None):
        process = self.process(host_pid, namespace_pid, self.home / 'rsi/config.json')
        status = f'Name:\t{name}\nState:\tS (sleeping)\nUid:\t0\t0\t0\t0\nNSpid:\t{host_pid}\t{namespace_pid}\n'
        if kthread is not None:
            status += f'Kthread:\t{kthread}\n'
        (process / 'status').write_text(status, encoding='utf-8')
        (process / 'cmdline').write_bytes(b'')
        # pid (comm) state ppid pgrp session tty_nr tpgid flags ...
        (process / 'stat').write_text(f'{host_pid} ({name}) S 2 0 0 0 -1 {flags} 0 0\n', encoding='utf-8')
        return process

    @unittest.skipUnless(sys.platform == 'linux', 'PF_KTHREAD is a Linux kernel-owned process flag')
    def test_namespace_pid_collision_skips_only_proven_kernel_threads(self):
        namespace_home = Path('/app/.local/web/file-management/accounts/scope')
        # The real older-kernel failure has no status.Kthread field.
        self.kernel_process(656, 656)
        with mock.patch.object(Path, 'samefile', side_effect=AssertionError('Kernel thread has no account mount')) as same, \
                mock.patch.object(service.os, 'kill', side_effect=AssertionError('Must not signal any process')):
            self.assertFalse(service.file_worker_running(656, self.home, namespace_home, self.proc))
            self.assertFalse(service.file_worker_running(656, self.home, proc_root=self.proc))
        same.assert_not_called()

    @unittest.skipUnless(sys.platform == 'linux', 'PF_KTHREAD is a Linux kernel-owned process flag')
    def test_trusted_status_kernel_flag_works_without_older_stat_fallback(self):
        process = self.kernel_process(656, 656, kthread=1)
        (process / 'stat').unlink()
        self.assertFalse(service.file_worker_running(656, self.home, proc_root=self.proc))

    @unittest.skipUnless(sys.platform == 'linux', 'PF_KTHREAD is a Linux kernel-owned process flag')
    def test_empty_userspace_or_unknown_process_remains_a_restart_blocker(self):
        process = self.kernel_process(656, 656, flags=0x8040, name='[scsi_eh_5]')
        # A root UID, bracketed kernel-looking name and empty cmdline prove nothing.
        with self.assertRaisesRegex(RuntimeError, 'Unknown File background worker'):
            service.file_worker_running(656, self.home, proc_root=self.proc)
        (process / 'stat').unlink()
        with self.assertRaisesRegex(RuntimeError, 'Unknown File background worker'):
            service.file_worker_running(656, self.home, proc_root=self.proc)
        (process / 'stat').write_text('656 (scsi_eh_5) broken 2097152', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'Unknown File background worker'):
            service.file_worker_running(656, self.home, proc_root=self.proc)
        original = Path.read_text
        def inaccessible(path, *args, **kwargs):
            if path == process / 'stat':
                raise PermissionError('Unknown empty-cmdline process stat')
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, 'read_text', inaccessible):
            with self.assertRaisesRegex(RuntimeError, 'Unknown File background worker'):
                service.file_worker_running(656, self.home, proc_root=self.proc)

    @unittest.skipUnless(sys.platform == 'linux', 'PF_KTHREAD is a Linux kernel-owned process flag')
    def test_stat_comm_parentheses_do_not_move_the_flags_field(self):
        process = self.kernel_process(656, 656, flags=0x8040, name='worker ) 2097152 ( S')
        with self.assertRaisesRegex(RuntimeError, 'Unknown File background worker'):
            service.file_worker_running(656, self.home, proc_root=self.proc)
        (process / 'stat').write_text('999 (scsi_eh_5) S 2 0 0 0 -1 2097152 0\n', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'Unknown File background worker'):
            service.file_worker_running(656, self.home, proc_root=self.proc)

    @unittest.skipUnless(sys.platform == 'linux', 'PF_KTHREAD is a Linux kernel-owned process flag')
    def test_skipping_a_kernel_collision_still_detects_the_actual_namespaced_worker(self):
        namespace_home = Path('/app/.local/web/file-management/accounts/scope')
        self.kernel_process(42, 42)
        self.process(54321, 42, namespace_home / 'rsi/config.json')
        with mock.patch.object(Path, 'samefile', return_value=True) as same:
            self.assertTrue(service.file_worker_running(42, self.home, namespace_home, self.proc))
        same.assert_called_once_with(self.home)

    @unittest.skipUnless(os.name == 'posix', 'Hosted PID-namespace inspection is Linux-only')
    def test_unrelated_namespace_pid_never_inspects_inaccessible_mount(self):
        namespace_home = Path('/app/.local/web/file-management/accounts/scope')
        process = self.process(1043, 1043, namespace_home / 'rsi' / 'config.json', command='systemd-udevd')
        with mock.patch.object(Path, 'samefile', side_effect=PermissionError('Unrelated root process')) as same, \
                mock.patch.object(service.os, 'kill', side_effect=AssertionError('Must not signal any process')):
            self.assertFalse(service.file_worker_running(1043, self.home, namespace_home, self.proc))
            # Even a worker for a different account is not a mount candidate.
            (process / 'cmdline').write_bytes(b'python\0rsi-worker.py\0--config\0/app/.local/web/file-management/accounts/other/rsi/config.json\0')
            self.assertFalse(service.file_worker_running(1043, self.home, namespace_home, self.proc))
        same.assert_not_called()

    @unittest.skipUnless(os.name == 'posix', 'Hosted PID-namespace inspection is Linux-only')
    def test_namespace_candidate_unknown_command_or_config_still_refuses(self):
        namespace_home = Path('/app/.local/web/file-management/accounts/scope')
        process = self.process(54321, 42, namespace_home / 'rsi' / 'config.json')
        with mock.patch.object(Path, 'samefile', side_effect=AssertionError('Identity must be established first')) as same:
            for command in (b'', b'python\0rsi-worker.py\0', b'python\0rsi-worker.py\0--config\0'):
                with self.subTest(command=command):
                    (process / 'cmdline').write_bytes(command)
                    with self.assertRaisesRegex(RuntimeError, 'Unknown File background worker'):
                        service.file_worker_running(42, self.home, namespace_home, self.proc)
            with mock.patch.object(Path, 'read_bytes', side_effect=PermissionError('Inaccessible candidate command')):
                with self.assertRaisesRegex(RuntimeError, 'Unknown File background worker'):
                    service.file_worker_running(42, self.home, namespace_home, self.proc)
        same.assert_not_called()

    @unittest.skipUnless(os.name == 'posix', 'Hosted PID-namespace inspection is Linux-only')
    def test_member_pid_uses_namespace_id_and_bind_inode_not_host_pid(self):
        namespace_home = Path('/app/.local/web/file-management/accounts/scope')
        self.process(54321, 42, namespace_home / 'rsi' / 'config.json')
        with mock.patch.object(Path, 'samefile', return_value=True) as same:
            self.assertTrue(service.file_worker_running(42, self.home, namespace_home, self.proc))
        same.assert_called_once_with(self.home)
        with mock.patch.object(Path, 'samefile', return_value=False):
            self.assertFalse(service.file_worker_running(42, self.home, namespace_home, self.proc))
        with mock.patch.object(Path, 'samefile', side_effect=PermissionError('Synthetic inaccessible namespace')):
            with self.assertRaisesRegex(RuntimeError, 'Unknown File background worker'):
                service.file_worker_running(42, self.home, namespace_home, self.proc)


class PublicRecoveryTests(unittest.TestCase):
    def setUp(self):
        PlanTests.setUp(self)
        config=service.read(self.config);config['publicOrigin']='https://app.example.workers.dev';service.save(self.config,config)
        self.lifecycle=service.Lifecycle(self.plan)
        self.backend={'owner':{'pid':111,'start_ticks':'11','argv_sha256':'owner','cwd':str(self.root)},
                      'gateway':{'pid':112,'start_ticks':'12','argv_sha256':'gateway','cwd':str(self.root)}}
        self.origin='https://candidate-fixture.trycloudflare.com'
        argv=[sys.executable,'tunnel','--no-autoupdate','--protocol','http2','--url',
              'http://127.0.0.1:%s' % config['port'],'--http-host-header','app.example.workers.dev']
        self.old={'pid':51042,'start_ticks':'605440366','argv_sha256':service.hashlib.sha256(
            b'\0'.join(os.fsencode(v) for v in argv)+b'\0').hexdigest(),'cwd':str(self.root)}
        self.candidate={**self.old,'pid':19999,'start_ticks':'99'}
        self.public={'version':1,'public_origin':config['publicOrigin'],
                     'previous_origin':'https://old-fixture.trycloudflare.com','previous_process':self.old,
                     'tunnel':{'argv':argv,'cwd':str(self.root),'env':{'PATH':str(self.root)},
                               'binary_sha256':service.hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()}}
        self.public_path=self.root/'public.json';service.save(self.public_path,self.public)
        self.record={'plan':self.plan,'digest':service.plan_digest(self.plan),'processes':self.backend}
        service.save(self.lifecycle.state_path,self.record)
        self.expected={p:{'status':200,'sha256':p,'bytes':99} for p in ('/login','/assets/geneloop-spiral.svg')}
        self.good=False;self.direct_good=True
        self.child=mock.Mock(pid=19999);self.child.poll.return_value=None
        self.protected=self.output/'active-task.json';service.save(self.protected,{'status':'running','paid':19})

    def evidence(self, **changes):
        value={'version':1,'method':'cloudflare-dashboard','public_origin':self.public['public_origin'],
               'worker_name':'app','binding_name':'UPSTREAM_ORIGIN','binding_type':'plain_text',
               'upstream_origin':self.origin,'worker_code_unchanged':True,'other_bindings_unchanged':True,**changes}
        path=self.root/'route-evidence.json';service.save(path,value);return path

    def probe(self, origin, *_args, **_kwargs):
        if origin.startswith('http://127.0.0.1:') or origin==self.origin and self.direct_good or self.good:
            return self.expected
        return {p:{'status':530,'error_body':'error 1033'} for p in self.expected}

    def launch(self, *_args, **kwargs):
        kwargs['stdout'].write((self.origin+'\nRegistered tunnel connection\n').encode());return self.child

    def environment(self):
        from contextlib import ExitStack
        stack=ExitStack()
        stack.enter_context(mock.patch.object(self.lifecycle,'lock',return_value=nullcontext()))
        stack.enter_context(mock.patch.object(self.lifecycle,'inspect',return_value=self.backend))
        stack.enter_context(mock.patch.object(self.lifecycle,'health',return_value={'model_requests':0}))
        stack.enter_context(mock.patch.object(service,'identity',side_effect=lambda pid:self.old if pid==51042 else self.candidate))
        stack.enter_context(mock.patch.object(service,'command_matches',return_value=True))
        stack.enter_context(mock.patch.object(service,'public_probe',side_effect=self.probe))
        stack.enter_context(mock.patch.object(service,'assert_idle',side_effect=AssertionError('must not inspect or block active tasks')))
        stack.enter_context(mock.patch.object(self.lifecycle,'stop_record',side_effect=AssertionError('must not stop backend')))
        self.popen=stack.enter_context(mock.patch.object(service.subprocess,'Popen',side_effect=self.launch))
        self.kill=stack.enter_context(mock.patch.object(service.os,'kill',side_effect=AssertionError('must not signal legacy/foreign PID')))
        self.cloudflare=stack.enter_context(mock.patch.object(service,'CloudflareWorkerSettings'))
        return stack

    def test_manual_prepare_confirm_preserves_backend_active_tasks_and_foreign_tunnels(self):
        before=self.lifecycle.state_path.read_bytes();task=self.protected.read_bytes();runtime=self.pointer.read_bytes()
        with self.environment():
            prepared=self.lifecycle.run('public-prepare',self.public_path)
            self.assertTrue(prepared['awaiting_route_update']);self.assertEqual(prepared['candidate_origin'],self.origin)
            self.assertFalse((self.lifecycle.root/'public-current.json').exists())
            self.good=True;result=self.lifecycle.run('public-confirm',self.public_path,self.evidence())
            self.assertTrue(result['public_healthy']);self.cloudflare.assert_not_called();self.kill.assert_not_called()
            self.child.terminate.assert_not_called();self.assertEqual(self.popen.call_count,1)
        self.assertEqual(self.lifecycle.state_path.read_bytes(),before)
        self.assertEqual(self.protected.read_bytes(),task);self.assertEqual(self.pointer.read_bytes(),runtime)
        saved=service.read(self.lifecycle.root/'public-current.json')
        self.assertEqual(saved['confirmation']['method'],'manual-dashboard-attestation')
        self.assertEqual(saved['process'],self.candidate)

    def test_proxy_domain_rejection_is_retained_as_unverified_prepare_not_success(self):
        self.direct_good=False
        with self.environment():
            result=self.lifecycle.run('public-recover',self.public_path)
            self.assertTrue(result['awaiting_route_update']);self.assertFalse(result['candidate_direct_verified'])
            self.assertNotIn('public_healthy',result);self.child.terminate.assert_not_called()
            with self.assertRaisesRegex(RuntimeError,'awaits route update'):
                self.lifecycle.run('public-prepare',self.public_path)
            self.assertEqual(self.popen.call_count,1)

    def test_healthy_public_recovery_is_noop_and_check_has_no_side_effects(self):
        self.good=True
        with self.environment():
            self.assertTrue(self.lifecycle.run('public-check',self.public_path)['public_healthy'])
            self.assertTrue(self.lifecycle.run('public-recover',self.public_path)['already_running'])
            self.popen.assert_not_called();self.cloudflare.assert_not_called();self.kill.assert_not_called()

    def test_changed_old_generation_refuses_before_candidate_or_cloudflare_write(self):
        with self.environment(),mock.patch.object(service,'identity',return_value={**self.old,'start_ticks':'reused'}):
            with self.assertRaisesRegex(RuntimeError,'generation changed'):
                self.lifecycle.run('public-prepare',self.public_path)
            self.popen.assert_not_called();self.cloudflare.assert_not_called();self.kill.assert_not_called()

    def test_confirm_requires_exact_candidate_dashboard_evidence_and_real_public_bytes(self):
        with self.environment():
            self.lifecycle.run('public-prepare',self.public_path)
            for evidence in (None,self.evidence(upstream_origin='https://foreign.trycloudflare.com')):
                with self.assertRaises(RuntimeError):self.lifecycle.run('public-confirm',self.public_path,evidence)
            with self.assertRaisesRegex(RuntimeError,'do not match'):
                self.lifecycle.run('public-confirm',self.public_path,self.evidence())
            self.good=True
            with mock.patch.object(service,'identity',return_value={**self.candidate,'start_ticks':'reused'}):
                with self.assertRaisesRegex(RuntimeError,'identity changed'):
                    self.lifecycle.run('public-confirm',self.public_path,self.evidence())
            self.child.terminate.assert_not_called();self.assertFalse((self.lifecycle.root/'public-current.json').exists())

    def test_public_config_rejects_foreign_target_extra_shell_flags_and_binary_drift(self):
        for mutation in ('port','flags','binary'):
            value=json.loads(json.dumps(self.public))
            if mutation=='port':value['tunnel']['argv'][6]='http://127.0.0.1:33100'
            if mutation=='flags':value['tunnel']['argv']+=['--exec','shell']
            if mutation=='binary':value['tunnel']['binary_sha256']='0'*64
            service.save(self.public_path,value)
            with self.assertRaisesRegex(RuntimeError,'verified cloudflared'):
                service.load_public_config(self.public_path,self.plan)

    def test_failed_candidate_start_cleans_only_this_exact_child(self):
        def no_origin(*_args,**kwargs):return self.child
        with self.environment(),mock.patch.object(service.subprocess,'Popen',side_effect=no_origin), \
                mock.patch.object(service.time,'monotonic',side_effect=[0,91]):
            with self.assertRaisesRegex(RuntimeError,'did not pass direct'):
                self.lifecycle.run('public-prepare',self.public_path)
            self.child.terminate.assert_called_once_with();self.child.wait.assert_called_once_with(timeout=45)
            self.kill.assert_not_called();self.cloudflare.assert_not_called()
            self.assertFalse((self.lifecycle.root/'public-pending.json').exists())

    def test_public_operation_uses_the_same_lifecycle_lock(self):
        with mock.patch.object(self.lifecycle,'lock',side_effect=RuntimeError('Another service operation is running')), \
                mock.patch.object(self.lifecycle,'public_operation') as operation:
            with self.assertRaisesRegex(RuntimeError,'Another service operation'):
                self.lifecycle.run('public-prepare',self.public_path)
            operation.assert_not_called()


class CloudflarePublicSettingsTests(unittest.TestCase):
    def test_adapter_has_one_fixed_authority_and_preserves_single_binding_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            token=Path(temporary).resolve()/'token';token.write_text('synthetic-fixture-token');token.chmod(0o600)
            config={'account_id':'a'*32,'script_name':'app','api_token_file':str(token)}
            client=service.CloudflareWorkerSettings(config)
            response=mock.MagicMock();response.__enter__.return_value=response
            response.read.return_value=b'{"success":true,"result":{"accepted":true}}'
            opener=mock.Mock();opener.open.return_value=response
            with mock.patch.object(service,'public_opener',return_value=opener):
                self.assertEqual(client.request('/settings',{'bindings':[{'name':'UPSTREAM_ORIGIN',
                    'type':'plain_text','text':'https://candidate.trycloudflare.com'}]}),{'accepted':True})
            request=opener.open.call_args.args[0]
            self.assertEqual(request.full_url,'https://api.cloudflare.com/client/v4/accounts/'+'a'*32+'/workers/scripts/app/settings')
            self.assertEqual(request.method,'PATCH');self.assertEqual(request.get_header('Authorization'),'Bearer synthetic-fixture-token')
            self.assertIn(b'name="settings"',request.data);self.assertNotIn(b'synthetic-fixture-token',request.data)
            self.assertIsNone(service.NoRedirect().redirect_request(None,None,302,None,None,None))

    def test_settings_adapter_refuses_unknown_bindings_and_concurrent_deployment_changes(self):
        client=service.CloudflareWorkerSettings({'account_id':'a'*32,'script_name':'app'})
        for bindings in ([{'name':'UPSTREAM_ORIGIN','type':'secret_text'}],
                         [{'name':'UPSTREAM_ORIGIN','type':'plain_text','text':'old'},{'name':'OTHER','type':'plain_text','text':'keep'}]):
            with mock.patch.object(client,'request',side_effect=[{'deployments':[{'id':'old-version'}]},{'bindings':bindings}]):
                with self.assertRaisesRegex(RuntimeError,'single plain'):client.snapshot()
        with mock.patch.object(client,'snapshot',return_value={'deployment_id':'changed'}), \
                mock.patch.object(client,'request') as request:
            with self.assertRaisesRegex(RuntimeError,'changed before publication'):
                client.replace({'deployment_id':'previous'},'https://candidate.trycloudflare.com')
            request.assert_not_called()


class PublicProbeHeaderTests(unittest.TestCase):
    def test_probes_set_explicit_user_agent_and_preserve_host(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'application-fixture'
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(service, 'public_opener', return_value=opener):
            result = service.public_probe('http://127.0.0.1:31332', host='app.fixture.workers.dev')
        self.assertEqual(len(result), 2)
        for call in opener.open.call_args_list:
            request = call.args[0]
            self.assertEqual(request.get_header('User-agent'), 'Mozilla/5.0 GeneLoop-Service-Check')
            self.assertEqual(request.get_header('Host'), 'app.fixture.workers.dev')


class StartupListenerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = self.root / 'gateway.json'
        self.policy = self.root / 'policy.json'
        service.save(self.config, {'ownerPort': 31331, 'port': 31332})
        service.save(self.policy, {'output': str(self.root / 'tasks')})
        spec = {'argv': [sys.executable, 'fixture.py'], 'cwd': str(self.root),
                'env': {'SSS_WEB_POLICY': str(self.policy)}}
        self.plan = {'state_dir': str(self.root / 'service'), 'gateway_config': str(self.config),
                     'owner': spec, 'gateway': spec.copy()}
        self.lifecycle = service.Lifecycle(self.plan)
        self.child = mock.Mock(pid=12345)
        self.child.poll.return_value = None
        self.found = {'pid': self.child.pid, 'start_ticks': '42',
                      'argv_sha256': 'fixture', 'cwd': str(self.root)}

    def row(self, pid=None, port=31332):
        return ('LISTEN 0 128 127.0.0.1:%s 0.0.0.0:*' % port +
                (' users:(("fixture",pid=%s,fd=3))' % pid if pid else ''))

    def test_launch_waits_for_missing_or_duplicate_attribution(self):
        incomplete = self.row()
        ready = self.row(self.child.pid)
        for first in (incomplete, incomplete + '\n' + incomplete,
                      ready + '\n' + incomplete):
            with self.subTest(snapshot=first):
                directory = self.root / ('launch-' + str(len(self.lifecycle.started)))
                directory.mkdir()
                with mock.patch.object(service.subprocess, 'Popen', return_value=self.child), \
                        mock.patch.object(service.subprocess, 'check_output', side_effect=[first, ready]) as scan, \
                        mock.patch.object(service, 'identity', return_value=self.found), \
                        mock.patch.object(service.time, 'sleep') as sleep:
                    self.assertEqual(self.lifecycle.launch('gateway', self.plan, directory), self.found)
                self.assertEqual(scan.call_count, 2)
                sleep.assert_called_once_with(.1)

    def test_launch_immediately_refuses_any_explicit_foreign_pid(self):
        foreign = self.row(54321)
        ready = self.row(self.child.pid)
        snapshots = (foreign, self.row() + '\n' + foreign, ready + '\n' + foreign,
                     ready + ' users:(("foreign",pid=54321,fd=4))')
        for first in snapshots:
            with self.subTest(snapshot=first):
                directory = self.root / ('foreign-' + str(len(self.lifecycle.started)))
                directory.mkdir()
                with mock.patch.object(service.subprocess, 'Popen', return_value=self.child), \
                        mock.patch.object(service.subprocess, 'check_output', return_value=first) as scan, \
                        mock.patch.object(service, 'identity') as identify, \
                        mock.patch.object(service.time, 'sleep') as sleep:
                    with self.assertRaisesRegex(RuntimeError, 'Unexpected listener during startup'):
                        self.lifecycle.launch('gateway', self.plan, directory)
                self.assertEqual(scan.call_count, 1)
                identify.assert_not_called()
                sleep.assert_not_called()

    def test_persistent_unknown_times_out_without_publishing_and_cleans_only_child(self):
        with mock.patch.object(self.lifecycle, 'inspect', return_value={'owner': None, 'gateway': None}), \
                mock.patch.object(service.subprocess, 'Popen', return_value=self.child), \
                mock.patch.object(service.subprocess, 'check_output', return_value=self.row(port=31331)), \
                mock.patch.object(service.time, 'monotonic', side_effect=[0, 0, 61]), \
                mock.patch.object(service.time, 'sleep'), \
                mock.patch.object(self.lifecycle, 'health') as health, \
                mock.patch.object(self.lifecycle, 'publish_state') as publish:
            with self.assertRaisesRegex(RuntimeError, 'Service startup timed out'):
                self.lifecycle.start()
        self.child.terminate.assert_called_once_with()
        self.child.wait.assert_called_once_with(timeout=45)
        health.assert_not_called()
        publish.assert_not_called()
        self.assertIsNone(self.lifecycle.current())

    def test_global_listener_still_refuses_incomplete_or_duplicate_rows(self):
        for snapshot in (self.row(), self.row(self.child.pid) + '\n' + self.row()):
            with self.subTest(snapshot=snapshot), \
                    mock.patch.object(service.subprocess, 'check_output', return_value=snapshot):
                with self.assertRaisesRegex(RuntimeError, 'Cannot identify the local listener safely'):
                    service.listener(31332)


@unittest.skipUnless(sys.platform == 'linux' and shutil.which('ss'), 'Linux process/listener integration')
class LinuxLifecycleTests(PlanTests):
    def setUp(self):
        super().setUp()
        self.lifecycle = service.Lifecycle(self.plan)
        self.addCleanup(self.cleanup_processes)

    def cleanup_processes(self):
        # Explicit Popen handles belong only to this test, never arbitrary PIDs.
        for child in reversed(self.lifecycle.started):
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)

    def test_start_is_idempotent_and_authentication_is_required(self):
        first = self.lifecycle.run('start')
        old = self.lifecycle.current()['processes']
        second = self.lifecycle.run('start')
        self.assertFalse(first['already_running'])
        self.assertTrue(second['already_running'])
        self.assertEqual(old, self.lifecycle.current()['processes'])
        self.assertTrue(self.lifecycle.run('check')['owner_authenticated'])
        Path(service.read(self.config)['ownerTokenFile']).write_text('http://127.0.0.1:1/?token=invalid')
        with self.assertRaises(ValueError):
            self.lifecycle.run('check')

    def test_restart_rotates_token_preserves_data_and_can_rollback(self):
        original = self.output / 'user-file.txt'
        original.write_text('keep original bytes')
        self.lifecycle.run('start')
        before = self.lifecycle.current()['processes']
        token = Path(service.read(self.config)['ownerTokenFile']).read_text()
        self.lifecycle.run('restart')
        after = self.lifecycle.current()['processes']
        self.assertNotEqual(before['owner']['pid'], after['owner']['pid'])
        self.assertNotEqual(token, Path(service.read(self.config)['ownerTokenFile']).read_text())
        self.assertEqual(original.read_text(), 'keep original bytes')
        self.assertEqual(service.read(self.pointer)['budget'], {'requests': 19, 'spent': .25})
        self.assertEqual(service.read(self.pointer)['owner_pid'], after['owner']['pid'])
        self.lifecycle.run('rollback')
        self.assertTrue(self.lifecycle.run('check')['owner_authenticated'])
        self.assertTrue(self.lifecycle.run('start')['already_running'])

    def test_failed_gateway_start_rolls_back_to_healthy_previous_plan(self):
        self.lifecycle.run('start')
        failed = json.loads(json.dumps(self.plan))
        failed['gateway']['env']['FAIL_SERVICE'] = 'gateway'
        self.lifecycle.plan = failed
        with self.assertRaises(RuntimeError):
            self.lifecycle.run('restart')
        self.assertTrue(self.lifecycle.run('check')['owner_authenticated'])

    def test_active_task_refuses_restart_without_stopping_processes(self):
        self.lifecycle.run('start')
        before = self.lifecycle.current()['processes']
        task = self.output / 'tasks' / 'running'
        task.mkdir(parents=True)
        service.save(task / 'task-state.json', {'status': 'running'})
        with self.assertRaises(RuntimeError):
            self.lifecycle.run('restart')
        self.assertEqual(before, self.lifecycle.current()['processes'])
        self.assertTrue(all(service.identity(v['pid']) == v for v in before.values()))

    def test_lock_rejects_concurrent_operation(self):
        with self.lifecycle.lock():
            other = service.Lifecycle(self.plan)
            with self.assertRaises(RuntimeError):
                with other.lock():
                    self.fail('concurrent operation acquired the lock')

    def test_foreign_listener_is_not_adopted_or_stopped(self):
        config = service.read(self.config)
        with socket.socket() as foreign:
            foreign.bind(('127.0.0.1', config['ownerPort']))
            foreign.listen()
            with self.assertRaises(RuntimeError):
                self.lifecycle.run('start')
            self.assertGreater(foreign.fileno(), -1)

    def test_changed_process_generation_refuses_restart(self):
        self.lifecycle.run('start')
        before = self.lifecycle.current()
        corrupted = json.loads(json.dumps(before))
        corrupted['processes']['gateway']['start_ticks'] = 'not-the-current-process'
        service.save(self.lifecycle.state_path, corrupted)
        with self.assertRaises(RuntimeError):
            self.lifecycle.run('restart')
        self.assertTrue(all(service.identity(v['pid']) == v for v in before['processes'].values()))

    def test_in_place_managed_config_change_refuses_restart(self):
        self.lifecycle.run('start')
        before = self.lifecycle.current()
        config = Path(before['plan']['gateway_config'])
        service.save(config, {**service.read(config), 'changed_in_place': True})
        with self.assertRaises(RuntimeError):
            self.lifecycle.run('restart')
        self.assertTrue(all(service.identity(v['pid']) == v for v in before['processes'].values()))


if __name__ == '__main__':
    unittest.main()
