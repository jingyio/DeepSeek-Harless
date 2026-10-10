"""由私有实验摘要生成中文 PDF；缺失的数据明确写未知，不补造效果。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
SENSITIVE = {'api_key', 'deepseek_api_key', 'password', 'authorization', 'secret', 'access_token', 'refresh_token'}
KINDS = {
    'real_api_execution': '真实云 API 与实际工具执行',
    'historical_real_deepseek_plan_replay': '历史真实 DeepSeek 页面计划的确定性重放',
    'preview': '配置预览，未执行付费实验',
    'synthetic': '合成开发诊断',
    'simulation': '模拟执行',
}
QUALITY_LABELS = {
    'not_reviewed': '质量未评审',
    'quality_not_reviewed': '质量未评审',
    'assistant_aided_review_not_human_blind_review': 'AI 辅助审查，未做人工盲评',
    'human_blind_review_passed': '人工盲评通过',
    'human_blind_review_failed': '人工盲评未通过',
}


def _private(value: str | Path) -> Path:
    root = ROOT.resolve()
    private = (root / '.local').resolve()
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not private.is_relative_to(root) or not path.is_relative_to(private):
        raise ValueError('报告摘要、引用产物和输出必须位于仓库 .local')
    return path


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _display(value, *, money=False):
    if value is None:
        return '未知 / 未记录'
    if money:
        return f'${value:.6f}' if _number(value) is not None else '未知 / 未记录'
    if isinstance(value, bool):
        return '是' if value else '否'
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(_redact(value), ensure_ascii=False, sort_keys=True)
    return str(value)


def _redact(value):
    if isinstance(value, dict):
        return {str(key): '[凭证已隐藏]' if str(key).lower() in SENSITIVE else _redact(item)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _metric(run: dict, *keys):
    for container in (run, run.get('metrics', {}), run.get('ledger', {})):
        if not isinstance(container, dict):
            continue
        for key in keys:
            if key in container and container[key] is not None:
                return container[key]
    return None


def _total(rows: list[dict], *keys):
    """缺项显示未知，避免把缺失账本默认为零成本。"""
    values = [_number(_metric(row, *keys)) for row in rows]
    return sum(values) if rows and all(value is not None for value in values) else None


def _quality(value):
    return QUALITY_LABELS.get(str(value), value)


def _assistant_review(value):
    return {'requires_revision': 'AI 辅助审查：需要修订',
            'no_confirmed_artifact': '无确认成品可审',
            'no_major_issue_observed': 'AI 辅助审查：未观察到重大问题',
            'not_reviewed': '未做辅助审查'}.get(str(value), value)


def _group_name(value):
    if value is None:
        return '未分组'
    return {'steps_baseline': '普通 DSH', 'baseline': '普通 DSH',
            'composed': '组合脚本', 'script': '组合脚本',
            'motif': 'Motif', 'execute': 'Motif',
            'training': '训练轨迹', 'heldout_certification': '独立认证',
            'development': '开发试跑', 'rsi': 'RSI 提案',
            'evaluation': '评测运行', 'auxiliary_revision': '辅助修订',
            'auxiliary_style_diagnostic': '辅助风格诊断'}.get(str(value), str(value))


def _cohort(run):
    return str(run.get('evaluation_cohort_id', run.get('comparison_cohort_id', 'cohort_unrecorded')))


def _run_id(run):
    return Path(run['run_dir']).name if run.get('run_dir') else str(run.get('run_id') or '未记录')


def _task_name(value):
    return {'train-simclr': '训练轨迹：SimCLR',
            'train-vit': '训练轨迹：ViT',
            'certify-clip': '独立认证：CLIP',
            'development-missing-api-environment': '开发试跑：缺 API 环境',
            'development-demo-invalid-plan': '开发试跑：无效计划',
            'development-demo-rate-limit': '开发试跑：请求拒绝诊断',
            'real-rsi-guard-proposal': 'RSI 准入规则提案',
            'assistant-aided-demo-revision': '演示稿辅助修订',
            'final-assisted-revision-02-academic': '最终辅助修订：学术风格',
            'final-assisted-revision-02-lab': '最终辅助修订：组会风格',
            'multi-paper-lab': '多论文组会',
            'vision-method-comparison': '视觉方法比较',
            'lora-short-talk': 'LoRA 短讲',
            'existing-deck-conference': '已有稿会议风格',
            'mixed-material-update': '旧稿与 BERT 更新'}.get(str(value), str(value))


def _status(run):
    value = run.get('status', '未记录运行状态')
    if value == 'complete':
        auxiliary = (run.get('group') == 'auxiliary_revision'
                     or run.get('cost_category') in {'auxiliary_revision', 'auxiliary_style_diagnostic'})
        return '工具交付完成（辅助修订）' if auxiliary else '工具交付完成'
    if value == 'done':
        return '会话完成并程序交付' if run.get('delivery_completed') is True else '会话结束，交付未确认'
    if value == 'incomplete' and run.get('delivery_completed') is True:
        return '会话未完成，成品已确认'
    return {'incomplete': '会话未完成', 'error': '运行错误', 'not_delivered': '未完成交付',
            'tools_done': '修订工具完成', 'missing_dependency': '缺少运行依赖',
            'source_version_changed': '来源版本改变', 'preview': '未执行，仅预览'}.get(str(value), value)


def _validation_reports(value, *, depth=0, seen=None):
    if depth > 6:
        return []
    seen = seen if seen is not None else set()
    if isinstance(value, (list, tuple)):
        return [report for item in value[:100] for report in _validation_reports(item, depth=depth + 1, seen=seen)]
    if isinstance(value, str):
        try:
            path = _private(value)
            if path.suffix.lower() != '.json' or path in seen or not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
                return []
            seen.add(path)
            return _validation_reports(json.loads(path.read_text(encoding='utf-8')), depth=depth + 1, seen=seen)
        except (OSError, ValueError):
            return []
    if not isinstance(value, dict):
        return []
    if isinstance(value.get('artifacts'), list):
        return [value]
    reports = []
    for key in ('reports', 'validation', 'validations', 'report', 'report_path', 'validation_path', 'items', 'path'):
        if key in value:
            reports.extend(_validation_reports(value[key], depth=depth + 1, seen=seen))
    return reports


def _font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    candidates = [os.environ.get('SSS_REPORT_FONT'),
                  '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
                  '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
                  '/usr/share/fonts/truetype/arphic/uming.ttc',
                  '/usr/share/fonts/truetype/arphic/ukai.ttc',
                  'C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simsun.ttc']
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont('ResearchCJK', candidate, subfontIndex=0))
            return 'ResearchCJK', str(Path(candidate).resolve())
        except Exception:
            # Noto CJK 的 PostScript outlines 不被 ReportLab TTFont 支持。
            continue
    raise RuntimeError('缺少可嵌入中文 TrueType 字体；服务器安装 fonts-wqy-microhei 或设置 SSS_REPORT_FONT')


def writer(summary: dict, path: str | Path) -> dict:
    """写入中文实验报告，返回 PDF 及来源摘要 SHA；不执行 API 或修改交付物。"""
    if not isinstance(summary, dict):
        raise ValueError('summary 必须是 JSON 对象')
    output = _private(path)
    if output.suffix.lower() != '.pdf':
        raise ValueError('报告输出必须为 PDF')
    if output.exists():
        raise ValueError('报告路径已存在，请使用新的实验或报告版本，保留历史结果')
    evidence_path = output.with_suffix('.review-evidence.json')
    if evidence_path.exists() or output.with_suffix('.report.json').exists():
        raise ValueError('报告证据或元数据路径已存在，请使用新的报告版本')
    runs = summary.get('runs', [])
    if not isinstance(runs, list) or len(runs) > 100 or any(not isinstance(run, dict) for run in runs):
        raise ValueError('runs 必须是最多 100 项的对象列表')
    preview_selection = summary.get('report_preview_selection')
    if preview_selection is not None and (not isinstance(preview_selection, list)
            or any(not isinstance(value, str) or re.fullmatch(r'[0-9a-fA-F]{64}', value) is None
                   for value in preview_selection)):
        raise ValueError('report_preview_selection 必须是 PPTX SHA256 字符串列表')
    selected_products = None if preview_selection is None else {value.lower() for value in preview_selection}
    comparison_cohorts = list(dict.fromkeys(_cohort(run) for run in runs
                                          if run.get('comparison_included') is True))
    cohort_tags = {cohort: f'C{index + 1}' for index, cohort in enumerate(comparison_cohorts)}

    def run_label(run):
        cohort = cohort_tags.get(_cohort(run), '非对照')
        return f"{_task_name(run.get('task_id'))}\n{cohort} / {_run_id(run)[:8]}"

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether

    font, font_path = _font()
    output.parent.mkdir(parents=True, exist_ok=True)
    kind = summary.get('experiment_type', summary.get('type', 'unknown'))
    experiment_id = str(summary.get('experiment_id', '未记录实验 ID'))
    body = ParagraphStyle('Body', fontName=font, fontSize=10.3, leading=15.5, spaceAfter=7,
                          wordWrap='CJK', allowWidows=0, allowOrphans=0)
    small = ParagraphStyle('Small', parent=body, fontSize=8.3, leading=12, spaceAfter=3)
    heading = ParagraphStyle('Heading', parent=body, fontSize=15, leading=21,
                             textColor=colors.HexColor('#17345C'), spaceBefore=10, spaceAfter=10,
                             keepWithNext=True)
    title = ParagraphStyle('Title', parent=body, fontSize=25, leading=35, spaceAfter=18, keepWithNext=True)
    group_heading = ParagraphStyle('GroupHeading', parent=small, keepWithNext=True)
    caption = ParagraphStyle('Caption', parent=small, alignment=TA_CENTER)
    story = []
    available_width = A4[0] - 88

    def paragraph(value, style=body):
        text = _display(value).replace('\u2011', '-').replace('\u2013', '-').replace('\u2014', '-')
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', ' ', text)
        return Paragraph(escape(text).replace('\n', '<br/>'), style)

    def text(value, style=body):
        story.append(paragraph(value, style))

    def section(value):
        text(value, heading)

    def table(headers, rows, widths=None):
        contents = [[paragraph(cell, small) for cell in headers]]
        contents.extend([[paragraph(cell, small) for cell in row] for row in rows])
        instance = Table(contents, colWidths=widths or [available_width / len(headers)] * len(headers), repeatRows=1, hAlign='LEFT')
        instance.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8EEF6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#17345C')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F8FB')]),
            ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#D6DFE9')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(instance)
        story.append(Spacer(1, 9))

    text('科研 PPT Agent\n实验与交付报告', title)
    text(experiment_id, heading)
    text('实验性质：' + KINDS.get(kind, str(kind)))
    learning_overview = summary.get('learning', {})
    learning_overview = learning_overview if isinstance(learning_overview, dict) else {}

    def learning_count(field, category):
        recorded = _number(learning_overview.get(field))
        if recorded is not None:
            return recorded
        if any('cost_category' in run for run in runs):
            return sum(run.get('cost_category') == category for run in runs)
        return None

    overview_cost = _number(summary.get('total_accounted_usd'))
    overview_quality = summary.get('quality')
    blind_review_label = ('人工未盲评' if overview_quality in {'not_reviewed', 'quality_not_reviewed',
                          'assistant_aided_review_not_human_blind_review'}
                          else _quality(overview_quality) if overview_quality is not None
                          else '人工盲评状态未记录')
    invoice_label = ('账单未核对（实付未知）' if summary.get('invoice_paid_usd') is None
                     else '账单实付已记录；核对状态以原证据为准')
    section('关键记录概览')
    table(['项目', '实际记录'], [
        ['真实对照运行' if kind == 'real_api_execution' else '对照运行记录',
         str(sum(run.get('comparison_included') is True for run in runs)) + ' 个；各轮分别统计'],
        ['训练 / 独立认证',
         _display(learning_count('training_runs', 'training')) + ' 个训练 / '
         + _display(learning_count('heldout_certification_runs', 'heldout_certification')) + ' 个独立认证'],
        ['累计已记录上游请求', summary.get('recorded_upstream_requests')],
        ['代理累计估费（非账单实付）',
         f'${overview_cost:.9f}' if overview_cost is not None else '未知 / 未记录'],
        ['质量与账单核对', blind_review_label + '；' + invoice_label],
    ], [available_width * .43, available_width * .57])
    text('本报告参考团队同伴的实验报告组织方式，区分命令发起者、实际工具执行、交付质量、运行费用和学习成本。')
    if kind == 'historical_real_deepseek_plan_replay':
        text('本次重用历史真实 DeepSeek 生成的页面计划，检验新版工具交付。没有新增模型请求；运行中记录的零 API 费用不能代表重新完成论文理解与叙事的成本。')
    elif kind == 'preview':
        text('本次仅为配置和实验矩阵预览。未执行组不得记为成功或零成本成果。')
    elif kind not in {'real_api_execution'}:
        text('当前实验性质不支持直接作真实产品质量或云 API 降本结论；需结合数据来源与执行记录解释。')
    text('质量边界：程序检查通过不等于科学内容、图表解释或整体视觉交付合格；未提供人工评审记录时，一律视为质量未评审。')

    section('1. 目标、假设与可否定条件')
    text(summary.get('question', '在完成多论文科研 PPT 和已有 PPT 重排任务时，验证结构执行能否减少模型调度，同时保留内容、来源和可编辑交付。'))
    text(summary.get('hypothesis', '待验证：在相同合格标准下，Motif 可以减少不需要语义判断的模型请求，并降低包含重试、恢复和学习认证的总成本。'))
    text('如果整体请求数未下降、合格成果成本上升、来源/版本错误、重要内容缺失或人工修订明显增加，则不能把局部 bypass 作为成功结论。')

    section('2. 任务、来源与实验性质')
    files = summary.get('input_files', [])
    if isinstance(files, list) and files:
        table(['输入 / 匿名来源', '版本 SHA256'], [[item.get('name', item.get('source_id', '未知来源')), item.get('sha256', item.get('version_sha256'))] for item in files if isinstance(item, dict)], [available_width * .36, available_width * .64])
    else:
        text('输入来源及版本：未在摘要中记录。任务文件位置可见逐运行记录，不应据此推断来源版本一致。')
    task_rows = [[run_label(run), _group_name(run.get('group')), _status(run), _quality(run.get('quality', summary.get('quality', '质量未评审')))] for run in runs]
    table(['任务', '组别', '运行状态', '质量状态'], task_rows or [['未记录', '未执行', '未执行', '质量未评审']])
    task_limits = [finding.get('finding') for review in summary.get('auxiliary_reviews', [])
                  if isinstance(review, dict) and review.get('task_id') == 'existing-deck-conference'
                  for finding in review.get('findings', [])
                  if isinstance(finding, dict) and finding.get('severity') == 'experiment_limitation']
    for limitation in dict.fromkeys(task_limits):
        text('已有 PPT 任务条件限制：' + _display(limitation), small)

    section('3. 三组对照与相同条件')
    if comparison_cohorts:
        table(['报告轮次标签', 'evaluation_cohort_id（兼容旧字段）'],
              [[cohort_tags[cohort], cohort] for cohort in comparison_cohorts],
              [available_width * .20, available_width * .80])
        text('C1、C2 等仅为本报告的定位标签，各轮分别统计；非对照运行另列，不混入收益。', small)
    names = {str(run.get('group', '')).lower() for run in runs}
    group_rows = []
    for group, label, purpose in [('baseline', '普通 DSH', '模型逐决策发起工具调用'), ('script', '普通组合工具 / 脚本', '检查简单工程串联是否已经足够'), ('motif', 'DSH + Motif', '认证结构在证据满足时发起后续调用')]:
        matching = [name for name in names if name == group or
                    (group == 'baseline' and name == 'steps_baseline') or
                    (group == 'motif' and name == 'execute') or
                    (group == 'script' and name in {'composite', 'composition', 'composed'})]
        state = '已记录运行' if matching else '未执行 / 本摘要没有该组记录'
        if kind == 'preview':
            state = '未执行 / 仅配置预览'
        elif matching and all(run.get('status') in {'missing_dependency', 'planned', 'preview', 'not_executed', 'skipped'}
                              for run in runs if str(run.get('group', '')).lower() in matching):
            state = '未执行 / 缺依赖或仅有规划记录'
        group_rows.append([label, state, purpose])
    table(['对照组', '本报告状态', '职责'], group_rows)
    text('公平比较应匹配模型版本、提示前缀、工具集合与顺序、任务输入、输出要求、预算、推理模式及质量门槛；未匹配字段必须列为限制。')

    section('4. 模型、Graph 与 Code 的分工')
    table(['层', '负责什么', '本报告能据何种证据确认'], [
        ['LLM', '论文理解、贡献选材、多文档比较、叙事、科学解释和内容修订', '真实调用轨迹与提交页面计划；重放不证明新增理解能力'],
        ['Graph / Motif', '已认证节点依赖、参数流、版本及执行条件；条件不足时交接模型', 'manifest/library 摘要与 bypass 审计；未记录则未知'],
        ['Code / MCP', '文档解析、素材提取、模板应用、原生 PPTX 生成、真实预览和完整性检查', '实际工具结果、PPTX/PDF/PNG 及验收报告'],
    ])
    text('工具仍需实际执行。Motif 命中是命令发起权的局部变化，不应省略读取、渲染、核验或来源守卫。')

    section('5. 有效配置与复现定位')
    configuration = _redact(summary.get('config', {}))
    if isinstance(configuration, dict) and configuration:
        table(['配置项', '记录值'], [[key, _display(value)] for key, value in list(configuration.items())[:60]], [available_width * .30, available_width * .70])
    else:
        text('有效配置快照：未记录。')
    missing = summary.get('missing_configuration', [])
    if missing:
        text('缺失配置：' + _display(missing))
    text('推理模式以实际请求配置为准；只有明确记录 reasoning_effort="off" 或 provider 的 disabled thinking 字段，才记为关闭思考。本报告不替入口补写有效值。')

    section('6. 逐运行请求、Token、费用与耗时')
    # 学习轨迹、认证、开发试跑和辅助修订不能混入测试组收益。
    comparison = [run for run in runs if run.get('comparison_included') is True]
    if comparison:
        comparison_keys = list(dict.fromkeys((_cohort(run),
                                              str(run.get('group'))) for run in comparison))
        def cohort_rows(cohort, group):
            return [run for run in comparison if _cohort(run) == cohort
                    and str(run.get('group')) == group]

        group_rows = []
        for cohort, group in comparison_keys:
            selected = cohort_rows(cohort, group)
            group_rows.append([cohort_tags[cohort] + ' / ' + _group_name(group), len(selected),
                               sum(run.get('status') == 'done' and run.get('delivery_completed') is True for run in selected),
                               _total(selected, 'metrics_budget_gate_request_count', 'upstream_requests', 'paid_model_requests'),
                               _display(_total(selected, 'api_cost_usd', 'budget_accounted_usd'), money=True),
                               _total(selected, 'elapsed_seconds')])
        table(['对照轮次 / 组', '已执行题数', '会话完成且交付', '实际 API 请求', '代理估费 USD', '总耗时秒'], group_rows)
        text('上表仅聚合摘要明确标为 comparison_included=true 的评测运行。完整程序交付需要会话完成且有经核验的交付工具结果；该列仍不代表人工内容质量合格。训练、认证、开发失败和辅助修订费用在逐运行与学费记录中另列。')
        text('不同evaluation_cohort_id（兼容comparison_cohort_id）分别统计；修复后复跑不覆盖首轮失败，也不与首轮合并为同一组均值。')
        table(['对照轮次 / 组', '未命中输入', '缓存命中输入', '输出 Token', 'verified bypass'],
              [[cohort_tags[cohort] + ' / ' + _group_name(group),
                _total(cohort_rows(cohort, group), 'cache_miss_tokens', 'input_tokens', 'prompt_cache_miss_tokens', 'inputTokens'),
                _total(cohort_rows(cohort, group), 'cache_hit_tokens', 'cache_read_input_tokens', 'prompt_cache_hit_tokens', 'cacheReadTokens'),
                _total(cohort_rows(cohort, group), 'completion_tokens', 'output_tokens', 'outputTokens'),
                _total(cohort_rows(cohort, group), 'model_requests_skipped_verified', 'verified_bypass')]
               for cohort, group in comparison_keys])
    else:
        text('摘要未明确指定评测运行（comparison_included=true），故未把学习、演示或修订运行混合成组别收益。下表按实际记录逐项展示。')
    rows = []
    for run in runs:
        rows.append([run_label(run), _group_name(run.get('group')), _metric(run, 'model_requests'),
                     _metric(run, 'metrics_budget_gate_request_count', 'upstream_requests', 'paid_model_requests'),
                     _display(_metric(run, 'api_cost_usd', 'budget_accounted_usd'), money=True),
                     _metric(run, 'elapsed_seconds')])
    table(['任务', '组', '模型请求记录', '上游实际请求', '代理估费 USD', '耗时秒'], rows or [['未执行'] * 6])
    if any('success_request_count' in run or 'ledger_request_records' in run for run in runs):
        table(['任务 / 组', '200 响应', '非200响应', '账本响应记录', '请求计数完整'],
              [[run_label(run) + ' / ' + _group_name(run.get('group')),
                run.get('success_request_count'), run.get('failed_request_count'),
                run.get('ledger_request_records'), run.get('status_counting_complete')]
               for run in runs])
        text('上表的 200 / 非200 次数是账本可见响应的分类；未能确定全部转发请求均有响应记录时，不把账本小计当总请求数。200 响应也不等于已完成账单核对。')
        denials = [run for run in runs if run.get('local_budget_denial_observed') or run.get('http_429_observed_in_harness_log')]
        if denials:
            table(['任务 / 组', '本地预算拒绝', 'Harness 见429', '429来源记录'],
                  [[run_label(run) + ' / ' + _group_name(run.get('group')),
                    run.get('local_budget_denial_observed'), run.get('http_429_observed_in_harness_log'),
                    run.get('http_429_origin')] for run in denials])
            text('本地预算代理也会返回429。只有上游账本有对应429响应时才称上游限流；来源未知时保留未知，不能由会话error推断DeepSeek限流。')
    token_rows = [[run_label(run), _group_name(run.get('group')),
                   _metric(run, 'cache_miss_tokens', 'input_tokens', 'prompt_cache_miss_tokens', 'inputTokens'),
                   _metric(run, 'cache_hit_tokens', 'cache_read_input_tokens', 'prompt_cache_hit_tokens', 'cacheReadTokens'),
                   _metric(run, 'completion_tokens', 'output_tokens', 'outputTokens'),
                   _metric(run, 'model_requests_skipped_verified', 'verified_bypass')] for run in runs]
    table(['任务', '组', '未命中输入', '缓存命中输入', '输出 Token', 'verified bypass'], token_rows or [['未执行'] * 6])
    text('代理累计估费：' + _display(summary.get('total_accounted_usd'), money=True))
    text('真实账单实付：' + _display(summary.get('invoice_paid_usd'), money=True))
    text('费用属性：' + _display(summary.get('billing', '未知；不得将预算上限或代理估费称为账单实付')))
    text('上游实际请求包含被预算代理转发的失败请求，不能等同于已计费成功请求。模型请求记录与上游请求可能因失败或重试不同；Token 合计、缓存状态和内容长度影响费用，不能只用跳过次数推断降本。')

    section('7. 交付质量、失败与人工修订')
    quality_rows, report_cache = [], {}
    for index, run in enumerate(runs):
        reports = _validation_reports(run.get('validation', {}))
        if not reports:
            reports = _validation_reports(run.get('delivery', {}))
        report_cache[index] = reports
        passed = sum(report.get('passed') is True for report in reports)
        errors = [issue.get('code', issue.get('message', '未分类')) if isinstance(issue, dict) else str(issue) for report in reports for issue in report.get('errors', [])]
        quality_rows.append([run_label(run), _group_name(run.get('group')), f'{passed}/{len(reports)}' if reports else '未知 / 未记录',
                             _quality(run.get('quality', '质量未评审')), _display(run.get('human_revision_minutes')),
                             ', '.join(errors)[:500] or _display(run.get('failure', run.get('error')))])
    table(['任务', '组', '程序验收通过', '内容/视觉评审', '人工修订分', '失败 / 异常'], quality_rows or [['未执行'] * 6])
    if any(run.get('assistant_review_status') for run in runs):
        table(['任务 / 组', 'AI 辅助审查', '已检查页面'],
              [[run_label(run) + ' / ' + _group_name(run.get('group')),
                _assistant_review(run.get('assistant_review_status', 'not_reviewed')),
                run.get('assistant_reviewed_pages')] for run in runs])
    text('程序验收包括原生可编辑文字、页数、来源备注、提交文本保留、真实 PDF 与 PNG。它不能核验科学论断是否成立、引用是否充分或图表解释是否正确。')
    text('未提供盲评通过标记和修订时长时，不计算每份合格成果均费，也不声明两组质量等价。失败尝试、限流、恢复费用须保留，不从总成本中剔除。')
    reviews = summary.get('auxiliary_reviews', [])
    if isinstance(reviews, list) and reviews:
        text('AI 辅助审查与修订记录', heading)
        text('以下记录是 Agent 对实际页面及原来源的辅助审查。它不能充当人工盲评，修订稿不能追溯改写成原运行无须修订的成功交付。所有审查均列入索引，正文重点展示重大反例与辅助修订。')
        text('完整审查范围、全部发现、来源证据与修订历史保存在随报告分发的 ' + evidence_path.name + '，按完整 run_id 和 PPTX SHA256 定位；该文件不含原始运行日志。', small)
        run_lookup = {_run_id(run): run for run in runs}
        review_groups = {}
        for review in reviews:
            if isinstance(review, dict):
                matched = run_lookup.get(str(review.get('run_id')), {})
                cohort = _cohort(review) if any(key in review for key in ('evaluation_cohort_id', 'comparison_cohort_id')) else _cohort(matched)
                tag = cohort_tags.get(cohort, '非对照 / 未记录轮次')
                key = (tag, str(review.get('task_id', matched.get('task_id', '辅助修订'))))
                review_groups.setdefault(key, []).append(review)
        for (tag, task), task_reviews in review_groups.items():
            text(tag + ' / ' + _task_name(task), group_heading)
            rows = []
            for review in task_reviews:
                pages = review.get('reviewed_pages')
                page_count = len(pages) if isinstance(pages, list) else pages
                issues = list(dict.fromkeys(str(finding.get('category', finding.get('severity', '未分类')))
                                           for finding in review.get('findings', [])
                                           if isinstance(finding, dict) and finding.get('severity') not in {'checked', 'layout_limit'}))
                rows.append([_group_name(review.get('group', '未记录')),
                             _assistant_review(review.get('assistant_quality_status', 'not_reviewed')),
                             page_count,
                             _run_id(review)[:8] + '\n' + str(review.get('pptx_sha256') or '未记录')[:12],
                             ', '.join(issues) or '详见完整记录'])
            table(['组', '辅助审查结论', '页数', '运行 / 成品摘要', '问题类别'], rows,
                  [available_width * .12, available_width * .29, available_width * .08,
                   available_width * .21, available_width * .30])
            for review in task_reviews:
                for finding in review.get('findings', []):
                    if not isinstance(finding, dict):
                        continue
                    severity = str(finding.get('severity', ''))
                    if not (severity.startswith('major') or severity in {'unsupported_source', 'source_condition_ambiguity'}
                            or finding.get('before') or finding.get('after')):
                        continue
                    page = finding.get('page', finding.get('pages'))
                    label = _group_name(review.get('group')) + ' / 运行 ' + _run_id(review)[:8]
                    if page is not None:
                        label += ' / 页 ' + _display(page)
                    detail = (_display(finding.get('before')) + '；修订：' + _display(finding.get('after'))
                              if finding.get('before') or finding.get('after') else _display(finding.get('finding')))
                    text(label + '：' + detail, small)

    section('8. RSI、学习认证与学费')
    rsi = summary.get('rsi')
    learning = summary.get('learning', summary.get('learning_cost'))
    text('本次 RSI 记录：' + _display(rsi))
    text('本次学习 / 认证开销：' + _display(learning))
    text('未提供候选规则、固定验证反例、独立认证、启用摘要和后续任务记录时，不能宣称本次已发生自主改进。当前受限准入原型与真实轨迹 Motif 学习分别报告。')
    text('首批总成本应包含真实轨迹收集、学习、认证、规则提案、失败重试和人工修订。没有这些数值，不估算回本周期。')

    section('9. 当前结论与可复现证据')
    conclusions = summary.get('conclusions', summary.get('conclusion'))
    if conclusions:
        text(conclusions)
    else:
        text('当前摘要不足以证明稳定降本。已完成的运行和程序验收仅按上表报告，科研与视觉质量未评审的交付不计为已合格。')
    for run in runs:
        paths = {key: run.get(key) for key in ('run_dir', 'log_path', 'job_path') if run.get(key)}
        if paths:
            text(_task_name(run.get('task_id', '未知任务')) + ' / '
                 + _group_name(run.get('group', '未知组')) + ': ' + _display(paths), small)
    story.append(KeepTogether([paragraph('限制：' + _display(summary.get('limitations',
                 '未完成账单核对、人工盲评与真实用户修订时间统计；跨任务稳定收益仍待验证。')))]))

    previews = []
    seen_paths = set()
    omitted = 0
    filtered_references = set()
    embedded_products = set()
    for index, run in enumerate(runs):
        for report in report_cache.get(index, []):
            for artifact in report.get('artifacts', []):
                if not isinstance(artifact, dict) or artifact.get('kind') != 'preview':
                    continue
                product_sha = str(report.get('pptx_sha256', '')).lower()
                if selected_products is not None and product_sha not in selected_products:
                    # 主动选择的附录范围与文件缺失、内容失效、质量结论分开记账。
                    filtered_references.add(str(artifact.get('path', '未记录路径')))
                    continue
                try:
                    preview = _private(artifact['path'])
                    if preview.suffix.lower() not in {'.png', '.jpg', '.jpeg'} or not preview.is_file():
                        omitted += 1
                        continue
                    actual_hash = hashlib.sha256(preview.read_bytes()).hexdigest()
                    if artifact.get('sha256') and actual_hash != artifact['sha256']:
                        omitted += 1
                        continue
                    if preview in seen_paths:
                        continue
                    seen_paths.add(preview)
                    previews.append((run, artifact, preview, report))
                    embedded_products.add(product_sha)
                except (OSError, ValueError, KeyError):
                    omitted += 1

    if previews:
        story.append(PageBreak())
        section('附录：实际 PPT 全部页面预览' if selected_products is None else '附录：选定成品的实际页面预览')
        text('以下图片来自实际 LibreOffice → PDF → PNG 渲染；按记录 SHA256 核对，各页标明运行与成品摘要。缩略页用于交付审阅，不代表人工已完成视觉验收。')
        if selected_products is None:
            text('本附录包含摘要中失败验收和重试的所有可验证预览。', small)
        else:
            text('本报告按 report_preview_selection 中的完整 PPTX SHA256 选择代表成品。其他运行及中间稿的预览已保留在独立成品包 / 原始证据中；不嵌入图片不代表成果缺失、质量通过或从成本中排除。', small)
        cell_width = (available_width - 12) / 2
        for offset in range(0, len(previews), 6):
            if offset:
                story.append(PageBreak())
            cells = []
            for run, artifact, preview, report in previews[offset:offset + 6]:
                image_width, image_height = ImageReader(str(preview)).getSize()
                scaled_height = min(155, cell_width * image_height / image_width)
                scaled_width = scaled_height * image_width / image_height
                label = f"{_task_name(run.get('task_id', '任务'))} / {_group_name(run.get('group', '组别'))} / 第 {artifact.get('page', '?')} 页"
                run_id = _run_id(run)[:8]
                product_id = str(report.get('pptx_sha256', '未记录'))[:12]
                label += f"\n运行 {run_id} / 成品 {product_id} / 程序验收{'通过' if report.get('passed') is True else '未通过'}"
                cells.append([paragraph(label, caption), Image(str(preview), width=scaled_width, height=scaled_height)])
            if len(cells) % 2:
                cells.append('')
            grid = Table([cells[index:index + 2] for index in range(0, len(cells), 2)], colWidths=[cell_width, cell_width], hAlign='LEFT')
            grid.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 12)]))
            story.append(grid)
    else:
        section('附录：实际 PPT 预览')
        if selected_products is None:
            text('摘要没有可验证的实际页面 PNG；本报告没有用示意图或模板图替代真实交付预览。')
        elif not selected_products:
            text('本报告明确选择不嵌入页面预览。实际页面保留在独立成品包 / 原始证据中；该选择不改变交付与质量状态。')
        else:
            text('所选 PPTX SHA256 没有可验证的页面预览，需核对选择与实际验收产物；不能由该结果推断其他运行没有成品。')
    if selected_products is not None:
        text(f'按附录选择未嵌入 {len(filtered_references)} 个其他预览引用；这些项目没有计入文件缺失数量。完整选择摘要见报告元数据。', small)
        unmatched = sorted(selected_products - embedded_products)
        if unmatched:
            text('尚未嵌入预览的所选 PPTX SHA256：' + _display(unmatched), small)
    if omitted:
        text(f'未嵌入 {omitted} 项预览：文件缺失、路径未获准或内容摘要不符，需检查原始验收报告。')

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor('#667388'))
        canvas.drawString(44, 27, '科研 PPT Agent - 私有实验报告')
        canvas.drawRightString(A4[0] - 44, 27, str(document.page))
        canvas.restoreState()

    document = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=44, leftMargin=44,
                                 topMargin=42, bottomMargin=43, title='科研 PPT Agent 实验与交付报告', author='SSS Research PPT')
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    summary_sha = hashlib.sha256(json.dumps(summary, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    evidence = {'schema_version': 1, 'experiment_id': experiment_id, 'summary_sha256': summary_sha,
                'scope': 'complete_auxiliary_review_records_not_human_blind_review',
                'human_blind_review': False,
                'auxiliary_reviews': _redact(reviews) if isinstance(reviews, list) else [],
                'run_index': [{'run_id': _run_id(run), 'task_id': run.get('task_id'),
                               'group': run.get('group'), 'evaluation_cohort_id': _cohort(run),
                               'comparison_included': run.get('comparison_included'),
                               'run_dir': run.get('run_dir'), 'log_path': run.get('log_path'),
                               'job_path': run.get('job_path')} for run in runs]}
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    result = {'path': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'experiment_id': experiment_id, 'experiment_type': kind, 'runs': len(runs),
              'embedded_preview_count': len(previews), 'omitted_preview_count': omitted,
              'preview_selection_enabled': selected_products is not None,
              'requested_preview_pptx_sha256': sorted(selected_products) if selected_products is not None else None,
              'embedded_preview_pptx_sha256': sorted(embedded_products),
              'selection_excluded_preview_reference_count': len(filtered_references),
              'selected_pptx_without_embedded_preview': sorted(selected_products - embedded_products) if selected_products is not None else [],
              'auxiliary_review_count': len(reviews) if isinstance(reviews, list) else 0,
              'review_evidence_path': str(evidence_path),
              'review_evidence_sha256': hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
              'font_path': font_path, 'scientific_quality': 'not_certified_by_report_writer',
              'summary_sha256': summary_sha}
    output.with_suffix('.report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description='从私有实验摘要生成中文 PDF 报告，不调用模型')
    parser.add_argument('--summary', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    source = _private(args.summary)
    if not source.is_file() or source.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('摘要须为不超过 20 MiB 的私有 JSON 文件')
    print(json.dumps(writer(json.loads(source.read_text(encoding='utf-8')), args.output), ensure_ascii=False))


if __name__ == '__main__':
    main()
