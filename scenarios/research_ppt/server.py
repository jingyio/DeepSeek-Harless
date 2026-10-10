"""科研 PPT MCP；输出权限来自准备阶段固定的 job 文件。"""
from pathlib import Path
from functools import wraps
import json
import os
import re
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from scenarios.research_ppt.service import PPTService, RenderFailure


_SAFE_ERRORS = {
    '任务处于预览模式，未授权生成文件': ('output_permission_denied', '需要用户明确授权输出；保持预览模式，不能绕过权限。'),
    '此任务未启用 RSI 更新': ('rsi_permission_denied', '需要用户明确授权 RSI 更新；不能自行修改任务权限。'),
    '本任务 RSI 准入提案已达 3 次上限，保持原有 active 版本': ('rsi_attempt_limit', '停止本任务准入提案；原有 active 版本保留，不能重置任务或扩大权限绕过上限。'),
    '输入版本已变化，请重新准备任务': ('source_version_changed', '重新准备并读取当前来源，再重新生成完整计划。'),
    '产物版本已变化，旧核验失效': ('artifact_version_changed', '重新生成并核验当前产物，不能交付旧核验结果。'),
    '核验预览产物已缺失或变化，旧核验失效': ('preview_artifact_version_changed', '调用 render_deck/restyle_deck 生成新副本，再 validate_deck 重建 PDF/PNG；不能复用旧 validation_id 或交付失效预览。'),
    '输入标识未获准访问': ('invalid_source', '使用 list_inputs 返回的 document_id。'),
    '未知 source_id，请先 pin_source': ('invalid_source', '先用 pin_source 获取真实 source_id，再读取并引用。'),
    '来源尚未读取或页码越界': ('invalid_source', '读取该来源并使用实际有效页码，保留每页 sources。'),
    '页码越界': ('invalid_source', '使用已固定来源的合法页码。'),
    '来源需要 source_id 和 page': ('invalid_plan', 'sources 每项使用真实 source_id 与整数 page。'),
    '每页必须声明 sources: [{source_id, page}]': ('invalid_plan', '为每页补充真实来源与页码，保留用户要求的完整页数。'),
    '计划需要 title 和 slides': ('invalid_plan', '提交包含 title 与完整 slides 的计划，只使用支持字段。'),
    '幻灯片包含不支持的字段': ('invalid_plan', '使用规定的页面字段，修正完整计划后重试。'),
    '图片必须引用 source_id 和 image_id，不接受路径或 URL': ('invalid_image', '引用 read_source 或 extract_figure 返回的真实 source_id/image_id。'),
    '图片来源尚未读取': ('invalid_image', '先读取或提取来源中的真实图件，再生成计划。'),
    '图片标识不存在': ('invalid_image', '重新查看 read_source 的 images 或调用 extract_figure，使用真实返回的 image_id；不要编造标识。'),
    '图件裁取需要合法 PDF 页码': ('invalid_image', '选择已固定 PDF 来源的有效页码。'),
    'bbox 为 [左,上,右,下]，使用 0–1 归一化坐标': ('invalid_image', '提交四个 0–1 坐标，左小于右、上小于下。'),
    '图件尺寸不在支持范围，请选择更大的区域': ('invalid_image', '选择更大的有效区域重新提取。'),
    '图件候选不存在或已失效，请先 read_page': ('invalid_image', '读取实际含图注的页，使用本次 figure_candidates 返回的 candidate_id。'),
    '图件区域缺少可核验的图注和几何证据；先 read_page 选择 figure_candidates': ('invalid_image', '禁止猜 bbox；先 read_page 读取实际图注和候选，用 candidate_id 提取。无候选时说明定位限制或仅保留整页证据。'),
    '风格转换组合计划需要 operation、source_id 和 template': ('invalid_plan', '此任务为 restyle；build_delivery 使用 {operation:restyle,source_id:真实句柄,template:academic或lab}。'),
    '未知 deck_id': ('invalid_artifact', '使用本次成功 render_deck/restyle_deck 返回的 deck_id。'),
    '未通过真实渲染与完整性检查，不能标记为已交付': ('validation_failed', '先 validate_deck，修复其报告的问题后重新核验。'),
    '产物可编辑性或页数检查失败': ('validation_failed', '检查完整内容计划与用户页数要求，重新生成并核验。'),
    '风格转换需 PPTX 输入，目标页数必须与原文件一致': ('invalid_plan', '使用 PPTX 输入并保持原始页数，再执行风格转换。'),
    '模板只能是 academic 或 lab': ('invalid_plan', '选择 list_templates 返回的 academic 或 lab。'),
    '风格转换改变了原始文字，拒绝交付': ('validation_failed', '保留原始文字后重新生成风格转换副本。'),
    '风格转换改变了原始布局，拒绝交付': ('validation_failed', '保留原对象位置与表格尺寸后重新生成转换副本。'),
    '风格转换改变了原始讲者备注，拒绝交付': ('validation_failed', '保留完整原讲者备注，来源说明仅追加，再核验副本。'),
    '风格转换改变了原始图像、图表或嵌入数据，拒绝交付': ('validation_failed', '保留原始媒体与数据后重新生成风格转换副本。'),
    '无法提取文本，首版不支持扫描件 OCR': ('unsupported_input', '请求可提取文字的来源或补充文本；不要编造扫描件内容。'),
    '首版不处理加密 PDF': ('unsupported_input', '提供允许读取的非加密 PDF。'),
    '首版限制 1–200 页': ('unsupported_input', '提供 1–200 页来源。'),
    '首版只接收 PDF/PPTX': ('unsupported_input', '提供 PDF 或 PPTX 输入。'),
    '输入必须是小于 30 MiB 的文件': ('unsupported_input', '提供小于 30 MiB 的输入。'),
    'PPTX 展开大小超出限制': ('unsupported_input', '提供满足大小限制的 PPTX。'),
    '请先在 scenarios/research_ppt 运行 npm ci 和 npm run build': ('dependency_missing', '由开发者安装并构建场景依赖后重试。'),
    '此任务未配置独立认证的生成工具': ('generated_tool_unavailable', '使用当前任务允许的工具；生成工具必须先通过独立认证。'),
    '生成工具认证版本已变化，请重新准备任务': ('generated_tool_version_changed', '停止旧证书调用，重新核对代码与认证证据。'),
    '图件目录仅支持真实 PDF': ('unsupported_input', '图件目录使用 PDF；已有 PPTX 使用来源读取与副本修订入口。'),
    '未知图件目录句柄，请先 pin_figure_catalog': ('invalid_source', '先 pin_figure_catalog 获取真实目录作用域 source_id。'),
    '生成目录与真实图件候选不一致，拒绝使用': ('generated_tool_validation_failed', '保留失败记录，回到 read_page 获取真实候选，不使用该目录。'),
    '局部修订仅支持本任务生成并保留完整计划的 PPT': ('revision_unavailable', '只修订本任务生成的 deck_id；已有外部 PPT 内容修改目前需显式重建。'),
    '局部修订改变了非目标页面，拒绝交付': ('revision_preservation_failed', '原稿保留；重新核对修改范围与布局后生成新副本。'),
    'updates 必须是非空列表': ('invalid_plan', 'updates 使用 [{page:整数,changes:仅要修改的字段}]。'),
    '每项修订仅接受 page 和 changes': ('invalid_plan', '每项修订只包含 page 和 changes。'),
    '修订页码必须是有效的 1-based 整数': ('invalid_plan', '使用实际页数范围内的整数 page。'),
    '修订页码重复': ('invalid_plan', '同一页的修改合并成一项 changes，不重复列 page。'),
    'changes 必须包含合法的幻灯片字段，不能有未知字段': ('invalid_plan', 'changes 只包含要修改的已有页面字段。'),
    '幻灯片必须包含 title/bullets/sources，且不能有未知字段': ('invalid_plan', '保留完整 title、bullets 和 sources，使用已支持的页面字段。'),
}
_RENDER_ERRORS = {
    '需要标题、1–30 页幻灯片及可选 academic/lab 模板',
    '超出文本容量或缺少合法来源，请修改计划', '不支持的 layout',
    '每页只能选择图片、表格、数据图或双栏比较之一', '图片格式或尺寸无效',
    '表格需要 2–6 行、1–4 列及短单元格',
    '数据图只接受 bar/line、2–10 个分类、1–3 组对应的有限数值；请勿猜测数据',
    '双栏比较需要 left/right 的 title 和 bullets，页级 bullets 留空',
    '每页只能选择图片、表格、数据图、双栏比较或流程图之一',
    'process 需要 layout=process、2–5 个短 label/detail 步骤，页级 bullets 留空',
    'takeaway 应是 1–90 字符的短结论，必须由调用者核对来源',
    'layout 与页面内容类型不一致', '正文文本溢出，请缩短或分成两页',
    '表格文本溢出，请缩短单元格或分成多页', '图表分类标签过长，请缩短标签或减少分类',
    '准入程序必须使用固定 schema，且不能放宽外层边界',
}
_ROLE = r'(?:title|body_[1-5]|left_heading|right_heading|left_[1-4]|right_[1-4]|footer|page)'


def _safe_failure(exc: ValueError) -> dict:
    """仅公开已知业务消息，禁止把 Node stderr、路径或输入内容回传。"""
    message = str(exc)
    if isinstance(exc, RenderFailure):
        report = exc.report
        code = report.get('code')
        actions = {
            'text_overflow': '缩短具体位置的文字，保持事实条件、来源和指定总页数。',
            'table_overflow': '缩短表格单元格或重组本页内容，保持数据和比较条件。',
            'chart_label_overflow': '缩短图表标签，保持原始数值和单位。',
            'out_of_bounds': '减少本页密度并使用支持的页面结构，保持来源和总页数。',
            'content_overlap': '缩短或重组本页内容，保持科研条件和总页数。',
        }
        if code in actions:
            feedback = {'error': code, 'message': '确定性版面检查拒绝了本页计划。', 'next_action': actions[code]}
            if type(report.get('page')) is int and 1 <= report['page'] <= 30:
                feedback['page'] = report['page']
            if isinstance(report.get('role'), str) and re.fullmatch(r'[a-z_0-9]{1,64}', report['role']):
                feedback['role'] = report['role']
            return feedback
        # schema 错误仍通过白名单消息恢复，不公开任意 JSON 内容。
        message = '场景 Node 工具执行失败: ' + message
    if message in _SAFE_ERRORS:
        code, action = _SAFE_ERRORS[message]
        return {'error': code, 'message': message, 'next_action': action}
    if re.fullmatch(r'修订字段 (?:title|bullets|sources|notes|image|table|chart|layout|comparison|process|takeaway) 的类型或结构无效', message):
        return {'error': 'invalid_plan', 'message': message,
                'next_action': '使用 read_deck_plan 查看原字段格式，只修改明确要求的页和字段后重试。'}
    if re.fullmatch(r'任务要求总共 (?:[1-9]|[12][0-9]|30) 页', message):
        return {'error': 'invalid_plan', 'message': message,
                'next_action': '按要求提交完整页数的计划；保留每页真实 sources，修正后重试。'}
    if message.startswith('场景 Node 工具执行失败: '):
        for line in message.removeprefix('场景 Node 工具执行失败: ').splitlines():
            candidate = line.strip().removeprefix('Error: ')
            page = re.fullmatch(r'第 ([1-9]|[12][0-9]|30) 页：(.*)', candidate)
            detail = page[2] if page else candidate
            if (detail in _RENDER_ERRORS or re.fullmatch(r'封面/章节页最多 [1-5] 条短句', detail)
                    or re.fullmatch(_ROLE + r' 文本溢出，请缩短正文、标题或分成多页；不会自动删改科研内容', detail)
                    or re.fullmatch(_ROLE + r' 超出版面边界', detail)
                    or re.fullmatch(_ROLE + r' 与 ' + _ROLE + r' 版面重叠', detail)):
                return {'error': 'invalid_plan', 'message': candidate,
                        'next_action': '按具体校验信息修正完整计划后重试，保持指定页数、真实来源与图件引用。'}
    return {'error': 'internal_processing_failed', 'message': '工具内部处理失败，详细信息保留在受保护的服务器日志。',
            'next_action': '请开发者查看本次工具日志；本次调用未成功，不能交付或扩大权限。'}


def _tool_errors(fn, service):
    # wraps 保留函数名、说明、输入/输出注解，因此工具 schema 与顺序不变。
    @wraps(fn)
    def invoke(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError as exc:
            failure = _safe_failure(exc)
            try:
                service.record('tool_rejected', {'tool': fn.__name__, 'reason': failure['message']})
            except Exception:
                # 记日志失败不能吞掉业务错误或伪装成成功。
                pass
            return CallToolResult(is_error=True, content=[TextContent(type='text', text=json.dumps(failure, ensure_ascii=False))])
    return invoke


def create_server(job_path: Path):
    service = PPTService(job_path)
    server = MCPServer('SSS research PPT')

    def list_inputs() -> dict:
        """List the approved inputs, requested slide count and output permission."""
        return service.list_inputs()

    def pin_source(document_id: str) -> dict:
        """Pin one approved PDF/PPTX to a fresh versioned source handle."""
        return service.pin_source(document_id)

    def read_source(source_id: str) -> dict:
        """Read the text and image inventory of a pinned source; reject a changed version."""
        return service.read_source(source_id)

    def read_page(source_id: str, page: int) -> dict:
        """Read a complete page; PDF figure_candidates contain actual caption/graphics geometry, not semantic certification."""
        return service.read_page(source_id, page)

    def list_templates() -> dict:
        """List the supported academic templates and editable layouts."""
        return service.list_templates()

    def extract_figure(source_id: str, page: int, bbox: list[float] | None = None,
                       candidate_id: str | None = None) -> dict:
        """Extract a PDF figure using read_page's candidate_id; legacy bbox must match caption geometry. Whole-page bbox is page evidence only."""
        return service.extract_figure(source_id,page,bbox,candidate_id)

    def render_deck(plan: dict) -> dict:
        """Create a new editable PPTX from a cited slide plan in this task's output directory."""
        return service.render_deck(plan)

    def inspect_deck(deck_id: str) -> dict:
        """Check the generated deck's page count, editable text and package integrity."""
        return service.inspect_deck(deck_id)

    def validate_deck(deck_id: str) -> dict:
        """Render real PDF/previews and check text, notes, pages and geometry; not scientific certification."""
        return service.validate_deck(deck_id)

    def deliver_deck(validation_id: str) -> dict:
        """Return files only after a successful current-version render and integrity validation."""
        return service.deliver_deck(validation_id)

    def build_delivery(plan: dict) -> dict:
        """Ordinary generate/restyle + inspect/validate/deliver script. Restyle plan: {operation:restyle,source_id,template}."""
        return service.build_delivery(plan)

    def restyle_deck(source_id: str, template: str) -> dict:
        """Restyle a PPTX copy, preserving original text/media/charts and slide count."""
        return service.restyle_deck(source_id,template)

    def read_deck_plan(deck_id: str) -> dict:
        """Read this task's generated plan before targeted revision; file/source versions remain checked."""
        return service.read_deck_plan(deck_id)

    def revise_deck(deck_id: str, updates: list[dict]) -> dict:
        """Revise explicit page+changes in a new PPTX; reject any non-target page content/media/layout change. Revalidate the new deck."""
        return service.revise_deck(deck_id, updates)

    def pin_figure_catalog(document_id: str) -> dict:
        """Pin an approved PDF to a unique source-scoped figure-catalog handle, bound to source and certified tool code."""
        return service.pin_figure_catalog(document_id)

    def rsi_status() -> dict:
        """Read the current reuse guard, candidate schema and recent validation feedback."""
        return service.rsi_status()

    def propose_guard(program: dict) -> dict:
        """Submit a bounded guard program; fixed tests reject or activate it and return feedback."""
        return service.propose_guard(program)

    def layout_policy_status() -> dict:
        """Read training layout diagnostics and bounded policy schema; heldout cases remain hidden."""
        return service.layout_policy_status()

    def propose_layout_policy(policy: dict) -> dict:
        """Test a model-proposed bounded layout policy on real training drafts; never activate from schema alone."""
        return service.propose_layout_policy(policy)

    for fn in (list_inputs, list_templates, pin_source, read_source, read_page, extract_figure,
               inspect_deck, deliver_deck, read_deck_plan, rsi_status, layout_policy_status):
        server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(_tool_errors(fn, service))
    for fn in (render_deck, restyle_deck, revise_deck, validate_deck, build_delivery, propose_guard, propose_layout_policy):
        server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))(_tool_errors(fn, service))
    if service.job.get('generated_tool_certificate'):
        tool = service.pinned_figure_tool()
        def generated_reader(source_id: str) -> dict:
            return service.read_generated_catalog(source_id)
        generated_reader.__name__ = tool['name']
        generated_reader.__doc__ = ('Read pinned PDF figure page/caption/bbox via certified DeepSeek-generated TypeScript. '
                                    'Figure interpretation remains a model decision.')
        for fn in (pin_figure_catalog, generated_reader):
            server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(_tool_errors(fn, service))
    return server


if __name__ == '__main__':
    create_server(Path(os.environ['SSS_PPT_JOB'])).run(transport='stdio')
