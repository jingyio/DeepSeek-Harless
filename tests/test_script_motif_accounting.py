"""无模型诊断：完成状态、原件 PDF 和跳过计数不能冒充交付/净收益。"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('script_accounting', ROOT / 'scripts/summarize-script-motif-run.py')
accounting = importlib.util.module_from_spec(spec)
spec.loader.exec_module(accounting)


def test_completed_with_only_input_pdf_is_not_report_delivery(tmp_path):
    task = tmp_path / 'task'
    task.mkdir()
    work = tmp_path / 'work'
    (work / 'inputs').mkdir(parents=True)
    (work / 'inputs' / 'paper.pdf').write_bytes(b'%PDF-original')
    (task / 'task-state.json').write_text(json.dumps({'task_id': 'test', 'status': 'completed', 'stats': {'upstream_requests': 8}}))
    (task / 'effective-config.json').write_text(json.dumps({'workspace': str(work), 'provider_mode': 'real'}))
    (task / 'events.jsonl').write_text(json.dumps({'type': 'turn/end', 'data': {'reason': {'kind': 'max-tokens'}}}) + '\n')
    (task / 'script-motif-audit.jsonl').write_text(json.dumps({'kind': 'script_model_request_skipped_verified'}) + '\n')
    summary = accounting.summarize(task)
    assert not summary['pdf_delivery_observed']
    assert summary['verified_script_skips'] == 1
    assert summary['stats']['upstream_requests'] == 8
    assert not summary['embedding_timing_available']
    (work / 'outputs').mkdir()
    (work / 'outputs' / 'report.pdf').write_bytes(b'%PDF-diagnostic')
    summary = accounting.summarize(task)
    assert summary['pdf_delivery_observed']
    assert summary['quality'] == 'not_independently_reviewed'
