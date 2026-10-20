"""One Linux lifecycle entry for the prepared GeneLoop owner and account gateway.

Release preparation remains separate: supply a private JSON launch plan, never
modify live files in place. This tool owns process identity, auth, receipts and
rollback. It never starts/stops the shared model budget or changes user data.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from uuid import uuid4
import urllib.error
import urllib.request

from harless_owner_access import sync_owner_access, verify_access


TERMINAL = {'completed', 'failed', 'cancelled', 'budget_exhausted', 'awaiting_confirmation'}
FILE_TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as output:
            temporary.chmod(0o600)
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write('\n')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def private_file(path):
    path = Path(path)
    if path.is_symlink() or not path.is_absolute() or not path.is_file():
        raise RuntimeError('Private launch/configuration file must be an absolute regular file')
    if os.name == 'posix' and path.stat().st_mode & 0o077:
        raise RuntimeError('Private launch/configuration files require mode 600')
    return path


def load_plan(path):
    plan = read(private_file(path))
    if plan.get('version') != 1:
        raise RuntimeError('Unsupported service plan version')
    if plan.get('source_sha') and not re.fullmatch('[0-9a-f]{40}', plan['source_sha']):
        raise RuntimeError('Invalid release source SHA')
    if plan.get('runtime_pointer'):
        private_file(plan['runtime_pointer'])
    state = Path(plan['state_dir'])
    if not state.is_absolute() or state.is_symlink():
        raise RuntimeError('Invalid service state directory')
    config = read(private_file(plan['gateway_config']))
    for role in ('owner', 'gateway'):
        spec = plan[role]
        if (not isinstance(spec.get('argv'), list) or not spec['argv'] or
                not all(isinstance(v, str) and v and '\0' not in v for v in spec['argv']) or
                not Path(spec['argv'][0]).is_absolute() or not Path(spec['argv'][0]).is_file() or
                not Path(spec['cwd']).is_absolute() or not Path(spec['cwd']).is_dir() or
                not isinstance(spec.get('env'), dict) or
                not all(isinstance(k, str) and isinstance(v, str) for k, v in spec['env'].items())):
            raise RuntimeError('Invalid explicit process launch specification')
    if plan['gateway_config'] not in plan['gateway']['argv']:
        raise RuntimeError('Gateway command must use the declared configuration')
    for field in ('ownerPort', 'port'):
        if type(config.get(field)) is not int or not 1 <= config[field] <= 65535:
            raise RuntimeError('Invalid service port')
    if config['ownerPort'] == config['port']:
        raise RuntimeError('Owner and gateway ports must differ')
    policy = read(private_file(plan['owner']['env']['SSS_WEB_POLICY']))
    if Path(policy['output']).resolve() != Path(plan['owner_output']).resolve():
        raise RuntimeError('Owner output differs from the preserved launch plan')
    if not Path(plan['owner_output']).is_absolute():
        raise RuntimeError('Owner output must be absolute')
    return plan


def plan_digest(plan):
    """Copied launch files keep the same intent; changed contents never do."""
    value = json.loads(json.dumps(plan))
    files = [plan['gateway_config'], plan['owner']['env']['SSS_WEB_POLICY']]
    argv = plan['owner']['argv']
    if '--patch' in argv:
        files.append(argv[argv.index('--patch') + 1])
    mapping = {p: 'sha256:' + hashlib.sha256(private_file(p).read_bytes()).hexdigest() for p in files}
    value['gateway_config'] = mapping[value['gateway_config']]
    for role in ('owner', 'gateway'):
        value[role]['argv'] = [mapping.get(v, v) for v in value[role]['argv']]
    value['owner']['env']['SSS_WEB_POLICY'] = mapping[value['owner']['env']['SSS_WEB_POLICY']]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def identity(pid):
    proc = Path('/proc') / str(pid)
    try:
        stat = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] == 'Z':
            return None
        return {'pid': pid, 'start_ticks': stat[19],
                'argv_sha256': hashlib.sha256((proc / 'cmdline').read_bytes()).hexdigest(),
                'cwd': os.readlink(proc / 'cwd')}
    except (FileNotFoundError, ProcessLookupError):
        return None


def command_matches(pid, spec):
    proc = Path('/proc') / str(pid)
    command = b'\0'.join(os.fsencode(v) for v in spec['argv']) + b'\0'
    environment = dict(os.fsdecode(v).split('=', 1) for v in (proc / 'environ').read_bytes().split(b'\0') if b'=' in v)
    return ((proc / 'cmdline').read_bytes() == command and
            Path(os.readlink(proc / 'cwd')).resolve() == Path(spec['cwd']).resolve() and
            all(environment.get(k) == v for k, v in spec['env'].items()))


def listener_rows(port):
    return [row for row in subprocess.check_output(['ss', '-lntp'], text=True).splitlines()
            if re.search(r'127\.0\.0\.1:' + str(port) + r'\s', row)]


def listener(port):
    rows = listener_rows(port)
    if not rows:
        return None
    matches = [re.search(r'pid=(\d+)', row) for row in rows]
    if len(rows) != 1 or not matches[0]:
        raise RuntimeError('Cannot identify the local listener safely')
    return int(matches[0].group(1))


def starting_listener(port, child_pid):
    """Only a known child may wait for a complete ss process/socket snapshot."""
    rows = listener_rows(port)
    pids = {int(pid) for row in rows for pid in re.findall(r'pid=(\d+)', row)}
    if pids - {child_pid}:
        raise RuntimeError('Unexpected listener during startup; no foreign process will be stopped')
    # ss gathers sockets and process ownership separately. Missing attribution or
    # duplicate rows are not readiness; launch's existing deadline bounds retries.
    return child_pid if len(rows) == 1 and pids == {child_pid} else None


def file_worker_running(pid, home, namespace_home=None, proc_root=Path('/proc')):
    """Read-only identity check; member lock PIDs belong to their bwrap namespace.

    A reused PID running another command is not the old learner. Inaccessible
    process facts are unknown, never permission to interrupt or remove a lock.
    """
    if type(pid) is not int or pid <= 0:
        raise RuntimeError('Unknown File background worker identity; restart refused')
    home = Path(home)
    try:
        processes = [proc_root / str(pid)] if namespace_home is None else list(proc_root.iterdir())
        for process in processes:
            if not process.name.isdecimal():
                continue
            try:
                status = (process / 'status').read_text(encoding='utf-8')
                if re.search(r'^State:\s+Z\b', status, re.M):
                    continue
                if namespace_home is not None:
                    match = re.search(r'^NSpid:\s+([0-9\s]+)$', status, re.M)
                    if not match:
                        raise RuntimeError('Unknown File worker PID namespace; restart refused')
                    if int(match.group(1).split()[-1]) != pid:
                        continue
                    mounted = process / 'root' / Path(namespace_home).relative_to('/')
                    if not mounted.samefile(home):
                        continue
                argv = [os.fsdecode(value) for value in (process / 'cmdline').read_bytes().split(b'\0') if value]
                if not argv:
                    raise RuntimeError('Unknown File background worker process; restart refused')
                if not any(Path(value).name == 'rsi-worker.py' for value in argv):
                    continue  # The recorded PID has been reused by another program.
                if '--config' not in argv:
                    raise RuntimeError('Unknown File background worker configuration; restart refused')
                position = argv.index('--config') + 1
                if position >= len(argv):
                    raise RuntimeError('Unknown File background worker configuration; restart refused')
                config = Path(argv[position])
                account = Path(namespace_home) if namespace_home is not None else home
                if config.is_absolute() and config.is_relative_to(account / 'rsi'):
                    return True
            except (FileNotFoundError, ProcessLookupError):
                continue
    except (OSError, ValueError, TypeError) as error:
        raise RuntimeError('Unknown File background worker process; restart refused') from error
    return False


def assert_idle(plan):
    config = read(plan['gateway_config'])
    outputs = [Path(plan['owner_output'])]
    members = Path(config['membersDir'])
    if members.exists():
        outputs += [p / 'tasks' for p in members.iterdir() if p.is_dir()]
    # File's SDK has its own durable state, outside ordinary tasks/comparisons.
    # Members persist under their output bind. The established owner home is
    # rooted in the RUNNING gateway checkout, not the candidate release/output.
    file_roots = [(outputs[0] / 'file-management', None)] + [
        (output / 'file-management', output.parent / 'config' / 'policy.json') for output in outputs[1:]]
    if config.get('sourceDir') is not None:
        source = Path(config['sourceDir'])
        if not source.is_absolute() or source.is_symlink() or source.name != 'src' or not source.is_dir():
            raise RuntimeError('Unknown owner File source root; restart refused')
        root = source.resolve().parent
        gateway = root / 'scripts' / 'harless_gateway.mjs'
        argv = plan.get('gateway', {}).get('argv', [])
        if (not gateway.is_file() or gateway.is_symlink() or
                Path(plan.get('gateway', {}).get('cwd', '')).resolve() != root or
                not any(isinstance(value, str) and Path(value).is_absolute() and
                        Path(value).resolve() == gateway for value in argv)):
            raise RuntimeError('Owner File source root differs from running gateway; restart refused')
        file_roots.append((root / '.local' / 'web' / 'file-management', None))
    for directory, member_policy in file_roots:
        workers = set()

        def remember_worker(pid, home):
            namespace_home = None
            if member_policy is not None:
                try:
                    output = Path(read(member_policy)['output'])
                    if not output.is_absolute():
                        raise ValueError('Member output is not absolute')
                    namespace_home = output / 'file-management' / home.relative_to(directory)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    raise RuntimeError('Unknown File background worker scope; restart refused') from error
            if type(pid) is not int or pid <= 0:
                raise RuntimeError('Unknown File background worker identity; restart refused')
            workers.add((pid, home, namespace_home))

        for path in directory.glob('accounts/*/tasks/*/state.json'):
            try:
                if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(directory.resolve()):
                    raise ValueError('Invalid File state path')
                state = read(path)
                if not isinstance(state, dict):
                    raise ValueError('Invalid File state object')
            except (OSError, ValueError, TypeError) as error:
                raise RuntimeError('Unknown File task state; restart refused') from error
            if not isinstance(state.get('status'), str) or state['status'] not in FILE_TERMINAL:
                raise RuntimeError('Active or unknown File task exists; restart refused')
            metrics = state.get('metrics')
            if metrics is not None and not isinstance(metrics, dict):
                raise RuntimeError('Unknown File background worker receipt; restart refused')
            learning = (metrics or {}).get('continuous_rsi')
            if learning is not None and not isinstance(learning, dict):
                raise RuntimeError('Unknown File background worker receipt; restart refused')
            worker = (learning or {}).get('worker')
            if worker is not None:
                if not isinstance(worker, dict):
                    raise RuntimeError('Unknown File background worker receipt; restart refused')
                remember_worker(worker.get('pid'), path.parents[2])
        for path in directory.glob('accounts/*/rsi/*/worker.lock'):
            try:
                if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(directory.resolve()):
                    raise ValueError('Invalid File worker lock path')
                lock = read(path)
                if not isinstance(lock, dict):
                    raise ValueError('Invalid File worker lock object')
            except FileNotFoundError:
                continue  # The learner released its own lock during this read.
            except (OSError, ValueError, TypeError) as error:
                raise RuntimeError('Unknown File background worker lock; restart refused') from error
            remember_worker(lock.get('pid'), path.parents[2])
        for pid, home, namespace_home in workers:
            if file_worker_running(pid, home, namespace_home):
                raise RuntimeError('Active File background learning worker exists; restart refused')
    for output in outputs:
        for path in output.glob('tasks/*/task-state.json'):
            if read(path).get('status') not in TERMINAL:
                raise RuntimeError('Active or unknown task exists; restart refused')
        path = output / 'comparisons.json'
        if path.exists():
            turns = read(path).get('turns')
            if not isinstance(turns, list):
                raise RuntimeError('Unknown comparison state; restart refused')
            for turn in turns:
                if (turn.get('status') not in {'completed', 'failed', 'cancelled'} or
                        any(v.get('status') not in {'completed', 'failed', 'cancelled'}
                            for v in turn.get('lanes', {}).values())):
                    raise RuntimeError('Active comparison exists; restart refused')


def same_data(old, new):
    a, b = read(old['gateway_config']), read(new['gateway_config'])
    # Release switching cannot silently move accounts, sessions, or budget routes.
    for key in ('dataDir', 'membersDir', 'ownerTokenFile', 'port', 'ownerPort',
                'scopedBudgetPort', 'upstreamBrokerPort', 'upstreamControlPort'):
        if a.get(key) != b.get(key):
            raise RuntimeError('Persistent data/port change requires a separate reviewed migration')
    if old['owner_output'] != new['owner_output'] or old['owner']['env'].get('DSH_HOME') != new['owner']['env'].get('DSH_HOME'):
        raise RuntimeError('Owner persistent storage cannot change during restart')


class Lifecycle:
    def __init__(self, plan):
        self.plan = plan
        self.root = Path(plan['state_dir'])
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == 'posix' and self.root.stat().st_mode & 0o077:
            raise RuntimeError('Service state directory requires mode 700')
        self.state_path = self.root / 'current.json'
        self.previous_path = self.root / 'previous.json'
        self.started = []

    @contextmanager
    def lock(self):
        import fcntl
        with (self.root / 'lifecycle.lock').open('a') as lock:
            os.chmod(lock.name, 0o600)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Another service operation is running') from None
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def current(self):
        return read(self.state_path) if self.state_path.exists() else None

    def inspect(self, plan, record=None, reuse=None):
        config = read(plan['gateway_config'])
        result = {}
        for role, port in [('owner', config['ownerPort']), ('gateway', config['port'])]:
            pid = listener(port)
            if pid is None:
                result[role] = None
                continue
            found = identity(pid)
            reused = (reuse and plan_digest(plan) == reuse['digest'] and
                      found == reuse['processes'].get(role))
            if not found or (not reused and not command_matches(pid, plan[role])):
                raise RuntimeError('Unexpected listener; no process will be stopped or replaced')
            if record and record['processes'].get(role) != found:
                raise RuntimeError('Process generation changed; explicit adoption required')
            result[role] = found
        return result

    def health(self, plan):
        config = read(plan['gateway_config'])
        verify_access(Path(config['ownerTokenFile']).read_text(encoding='utf-8').strip(), config['ownerPort'])
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:%s/login' % config['port'], timeout=10) as response:
            if response.status != 200:
                raise RuntimeError('Gateway login page unavailable')
        return {'owner_authenticated': True, 'gateway_login_status': 200, 'model_requests': 0}

    def snapshot(self, plan, directory):
        """Freeze private launch files so a future prepared plan cannot overwrite rollback."""
        frozen = json.loads(json.dumps(plan))
        owner = frozen['owner']
        paths = {plan['gateway_config']: 'gateway.json',
                 owner['env']['SSS_WEB_POLICY']: 'owner-policy.json'}
        if '--patch' in owner['argv']:
            paths[owner['argv'][owner['argv'].index('--patch') + 1]] = 'owner.patch.yml'
        mapping = {}
        for source, name in paths.items():
            target = directory / name
            target.write_bytes(private_file(source).read_bytes())
            target.chmod(0o600)
            mapping[source] = str(target)
        for role in ('owner', 'gateway'):
            frozen[role]['argv'] = [mapping.get(v, v) for v in frozen[role]['argv']]
        owner['env']['SSS_WEB_POLICY'] = mapping[owner['env']['SSS_WEB_POLICY']]
        frozen['gateway_config'] = mapping[plan['gateway_config']]
        save(directory / 'plan.json', frozen)
        return frozen

    def receipt(self, event, **values):
        path = self.root / ('receipt-' + uuid4().hex + '.json')
        save(path, {'event': event, 'at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **values})
        return str(path)

    def publish_state(self, record):
        save(self.state_path, record)
        pointer = record['plan'].get('runtime_pointer')
        if pointer:
            # Preserve every existing budget/account/experiment receipt field.
            runtime = read(private_file(pointer))
            if not isinstance(runtime, dict) or not all(k in runtime for k in ('owner_pid', 'gateway_pid')):
                raise RuntimeError('Runtime pointer is not an existing service process record')
            runtime.update(owner_pid=record['processes']['owner']['pid'],
                           gateway_pid=record['processes']['gateway']['pid'],
                           service_lifecycle={'state_dir': str(self.root), 'config_digest': record['digest']})
            source = record['plan'].get('source_sha')
            if source:
                runtime.update(source_sha=source, runtime_code_sha=source)
            save(pointer, runtime)

    def launch(self, role, plan, directory):
        config = read(plan['gateway_config'])
        port = config['ownerPort'] if role == 'owner' else config['port']
        spec = plan[role]
        log_path = directory / (role + '.log')
        with log_path.open('xb') as log:
            log_path.chmod(0o600)
            child = subprocess.Popen(spec['argv'], cwd=spec['cwd'], env=spec['env'], stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.started.append(child)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError('Service exited during startup; inspect private log')
            if starting_listener(port, child.pid) == child.pid:
                if role == 'owner':
                    if 'dsh web: ' not in log_path.read_text(encoding='utf-8', errors='replace'):
                        time.sleep(.1)
                        continue
                    sync_owner_access(plan['gateway_config'], log_path)
                return identity(child.pid)
            time.sleep(.1)
        raise RuntimeError('Service startup timed out')

    def stop_record(self, record):
        for role in ('gateway', 'owner'):
            expected = record['processes'].get(role)
            if not expected:
                continue
            found = identity(expected['pid'])
            if found is None:
                continue
            if found != expected:
                raise RuntimeError('Refusing to stop a reused or changed process')
            os.kill(expected['pid'], signal.SIGTERM)
            deadline = time.monotonic() + 45
            while identity(expected['pid']) is not None:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Graceful stop timed out; no force kill was issued')
                time.sleep(.1)
            if role == 'gateway':
                assert_idle(record['plan'])

    def start(self, plan=None, reuse=None):
        plan = plan or self.plan
        processes = self.inspect(plan, reuse=reuse)
        if all(processes.values()):
            result = self.health(plan)
            if not self.current():
                directory = self.root / ('adopt-' + uuid4().hex)
                directory.mkdir(mode=0o700)
                self.snapshot(plan, directory)
                self.publish_state({'plan': plan, 'digest': plan_digest(plan),
                                    'rollback_plan': str(directory / 'plan.json'), 'processes': processes})
            return {'already_running': True, **result}
        directory = self.root / ('start-' + uuid4().hex)
        directory.mkdir(mode=0o700)
        frozen = self.snapshot(plan, directory)
        old_count = len(self.started)
        try:
            # A partial start may keep an already healthy owner/gateway. Its
            # actual launch spec remains in the state for exact identity checks.
            actual = json.loads(json.dumps(frozen))
            for role in ('owner', 'gateway'):
                if processes[role]:
                    actual[role] = reuse['plan'][role] if reuse else plan[role]
                else:
                    processes[role] = self.launch(role, frozen, directory)
            result = self.health(frozen)
            if processes['gateway'] and reuse and actual['gateway'] == reuse['plan']['gateway']:
                actual['gateway_config'] = reuse['plan']['gateway_config']
            elif actual['gateway'] == plan['gateway']:
                actual['gateway_config'] = plan['gateway_config']
            self.publish_state({'plan': actual, 'digest': plan_digest(actual),
                                'rollback_plan': str(directory / 'plan.json'), 'processes': processes})
            return {'already_running': False, **result}
        except BaseException:
            # Only children started by this attempt are eligible for cleanup.
            for child in reversed(self.started[old_count:]):
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=45)
            raise

    def restart(self, target=None):
        old = self.current()
        if not old:
            raise RuntimeError('Run start to validate/adopt the current deployment before restart')
        if plan_digest(old['plan']) != old['digest']:
            raise RuntimeError('Managed configuration changed in place; use a separate prepared plan')
        target = target or self.plan
        self.inspect(old['plan'], old)
        same_data(old['plan'], target)
        assert_idle(old['plan'])
        if not all(old['processes'].values()):
            raise RuntimeError('Incomplete deployment; use start for recovery')
        try:
            self.stop_record(old)
            result = self.start(target)
            save(self.previous_path, {'plan': old['rollback_plan']})
            return result
        except BaseException as failure:
            # Restore the previous prepared launch files, using the same start
            # path and fresh token check. Never restore passwords/user files.
            try:
                rollback = load_plan(old['rollback_plan'])
                result = self.start(rollback, reuse=old)
                self.receipt('rollback_after_failure', healthy=True, **result)
            except BaseException:
                self.receipt('rollback_after_failure', healthy=False)
            raise failure

    def run(self, action):
        with self.lock():
            if action in ('status', 'check'):
                record = self.current()
                plan = record['plan'] if record else self.plan
                if record and plan_digest(plan) != record['digest']:
                    raise RuntimeError('Managed configuration changed in place')
                processes = self.inspect(plan, record)
                result = {'running': {k: bool(v) for k, v in processes.items()},
                          'pids': {k: v['pid'] if v else None for k, v in processes.items()}}
                if action == 'check':
                    if not all(processes.values()):
                        raise RuntimeError('Service is not fully running')
                    result.update(self.health(plan))
                return result
            if action == 'start':
                record = self.current()
                if record:
                    if plan_digest(record['plan']) != record['digest']:
                        raise RuntimeError('Managed configuration changed in place')
                    if plan_digest(self.plan) != record['digest']:
                        raise RuntimeError('A different release is running; use restart with the prepared plan')
                    self.inspect(record['plan'], record)
                result = self.start(record['plan'] if record else self.plan)
            elif action == 'restart':
                result = self.restart()
            elif action == 'rollback':
                if not self.previous_path.exists():
                    raise RuntimeError('No previous managed release is available')
                result = self.restart(load_plan(read(self.previous_path)['plan']))
            else:
                raise RuntimeError('Unsupported lifecycle operation')
            result['receipt'] = self.receipt(action, **result)
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'restart', 'status', 'check', 'rollback'])
    parser.add_argument('--config', default=os.environ.get('GENELOOP_SERVICE_CONFIG'))
    args = parser.parse_args()
    if not args.config:
        parser.error('Set GENELOOP_SERVICE_CONFIG or provide --config PRIVATE-SERVICE-PLAN.json')
    try:
        if sys.platform != 'linux':
            raise RuntimeError('Hosted service lifecycle requires Linux; local development uses npm run web')
        print(json.dumps(Lifecycle(load_plan(args.config)).run(args.action), ensure_ascii=False))
    except Exception as error:
        # Process argv/env and HTTP exception URLs may contain credentials.
        print(json.dumps({'ok': False, 'error_type': type(error).__name__,
                          'message': str(error) if isinstance(error, RuntimeError) else 'Invalid configuration or service operation failed'}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
