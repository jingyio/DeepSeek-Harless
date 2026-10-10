"""PPT 场景 MCP 的实现；只允许读取准备阶段列明的文件。"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4
from .documents import file_hash, parse_document, inspect_pptx, pdf_page_geometry

SCENE = Path(__file__).resolve().parent
ROOT = SCENE.parents[1]


def private_path(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to((ROOT / '.local').resolve()):
        raise ValueError('运行数据必须位于仓库 .local')
    return resolved


class RenderFailure(ValueError):
    """枚举化的渲染失败；原 stderr 仅留在私有日志。"""
    def __init__(self, report: dict):
        self.report = report
        super().__init__(report.get('error', '确定性布局失败'))


def node(script: str, payload: dict, *args: str) -> dict:
    runner = SCENE / 'dist' / script
    if not runner.exists():
        raise ValueError('请先在 scenarios/research_ppt 运行 npm ci 和 npm run build')
    result = subprocess.run(['node', str(runner), *args], input=json.dumps(payload, ensure_ascii=False),
                            text=True, encoding='utf-8', capture_output=True, timeout=90)
    if result.returncode:
        if script == 'render.js':
            try:
                report = json.loads(result.stderr.strip())
                if isinstance(report, dict) and report.get('ok') is False:
                    raise RenderFailure(report)
            except json.JSONDecodeError:
                pass
        # 验证失败的结果可反馈给模型；不泄露进程环境和凭证。
        try:
            return json.loads(result.stdout)
        except ValueError:
            raise ValueError('场景 Node 工具执行失败: ' + result.stderr[-1200:])
    return json.loads(result.stdout)


class PPTService:
    def __init__(self, job_path: Path):
        self.job_path = private_path(job_path)
        self.job = json.loads(self.job_path.read_text(encoding='utf-8'))
        self.output = self.job_path.parent / 'outputs'
        self.handles, self.decks = {}, {}
        self.deck_records, self.validations = {}, {}
        self.catalogs = {}
        self.rsi = private_path(Path(self.job.get('rsi_dir', ROOT / '.local/research-ppt/rsi')))
        self.rsi.mkdir(parents=True, exist_ok=True)

    def record(self, kind: str, data: dict):
        with (self.job_path.parent / 'feedback.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps({'kind': kind, **data}, ensure_ascii=False) + '\n')

    def list_inputs(self) -> dict:
        return {'inputs': [{k: row[k] for k in ('document_id', 'name', 'version_sha256')}
                           for row in self.job['inputs']], 'instruction': self.job['instruction'],
                'slide_count': self.job['slides'], 'output_enabled': self.job['allow_output'],
                'template': self.job.get('template', 'academic'),
                'operation': self.job.get('operation', 'generate')}

    def list_templates(self) -> dict:
        return {'templates': [
            {'id': 'academic', 'purpose': '学术会议，白底深蓝、统一标题与来源'},
            {'id': 'lab', 'purpose': '组会，白底青色、支持方法比较与结果图表'}],
            'layouts': ['title','content','image','table','chart','section','comparison','process'],
            'editable': ['text','tables','native_data_charts','native_process_diagrams'],
            'image_scope': '论文原图及公式保留为图片，不声称曲线或公式对象可编辑'}

    @property
    def input_version(self):
        return hashlib.sha256(json.dumps([row['version_sha256'] for row in self.job['inputs']]).encode()).hexdigest()

    def extract_figure(self, source_id: str, page: int, bbox: list[float] | None = None,
                       candidate_id: str | None = None) -> dict:
        item = self.source(source_id)
        if item['parsed']['format'] != 'pdf' or type(page) is not int or not 1 <= page <= item['parsed']['page_count']:
            raise ValueError('图件裁取需要合法 PDF 页码')
        geometry = pdf_page_geometry(Path(item['row']['path']), page, item['row']['version_sha256'])
        self.current(item['row'])
        candidates = geometry['figure_candidates']
        candidate = None
        if candidate_id is not None:
            matches = [row for row in candidates if row['candidate_id'] == candidate_id]
            if len(matches) != 1:
                raise ValueError('图件候选不存在或已失效，请先 read_page')
            candidate = matches[0]
            if bbox is None:
                bbox = candidate['bbox']
        if (not isinstance(bbox, list) or len(bbox) != 4 or
                any(type(x) not in (int,float) or not 0 <= x <= 1 for x in bbox) or
                not bbox[0] < bbox[2] or not bbox[1] < bbox[3]):
            raise ValueError('bbox 为 [左,上,右,下]，使用 0–1 归一化坐标')
        import fitz
        from .documents import image_record
        whole_page = bbox == [0, 0, 1, 1]
        if candidate_id is not None and whole_page:
            raise ValueError('图件区域缺少可核验的图注和几何证据；先 read_page 选择 figure_candidates')
        if not whole_page:
            requested = fitz.Rect(bbox)
            matches = []
            for row in ([candidate] if candidate is not None else candidates):
                expected = fitz.Rect(row['bbox'])
                overlap = (requested & expected).get_area()
                if (overlap >= expected.get_area() * 0.97
                        and overlap >= requested.get_area() * 0.80):
                    matches.append(row)
            if len(matches) != 1:
                raise ValueError('图件区域缺少可核验的图注和几何证据；先 read_page 选择 figure_candidates')
            candidate = matches[0]
        with fitz.open(item['row']['path']) as pdf:
            sheet = pdf[page-1]
            rect = fitz.Rect(bbox[0]*sheet.rect.width,bbox[1]*sheet.rect.height,
                             bbox[2]*sheet.rect.width,bbox[3]*sheet.rect.height)
            image = image_record(sheet.get_pixmap(matrix=fitz.Matrix(4,4),clip=rect).tobytes('png'),
                                 'crop_'+uuid4().hex[:16],page)
        self.current(item['row'])
        if image is None:
            raise ValueError('图件尺寸不在支持范围，请选择更大的区域')
        image['evidence_scope'] = 'page_evidence' if whole_page else 'caption_geometry_candidate'
        if candidate is not None:
            image['caption'] = candidate['caption']
            image['candidate_id'] = candidate['candidate_id']
        item['parsed']['images'].append(image)
        item['read'] = True
        return {'source_id':source_id,'version_sha256':item['row']['version_sha256'],
                'image_id':image['image_id'],'page':page,'bbox':bbox,
                'width':image['width'],'height':image['height'],
                'evidence_scope':image['evidence_scope'],
                'candidate_id':candidate['candidate_id'] if candidate else None,
                'caption':candidate['caption'] if candidate else None,
                'scope':('完整来源页，仅为页面证据，不能称已定位某张原图' if whole_page else
                         '图注和可见图形几何支持的裁图候选；图件含义与完整性仍需审阅')}

    def current(self, row: dict):
        if file_hash(Path(row['path'])) != row['version_sha256']:
            raise ValueError('输入版本已变化，请重新准备任务')

    def pin_source(self, document_id: str) -> dict:
        rows = [row for row in self.job['inputs'] if row['document_id'] == document_id]
        if len(rows) != 1:
            raise ValueError('输入标识未获准访问')
        row = rows[0]
        self.current(row)
        handle = 'source-' + hashlib.sha256((document_id + row['version_sha256']).encode()).hexdigest()[:32]
        if handle in self.handles:
            parsed = self.handles[handle]['parsed']
        else:
            parsed = parse_document(Path(row['path']))
            self.current(row)
            self.handles[handle] = {'row': row, 'parsed': parsed, 'read': False}
        result = {'document_id': document_id, 'source_id': handle, 'version_sha256': row['version_sha256'],
                  **{k: parsed[k] for k in ('format', 'page_count', 'text_chars')}}
        self.record('source_pinned', result)
        return result

    def source(self, source_id: str) -> dict:
        if source_id not in self.handles:
            raise ValueError('未知 source_id，请先 pin_source')
        value = self.handles[source_id]
        self.current(value['row'])
        return value

    def read_source(self, source_id: str) -> dict:
        item = self.source(source_id)
        parsed = item['parsed']
        if not parsed['text_chars']:
            self.record('source_failed', {'source_id': source_id, 'reason': 'no_text'})
            raise ValueError('无法提取文本，首版不支持扫描件 OCR')
        remaining, pages = 24000, []
        for p in parsed['pages']:
            text = p['text'][:max(0, remaining)]
            pages.append({'page': p['page'], 'text': text, 'truncated': p['truncated'] or len(text) < len(p['text'])})
            remaining -= len(text)
        item['read'] = True
        return {'source_id': source_id, 'document_id': item['row']['document_id'],
                'version_sha256': item['row']['version_sha256'], 'pages': pages,
                'images': [{k: v for k, v in img.items() if k != 'data'} for img in parsed['images']],
                'warnings': parsed['warnings'], 'read_page_for_truncated_text': any(p['truncated'] for p in pages)}

    def read_page(self, source_id: str, page: int) -> dict:
        item = self.source(source_id)
        if type(page) is not int or not 1 <= page <= item['parsed']['page_count']:
            raise ValueError('页码越界')
        geometry = (pdf_page_geometry(Path(item['row']['path']), page, item['row']['version_sha256'])
                    if item['parsed']['format'] == 'pdf' else {})
        self.current(item['row'])
        item['read'] = True
        return {'source_id': source_id, 'version_sha256': item['row']['version_sha256'],
                **item['parsed']['pages'][page-1], **geometry}

    def pinned_figure_tool(self) -> dict:
        from .generated_tools import load_certified_tool
        certificate = self.job.get('generated_tool_certificate')
        if not certificate:
            raise ValueError('此任务未配置独立认证的生成工具')
        path = private_path(Path(certificate))
        if file_hash(path) != self.job.get('generated_tool_certificate_sha256'):
            raise ValueError('生成工具认证版本已变化，请重新准备任务')
        return load_certified_tool(path)

    def pin_figure_catalog(self, document_id: str) -> dict:
        tool = self.pinned_figure_tool()
        pinned = self.pin_source(document_id)
        item = self.source(pinned['source_id'])
        if item['parsed']['format'] != 'pdf':
            raise ValueError('图件目录仅支持真实 PDF')
        handle = 'source-' + hashlib.sha256(('figure-catalog:' + document_id + pinned['version_sha256'] + tool['code_sha256']).encode()).hexdigest()[:32]
        self.catalogs[handle] = {'document_id': document_id, 'source_id': pinned['source_id'],
                                 'version_sha256': pinned['version_sha256'], 'tool_code_sha256': tool['code_sha256']}
        # 图件定位与提取使用同一真实来源；新句柄限制为此证书的目录作用域。
        self.handles[handle] = item
        return {'document_id': document_id, 'source_id': handle,
                'version_sha256': pinned['version_sha256'], 'page_count': pinned['page_count'],
                'generated_tool': tool['name'], 'tool_code_sha256': tool['code_sha256']}

    def read_generated_catalog(self, source_id: str) -> dict:
        from .figure_catalog import catalog_input, verify_catalog
        from .generated_tools import run_certified_tool
        if source_id not in self.catalogs:
            raise ValueError('未知图件目录句柄，请先 pin_figure_catalog')
        bound = self.catalogs[source_id]
        tool = self.pinned_figure_tool()
        if tool['code_sha256'] != bound['tool_code_sha256']:
            raise ValueError('生成工具认证版本已变化，请重新准备任务')
        item = self.source(source_id)
        payload = catalog_input(Path(item['row']['path']), source_id, bound['version_sha256'])
        if self.job.get('catalog_execution') == 'manual':
            from .figure_catalog import expected_catalog
            result = expected_catalog(payload)
            execution = {'implementation': 'human_written_reference_not_model_generated'}
        else:
            executed = run_certified_tool(tool['certificate_path'], payload)
            result = executed['output']
            execution = {'implementation': 'deepseek_generated_compiled_typescript',
                         'execution_sha256': executed['execution_sha256']}
        verify_catalog(payload, result)
        self.current(item['row'])
        item['read'] = True
        self.record('figure_catalog_read', {'source_id': source_id, 'tool': tool['name'],
            'source_sha256': bound['version_sha256'], 'tool_code_sha256': tool['code_sha256'],
            'figure_count': len(result['figures']), **execution})
        return {**result, 'evidence_scope': 'caption_geometry_only_not_scientific_certification',
                'tool_code_sha256': tool['code_sha256']}

    def render_deck(self, plan: dict) -> dict:
        if not self.job['allow_output']:
            raise ValueError('任务处于预览模式，未授权生成文件')
        if (not isinstance(plan, dict) or not {'title','slides'} <= set(plan) or
                set(plan) - {'title','slides','template'} or not isinstance(plan['slides'], list)):
            raise ValueError('计划需要 title 和 slides')
        if len(plan['slides']) != self.job['slides']:
            raise ValueError(f"任务要求总共 {self.job['slides']} 页")
        deck = copy.deepcopy(plan)
        deck.setdefault('template', self.job.get('template','academic'))
        normalized_pages = []
        for page, slide in enumerate(deck['slides'], 1):
            if isinstance(slide, dict) and 'bullets' not in slide:
                # 缺失的正文列表没有内容可删；显式 null/错误类型仍由协议拒绝。
                slide['bullets'] = []
                normalized_pages.append(page)
        if normalized_pages:
            self.record('plan_normalized', {'action':'missing_empty_bullets','pages':normalized_pages})
        if self.job.get('layout_policy'):
            from .layout_learning import validate_certificate
            path = private_path(Path(self.job['layout_policy_certificate']))
            if file_hash(path) != self.job['layout_policy_certificate_sha256']:
                raise ValueError('布局策略认证版本改变，请重新准备任务')
            certificate = validate_certificate(path)
            checked = node('layout-policy-cli.js', certificate['policy'])
            if checked.get('valid') is not True or checked.get('policy_digest') != self.job['layout_policy_digest']:
                raise ValueError('布局策略摘要或协议无效')
            deck['layout_policy'] = checked['policy']
        for slide in deck['slides']:
            if not isinstance(slide, dict) or set(slide) - {'title','bullets','sources','notes','image','table','chart','layout','comparison','process','takeaway'}:
                raise ValueError('幻灯片包含不支持的字段')
            citations = slide.get('sources')
            if not isinstance(citations, list) or not citations:
                raise ValueError('每页必须声明 sources: [{source_id, page}]')
            resolved = []
            for cite in citations:
                if not isinstance(cite, dict) or set(cite) != {'source_id', 'page'}:
                    raise ValueError('来源需要 source_id 和 page')
                item = self.source(cite['source_id'])
                if not item['read'] or type(cite['page']) is not int or not 1 <= cite['page'] <= item['parsed']['page_count']:
                    raise ValueError('来源尚未读取或页码越界')
                resolved.append(f"{item['row']['name']} 第 {cite['page']} 页; SHA256 {item['row']['version_sha256']}")
            slide['sources'] = resolved
            if slide.get('image') is not None:
                image = slide['image']
                if not isinstance(image, dict) or set(image) != {'source_id', 'image_id'}:
                    raise ValueError('图片必须引用 source_id 和 image_id，不接受路径或 URL')
                item = self.source(image['source_id'])
                if not item['read']:
                    raise ValueError('图片来源尚未读取')
                matches = [x for x in item['parsed']['images'] if x['image_id'] == image['image_id']]
                if len(matches) != 1:
                    raise ValueError('图片标识不存在')
                slide['image'] = {k: matches[0][k] for k in ('data','width','height')}
                slide['sources'].append(f"{item['row']['name']} 图片 {image['image_id']} 第 {matches[0]['page']} 页")
                if matches[0].get('caption'):
                    slide['sources'].append('原图定位图注（几何候选，语义未认证）：' + matches[0]['caption'][:180])
                elif matches[0].get('evidence_scope') == 'page_evidence':
                    slide['sources'].append('整页页面证据；未定位或认证任何特定图件')
        run_dir = self.output / uuid4().hex
        run_dir.mkdir(parents=True, exist_ok=False)
        encoded = json.dumps(deck, ensure_ascii=False)
        (run_dir / 'plan.json').write_text(encoded, encoding='utf-8')
        target = run_dir / 'presentation.pptx'
        try:
            try:
                result = node('render.js', {}, str(run_dir / 'plan.json'), str(target))
            except RenderFailure as exc:
                if not self.job.get('layout_policy') or exc.report.get('code') not in {
                        'text_overflow','table_overflow','chart_label_overflow','out_of_bounds','content_overlap'}:
                    raise
                # 保留失败候选与原计划；在新目录中回退，不能覆盖失败证据。
                self.record('layout_policy_fallback', {'policy_digest':self.job['layout_policy_digest'],
                    'failed_run_id':run_dir.name,'reason':str(exc)[-1000:]})
                deck.pop('layout_policy',None)
                run_dir = self.output / uuid4().hex
                run_dir.mkdir(parents=True,exist_ok=False)
                (run_dir/'plan.json').write_text(json.dumps(deck,ensure_ascii=False),encoding='utf-8')
                target = run_dir/'presentation.pptx'
                result = node('render.js', {}, str(run_dir/'plan.json'), str(target))
                result['layout_policy_fallback'] = True
            result.pop('layout_manifest',None)
            report = inspect_pptx(target)
            if not report['each_slide_has_editable_text'] or report['slide_count'] != self.job['slides']:
                raise ValueError('产物可编辑性或页数检查失败')
        except Exception as exc:
            self.record('render_failed', {'reason': str(exc)[:1500], 'run_id': run_dir.name})
            raise
        (run_dir / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        self.decks[run_dir.name] = target
        request_plan = copy.deepcopy(plan)
        for slide in request_plan['slides']:
            slide.setdefault('bullets', [])
        self.deck_records[run_dir.name] = {'sha256': report['file_sha256'], 'sources': [s['sources'] for s in deck['slides']],
            'input_version':self.input_version, 'plan': deck, 'request_plan': request_plan}
        self.record('render_passed', {'deck_id': run_dir.name, **report})
        return {'deck_id': run_dir.name, 'path': str(target), 'input_version':self.input_version, **result, **report}

    def read_deck_plan(self, deck_id: str) -> dict:
        self.checked_deck(deck_id)
        record = self.deck_records[deck_id]
        if 'request_plan' not in record:
            raise ValueError('局部修订仅支持本任务生成并保留完整计划的 PPT')
        return {'deck_id': deck_id, 'input_version': self.input_version,
                'file_sha256': record['sha256'], 'plan': copy.deepcopy(record['request_plan'])}

    def revise_deck(self, deck_id: str, updates: list[dict]) -> dict:
        from .revision import merge_slide_updates, verify_unmodified_slides
        if not self.job['allow_output']:
            raise ValueError('任务处于预览模式，未授权生成文件')
        original = self.checked_deck(deck_id)
        plan = self.read_deck_plan(deck_id)['plan']
        merged = merge_slide_updates(plan, updates)
        result = self.render_deck(merged)
        new_id = result['deck_id']
        try:
            audit = verify_unmodified_slides(self.checked_deck(deck_id), self.checked_deck(new_id), [row['page'] for row in updates])
        except ValueError:
            self.decks.pop(new_id, None)
            self.deck_records.pop(new_id, None)
            self.record('revision_rejected', {'parent_deck_id': deck_id, 'candidate_deck_id': new_id})
            raise ValueError('局部修订改变了非目标页面，拒绝交付') from None
        self.record('revision_passed', {'parent_deck_id': deck_id, 'deck_id': new_id, 'audit': audit})
        return {**result, 'parent_deck_id': deck_id, 'revision_audit': audit,
                'next_action': '重新 inspect_deck、validate_deck、deliver_deck；旧 validation_id 不适用新副本。'}

    def checked_deck(self, deck_id: str) -> Path:
        if deck_id not in self.decks or deck_id not in self.deck_records:
            raise ValueError('未知 deck_id')
        for row in self.job['inputs']:
            self.current(row)
        target = self.decks[deck_id]
        if file_hash(target) != self.deck_records[deck_id]['sha256']:
            raise ValueError('产物版本已变化，旧核验失效')
        return target

    def inspect_deck(self, deck_id: str) -> dict:
        target = self.checked_deck(deck_id)
        return {'deck_id':deck_id,'input_version':self.input_version,**inspect_pptx(target)}

    def checked_validation_artifacts(self, report: dict):
        """缓存核验不能授权交付随后缺失、替换或越界的 PDF/PNG。"""
        message = '核验预览产物已缺失或变化，旧核验失效'
        artifacts = report.get('artifacts')
        if not isinstance(artifacts, list) or (report.get('passed') and not artifacts):
            raise ValueError(message)
        for artifact in artifacts:
            if (not isinstance(artifact, dict) or not isinstance(artifact.get('path'), str)
                    or not isinstance(artifact.get('sha256'), str)):
                raise ValueError(message)
            try:
                path = private_path(Path(artifact['path']))
                if file_hash(path) != artifact['sha256']:
                    raise ValueError(message)
            except (OSError, ValueError):
                # 不回传失效预览的路径或底层文件异常。
                raise ValueError(message) from None

    def validate_deck(self, deck_id: str) -> dict:
        from .validation import validate_delivery
        target = self.checked_deck(deck_id)
        record = self.deck_records[deck_id]
        previous = next((row for row in self.validations.values() if row['deck_id']==deck_id), None)
        if previous is not None:
            self.checked_validation_artifacts(previous)
            return previous
        report = validate_delivery(target,self.job['slides'],expected_sources=record['sources'])
        self.checked_deck(deck_id)
        validation_id = 'validation-'+uuid4().hex
        result = {**report,'validation_id':validation_id,'deck_id':deck_id,'input_version':self.input_version,
                  'file_sha256':record['sha256']}
        self.validations[validation_id] = result
        self.record('delivery_validation',{'deck_id':deck_id,'validation_id':validation_id,'passed':report['passed']})
        return result

    def deliver_deck(self, validation_id: str) -> dict:
        report = self.validations.get(validation_id)
        if report is None or not report['passed']:
            raise ValueError('未通过真实渲染与完整性检查，不能标记为已交付')
        target = self.checked_deck(report['deck_id'])
        self.checked_validation_artifacts(report)
        return {'validation_id':validation_id,'deck_id':report['deck_id'],'path':str(target),
                'input_version':self.input_version,'file_sha256':report['file_sha256'],
                'artifacts':report['artifacts'],'warnings':report['warnings'],
                'scientific_quality':'未完成人工事实和视觉审阅','editable':True}

    def build_delivery(self, plan: dict) -> dict:
        """普通组合脚本对照：同一生成和验收函数，不另外实现 Agent 循环。"""
        if self.job.get('operation') == 'restyle':
            if (not isinstance(plan, dict) or set(plan) != {'operation', 'source_id', 'template'}
                    or plan['operation'] != 'restyle'):
                raise ValueError('风格转换组合计划需要 operation、source_id 和 template')
            rendered = self.restyle_deck(plan['source_id'], plan['template'])
        else:
            rendered = self.render_deck(plan)
        self.inspect_deck(rendered['deck_id'])
        checked = self.validate_deck(rendered['deck_id'])
        if not checked['passed']:
            return {'delivered':False,**checked}
        return {'delivered':True,**self.deliver_deck(checked['validation_id'])}

    def restyle_deck(self, source_id: str, template: str) -> dict:
        if not self.job['allow_output']:
            raise ValueError('任务处于预览模式，未授权生成文件')
        from .restyle import restyle
        item = self.source(source_id)
        if item['parsed']['format'] != 'pptx' or item['parsed']['page_count'] != self.job['slides']:
            raise ValueError('风格转换需 PPTX 输入，目标页数必须与原文件一致')
        run_dir = self.output / uuid4().hex
        run_dir.mkdir(parents=True,exist_ok=False)
        target = run_dir/'presentation.pptx'
        label = f"{item['row']['name']}; SHA256 {item['row']['version_sha256']}"
        report = restyle(Path(item['row']['path']),target,template,label)
        self.current(item['row'])
        self.decks[run_dir.name] = target
        self.deck_records[run_dir.name] = {'sha256':report['file_sha256'],'input_version':self.input_version,
            'sources':[[f'来源：{label}，原幻灯片 {i+1}'] for i in range(report['slide_count'])]}
        self.record('restyle_passed',{'deck_id':run_dir.name,**report})
        return {'deck_id':run_dir.name,'path':str(target),'input_version':self.input_version,**report}

    def guard_attempt_count(self) -> int:
        """Persistent per-job quota, including proposals predating the quota files."""
        attempts = self.job_path.parent / 'rsi-attempts'
        used = max((int(path.stem.split('-')[1]) for path in attempts.glob('attempt-*.json')), default=0)
        feedback = self.rsi / 'feedback.jsonl'
        if feedback.exists():
            completed = sum(json.loads(line).get('job_id') == self.job['job_id']
                            for line in feedback.read_text(encoding='utf-8').splitlines() if line.strip())
            used = max(used, completed)
        return used

    def reserve_guard_attempt(self) -> int:
        attempts = self.job_path.parent / 'rsi-attempts'
        attempts.mkdir(exist_ok=True)
        # Exclusive creation prevents parallel MCP requests spending the same
        # slot. Reserve before schema validation; a rejected attempt also costs.
        for number in range(self.guard_attempt_count() + 1, 4):
            try:
                with (attempts / f'attempt-{number}.json').open('x', encoding='utf-8') as stream:
                    json.dump({'job_id': self.job['job_id'], 'attempt': number}, stream)
            except FileExistsError:
                continue
            self.record('rsi_attempt', {'attempt': number, 'limit': 3})
            return number
        raise ValueError('本任务 RSI 准入提案已达 3 次上限，保持原有 active 版本')

    def rsi_status(self) -> dict:
        active = self.rsi / 'active-guard.json'
        feedback = self.rsi / 'feedback.jsonl'
        task_feedback = self.job_path.parent / 'feedback.jsonl'
        attempts = self.guard_attempt_count()
        return {'active': json.loads(active.read_text(encoding='utf-8')) if active.exists() else None,
                'guard_attempt_limit': 3, 'guard_attempts_used': attempts,
                'attempts_remaining': max(0, 3 - attempts),
                'task_feedback': [json.loads(line) for line in task_feedback.read_text(encoding='utf-8').splitlines()[-10:]] if task_feedback.exists() else [],
                'feedback': [json.loads(line) for line in feedback.read_text(encoding='utf-8').splitlines()[-10:]] if feedback.exists() else [],
                'candidate_schema': {'schema_version': 1, 'formats': ['pdf','pptx'], 'min_text_chars': 'integer 1..1000', 'max_pages': 'integer 1..200'},
                'scope': '额外约束结构复用的准入条件；不能绕过公共 Motif 认证、来源版本或权限守卫'}

    def propose_guard(self, program: dict) -> dict:
        if not self.job.get('allow_rsi', False):
            raise ValueError('此任务未启用 RSI 更新')
        self.reserve_guard_attempt()
        result = node('guard-cli.js', program)
        proposal_id = uuid4().hex
        record = {'proposal_id': proposal_id, 'job_id': self.job['job_id'], **result}
        (self.rsi / f'proposal-{proposal_id}.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        if result.get('accepted'):
            active = self.rsi / 'active-guard.json'
            record['previous'] = json.loads(active.read_text(encoding='utf-8'))['program_digest'] if active.exists() else None
            temporary = self.rsi / f'active-{proposal_id}.tmp'
            temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(active)
        with (self.rsi / 'feedback.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        return record

    def layout_policy_status(self) -> dict:
        from .layout_learning import status
        return status(self.job, self.job_path)

    def propose_layout_policy(self, policy: dict) -> dict:
        from .layout_learning import propose
        return propose(self.job, self.job_path, policy)
