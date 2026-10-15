"""Write an eight-page Chinese implementation/evidence report from observed runs.

This is an offline delivery tool, never part of the agent's frozen tool runtime.
It reads summarize.py's RESULTS.json and actual run artifacts, makes no model
calls, and does not invent missing measurements or silently discard failures.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from report_ops import _pdf_fonts

INK = "#17324d"
BLUE = "#2377a4"
ORANGE = "#d07835"
LIGHT = "#eef3f7"
GRAY = "#657b8b"
PHASES = {"training": "训练", "certification": "独立认证", "heldout": "留出评估", "development_pilot": "开发试跑"}
MODES = {"baseline": "普通 DSH", "execute": "Motif 执行", "shadow": "只观察"}
CASES = {"train_materials": "材料强度", "train_ml": "算法准确率", "cert_environment": "水质与温度",
         "eval_biology": "培养样本生物量", "eval_education": "训练前后成绩", "eval_energy": "负载与能耗"}


def read(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value, digits=3):
    if value is None:
        return "未记录"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def locate_run(row: dict, runs_root: Path) -> Path | None:
    direct = Path(row.get("directory", ""))
    if direct.is_dir() and (direct / "manifest.json").is_file():
        return direct
    for path in runs_root.rglob("manifest.json"):
        if read(path, {}).get("run_id") == row["run_id"]:
            return path.parent
    return None


def locate_artifact(raw: str, run: Path | None) -> Path | None:
    if run is None:
        return None
    normalized = raw.replace("\\", "/")
    marker = "/artifacts/"
    if marker not in normalized:
        return None
    workspace = (run / "workspace").resolve()
    result = (workspace / "artifacts" / normalized.split(marker, 1)[1]).resolve()
    return result if result.is_relative_to(workspace) and result.is_file() else None


def records(run: Path | None) -> list[dict]:
    if run is None:
        return []
    return [read(path) for path in sorted((run / "workspace" / "records").glob("*.json"))]


def first_manifest(rows, folders):
    for row in rows:
        folder = folders[row["run_id"]]
        if folder:
            return read(folder / "manifest.json", {})
    return {}


def make_time_plot(pairs: list[dict], directory: Path) -> Path | None:
    if not pairs:
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    fig, ax = plt.subplots(figsize=(9.3, 3.35), layout="constrained")
    plt.rcParams["font.family"] = "DejaVu Sans"
    x, width = np.arange(len(pairs)), 0.34
    for shift, arm, color, label in [(-width / 2, "baseline", BLUE, "Ordinary DSH"),
                                      (width / 2, "execute", ORANGE, "Certified motif")]:
        values = [row.get(arm + "_elapsed_seconds", 0) for row in pairs]
        bars = ax.bar(x + shift, values, width, color=color, label=label)
        ax.bar_label(bars, labels=[f"{value:.1f}" for value in values], padding=3, fontsize=9)
    ax.set_xticks(x, [row["case_id"].removeprefix("eval_").capitalize() for row in pairs])
    ax.set_ylabel("Observed end-to-end seconds")
    ax.set_title("Runtime includes model, MCP and artifact work", loc="left", color=INK, weight="bold", pad=13)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.grid(True, alpha=0.16); ax.set_axisbelow(True)
    ax.set_ylim(0, max(ax.get_ylim()[1] * 1.16, 1))
    ax.legend(frameon=False, fontsize=9)
    fig.supxlabel("Single observed run per arm. Run order, network and cache conditions were not randomized.", fontsize=8)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "observed_elapsed.png"
    fig.savefig(path, dpi=240); plt.close(fig)
    return path


class Page:
    def __init__(self, canvas, font, page_no, title, subtitle=""):
        from reportlab.lib import colors
        self.canvas, self.font, self.page_no = canvas, font, page_no
        self.width, self.height = 595.276, 841.89
        self.margin, self.usable = 44, 507.276
        self.y = self.height - 46
        canvas.setFillColor(colors.HexColor(GRAY)); canvas.setFont(font, 8)
        canvas.drawString(self.margin, self.y, "RESEARCH REPORT AGENT / IMPLEMENTATION & EVIDENCE")
        self.y -= 35
        self.p(title, size=22, leading=29, gap=10, color=INK)
        if subtitle:
            self.p(subtitle, size=9.1, leading=14, gap=12, color=GRAY)

    def p(self, text, size=10, leading=16, gap=9, color=INK, width=None, x=None):
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph
        style = ParagraphStyle("p", fontName=self.font, fontSize=size, leading=leading,
                               textColor=colors.HexColor(color), wordWrap="CJK")
        item = Paragraph(html.escape(str(text)).replace("\n", "<br/>"), style)
        actual_width = self.usable if width is None else width
        _, height = item.wrap(actual_width, 900)
        if self.y - height < 52:
            raise ValueError(f"Implementation report page {self.page_no} overflows; shorten content.")
        item.drawOn(self.canvas, self.margin if x is None else x, self.y - height)
        self.y -= height + gap

    def heading(self, text):
        self.p(text, size=12.2, leading=19, gap=6)

    def table(self, rows, widths=None, size=8.5):
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph, Table, TableStyle
        style = ParagraphStyle("cell", fontName=self.font, fontSize=size, leading=size * 1.45,
                               wordWrap="CJK", textColor=colors.HexColor(INK))
        values = [[Paragraph(html.escape(str(cell)).replace("\n", "<br/>"), style) for cell in row] for row in rows]
        table = Table(values, colWidths=widths or [self.usable / len(rows[0])] * len(rows[0]))
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5edf4")),
                                   ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fa")]),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                                   ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        _, height = table.wrap(self.usable, 900)
        if self.y - height < 52:
            raise ValueError(f"Implementation report table on page {self.page_no} overflows.")
        table.drawOn(self.canvas, self.margin, self.y - height)
        self.y -= height + 13

    def image(self, path, height=None, width=None):
        from PIL import Image
        from reportlab.lib.utils import ImageReader
        image = Image.open(path)
        w = width or self.usable
        h = height or w * image.height / image.width
        if self.y - h < 52:
            raise ValueError(f"Implementation report image on page {self.page_no} overflows.")
        self.canvas.drawImage(ImageReader(image), self.margin + (self.usable - w) / 2, self.y - h, width=w, height=h)
        self.y -= h + 9

    def finish(self, source_sha):
        from reportlab.lib import colors
        self.canvas.setStrokeColor(colors.HexColor("#d4e0e8"))
        self.canvas.line(self.margin, 40, self.width - self.margin, 40)
        self.canvas.setFillColor(colors.HexColor(GRAY)); self.canvas.setFont(self.font, 7.5)
        self.canvas.drawString(self.margin, 27, "真实执行 / 合成观测数据 | RESULTS " + source_sha[:12])
        self.canvas.drawRightString(self.width - self.margin, 27, f"{self.page_no} / 8")
        self.canvas.showPage()


def architecture(page: Page, library: dict):
    """Code-native vector diagram: semantic checkpoints remain in the loop."""
    from reportlab.lib import colors
    c, x, y, w = page.canvas, page.margin, page.y, page.usable
    stages = [
        ("LLM 判断设计、列名与缺失处理", "plan_analysis", "run_analysis → verify_analysis"),
        ("LLM 解释结果并选择图型", "plan_figures", "render_figures → verify_figures"),
        ("LLM 撰写叙事并确定页数", "plan_report", "export_report → verify_report"),
    ]
    edges = {(item.get("from_tool", "").removeprefix("mcp__research_report__"),
              item.get("to_tool", "").removeprefix("mcp__research_report__"))
             for item in library.get("artifacts", [])}
    for i, (semantic, plan, deterministic) in enumerate(stages):
        top = y - i * 119
        c.setFillColor(colors.HexColor(LIGHT)); c.roundRect(x, top - 94, w, 94, 8, fill=1, stroke=0)
        c.setFillColor(colors.HexColor(INK)); c.setFont(page.font, 11)
        c.drawString(x + 13, top - 22, semantic)
        c.setFillColor(colors.HexColor(GRAY)); c.setFont("Helvetica", 9)
        c.drawString(x + 13, top - 42, plan + " → approved receipt / ID")
        tools = deterministic.split(" → ")
        certified_count = sum(pair in edges for pair in [(plan, tools[0]), (tools[0], tools[1])])
        if certified_count == 2:
            c.setFillColor(colors.HexColor(BLUE)); c.roundRect(x + 13, top - 79, w - 26, 25, 5, fill=1, stroke=0)
            c.setFillColor(colors.white)
        else:
            c.setStrokeColor(colors.HexColor(GRAY)); c.setDash([4, 3]); c.roundRect(x + 13, top - 79, w - 26, 25, 5, fill=0, stroke=1); c.setDash([])
            c.setFillColor(colors.HexColor(GRAY))
        c.setFont("Helvetica", 10)
        c.drawCentredString(x + w / 2, top - 71, deterministic)
        c.setFont(page.font, 7.5); c.setFillColor(colors.HexColor(GRAY))
        label = "已认证两条传递边；通过守卫后可由插件接管" if certified_count == 2 else "本次未认证；保留 LLM 发出每一步调用" if certified_count == 0 else "仅部分传递边认证；未认证步骤保留 LLM"
        c.drawCentredString(x + w / 2, top - 91, label)
        if i < 2:
            c.setStrokeColor(colors.HexColor(ORANGE)); c.setLineWidth(1.4)
            c.line(x + w / 2, top - 96, x + w / 2, top - 112)
            c.line(x + w / 2, top - 112, x + w / 2 - 4, top - 107)
            c.line(x + w / 2, top - 112, x + w / 2 + 4, top - 107)
    page.y -= 359


def report_previews(rows, folders, directory):
    import fitz
    from PIL import Image, ImageDraw
    candidates = [row for row in rows if row.get("automated_quality_eligible") and row["mode"] == "execute" and row.get("phase") != "development_pilot"]
    if not candidates:
        candidates = [row for row in rows if row.get("automated_quality_eligible") and row.get("phase") != "development_pilot"]
    chosen = candidates[:2]
    if not chosen:
        return None, []
    directory.mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGB", (1200, 880), "#e6ecf1")
    labels = []
    for i, row in enumerate(chosen):
        artifact = row.get("report_artifact", {})
        path = locate_artifact(artifact.get("path", ""), folders[row["run_id"]])
        if path is None or sha(path) != artifact.get("sha256"):
            continue
        with fitz.open(path) as doc:
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            image.thumbnail((565, 800)); sheet.paste(image, (20 + i * 590, 45))
            ImageDraw.Draw(sheet).text((20 + i * 590, 15), row["case_id"] + " / " + row["mode"], fill=INK)
        labels.append({"run_id": row["run_id"], "case_id": row["case_id"], "path": str(path), "sha256": sha(path)})
    if not labels:
        return None, []
    path = directory / "actual_report_previews.png"
    sheet.save(path)
    return path, labels


def build(results_path: Path, runs_root: Path, output: Path, review_path: Path | None = None, library_path: Path | None = None):
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.pagesizes import A4
    from summarize import plot_results
    summary = read(results_path)
    if not isinstance(summary, dict) or summary.get("schema_version") != 1 or not isinstance(summary.get("runs"), list):
        raise ValueError("Expected summarize.py schema-version-1 RESULTS.json.")
    rows = summary["runs"]
    if not rows:
        raise ValueError("No observed runs; do not create an experimental-results report from placeholders.")
    source_sha = sha(results_path)
    library_path = library_path or runs_root.parent / "library.json"
    library = read(library_path, {})
    if library.get("library_digest") != summary.get("library_digest"):
        raise ValueError("Supply the actual certified library matching RESULTS.json; the architecture must not guess certified edges.")
    folders = {row["run_id"]: locate_run(row, runs_root) for row in rows}
    missing_runs = [row["run_id"] for row in rows if folders[row["run_id"]] is None]
    if missing_runs:
        raise ValueError(f"Cannot locate actual evidence for runs: {missing_runs}")
    manifest = first_manifest([row for row in rows if row.get("phase") != "development_pilot"] + rows, folders)
    environment_path = runs_root.parent / "ENVIRONMENT.json"
    if not environment_path.is_file():
        environment_path = HERE / "ENVIRONMENT.json"
    environment = read(environment_path, {})
    pairs = [row for row in summary.get("paired_comparisons", []) if row.get("eligible_for_automatic_paired_comparison")]
    formal = [row for row in rows if row.get("phase") != "development_pilot"]
    pilots = [row for row in rows if row.get("phase") == "development_pilot"]
    qualified = [row for row in formal if row.get("automated_quality_eligible")]
    failures = [row for row in rows if not row.get("automated_quality_eligible")]
    output.parent.mkdir(parents=True, exist_ok=True)
    assets = output.parent / (output.stem + "_assets")
    plots = plot_results(summary, assets)
    plot_by_name = {Path(path).name: Path(path) for path in plots}
    time_plot = make_time_plot(pairs, assets)
    preview, preview_sources = report_previews(rows, folders, assets)
    review = read(review_path, {}) if review_path else {}
    font = _pdf_fonts()
    canvas = Canvas(str(output), pagesize=A4, invariant=1)
    canvas.setTitle("科研数据分析与报告 Agent：实现与真实执行证据")
    canvas.setAuthor("Research Report Agent Benchmark")
    now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M Asia/Shanghai")
    requests = sum(row.get("requests") or 0 for row in rows)
    verified = sum(row.get("verified_motif_bypasses", 0) for row in rows)
    confirmed = sum(row.get("confirmed_peak_estimate_cny", 0) for row in rows)
    offpeak = sum(row.get("confirmed_offpeak_estimate_cny", 0) for row in rows)
    reserved = sum(row.get("unknown_reserved_upper_cny", 0) for row in rows)
    unknown = sum(row.get("unknown_cost_requests", 0) for row in rows)

    p = Page(canvas, font, 1, "科研数据分析与报告 Agent", "实现、真实模型调用、模体接管与交付质量的证据报告 | " + now)
    p.p("目标：让模型负责科研判断，让可复用的确定性步骤完成计算、绘图、导出与核验。实验仅新增 benchmark 及其插件，通过 DSH 公开插件接口与 MCP 连接工具。")
    p.table([["已观察执行", "累计真实云请求", "正式自动验收合格", "日志验证接管"],
             [f"{len(rows)} 次", f"{requests} 次", f"{len(qualified)} 次", f"{verified} 次"]], size=10)
    p.heading("本次结果应如何阅读")
    if pairs:
        baseline = sum(row["baseline_requests"] for row in pairs)
        execute = sum(row["execute_requests"] for row in pairs)
        p.p(f"已得到 {len(pairs)} 组通过配置一致性与自动产物检查的留出对照。普通 DSH 共请求云模型 {baseline} 次，Motif 共请求 {execute} 次，差值 {baseline - execute} 次。费用、耗时和报告质量分别展示，不用请求数代替总收益。")
        before_cost = sum(row["baseline_confirmed_peak_cny"] for row in pairs)
        after_cost = sum(row["execute_confirmed_peak_cny"] for row in pairs)
        change = (after_cost / before_cost - 1) * 100 if before_cost else 0
        p.p(f"留出任务高峰费率估算：普通 DSH ¥{before_cost:.6f}，Motif ¥{after_cost:.6f}，变化 {change:+.2f}%。原始报告的科学叙事仍有审阅发现的问题，因此本次不能宣称同等科研质量下已获得总成本节省。", size=9.5, color=ORANGE)
    else:
        p.p("当前没有满足全部自动比较条件的留出配对，因此本报告不计算或宣称成本与请求数节省。已完成与失败的记录均保留。")
    p.table([["组件", "本次真实性与边界"],
             ["DSH / DeepSeek Flash", "真实运行时与真实云 API；不是本地脚本伪造模型回答。"],
             ["MCP / 统计与绘图", "真实 stdio MCP；实际读取 CSV，运行统计计算，写出图与 PDF。"],
             ["实验观测数据", "由固定随机种子生成；学科题目是分析场景，结果不构成真实科学发现。"],
             ["Motif", "benchmark 内的有界回执传递扩展；不是任意工作类型识别器。"],
             ["费用与质量", "模型 usage 按费率估算；非服务商账单。自动验收不等于独立专家审稿。"]], [103, 404])
    p.p(f"模型：{manifest.get('model', '未记录')}；DSH：{manifest.get('dsh', '未记录')}；原 manifest 的 SDK 字段：{manifest.get('python_sdk', '未记录')}；reasoning：{manifest.get('reasoning_effort', '未记录')}。授权 API 总预算上限为人民币 100 元。", size=9, color=GRAY)
    if environment:
        def sdk_values(value):
            if not isinstance(value, dict): return []
            found = [str(item) for key, item in value.items() if key == "deepseek-harness-sdk"]
            return found + [item for child in value.values() if isinstance(child, dict) for item in sdk_values(child)]
        versions = sorted(set(sdk_values(environment)))
        p.p("补充 ENVIRONMENT.json 的服务器实测记录：" + ("deepseek-harness-sdk=" + ", ".join(versions) if versions else "已提供环境补充文件，具体版本见原 JSON") + "。原 manifest 查找分发包名失败的缺项保持原样，未追改运行证据。", size=8.4, color=GRAY)
    p.finish(source_sha)

    p = Page(canvas, font, 2, "任务设计与数据来源", "分离训练、认证和留出评估；不使用同一研究决定的续写冒充独立任务")
    case_rows = [["任务", "用途 / 实际执行", "统计设计", "交付要求"]]
    for case_id in dict.fromkeys(row["case_id"] for row in rows):
        members = [row for row in rows if row["case_id"] == case_id]
        inspection = next((r["payload"] for row in members for r in records(folders[row["run_id"]]) if r.get("kind") == "inspection"), {})
        study = inspection.get("study", {})
        analysis = next((r["payload"] for row in members for r in records(folders[row["run_id"]]) if r.get("kind") == "analysis"), {})
        req = study.get("report_requirements", {})
        design = analysis.get("plan", {}).get("design", "未进入分析")
        label = {"independent_groups": "独立两组", "paired": "配对", "regression": "一元回归"}.get(design, design)
        role = next((row["phase"] for row in members if row["phase"] != "development_pilot"), members[0]["phase"])
        case_rows.append([CASES.get(case_id, case_id), PHASES.get(role, role) + f" / {len(members)} 次（含试跑）",
                          label, f"{req.get('pages', '?')} 页 / {req.get('figure_count', '?')} 图"])
    p.table(case_rows, [127, 122, 106, 152])
    p.p("生成器保存实际 CSV、研究说明和用户任务文本，并把生成参数/真值放在 agent 不使用的 oracle 文件中。CSV 包含少量缺失值。模型必须选择统计设计、列名、比较方向和缺失处理，不能仅按任务编号直接取答案。只有最终模体库引用的运行 ID 计为正式训练/认证；此前试跑单列并保留费用。")
    p.heading("跨学科复用的是分析结构")
    p.table([["结构", "实际计算", "领域判断仍由 LLM 负责"],
             ["独立两组", "Welch t 检验、均差区间、Hedges g", "是否独立、比较方向、实际意义和局限"],
             ["同一单元配对", "按编号对齐、配对 t 检验、差值区间", "谁与谁配对、缺失整对如何处理"],
             ["连续变量关联", "带截距 OLS、斜率区间、残差诊断", "变量选择、线性合理性、禁止因果跳跃"]], [100, 184, 223])
    p.p("图与报告需求随任务改变，包含不同图型、不同页数和不同叙事。不能把本次少量、结构清楚的案例外推为所有科研分析。", size=9.3, color=GRAY)
    p.finish(source_sha)

    p = Page(canvas, font, 3, "交互机制：保留语义判断", "三个设计候选；蓝色为实际认证路径，虚线为本次仍需模型的路径")
    architecture(p, library)
    p.p("图中所有步骤都调用真实 MCP 工具。蓝色路径可在守卫通过时由插件生成命令；虚线路径仍由模型发出每一步调用。插件不接管科研解释、方案修改或报告撰写。认证状态直接读取本次模体库，不根据设计目标推测。", size=9.5)
    p.heading("允许接管前需要同时满足")
    p.p("真实普通轨迹中重复出现，且通过独立任务认证；当前工具 schema 相同；LLM 明确授权这份计划的确定性续步；回执文件哈希、工作区、输入 CSV 和研究版本相符；候选下一步唯一。条件不满足或工具失败即回到模型。", size=9.5)
    report_edges = [item for item in library.get("artifacts", []) if item.get("to_tool", "").endswith(("__export_report", "__verify_report"))]
    missing_report_note = "报告导出两条边没有获得训练/认证所需的显式计划授权证据，本次未入库；保留该结果，没有为了增加接管数重训。" if not report_edges else "报告导出相关认证边以实际库为准。"
    p.p(f"实际认证的单步传递模体数：{summary.get('certified_motif_count', '未记录')}。{missing_report_note}本机制没有使用模拟 embedding，也不声称识别任意工作类型。", size=9.2, color=GRAY)
    p.finish(source_sha)

    p = Page(canvas, font, 4, "请求与模型费用对照", "仅展示满足输入、配置、工具 schema、日志与自动质量条件的配对")
    comparison = plot_by_name.get("heldout_comparison.png")
    if comparison:
        p.image(comparison)
    else:
        p.p("未获得合格的配对结果；不绘制空造的收益柱状图。")
    comparison_rows = [["留出任务", "请求数：普通 → Motif", "费率估算：普通 → Motif"]]
    for row in pairs:
        comparison_rows.append([CASES.get(row["case_id"], row["case_id"]), f"{row['baseline_requests']} → {row['execute_requests']}",
                                f"¥{row['baseline_confirmed_peak_cny']:.4f} → ¥{row['execute_confirmed_peak_cny']:.4f}"])
    if pairs: p.table(comparison_rows, [151, 155, 201])
    p.p("请求数来自预算代理实际转发次数，工具调用数来自 DSH 事件，接管数来自执行后核验成功的审计记录。图中费用使用同一高峰费率计算完整 usage，包含缓存命中、未命中输入及输出；不是用 token 总数粗略替代价格。")
    adverse = [row for row in pairs if row["execute_confirmed_peak_cny"] > row["baseline_confirmed_peak_cny"]]
    if adverse:
        details = []
        for row in adverse:
            cost_change = (row["execute_confirmed_peak_cny"] / row["baseline_confirmed_peak_cny"] - 1) * 100
            runtime_change = (row["execute_elapsed_seconds"] / row["baseline_elapsed_seconds"] - 1) * 100 if row["baseline_elapsed_seconds"] else None
            details.append(CASES.get(row["case_id"], row["case_id"]) + f"费用上升 {cost_change:.1f}%" + (f"、耗时变化 {runtime_change:+.1f}%" if runtime_change is not None else ""))
        p.p("必须保留的反例：" + "；".join(details) + "。接管减少局部模型请求，并不保证完整任务更便宜或更快；额外语义修正、输出长度及缓存都可能抵消收益。", size=9.2, color=ORANGE)
    p.p("相同数据和任务不保证两个自由生成的模型报告措辞、图型或重试行为完全相同。自动检查过关后，还应逐份比较科学论断、完整性和可读性。单次观察没有重复运行的方差估计或统计置信区间。", size=9.3, color=GRAY)
    p.finish(source_sha)

    p = Page(canvas, font, 5, "总成本与端到端耗时", "训练、认证、失败与重试的开销均保留；不把建库成本当成免费")
    if time_plot: p.image(time_plot)
    totals_rows = [["阶段 / 模式", "尝试 / 自动合格", "已知 usage 高峰估费", "未知费用预留"]]
    for row in summary.get("phase_totals_including_failed_attempts", []):
        totals_rows.append([PHASES.get(row["phase"], row["phase"]) + " / " + MODES.get(row["mode"], row["mode"]),
                           f"{row['attempts']} / {row['automatically_qualified']}", f"¥{row['confirmed_peak_estimate_cny']:.4f}", f"¥{row['unknown_reserved_upper_cny']:.4f}"])
    p.table(totals_rows, [157, 103, 136, 111], size=8.2)
    p.p(f"全部已知 usage 的高峰费率估算合计 ¥{confirmed:.4f}，低谷费率估算合计 ¥{offpeak:.4f}。另有 {unknown} 次费用不完整请求，记录的保守预留上界为 ¥{reserved:.4f}。这两种费率估算不是一份服务商实付账单。", size=9.5)
    ledger_total = [row.get("budget_accounted_cny") for row in summary.get("shared_budget_ledgers", []) if row.get("available")]
    p.p("共享预算账本已计入金额：" + ("、".join(f"¥{value:.4f}" for value in ledger_total) if ledger_total else "本地汇总未取得可验证账本") + "。未结算的预留可能高于实际支出；开发、人工评审及维护时间未包含在 API 费用中。", size=9.1, color=GRAY)
    p.finish(source_sha)

    p = Page(canvas, font, 6, "真实交付与格式检查", "下图从本次实际生成 PDF 的首页渲染，不是效果示意图")
    if preview: p.image(preview, height=363)
    else: p.p("尚无哈希核验通过的真实 PDF 可展示。")
    p.p("每份科研报告由模型提供中文解释，并引用计算记录中的统计指标。确定性工具生成清晰原始点、配对线、分布、效应区间、拟合和诊断图；图集同时保存高分辨率 PNG 与可缩放 SVG/PDF。")
    p.table([["自动检查", "本次检查的具体对象"],
             ["文件与布局", "实际 PDF 页数、图数、文字提取、页边界、占位符与文件哈希"],
             ["数据与数字", "原始 CSV 独立复算；报告引用绑定同一分析；图集引用与版本一致"],
             ["不能自动证明", "图表解释是否充分、研究设计是否成立、模型结论是否过度推断"]], [106, 401])
    p.finish(source_sha)

    p = Page(canvas, font, 7, "质量边界、失败与审阅", "自动检查与额外 AI 科学/视觉审阅分别记录；非盲审、非领域专家认可")
    p.p(f"正式运行自动产物验收合格 {len(qualified)} / {len(formal)} 次；另保留 {len(pilots)} 次开发试跑。全部记录中未合格或失败 {len(failures)} 次。旧版本通过不等于最终版本有效，试跑及失败费用均计入阶段成本。")
    quality_rows = [["报告 / 阶段", "自动合格", "页数", "图数", "工具错误"]]
    for row in formal:
        if row.get("automated_quality_eligible"):
            artifact = row.get("report_artifact", {})
            quality_rows.append([CASES.get(row["case_id"], row["case_id"]) + " / " + MODES.get(row["mode"], row["mode"]),
                                 "通过", artifact.get("target_pages", "?"), artifact.get("metadata", {}).get("figure_count", "?"), row.get("tool_error_results", "?")])
    if len(quality_rows) > 1: p.table(quality_rows, [246, 63, 48, 48, 102], size=8)
    if failures:
        counts = Counter((row.get("status", "unknown"), row.get("error_type") or "自动质量未通过") for row in failures)
        p.p("保留的失败：" + "；".join(f"{status} / {error}：{count} 次" for (status, error), count in counts.items()) + "。具体消息、启动诊断和未完成状态见各运行目录。", size=8.8)
    if review:
        p.p("另行提供的审阅记录：" + str(review.get("summary", "已提供结构化审阅文件；详见旁存 JSON。")), size=9)
    else:
        p.p("本报告脚本未执行独立人工或模型审稿；视觉检查和科学论断审阅需另行附证据。不能把自动通过写成论文级质量已获认证。", size=9, color=GRAY)
    p.p("局限：数据合成、任务数少、每个配对仅一次；缓存和运行顺序影响费用；未比较普通固定脚本；语义选择仍依赖 LLM；回执模体只复用已批准计划内的步骤，不能覆盖复杂开放科研过程。", size=9.1, color=GRAY)
    p.finish(source_sha)

    p = Page(canvas, font, 8, "实现索引与复现入口", "所有新增实现位于 benchmarks/research_report_agent_v1；上游 DSH 核心保持独立")
    p.table([["文件", "职责"],
             ["generate_data.py", "生成六类案例、实际 CSV、任务要求及独立 oracle"],
             ["data_tools.py / common.py", "数据检查、分析计划、真实统计、独立复算与内容寻址回执"],
             ["report_ops.py / server.py", "图型选择、实际渲染、中文 PDF、MCP 工具暴露与产物检查"],
             ["compile_motifs.py", "从普通真实轨迹发现重复参数传递，并在独立任务上认证"],
             ["motif_plugin.ts / .mjs", "DSH llm/stream 拦截、工具结果观察、守卫、执行后复核"],
             ["runner.py / pricing.json", "真实 API、总预算、稳定工具集、请求/响应/usage 与失败记录"],
             ["summarize.py", "配对公平性、失败计入、费用不确定项、JSON 与对照图"],
             ["write_experiment_report.py", "本报告；仅从已有真实记录读取，不调用模型或改写实验"]], [183, 324], size=8.7)
    p.heading("从日志追到一次具体优化")
    p.p("先在 motif-audit.jsonl 找到 model_request_skipped_verified，再用 call_id 对齐 agent-events.jsonl 的工具参数与结果。上一步的 record_path 指向内容寻址回执；模型真正收到和返回的内容在 model-requests/。报告与图位于 workspace/artifacts/。")
    p.heading("离线生成本报告")
    p.p("python benchmarks/research_report_agent_v1/summarize.py --runs-root RUNS --library LIBRARY.json --output RESULTS.json\npython benchmarks/research_report_agent_v1/write_experiment_report.py --results RESULTS.json --runs-root RUNS --output implementation_report.pdf", size=8.7, leading=13)
    p.p(f"代码基点：{manifest.get('commit', '未记录')}\n模体库摘要：{summary.get('library_digest', '未记录')}\nRESULTS 摘要：{source_sha}", size=8, leading=12, color=GRAY)
    p.finish(source_sha)
    canvas.save()
    qa = verify(output)
    evidence = {"report": str(output.resolve()), "results": str(results_path.resolve()), "results_sha256": source_sha,
                "library": str(library_path.resolve()), "library_digest": library.get("library_digest"),
                "environment_supplement": {"path": str(environment_path), "sha256": sha(environment_path)} if environment else None,
                "observed_run_count": len(rows), "eligible_pair_count": len(pairs), "preview_sources": preview_sources,
                "review_json": str(review_path.resolve()) if review_path else None, "automated_report_check": qa,
                "warning": "Automatic report generation is not scientific peer review or a provider invoice."}
    output.with_suffix(".evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    if not qa["passed"]:
        raise ValueError(f"Implementation report QA failed: {qa}")
    return evidence


def verify(path: Path) -> dict:
    import fitz
    problems, pages = [], []
    with fitz.open(path) as doc:
        for index, page in enumerate(doc):
            text = page.get_text()
            pages.append({"page": index + 1, "characters": len(text.strip()), "images": len(page.get_images())})
            if len(text.strip()) < 50 or "\ufffd" in text:
                problems.append({"page": index + 1, "issue": "missing_or_invalid_text"})
            for block in page.get_text("dict")["blocks"]:
                x0, y0, x1, y1 = block["bbox"]
                if x0 < 13 or y0 < 13 or x1 > page.rect.width - 13 or y1 > page.rect.height - 13:
                    problems.append({"page": index + 1, "issue": "page_boundary", "bbox": block["bbox"]})
    return {"passed": len(pages) == 8 and not problems, "expected_pages": 8, "pages": pages, "problems": problems,
            "visual_review": "Not performed by this function; render and inspect every page before delivery."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--runs-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--review-json", type=Path)
    parser.add_argument("--library", type=Path, help="Defaults to RUNS_ROOT/../library.json; digest must match RESULTS.")
    args = parser.parse_args()
    print(json.dumps(build(args.results.resolve(), args.runs_root.resolve(), args.output.resolve(), args.review_json, args.library), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
