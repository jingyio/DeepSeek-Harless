"""现有状态与记账的窄读取桥接；反馈执行与调度在TypeScript中。"""
import json
import sys
from pathlib import Path
from .service import private_path, ROOT
from .recovery import CheckpointPPTService
from .trial import verified_artifacts, summarize_ledger
from .accounting import collect_accounting, lines

def main():
    raw = sys.stdin.buffer.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('桥接输入过大')
    request = json.loads(raw)
    if request['action'] == 'accounting':
        run = private_path(Path(request['run_directory'])).resolve(strict=True)
        if not run.is_relative_to(ROOT / '.local/runs'):
            raise ValueError('费用目录不属于Harness运行')
        metrics = json.loads((run / 'metrics.json').read_text())
        print(json.dumps({'accounting': {**collect_accounting(run),
                        **summarize_ledger(lines(run / 'cost-ledger.jsonl'), metrics)}}, ensure_ascii=False), flush=True)
        return
    job = private_path(Path(request['job'])).resolve(strict=True)
    service = CheckpointPPTService(job)
    current = service.read_deck_plan(request['deck_id'])
    if current['file_sha256'] != request['expected_sha256']:
        raise ValueError('当前稿件版本变化')
    if request['action'] == 'inspect':
        result = current
    elif request['action'] == 'collect':
        run = private_path(Path(request['run_directory'])).resolve(strict=True)
        receipts = request['receipts']
        reports = {}
        for receipt in receipts:
            report = service.validations.get(receipt.get('validation_id'))
            if report and report.get('passed') is True:
                service.checked_validation_artifacts(report)
                reports[receipt['validation_id']] = report
        artifacts = verified_artifacts(receipts, job.parent / 'outputs', reports)
        metrics = json.loads((run / 'metrics.json').read_text())
        result = {'deliveries': artifacts,
                  'accounting': {**collect_accounting(run), **summarize_ledger(lines(run / 'cost-ledger.jsonl'), metrics)}}
    else:
        raise ValueError('未知读取动作')
    print(json.dumps(result, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()
