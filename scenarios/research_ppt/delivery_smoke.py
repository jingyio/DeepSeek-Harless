"""真实 TS→Python MCP 交付诊断，无模型、无假工具，仅服务器运行。

默认用 PyMuPDF 创建明确标注合成来源的合法 PDF，再调用公共 prepare。
可以 --job 指定刚 prepare 的未运行任务；诊断只改本次新副本/产物。
"""
from __future__ import annotations

import argparse
import asyncio
import copy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mcp import Client, StdioServerParameters
from scenarios.research_ppt.cli import prepare
from scenarios.research_ppt.documents import file_hash
from scenarios.research_ppt.recovery import CheckpointPPTService, CheckpointRejected, SCHEMA_VERSION
from scenarios.research_ppt.revision import verify_unmodified_slides
from scenarios.research_ppt.service import private_path

BASE_NAMES = ['list_inputs', 'list_templates', 'pin_source', 'read_source', 'read_page',
              'extract_figure', 'inspect_deck', 'deliver_deck', 'read_deck_plan',
              'list_restorable_decks', 'render_deck', 'restyle_deck', 'revise_deck',
              'validate_deck', 'build_delivery']
ADAPTER_NAMES = ['render_delivery', 'revise_delivery', 'pin_deck_pages', 'read_pinned_deck_pages',
                 'read_pending_plan', 'repair_pending_plan']
READ_ONLY_ADAPTER_NAMES = {'pin_deck_pages', 'read_pinned_deck_pages', 'read_pending_plan'}


def write(path, value):
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    path.chmod(0o600)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


@contextmanager
def mutated(path, replacement):
    original = path.read_bytes()
    if replacement == original:
        raise ValueError('负例必须实际改变字节')
    try:
        if replacement is None:
            path.unlink()
        else:
            path.write_bytes(replacement)
        yield
    finally:
        path.write_bytes(original)


class Diagnostic:
    def __init__(self, out, synthetic_input=False):
        self.out, self.checks = out, []
        self.synthetic_input = synthetic_input

    def check(self, name, passed, **evidence):
        item = {'name': name, 'passed': bool(passed), 'evidence': evidence}
        self.checks.append(item)
        write(self.out / 'progress.json', {'checks': self.checks})
        print(json.dumps(item, ensure_ascii=False), flush=True)
        if not passed:
            raise AssertionError(name)

    async def call(self, client, name, args, *, rejected=None):
        response = (await client.call_tool(name, args)).model_dump(mode='json', by_alias=True)
        value = response.get('structuredContent')
        if not isinstance(value, dict):
            block = next((b for b in response.get('content', []) if b.get('type') == 'text'), {})
            value = json.loads(block.get('text', '{}'))
        with (self.out / 'actual-mcp-calls.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'tool': name, 'arguments': args, 'response': response}, ensure_ascii=False) + '\n')
        if rejected is not None:
            self.check(name + ':rejected', response.get('isError') is True and value.get('code') in rejected,
                       code=value.get('code'), expected=sorted(rejected))
        else:
            self.check(name + ':success', response.get('isError') is not True and value.get('ok') is not False)
        return value


def params(job):
    node = shutil.which('node')
    adapter = ROOT / 'scenarios/research_ppt/dist/mcp-adapter.js'
    if not node or not adapter.is_file():
        raise ValueError('需先安装场景依赖并build真实TS适配器')
    font_environment = {name: os.environ[name] for name in ('FONTCONFIG_FILE', 'FONTCONFIG_PATH') if os.environ.get(name)}
    return StdioServerParameters(command=node, args=[str(adapter), '--job', str(job)], cwd=ROOT,
        env={**font_environment, 'SSS_PPT_DELIVERY_PYTHON': sys.executable, 'PYTHONPATH': str(ROOT), 'PYTHONUTF8': '1'})


def verify_artifacts(delivery, slides):
    path = private_path(Path(delivery['path']))
    if file_hash(path) != delivery['file_sha256'] or delivery.get('editable') is not True:
        return False
    pdf, pages = 0, []
    for artifact in delivery['artifacts']:
        if file_hash(private_path(Path(artifact['path']))) != artifact['sha256']:
            return False
        if artifact['kind'] == 'pdf':
            pdf += 1
        elif artifact['kind'] == 'preview':
            pages.append(artifact['page'])
        else:
            return False
    return pdf == 1 and sorted(pages) == list(range(1, slides + 1))


async def exercise(job, denied_job, diag):
    data = read(job)
    async with Client(params(job), read_timeout_seconds=180) as client:
        tools = (await client.list_tools()).tools
        schema = [tool.model_dump(mode='json', by_alias=True) for tool in tools]
        diag.check('fixed_real_schema_order', [tool.name for tool in tools] == BASE_NAMES + ADAPTER_NAMES)
        by_name = {row['name']: row for row in schema}
        diag.check('new_tools_read_only_annotations', all(
            by_name[name].get('annotations', {}).get('readOnlyHint') is (name in READ_ONLY_ADAPTER_NAMES)
            for name in ADAPTER_NAMES))
        inputs = await diag.call(client, 'list_inputs', {})
        pin = await diag.call(client, 'pin_source', {'document_id': inputs['inputs'][0]['document_id']})
        source = await diag.call(client, 'read_source', {'source_id': pin['source_id']})
        citation = [{'source_id': pin['source_id'], 'page': 1}]
        plan = {'title': 'Real delivery engineering check', 'template': 'academic', 'slides': [
            {'title': '中文渲染验收 Engineering page ' + str(i), 'bullets': ['Synthetic source; no scientific claim'],
             'sources': citation, 'notes': source['pages'][0]['text'][:150]}
            for i in range(1, data['slides'] + 1)]}
        if data['slides'] >= 3:
            geometry = await diag.call(client, 'read_page', {'source_id': pin['source_id'], 'page': 1})
            candidates = geometry.get('figure_candidates', [])
            diag.check('real_caption_geometry_candidate_available', bool(candidates)
                       and all(isinstance(row.get('candidate_id'), str) for row in candidates))
            if data.get('figure_evidence_policy') == 'caption-geometry-v1':
                whole = await diag.call(client, 'extract_figure',
                    {'source_id': pin['source_id'], 'page': 1, 'bbox': [0, 0, 1, 1]})
                whole_plan = copy.deepcopy(plan)
                whole_plan['slides'][1].update(layout='image', bullets=[],
                    image={'source_id': pin['source_id'], 'image_id': whole['image_id']},
                    notes='Whole page evidence must not satisfy an original-figure delivery contract.')
                rejected = await diag.call(client, 'render_delivery', {'plan': whole_plan},
                                           rejected={'backend_tool_failed'})
                diag.check('whole_page_rejected_as_original_figure',
                           rejected.get('backend_report', {}).get('error') == 'invalid_image')
            image = await diag.call(client, 'extract_figure',
                {'source_id': pin['source_id'], 'page': 1, 'candidate_id': candidates[0]['candidate_id']})
            diag.check('real_figure_candidate_extracted', image.get('evidence_scope') == 'caption_geometry_candidate'
                       and image.get('candidate_id') == candidates[0]['candidate_id'])
            plan['slides'][1].update(layout='image', bullets=[],
                image={'source_id': pin['source_id'], 'image_id': image['image_id']},
                notes='Synthetic caption-geometry figure for delivery diagnostics; no scientific quality claim.')
        bad = copy.deepcopy(plan)
        bad['slides'].append(copy.deepcopy(bad['slides'][0]))
        await diag.call(client, 'render_delivery', {'plan': bad}, rejected={'slide_count_mismatch'})
        rendered = await diag.call(client, 'render_delivery', {'plan': plan})
        diag.check('actual_render_delivery_artifact_hashes', rendered.get('delivered') is True
                   and verify_artifacts(rendered, data['slides']))
        page_pin = await diag.call(client, 'pin_deck_pages', {'deck_id': rendered['deck_id'], 'pages_csv': str(data['slides'])})
        page = await diag.call(client, 'read_pinned_deck_pages', {'source_id': page_pin['source_id']})
        diag.check('pin_read_actual_selected_page', page['slides'] == [{'page': data['slides'], 'slide': plan['slides'][-1]}])
        for csv in ('0', '1,1', '1.0', str(data['slides'] + 1)):
            await diag.call(client, 'pin_deck_pages', {'deck_id': rendered['deck_id'], 'pages_csv': csv}, rejected={'invalid_arguments'})
        await diag.call(client, 'pin_deck_pages', {'deck_id': 7, 'pages_csv': '1'}, rejected={'invalid_arguments'})
        with mutated(Path(rendered['path']), Path(rendered['path']).read_bytes() + b'\ncorrupt isolated deck\n'):
            await diag.call(client, 'read_pinned_deck_pages', {'source_id': page_pin['source_id']},
                            rejected={'backend_tool_failed', 'artifact_version_changed'})
        changed = copy.deepcopy(data)
        changed['allow_output'] = False
        with mutated(job, (json.dumps(changed) + '\n').encode()):
            await diag.call(client, 'read_pinned_deck_pages', {'source_id': page_pin['source_id']}, rejected={'job_version_changed'})
        if diag.synthetic_input:
            synthetic_source = Path(data['inputs'][0]['path'])
            with mutated(synthetic_source, synthetic_source.read_bytes() + b'\n% synthetic source mutation diagnostic\n'):
                await diag.call(client, 'read_pinned_deck_pages', {'source_id': page_pin['source_id']}, rejected={'source_version_changed'})
    async with Client(params(job), read_timeout_seconds=180) as client:
        tools2 = [tool.model_dump(mode='json', by_alias=True) for tool in (await client.list_tools()).tools]
        diag.check('real_schema_stable_after_process_restart', tools2 == schema)
        restored = await diag.call(client, 'list_restorable_decks', {})
        diag.check('same_job_checkpoint_restored', restored['restore']['restored'] is True
                   and any(row['deck_id'] == rendered['deck_id'] for row in restored['decks']))
        if data['slides'] >= 3:
            checkpoint_state = read(job.parent / 'service-checkpoint.json')['state']
            restored_images = checkpoint_state['handles'][pin['source_id']]['parsed']['images']
            diag.check('real_caption_figure_persisted_after_restart', any(
                row['image_id'] == plan['slides'][1]['image']['image_id'] and row['data'].startswith('image/png;base64,')
                and row.get('evidence_scope') == 'caption_geometry_candidate'
                for row in restored_images))
        await diag.call(client, 'read_pinned_deck_pages', {'source_id': page_pin['source_id']}, rejected={'invalid_source'})
        repin = await diag.call(client, 'pin_deck_pages', {'deck_id': rendered['deck_id'], 'pages_csv': str(data['slides'])})
        repage = await diag.call(client, 'read_pinned_deck_pages', {'source_id': repin['source_id']})
        diag.check('explicit_repin_same_current_content', page == repage)
        revised = await diag.call(client, 'revise_delivery', {'deck_id': rendered['deck_id'], 'updates': [
            {'page': data['slides'], 'changes': {'title': 'Explicit revised engineering page'}}]})
        diag.check('new_revision_real_preview_hashes', revised.get('delivered') is True and verify_artifacts(revised, data['slides']))
        audit = verify_unmodified_slides(Path(rendered['path']), Path(revised['path']), [data['slides']])
        diag.check('independent_non_target_OOXML_preserved', audit == revised['revision_audit'])
        current = await diag.call(client, 'read_deck_plan', {'deck_id': revised['deck_id']})
        diag.check('target_changed_other_page_plans_preserved', current['plan']['slides'][:-1] == plan['slides'][:-1]
                   and current['plan']['slides'][-1]['title'] == 'Explicit revised engineering page')
        diag.check('original_deck_bytes_preserved', file_hash(Path(rendered['path'])) == rendered['file_sha256'])
        for kind in ('pdf', 'preview'):
            artifact = next(row for row in revised['artifacts'] if row['kind'] == kind)
            path = Path(artifact['path'])
            with mutated(path, path.read_bytes() + b'\ncorrupt isolated preview\n'):
                await diag.call(client, 'deliver_deck', {'validation_id': revised['validation_id']}, rejected={'backend_tool_failed'})
        await diag.call(client, 'revise_delivery', {'deck_id': revised['deck_id'], 'updates': [
            {'page': data['slides'], 'changes': {'title': 'overflow ' * 500}}]}, rejected={'backend_tool_failed'})
        preserved = await diag.call(client, 'deliver_deck', {'validation_id': revised['validation_id']})
        diag.check('failed_revision_preserves_previous_delivery', preserved['file_sha256'] == revised['file_sha256'])
    async with Client(params(job), read_timeout_seconds=180) as client:
        again = await diag.call(client, 'deliver_deck', {'validation_id': revised['validation_id']})
        diag.check('real_second_restart_delivery', again['artifacts'] == revised['artifacts'] and verify_artifacts(again, data['slides']))
    checkpoint = job.parent / 'service-checkpoint.json'
    original = read(checkpoint)
    old = copy.deepcopy(original)
    old['schema_version'] = 1
    with mutated(checkpoint, (json.dumps(old) + '\n').encode()):
        try:
            CheckpointPPTService(job)
        except CheckpointRejected:
            diag.check('old_private_schema_1_rejected_without_resigning', True)
        else:
            diag.check('old_private_schema_1_rejected_without_resigning', False)
    for raw in (b'{"format":', b'{"format":"a","format":"b"}'):
        with mutated(checkpoint, raw):
            try:
                CheckpointPPTService(job)
            except CheckpointRejected:
                diag.check('broken_or_duplicate_checkpoint_rejected', True)
            else:
                diag.check('broken_or_duplicate_checkpoint_rejected', False)
    preview = Path(next(row for row in revised['artifacts'] if row['kind'] == 'preview')['path'])
    stable_checkpoint = checkpoint.read_bytes()
    try:
        with mutated(preview, None):
            restored = CheckpointPPTService(job)
            diag.check('missing_preview_only_revokes_validation', revised['validation_id'] not in restored.validations
                       and restored.read_deck_plan(revised['deck_id'])['deck_id'] == revised['deck_id'])
    finally:
        checkpoint.write_bytes(stable_checkpoint)
    stale = CheckpointPPTService(job)
    active = CheckpointPPTService(job)
    active.read_page(pin['source_id'], 1)
    try:
        stale.save_checkpoint('stale_diagnostic_instance')
    except CheckpointRejected:
        diag.check('stale_instance_cannot_overwrite_current_checkpoint', True)
    else:
        diag.check('stale_instance_cannot_overwrite_current_checkpoint', False)
    async with Client(params(denied_job), read_timeout_seconds=180) as client:
        await diag.call(client, 'render_delivery', {'plan': plan}, rejected={'output_permission_denied'})
        await diag.call(client, 'revise_delivery', {'deck_id': rendered['deck_id'], 'updates': [
            {'page': data['slides'], 'changes': {'title': 'not authorized'}}]}, rejected={'output_permission_denied'})
    return {'job_path': str(job), 'job_sha256': file_hash(job), 'checkpoint_schema_version': SCHEMA_VERSION,
            'initial': rendered, 'revision': revised}


async def run(args):
    if os.name != 'posix':
        raise RuntimeError('所有实验只在已激活环境的Linux服务器运行')
    out = private_path(args.out or ROOT / ('.local/research-ppt/delivery-smoke-' + uuid4().hex[:8]))
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    if args.job:
        job = private_path(args.job.resolve(strict=True))
        data = read(job)
        if (job.parent / 'service-checkpoint.json').exists() or not data['allow_output']:
            raise ValueError('--job只接受本次刚prepare、allow_output=true的未运行诊断任务')
        inputs = [Path(row['path']) for row in data['inputs']]
        slides = data['slides']
    else:
        import fitz
        pdf = out / 'synthetic-engineering-source.pdf'
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((72, 72), 'Synthetic engineering source.\nThis PDF checks real editable delivery and restart.\nIt is not research quality evidence.')
            page.draw_rect(fitz.Rect(100, 180, 420, 340), color=(0, 0, 0), width=2)
            page.draw_line(fitz.Point(120, 310), fitz.Point(380, 210), color=(0, 0, 1), width=3)
            page.insert_text((100, 365), 'Figure 1: Synthetic delivery diagnostic diagram.')
            document.save(pdf)
        inputs, slides = [pdf], 3
        job = prepare(inputs, '合成来源工程诊断：三页真实可编辑交付与MCP重启，非科研质量结论。', slides, allow_output=True)
    denied = prepare(inputs, '只读权限拒绝诊断；不得输出。', slides, allow_output=False)
    diag = Diagnostic(out, synthetic_input=args.job is None)
    summary = {'passed': False, 'model_requests': 0, 'scope': 'real_stdio_mcp_real_PDF_PPTX_LibreOffice_no_mock_no_quality_claim',
               'historical_frozen_implementation_modified': False}
    start = time.monotonic()
    try:
        summary['delivery'] = await exercise(job, denied, diag)
        summary['passed'] = True
    except Exception as error:
        summary.update(error_type=type(error).__name__, error_message=str(error)[:1200], negative_evidence_retained=True)
    finally:
        summary.update(checks=diag.checks, elapsed_seconds=round(time.monotonic() - start, 3))
        write(out / 'summary.json', summary)
        print(json.dumps({'passed': summary['passed'], 'out': str(out), 'model_requests': 0,
                          'error_type': summary.get('error_type'), 'error_message': summary.get('error_message')}, ensure_ascii=False), flush=True)
    return 0 if summary['passed'] else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path)
    parser.add_argument('--out', type=Path)
    raise SystemExit(asyncio.run(run(parser.parse_args())))
