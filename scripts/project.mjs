/** Cross-platform entry point. No shell scripts or platform-specific venv paths. */
import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';
const root = dirname(dirname(fileURLToPath(import.meta.url)));
// Node's dotenv parser never executes shell expressions and preserves existing env.
const dotenv = join(root, '.env');
if (existsSync(dotenv)) {
  if (!process.loadEnvFile) throw new Error('读取 .env 需要 Node.js 20.12+；推荐项目已验收的 Node 22。');
  process.loadEnvFile(dotenv);
}
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
  const [nodeMajor, nodeMinor] = process.versions.node.split('.').map(Number);
  if (nodeMajor > 22 || (nodeMajor === 22 && nodeMinor >= 18)) {
    run(process.execPath, ['scripts/build-continuation-policy.mjs', '--check']);
  }
  run(process.execPath, ['--test', 'tests/test_online_motif_frontier.mjs', 'tests/test_dsh_online_motif.mjs', 'tests/test_dsh_scenario_guard.mjs', 'tests/test_distributed_motif_library.mjs', 'tests/test_approved_plan_continuation.mjs', 'tests/test_dsh_web_policy.mjs', 'tests/test_web_task_request.mjs', 'tests/test_dsh_web_tasks.mjs', 'tests/test_dsh_completion_guard.mjs', 'tests/test_code_container.mjs', 'tests/test_entry_motif.mjs', 'tests/test_terminal_motif.mjs', 'tests/test_collection_motif.mjs', 'tests/test_collection_script.mjs', 'tests/test_plan_motif.mjs', 'tests/test_collection_reentry.mjs', 'tests/test_acceptance_guard.mjs', 'tests/test_harless_settings.mjs', 'tests/test_harless_native_picker.mjs', 'tests/test_harless_gateway.mjs', 'tests/test_web_budget_broker.mjs', 'tests/test_member_file_scope.mjs']);
} else if (action === 'scenario') {
  run(python, ['scripts/run-scenario.py', ...args]);
} else if (action === 'web') {
  run(python, ['scripts/harness-web.py', ...args]);
} else if (action === 'smoke') {
  run(python, ['scripts/smoke.py', ...args]);
} else if (action === 'python') {
  run(python, args);
} else { console.error('Use setup, test, scenario, web, smoke or python'); process.exit(1); }
