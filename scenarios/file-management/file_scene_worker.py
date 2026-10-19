"""File-only bridge to the existing durable Harness runner and RSI lifecycle.

The native web plugin owns authentication, upload receipts and user decisions.
This process never accepts a browser-supplied filesystem path or tool command.
"""
import json
import os
import shutil
import signal
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.adapters.continuous_rsi import PRIVATE_HOME, private, load_config, read, sha
from src.motif_core.offline.experience_registry import durable, digest
from management_prepare import prepare
from management_tools import tree
from management_web import default_config, dispatch
from src.adapters.file_scenario import prepare_scenario
from src.adapters.operation_runner import execute


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def run(value):
    request = read(private(value['request_file']))
    home = PRIVATE_HOME.resolve()
    directory = private(request['directory'])
    if not directory.is_relative_to(home / 'tasks'):
        raise ValueError('file task is outside this account')
    config = default_config(request['provider_mode'] == 'real')
    cfg = load_config(config)
    work = Path(cfg['workspace_roots'][0]) / 'workspaces' / digest(request['workspace_id'])
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    if value.get('resume_origin'):
        origin = private(value['resume_origin'])
        if not origin.is_relative_to(home):
            raise ValueError('recovery is outside this account')
    else:
        for source in request['sources']:
            file = private(source['path'])
            if not file.is_relative_to(directory / 'inputs') or sha(file) != source['sha256']:
                raise ValueError('original upload bytes changed')
            target = work / source['name']
            if target.exists() and sha(target) != source['sha256']:
                target = work / (target.stem + '-' + source['sha256'][:10] + target.suffix)
            if target.exists() and sha(target) != source['sha256']:
                raise ValueError('upload name conflicts with an existing copy')
            if not target.exists():
                # Publish only verified uploads; existing organized state is retained.
                staged = directory / ('staged-' + source['sha256'])
                shutil.copyfile(file, staged)
                if sha(staged) != source['sha256']:
                    raise ValueError('upload changed while copying')
                os.link(staged, target)
        prepare(directory / 'management', work, task_id=request['task_id'],
                objective=request['objective'], owner=request['owner'],
                workspace_id=request['workspace_id'])
    if not value.get('resume_origin') and request.get('prior_context'):
        prompt_file = directory / 'management/prompt.md'
        prompt_file.write_text(prompt_file.read_text()+'\n当前会话前文参考（不扩大文件、权限或预算范围）：\n'+json.dumps(request['prior_context'],ensure_ascii=False))
    task = directory / 'management/input.json'
    delivery = directory / 'management/delivery'
    os.environ.update(FM_TASK_FILE=str(task), FM_OUTPUT=str(delivery),
                      HARLESS_FILE_APPROVAL_HOME=str(directory / 'approvals'))
    args = SimpleNamespace(call_model=True, rsi_resume=value.get('resume_origin'),
        rsi_config=config, scenario=directory / 'management/scenario.json',
        model=request['model'], budget_usd=min(5, request['budget_usd']),
        max_steps=cfg['limits']['max_steps'], max_output=cfg['limits']['max_output'])
    def started(context):
        durable(directory / 'management/enrollment.json', context)
        emit({'kind': 'bound', 'origin': context['origin'], 'out': context['out'],
              'job_file': context['job_file']})
    result = execute(args, prepare_scenario(args.scenario,web_deployment=bool(os.environ.get('SSS_WEB_POLICY'))), on_start=started,
                     on_event=lambda event: emit({'kind': 'event', 'event': event}))
    rows = []
    if result.get('acceptance_passed'):
        context = read(directory / 'management/enrollment.json')
        out = Path(context['out'])
        # Collection verifies the same actual trace, report and final file tree.
        shutil.copyfile(out / 'agent-events.jsonl', out / 'events.jsonl')
        native = directory / 'exports'
        native.mkdir(exist_ok=True, mode=0o700)
        rows = dispatch({'action': 'collect', 'provider_mode': request['provider_mode'],
            'rsi_config': str(config), 'directory': str(directory / 'management'),
            'native_workspace': str(native)})
    public_result = {'kind': 'result', 'status': 'completed' if result.get('acceptance_passed') else
        'interrupted' if result.get('status') == 'interrupted' else 'failed',
        'metrics': result, 'artifacts': rows}
    durable(directory / 'result.json', public_result)
    emit(public_result)


if __name__ == '__main__':
    def interrupted(*_):
        raise KeyboardInterrupt('file task interrupted; original job retained')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        run(json.loads(sys.stdin.readline()))
    except Exception as error:
        # Full exception and failed run artifacts remain private; no fake success.
        import traceback
        traceback.print_exc(file=sys.stderr)
        emit({'kind': 'error', 'type': type(error).__name__, 'message': str(error)[:2000]})
        raise SystemExit(2)
