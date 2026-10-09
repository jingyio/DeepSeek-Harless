/** Cross-platform entry point. No shell scripts or platform-specific venv paths. */
import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';
const root = dirname(dirname(fileURLToPath(import.meta.url)));
const suffix = process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python';
const python = process.env.SSS_PYTHON ?? ['.venv-sss', '.venv312', '.venv']
  .map(dir => join(root, dir, suffix)).find(existsSync) ?? (process.platform === 'win32' ? 'python' : 'python3');
// Repository files and MCP/CLI output use UTF-8, including redirected Windows output.
const env = { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8',
  SSS_PURE_CODE_PYTHON: python };
function run(command, args) {
  const result = spawnSync(command, args, { cwd: root, env, stdio: 'inherit' });
  if (result.error) { console.error(result.error.message); process.exit(1); }
  if (result.status !== 0) process.exit(result.status ?? 1);
}
const [action, ...args] = process.argv.slice(2);
if (action === 'setup') {
  run(python, ['-m', 'venv', '.venv-sss']);
  run(join(root, '.venv-sss', suffix), ['-m', 'pip', 'install', '-r', 'requirements.txt']);
} else if (action === 'test') {
  run(python, ['-m', 'pytest', 'tests', '-q']);
  run(process.execPath, ['--test', 'tests/test_online_motif_frontier.mjs', 'tests/test_dsh_online_motif.mjs', 'tests/test_dsh_scenario_guard.mjs', 'tests/test_distributed_motif_library.mjs']);
} else if (action === 'scenario') {
  run(python, ['scripts/run-scenario.py', ...args]);
} else if (action === 'smoke') {
  run(python, ['scripts/smoke.py', ...args]);
} else if (action === 'python') {
  run(python, args);
} else { console.error('Use setup, test, scenario, smoke or python'); process.exit(1); }
