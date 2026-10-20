/** Native Bash lifecycle, confined to one Session's scratch space by bubblewrap. */
import { existsSync, lstatSync, mkdirSync, readFileSync, realpathSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve } from 'node:path';
import {fileURLToPath} from 'node:url';
import { LocalBashExecutor } from '@deepseek-ai/dsh-bash-local';
import type { ShellExecRequest, ShellExecSpec } from '@deepseek-ai/dsh-shell';
import {pptMasterInstallation} from './geneloop_skill_installation.mjs';

const inside = (root: string, path: string) => { const r = relative(root, path); return !r.startsWith('..') && !isAbsolute(r); };
function fixedDirectory(path: string) {
  if (!isAbsolute(path) || realpathSync(path) !== resolve(path) || !lstatSync(path).isDirectory() || lstatSync(path).isSymbolicLink())
    throw Error('command workspace is not a fixed directory');
  return path;
}
function prepareMountPoints(layout: ReturnType<typeof commandLayout>) {
  const work = fixedDirectory(layout.work), scratch = fixedDirectory(layout.scratch);
  if (scratch !== join(work, 'code')) throw Error('command scratch is not a fixed directory inside its workspace');
  // bubblewrap must find child bind destinations before /work becomes
  // read-only. These empty seats live only in this Session's scratch tree.
  for (const name of ['inputs', 'outputs']) {
    const path = join(scratch, name), existing = lstatSync(path, { throwIfNoEntry: false });
    if (existing && (existing.isSymbolicLink() || !existing.isDirectory()))
      throw Error('command mount point is not a fixed directory');
    if (!existing) mkdirSync(path, { mode: 0o700 });
    fixedDirectory(path);
  }
}
export function commandLayout(output: string, session: string) {
  if (!/^(?:session-[a-f0-9-]{36}|sss-[a-f0-9]{32})$/.test(session)) throw Error('command requires an owning Session');
  const work = join(output, 'sessions', session, 'work');
  for (const suffix of ['inputs', 'code', 'outputs/code', 'command-tmp']) mkdirSync(join(work, suffix), { recursive: true, mode: 0o700 });
  return { work: fixedDirectory(work), scratch: fixedDirectory(join(work, 'code')),
    inputs: fixedDirectory(join(work, 'inputs')), outputs: fixedDirectory(join(work, 'outputs/code')),
    temp:fixedDirectory(join(work,'command-tmp')) };
}
export function commandArgv(layout: ReturnType<typeof commandLayout>, command: string, cwd: string,
    python = process.env.SSS_PYTHON ?? '/usr/bin/python3', node = process.execPath, readOnly = false,
    resources: {pptMasterRoot?:string;rendererRoot?:string;fontRoot?:string;projectRoot?:string;network?:'none'} = {}) {
  if (process.platform !== 'linux' || !existsSync('/usr/bin/bwrap')) throw Error('isolated command execution requires Linux bubblewrap');
  prepareMountPoints(layout);
  // env -i also supports the server's older bubblewrap (without --clearenv).
  const args = ['/usr/bin/env', '-i', '/usr/bin/bwrap', '--unshare-user', '--unshare-pid', '--unshare-ipc', '--unshare-uts',
    '--die-with-parent', '--new-session', '--cap-drop', 'ALL'];
  if(resources.network==='none')args.push('--unshare-net');
  for (const path of ['/usr', '/bin', '/lib', '/lib64']) if (existsSync(path)) args.push('--ro-bind', path, path);
  args.push('--dir', '/etc');
  for (const path of ['/etc/ssl', '/etc/resolv.conf', '/etc/hosts', '/etc/nsswitch.conf'])
    if (existsSync(path)) args.push('--ro-bind', path, path);
  const roots = new Set([dirname(dirname(node)), dirname(dirname(python)), dirname(dirname(realpathSync(python)))]);
  for (const root of roots) if (root !== '/usr' && root !== '/') {
    fixedDirectory(root);
    if (!existsSync(join(root, 'bin')) || !existsSync(join(root, 'lib')) ||
        ['.env', '.ssh', 'accounts.json', '.credentials.yaml'].some(name => existsSync(join(root, name))))
      throw Error('command dependency is not a public runtime installation');
    args.push('--ro-bind', root, root);
  }
  const skill=pptMasterInstallation(resources.pptMasterRoot,resources.projectRoot);
  if(skill)args.push('--ro-bind',skill.source,skill.target);
  if(resources.rendererRoot){
    const renderer=fixedDirectory(resources.rendererRoot);
    if(!existsSync(join(renderer,'program/soffice.bin')) || !existsSync(join(renderer,'share')))throw Error('invalid command renderer installation');
    args.push('--ro-bind',renderer,'/opt/geneloop/libreoffice');
  }
  if(resources.fontRoot){
    const fonts=fixedDirectory(resources.fontRoot);
    if(!existsSync(join(fonts,'fonts-static.conf')))throw Error('invalid command font installation');
    args.push('--ro-bind',fonts,fonts,'--setenv','FONTCONFIG_FILE',join(fonts,'fonts-static.conf'),'--setenv','FONTCONFIG_PATH',fonts);
  }
  // Checkers and converters write reports/caches to /tmp, then read them in a
  // later native tool call. Persist only this Session's temp tree, never host /tmp.
  args.push('--proc', '/proc', '--dev', '/dev', '--bind', layout.temp, '/tmp', readOnly ? '--ro-bind' : '--bind', layout.scratch, '/work',
    '--ro-bind', layout.inputs, '/work/inputs', readOnly ? '--ro-bind' : '--bind', layout.outputs, '/work/outputs',
    '--setenv', 'HOME', '/work', '--setenv', 'PATH', `${dirname(python)}:${dirname(node)}:/opt/geneloop/libreoffice/program:/usr/bin:/bin`,
    '--setenv', 'PYTHONDONTWRITEBYTECODE', '1',
    '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'PYTHONUTF8', '1', '--setenv', 'MPLCONFIGDIR', '/tmp/matplotlib',
    '--setenv', 'OPENBLAS_NUM_THREADS', '1', '--setenv', 'OMP_NUM_THREADS', '1',
    '--setenv', 'NO_COLOR', '1', '--setenv', 'TERM', 'dumb', '--setenv', 'PAGER', 'cat',
    '--chdir', cwd, '/bin/bash', '--noprofile', '--norc', '-c', command);
  return args;
}
export default class GeneLoopShell extends LocalBashExecutor {
  get sandboxMode() { return 'workspace-write' as const; }
  resolve(request: ShellExecRequest): ShellExecSpec {
    const agent = this.ctx.get('agents')?.currentInitiator();
    if (!agent) throw Error('command requires an active owning Agent');
    const policy = JSON.parse(readFileSync(process.env.SSS_WEB_POLICY!, 'utf8'));
    const layout = commandLayout(policy.output, agent.session.id);
    const requested = request.workdir ?? '/work';
    const headerRoot = agent.session.header.cwd;
    let cwd = requested === '/work' || requested.startsWith('/work/') ? resolve(requested)
      : headerRoot && inside(headerRoot, requested) ? resolve('/work', relative(headerRoot, requested))
      : !isAbsolute(requested) ? resolve('/work', requested) : '';
    if (!cwd || !inside('/work', cwd)) throw Error('command working directory must stay inside /work');
    // Keep host spawn cwd valid, but only expose the virtual workspace to the command.
    const spec = super.resolve({ ...request, workdir: layout.scratch, env: {}, dshEnv: {}, sandboxPolicy: undefined });
    const readOnly=request.sandboxPolicy?.mode==='read-only';
    // Older Linux kernels cannot nest user namespaces inside the account bwrap.
    // A private socket creates the same Session-only bwrap outside that namespace.
    const socket=process.env.GENELOOP_COMMAND_SOCKET;
    const argv=socket ? [process.execPath,fileURLToPath(new URL('./geneloop_command_client.mjs',import.meta.url)),socket,
      Buffer.from(JSON.stringify({session:agent.session.id,command:request.command,cwd,readOnly})).toString('base64url')]
      : commandArgv(layout,request.command,cwd,undefined,undefined,readOnly,policy.command_resources??{});
    Object.assign(spec, { geneloopArgv: argv });
    return spec;
  }
  run(spec: ShellExecSpec) { return this.runArgv(spec, (spec as any).geneloopArgv ?? fail()); }
  start(spec: ShellExecSpec) { return this.startArgv(spec, (spec as any).geneloopArgv ?? fail()); }
}
function fail(): never { throw Error('unresolved isolated command'); }
