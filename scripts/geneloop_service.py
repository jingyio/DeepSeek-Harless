"""One Linux lifecycle entry for the prepared GeneLoop owner and account gateway.

Release preparation remains separate: supply a private JSON launch plan, never
modify live files in place. This tool owns process identity, auth, receipts and
rollback. It never starts/stops the shared model budget or changes user data.
"""
import argparse
import ctypes
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
from urllib.parse import urlparse

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


def assert_watch_capacity(plan):
    """Probe before stopping a healthy owner when native watchers are enabled."""
    if sys.platform != 'linux' or plan['owner']['env'].get('CHOKIDAR_USEPOLLING','').lower() in {'1','true'}:
        return
    libc=ctypes.CDLL(None,use_errno=True)
    libc.inotify_init1.argtypes=[ctypes.c_int]
    libc.inotify_init1.restype=ctypes.c_int
    libc.inotify_add_watch.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32]
    libc.inotify_add_watch.restype=ctypes.c_int
    descriptor=libc.inotify_init1(os.O_CLOEXEC)
    if descriptor < 0:
        raise RuntimeError('Native file watcher unavailable; prepare a polling launch plan before publishing')
    try:
        path=os.fsencode(plan['owner']['env']['SSS_WEB_POLICY'])
        if libc.inotify_add_watch(descriptor,path,2|4) < 0:
            raise RuntimeError('Native file watcher capacity exhausted; prepare a polling launch plan before publishing')
    finally:
        os.close(descriptor)


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


def linux_kernel_thread(process, status):
    """Prove an empty Linux cmdline is a kernel task, never infer from its name.

    Older kernels omit status.Kthread. /proc/pid/stat field 9 exposes the
    kernel-owned PF_KTHREAD flag; comm may contain spaces and parentheses.
    Missing facts remain unknown rather than permission to restart.
    """
    if sys.platform != 'linux':
        return False
    if re.search(r'^Kthread:\s+1\s*$', status, re.M):
        return True
    try:
        raw = (process / 'stat').read_text(encoding='utf-8')
    except FileNotFoundError:
        return False
    opening, closing = raw.find('('), raw.rfind(')')
    fields = raw[closing + 1:].split()
    if (opening <= 0 or closing <= opening or raw[:opening].strip() != process.name or
            len(fields) < 7 or len(fields[0]) != 1 or not fields[6].isdecimal()):
        raise ValueError('Invalid File worker process stat')
    return bool(int(fields[6]) & 0x00200000)


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
                argv = [os.fsdecode(value) for value in (process / 'cmdline').read_bytes().split(b'\0') if value]
                if not argv:
                    if linux_kernel_thread(process, status):
                        continue  # An unrelated kernel thread can share this namespace-local PID.
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
                if not config.is_absolute() or not config.is_relative_to(account / 'rsi'):
                    continue
                # A namespace-local PID can also name an unrelated host process.
                # Inspect its mount only after the command and account match;
                # inaccessible facts for an actual candidate still fail closed.
                if namespace_home is not None:
                    mounted = process / 'root' / Path(namespace_home).relative_to('/')
                    if not mounted.samefile(home):
                        continue
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


def json_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def load_public_config(path, plan):
    """A separate, immutable recovery recipe; never part of the backend plan."""
    value = read(private_file(path))
    if (set(value) - {'version','public_origin','previous_origin','previous_process','tunnel','cloudflare','https_proxy'} or
            value.get('version') != 1 or
            not re.fullmatch(r'https://[a-z0-9-]+\.[a-z0-9-]+\.workers\.dev', value.get('public_origin', '')) or
            not re.fullmatch(r'https://[a-z0-9-]+\.trycloudflare\.com', value.get('previous_origin', ''))):
        raise RuntimeError('Invalid prepared public recovery configuration')
    gateway = read(plan['gateway_config'])
    if gateway.get('publicOrigin') != value['public_origin']:
        raise RuntimeError('Public origin differs from the managed gateway')
    tunnel = value.get('tunnel', {})
    expected = ['tunnel','--no-autoupdate','--protocol','http2','--url',
                'http://127.0.0.1:%s' % gateway['port'],'--http-host-header',urlparse(value['public_origin']).hostname]
    argv = tunnel.get('argv', [])
    if (set(tunnel) != {'argv','cwd','env','binary_sha256'} or not isinstance(argv, list) or
            len(argv) != len(expected)+1 or argv[1:] != expected or
            not Path(argv[0]).is_absolute() or not Path(argv[0]).is_file() or
            hashlib.sha256(Path(argv[0]).read_bytes()).hexdigest() != tunnel['binary_sha256'] or
            not Path(tunnel['cwd']).is_absolute() or not Path(tunnel['cwd']).is_dir() or
            not isinstance(tunnel['env'], dict) or
            not all(isinstance(k,str) and isinstance(v,str) and '\0' not in k+v for k,v in tunnel['env'].items())):
        raise RuntimeError('Public recovery requires the exact verified cloudflared launch recipe')
    previous = value.get('previous_process', {})
    if (set(previous) != {'pid','start_ticks','argv_sha256','cwd'} or type(previous['pid']) is not int or previous['pid'] <= 0 or
            not isinstance(previous['start_ticks'],str) or not previous['start_ticks'].isdigit() or
            previous['cwd'] != tunnel['cwd'] or
            previous['argv_sha256'] != hashlib.sha256(b'\0'.join(os.fsencode(v) for v in argv)+b'\0').hexdigest()):
        raise RuntimeError('Missing exact previous tunnel identity')
    cloudflare = value.get('cloudflare')
    if cloudflare is not None and (set(cloudflare) != {'account_id','script_name','api_token_file','expected_deployment_id','expected_settings_sha256'} or
            not re.fullmatch('[a-f0-9]{32}',cloudflare.get('account_id','')) or
            not re.fullmatch('[a-z0-9-]+',cloudflare.get('script_name','')) or
            cloudflare['script_name'] != urlparse(value['public_origin']).hostname.split('.')[0] or
            not re.fullmatch('[a-zA-Z0-9-]+',cloudflare.get('expected_deployment_id','')) or
            not re.fullmatch('[a-f0-9]{64}',cloudflare.get('expected_settings_sha256',''))):
        raise RuntimeError('Invalid scoped Cloudflare settings authority')
    if cloudflare is not None:private_file(cloudflare['api_token_file'])
    proxy = value.get('https_proxy')
    if proxy is not None and not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}',proxy):
        raise RuntimeError('Public diagnostics require an explicit local CONNECT proxy')
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def public_opener(proxy=None):
    return urllib.request.build_opener(urllib.request.ProxyHandler({'https':proxy} if proxy else {}), NoRedirect())


def public_probe(origin, proxy=None, host=None):
    result = {}
    for path in ('/login','/assets/geneloop-spiral.svg'):
        headers = {'User-Agent': 'Mozilla/5.0 GeneLoop-Service-Check'}
        if host:
            headers['Host'] = host
        request = urllib.request.Request(origin+path, headers=headers)
        try:
            with public_opener(proxy).open(request, timeout=10) as response:
                body = response.read()
                result[path] = {'status':response.status,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)}
        except urllib.error.HTTPError as error:
            body=error.read()
            result[path]={'status':error.code,'sha256':hashlib.sha256(body).hexdigest(),
                          'bytes':len(body),'error_body':body[:4096].decode('utf-8',errors='replace')}
        except (OSError,urllib.error.URLError) as error:
            result[path]={'status':None,'error_type':type(error).__name__}
    return result


def probe_matches(actual, expected):
    return all(actual.get(path,{}).get('status') == expected.get(path,{}).get('status') == 200 and
               actual[path].get('sha256') == expected[path].get('sha256') for path in ('/login','/assets/geneloop-spiral.svg'))


class CloudflareWorkerSettings:
    """Only the existing Worker's settings; never arbitrary code upload/shell."""
    def __init__(self, config, proxy=None):
        self.config, self.proxy = config, proxy
        self.base = ('https://api.cloudflare.com/client/v4/accounts/'+config['account_id']+
                     '/workers/scripts/'+config['script_name'])

    def request(self, path, settings=None):
        token=private_file(self.config['api_token_file']).read_text(encoding='utf-8').strip()
        if not token or any(c.isspace() for c in token):raise RuntimeError('Invalid private Cloudflare API token file')
        headers={'Authorization':'Bearer '+token};body=None
        if settings is not None:
            boundary='geneloop-'+uuid4().hex
            body=('--'+boundary+'\r\nContent-Disposition: form-data; name="settings"\r\n'+
                  'Content-Type: application/json\r\n\r\n'+json.dumps(settings)+'\r\n--'+boundary+'--\r\n').encode()
            headers['Content-Type']='multipart/form-data; boundary='+boundary
        request=urllib.request.Request(self.base+path,data=body,headers=headers,method='PATCH' if settings is not None else 'GET')
        try:
            with public_opener(self.proxy).open(request,timeout=20) as response:value=json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise RuntimeError('Cloudflare scoped settings request failed (HTTP %s)' % error.code) from None
        if value.get('success') is not True or 'result' not in value:raise RuntimeError('Cloudflare returned no verified result')
        return value['result']

    def snapshot(self):
        deployments=self.request('/deployments');settings=self.request('/settings')
        rows=deployments.get('deployments',[]) if isinstance(deployments,dict) else []
        if not rows or not isinstance(rows[0].get('id'),str):raise RuntimeError('Unknown current Cloudflare deployment')
        bindings=settings.get('bindings') if isinstance(settings,dict) else None
        if (not isinstance(bindings,list) or len(bindings)!=1 or set(bindings[0])!={'name','type','text'} or
                bindings[0]['name']!='UPSTREAM_ORIGIN' or bindings[0]['type']!='plain_text' or
                not isinstance(bindings[0]['text'],str)):
            raise RuntimeError('Recovery supports only the verified single plain upstream binding')
        return {'deployment_id':rows[0]['id'],'deployments':deployments,'settings':settings,
                'upstream_origin':bindings[0]['text']}

    def replace(self, before, origin):
        if self.snapshot()!=before:raise RuntimeError('Cloudflare deployment changed before publication')
        settings={'bindings':[{'name':'UPSTREAM_ORIGIN','type':'plain_text','text':origin}]}
        if isinstance(before['settings'].get('annotations'),dict):
            settings['annotations']={k:v for k,v in before['settings']['annotations'].items() if k!='workers/triggered_by'}
        return self.request('/settings',settings)


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
        if not processes['owner']:
            assert_watch_capacity(plan)
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
        assert_watch_capacity(target)
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

    def public_confirm(self, config, path, record, processes, expected, route_evidence):
        pending=read(private_file(self.root/'public-pending.json'))
        attempt_path=private_file(pending['attempt'])
        if attempt_path.parent.parent!=self.root or not attempt_path.parent.name.startswith('public-recover-') or attempt_path.name!='attempt.json':
            raise RuntimeError('Unknown public recovery attempt location')
        attempt=read(attempt_path);digest=hashlib.sha256(private_file(path).read_bytes()).hexdigest()
        if (attempt.get('config_sha256')!=digest or attempt.get('backend_processes')!=processes or
                attempt.get('backend_digest')!=record['digest'] or attempt.get('stage')!='awaiting_route_update'):
            raise RuntimeError('Prepared public recovery or backend generation changed')
        candidate=attempt['candidate_process'];origin=attempt['candidate_origin']
        if identity(candidate['pid'])!=candidate or not command_matches(candidate['pid'],config['tunnel']):
            raise RuntimeError('Prepared candidate tunnel identity changed')
        if config.get('cloudflare'):
            after=CloudflareWorkerSettings(config['cloudflare'],config.get('https_proxy')).snapshot()
            if after['upstream_origin']!=origin:raise RuntimeError('Cloudflare readback differs from the candidate')
            save(attempt_path.parent/'cloudflare-after.json',after);confirmation={'method':'cloudflare-api-readback'}
        else:
            if not route_evidence:raise RuntimeError('Provide private --route-evidence from the authorized dashboard readback')
            evidence_path=private_file(route_evidence);evidence=read(evidence_path)
            wanted={'version':1,'method':'cloudflare-dashboard','public_origin':config['public_origin'],
                    'worker_name':urlparse(config['public_origin']).hostname.split('.')[0],
                    'binding_name':'UPSTREAM_ORIGIN','binding_type':'plain_text','upstream_origin':origin,
                    'worker_code_unchanged':True,'other_bindings_unchanged':True}
            if any(evidence.get(k)!=v for k,v in wanted.items()):raise RuntimeError('Dashboard evidence does not bind this exact upstream change')
            save(attempt_path.parent/'manual-route-evidence.json',evidence)
            confirmation={'method':'manual-dashboard-attestation','evidence_sha256':hashlib.sha256(evidence_path.read_bytes()).hexdigest()}
        observed=public_probe(config['public_origin'],config.get('https_proxy'))
        if not probe_matches(observed,expected):
            save(attempt_path.parent/'public-confirm-failure.json',{'probe':observed,'confirmation':confirmation})
            raise RuntimeError('Public login and logo do not match the running application')
        if identity(candidate['pid'])!=candidate or self.inspect(record['plan'],record)!=processes:
            raise RuntimeError('Managed generation changed during confirmation')
        attempt.update(stage='ready',public_probe=observed,confirmation=confirmation,old_tunnel_preserved=True,backend_unchanged=True)
        save(attempt_path,attempt);save(self.root/'public-current.json',{
            'config_sha256':digest,'public_origin':config['public_origin'],'upstream_origin':origin,
            'process':candidate,'attempt':str(attempt_path),'confirmation':confirmation})
        return {'public_healthy':True,'backend_unchanged':True,'old_tunnel_preserved':True,'model_requests':0,
                'receipt':self.receipt('public-confirm',healthy=True,attempt=str(attempt_path),confirmation=confirmation)}

    def public_operation(self, action, path, route_evidence=None):
        record=self.current()
        if not record or plan_digest(record['plan'])!=record['digest']:
            raise RuntimeError('Public recovery requires an unchanged managed backend')
        plan=record['plan'];processes=self.inspect(plan,record)
        if not all(processes.values()):raise RuntimeError('Public recovery cannot restart a missing backend')
        self.health(plan)
        config=load_public_config(path,plan);gateway=read(plan['gateway_config'])
        expected=public_probe('http://127.0.0.1:%s' % gateway['port'],host=urlparse(config['public_origin']).hostname)
        if not all(row.get('status')==200 for row in expected.values()):raise RuntimeError('Local application probes failed')
        if action=='public-confirm':return self.public_confirm(config,path,record,processes,expected,route_evidence)
        observed=public_probe(config['public_origin'],config.get('https_proxy'))
        healthy=probe_matches(observed,expected)
        receipt=self.receipt('public_probe',healthy=healthy,public_observation=observed,
                             local_observation=expected,backend_processes=processes,model_requests=0)
        if action=='public-check':
            return {'public_healthy':healthy,'backend_unchanged':True,'model_requests':0,'receipt':receipt}
        if healthy:return {'already_running':True,'public_healthy':True,'backend_unchanged':True,'model_requests':0,'receipt':receipt}
        old=config['previous_process'];found=identity(old['pid'])
        if found is not None and (found!=old or not command_matches(old['pid'],config['tunnel'])):
            raise RuntimeError('Previous tunnel generation changed; no foreign process will be adopted or stopped')
        pending_path=self.root/'public-pending.json'
        if pending_path.exists() and read(private_file(read(pending_path)['attempt'])).get('stage')=='awaiting_route_update':
            raise RuntimeError('A prepared candidate awaits route update; use public-confirm instead of starting another')
        cf=CloudflareWorkerSettings(config['cloudflare'],config.get('https_proxy')) if config.get('cloudflare') else None
        before=cf.snapshot() if cf else None
        if cf and (before['deployment_id']!=config['cloudflare']['expected_deployment_id'] or
                json_sha(before['settings'])!=config['cloudflare']['expected_settings_sha256'] or
                before['upstream_origin']!=config['previous_origin']):
            raise RuntimeError('Cloudflare authority differs from the prepared recovery recipe')
        directory=self.root/('public-recover-'+uuid4().hex);directory.mkdir(mode=0o700)
        save(directory/'public-config.json',config)
        if before:save(directory/'cloudflare-before.json',before)
        attempt={'stage':'prepared','backend_processes':processes,'old_process':old,
                 'previous_origin':config['previous_origin'],'probe_receipt':receipt,'model_requests':0,
                 'backend_digest':record['digest'],'config_sha256':hashlib.sha256(private_file(path).read_bytes()).hexdigest()}
        save(directory/'attempt.json',attempt)
        child=None;mutation_attempted=False;confirmed_old=False
        try:
            spec=config['tunnel'];log_path=directory/'tunnel.log'
            with log_path.open('xb') as log:
                log_path.chmod(0o600)
                child=subprocess.Popen(spec['argv'],cwd=spec['cwd'],env=spec['env'],stdin=subprocess.DEVNULL,
                                       stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            candidate=identity(child.pid)
            if candidate is None or not command_matches(child.pid,spec):raise RuntimeError('Candidate tunnel identity unavailable')
            attempt.update(stage='candidate_started',candidate_process=candidate);save(directory/'attempt.json',attempt)
            deadline=time.monotonic()+90;origin=None;candidate_probe=None
            while time.monotonic()<deadline:
                if child.poll() is not None:raise RuntimeError('Candidate tunnel exited; inspect the private log')
                raw=log_path.read_text(encoding='utf-8',errors='replace')
                origins=set(re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com\b',raw))
                if len(origins)>1:raise RuntimeError('Candidate log contains ambiguous tunnel origins')
                if origins and 'Registered tunnel connection' in raw:
                    origin=next(iter(origins));candidate_probe=public_probe(origin,config.get('https_proxy'))
                    attempt.update(candidate_origin=origin,candidate_probe=candidate_probe);save(directory/'attempt.json',attempt)
                    # Manual routing can verify the new hostname from the
                    # operator's network; a local proxy may reject that domain.
                    # This stage never claims public readiness or changes CF.
                    if probe_matches(candidate_probe,expected) or action=='public-prepare' or cf is None:break
                time.sleep(.5)
            else:raise RuntimeError('Candidate tunnel did not pass direct application verification')
            # Recheck live backend identity without touching its tasks or process.
            if self.inspect(plan,record)!=processes:raise RuntimeError('Backend generation changed during public recovery')
            if action=='public-prepare' or cf is None:
                attempt.update(stage='awaiting_route_update',candidate_direct_verified=probe_matches(candidate_probe,expected))
                save(directory/'attempt.json',attempt);save(pending_path,{'attempt':str(directory/'attempt.json')})
                return {'awaiting_route_update':True,'candidate_origin':origin,'candidate_direct_verified':attempt['candidate_direct_verified'],
                        'backend_unchanged':True,'old_tunnel_preserved':True,'model_requests':0,
                        'receipt':self.receipt('public-prepare',attempt=str(directory/'attempt.json'))}
            attempt['stage']='publication_attempted';save(directory/'attempt.json',attempt);mutation_attempted=True
            publish_error=None
            try:cf.replace(before,origin)
            except Exception as error:publish_error=type(error).__name__
            # A lost PATCH response is unknown, never permission to submit it again.
            after=cf.snapshot();save(directory/'cloudflare-after.json',after)
            confirmed_old=after['upstream_origin']==before['upstream_origin']
            if after['upstream_origin']!=origin:
                raise RuntimeError('Cloudflare readback did not confirm the candidate upstream')
            attempt.update(stage='upstream_confirmed',publication_error_type=publish_error);save(directory/'attempt.json',attempt)
            deadline=time.monotonic()+60
            while True:
                observed=public_probe(config['public_origin'],config.get('https_proxy'))
                attempt['public_probe']=observed;save(directory/'attempt.json',attempt)
                if probe_matches(observed,expected):break
                if time.monotonic()>=deadline:raise RuntimeError('Published upstream has not passed public application verification')
                time.sleep(.5)
            if identity(child.pid)!=candidate or self.inspect(plan,record)!=processes:
                raise RuntimeError('Managed generation changed before public recovery publication')
            attempt.update(stage='ready',upstream_origin=origin,old_tunnel_preserved=True,backend_unchanged=True)
            save(directory/'attempt.json',attempt);save(self.root/'public-current.json',{
                'config_sha256':hashlib.sha256(private_file(path).read_bytes()).hexdigest(),
                'public_origin':config['public_origin'],'upstream_origin':origin,'process':candidate,
                'cloudflare_snapshot':str(directory/'cloudflare-after.json'),'attempt':str(directory/'attempt.json')})
            return {'public_healthy':True,'backend_unchanged':True,'old_tunnel_preserved':True,'model_requests':0,
                    'receipt':self.receipt('public-recover',healthy=True,attempt=str(directory/'attempt.json'))}
        except BaseException as error:
            attempt.update(stage='failed',error_type=type(error).__name__,publication_attempted=mutation_attempted,
                           candidate_preserved=bool(child and mutation_attempted and not confirmed_old))
            save(directory/'attempt.json',attempt)
            # Only this attempt's child, and only while it cannot be the live
            # published upstream. The failed legacy tunnel is never signalled.
            if child and (not mutation_attempted or confirmed_old) and child.poll() is None:
                if identity(child.pid)!=attempt.get('candidate_process'):
                    raise RuntimeError('Candidate identity changed; no process was stopped') from None
                child.terminate();child.wait(timeout=45)
            self.receipt('public-recover',healthy=False,attempt=str(directory/'attempt.json'))
            raise error

    def run(self, action, public_config=None, route_evidence=None):
        with self.lock():
            if action in ('public-check','public-recover','public-prepare','public-confirm'):
                if not public_config:raise RuntimeError('Provide a prepared private --public-config')
                return self.public_operation(action,public_config,route_evidence)
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
                recovering = False
                if record:
                    if plan_digest(record['plan']) != record['digest']:
                        raise RuntimeError('Managed configuration changed in place')
                    if plan_digest(self.plan) != record['digest']:
                        # Both the failed release and its automatic rollback
                        # can exit before health. Permit a prepared recovery
                        # only when the known ports are vacant; never replace
                        # a surviving/unknown process or bypass active tasks.
                        processes = self.inspect(record['plan'], record)
                        if any(processes.values()):
                            raise RuntimeError('A different release is running; use restart with the prepared plan')
                        same_data(record['plan'], self.plan)
                        assert_idle(record['plan'])
                        recovering = True
                    else:
                        self.inspect(record['plan'], record)
                result = self.start(self.plan if recovering or not record else record['plan'])
                if recovering:
                    save(self.previous_path, {'plan': record['rollback_plan']})
                    result['recovered_stopped_deployment'] = True
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
    parser.add_argument('action', choices=['start', 'restart', 'status', 'check', 'rollback','public-check','public-recover','public-prepare','public-confirm'])
    parser.add_argument('--config', default=os.environ.get('GENELOOP_SERVICE_CONFIG'))
    parser.add_argument('--public-config', default=os.environ.get('GENELOOP_PUBLIC_CONFIG'))
    parser.add_argument('--route-evidence')
    args = parser.parse_args()
    if not args.config:
        parser.error('Set GENELOOP_SERVICE_CONFIG or provide --config PRIVATE-SERVICE-PLAN.json')
    try:
        if sys.platform != 'linux':
            raise RuntimeError('Hosted service lifecycle requires Linux; local development uses npm run web')
        result=Lifecycle(load_plan(args.config)).run(args.action,args.public_config,args.route_evidence)
        print(json.dumps(result, ensure_ascii=False))
        if args.action=='public-check' and not result.get('public_healthy'):raise SystemExit(1)
    except Exception as error:
        # Process argv/env and HTTP exception URLs may contain credentials.
        print(json.dumps({'ok': False, 'error_type': type(error).__name__,
                          'message': str(error) if isinstance(error, RuntimeError) else 'Invalid configuration or service operation failed'}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
