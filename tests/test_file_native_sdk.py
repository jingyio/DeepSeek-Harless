"""Trusted File capability expansion; no network/model calls in these diagnostics."""
import json
from pathlib import Path
import tempfile
import pytest
from src.adapters.file_scenario import ROOT, prepare_scenario
from src.adapters.harness_runtime import create_harness


def scenario(tmp_path):
    data = json.loads((ROOT / 'scenarios/example/scenario.json').read_text(encoding='utf-8'))
    data['prompt'] = str(ROOT / 'scenarios/example/prompt.md')
    data['servers'][0]['server_name'] = 'file_management'
    data['allowed_tools'] = ['mcp__file_management__submit_report']
    data['acceptance_guard'] = {'kind': 'file_management', 'max_repairs': None, 'durable_job': True}
    file = tmp_path / 'scenario.json'
    file.write_text(json.dumps(data), encoding='utf-8')
    return file, data


def test_only_trusted_web_durable_file_enables_session_todo_and_native_retry(tmp_path):
    file, _ = scenario(tmp_path)
    legacy = prepare_scenario(file)
    web = prepare_scenario(file, web_deployment=True)
    assert legacy['allowed_tools'] == ['mcp__file_management__submit_report']
    assert web['allowed_tools'] == [*legacy['allowed_tools'], 'todo_write']
    text = Path(web['patch']).read_text(encoding='utf-8')
    assert '- id: tool-todo\n  disabled: false\n  config:\n    allowParallelInProgress: true' in text
    assert '- id: llm-retry\n  disabled: false' in text
    assert 'retryableCodes: [EMPTY_RESPONSE, RATE_LIMIT, SERVER, TIMEOUT, TRANSPORT]' in text
    assert 'mode: normal' in text and 'maxDelayMs: 30000' in text
    assert 'compaction-basic\n  disabled: true' not in text
    assert '- id: tool-bash\n  disabled: true' in text
    assert '- id: tool-read\n  disabled: true' in text
    assert '- id: tool-skill\n  disabled: true' in text
    assert '- id: tool-todo\n  disabled: false' not in Path(legacy['patch']).read_text(encoding='utf-8')


@pytest.mark.parametrize('native_tool', ['todo_write', 'Bash', 'read_file', 'write_file', 'skill'])
def test_scenario_cannot_self_authorize_any_native_tool(tmp_path, native_tool):
    file, data = scenario(tmp_path)
    data['allowed_tools'].append(native_tool)
    file.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='configured MCP servers'):
        prepare_scenario(file, web_deployment=True)


def test_non_file_web_scenarios_do_not_acquire_native_tools_or_retry_override():
    result = prepare_scenario(ROOT / 'scenarios/example/scenario.json', web_deployment=True)
    assert 'todo_write' not in result['allowed_tools']
    assert '- id: llm-retry\n  disabled: false' not in Path(result['patch']).read_text(encoding='utf-8')


def test_generated_web_file_patch_boots_the_installed_sdk_without_model_calls(tmp_path):
    pytest.importorskip('deepseek_harness', reason='optional Python SDK is installed in the server runtime')
    file, _ = scenario(tmp_path)
    prepared = prepare_scenario(file, web_deployment=True)
    # The real acceptance plugin hashes its frozen task while loading. This
    # handshake creates no agent/job and never dispatches a model or tool call.
    with tempfile.TemporaryDirectory(prefix='native-sdk-boot-', dir=ROOT / '.local') as directory:
        private = Path(directory)
        task = private / 'task.json'
        task.write_text(json.dumps({'diagnostic': 'SDK configuration boot only'}), encoding='utf-8')
        with create_harness(root=ROOT, patches=(prepared['patch'],), cwd=str(tmp_path), runtime_cwd=str(tmp_path),
                            env={'DSH_HOME': str(tmp_path / 'dsh'),
                                 'SSS_SCENARIO_TOOLS': json.dumps(prepared['allowed_tools']),
                                 'FM_TASK_FILE': str(task),
                                 'FM_JOB_FILE': str(private / 'job.json'),
                                 'FM_OUTPUT': str(private / 'output'),
                                 'DEEPSEEK_BASE_URL': 'http://127.0.0.1:9',
                                 'DEEPSEEK_API_KEY': 'diagnostic-only'}):
            pass
