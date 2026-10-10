"""Real plotting and Chinese PDF tools for the research-report benchmark.

The LLM chooses a figure plan and writes an evidence-linked narrative.  These
tools execute that plan with matplotlib/reportlab, then inspect the actual files.
No network application, model response, or document is mocked in this module.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import re
from pathlib import Path
from typing import Any

try:
    from .common import get_record, get_run_dir, get_study, put_record, tool_response
except ImportError:
    from common import get_record, get_run_dir, get_study, put_record, tool_response


FIGURE_KINDS = {
    "independent_groups": {"distribution_ci", "effect_interval", "group_ecdf"},
    "paired": {"paired_change", "effect_interval", "change_distribution"},
    "regression": {"scatter_fit", "residuals", "effect_interval"},
}
COLORS = {"ink": "#17324d", "blue": "#2377a4", "orange": "#d07835", "gray": "#697886"}
NARRATIVE_FIELDS = ("title", "summary", "methods", "findings", "limitations", "next_steps")
METRIC_LABELS = {
    "n": "有效观测 / 配对数", "estimate": "主要效应估计", "ci_low": "置信区间下界",
    "ci_high": "置信区间上界", "p_value": "检验 p 值", "effect_size": "效应量（定义见方法）",
    "r_squared": "决定系数", "slope": "回归斜率", "intercept": "截距",
}


def _study() -> dict:
    value = get_study()
    return value.get("payload", value)


def _payload(identifier: str, kind: str | None = None) -> dict:
    return get_record(identifier, kind=kind)["payload"]


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _authorization(value: dict, tools: tuple[str, ...]) -> tuple[str, ...]:
    return tools if value.get("allow_deterministic_continuation") is True else ()


def _analysis(identifier: str) -> dict:
    result = _payload(identifier, "analysis")
    if not result.get("cleaned_records"):
        raise ValueError("Analysis contains no cleaned observations.")
    if result["plan"]["design"] not in FIGURE_KINDS:
        raise ValueError("Unsupported statistical design.")
    return result


def _english_title(value: str) -> str:
    if len(value) > 100 or any(ord(char) > 127 for char in value):
        raise ValueError("Figure titles must be concise English ASCII text; Chinese belongs in report captions.")
    return value


def plan_figures(analysis_id: str, spec: dict) -> dict:
    """Choose distinct plots matching the requested figure count and design.

    spec={"figures":[{"kind":"...","title":"Optional ASCII English title"}],
    "theme":"journal","language":"en","allow_deterministic_continuation":true}.
    independent_groups: distribution_ci (required), effect_interval, group_ecdf.
    paired: paired_change (required), effect_interval, change_distribution.
    regression: scatter_fit (required), residuals, effect_interval.
    Choose exactly the user's two or three figures; do not repeat a kind.
    distribution_ci shows raw observations with group means and confidence bars;
    group_ecdf compares full empirical distributions without binning;
    paired_change links observations within subjects; change_distribution plots
    within-subject differences; effect_interval shows the actual contrast/slope
    confidence interval; residuals diagnoses a regression. Titles must be English
    ASCII, not Chinese. Set allow_deterministic_continuation=true only to permit
    deterministic rendering and validation of this approved figure plan.
    """
    analysis = _analysis(analysis_id)
    if spec.get("theme", "journal") != "journal" or spec.get("language", "en") != "en":
        raise ValueError("This version supports the journal theme and English plot labels.")
    if type(spec.get("allow_deterministic_continuation", False)) is not bool:
        raise ValueError("allow_deterministic_continuation must be a boolean.")
    figures = spec.get("figures", [])
    if not isinstance(figures, list) or not 2 <= len(figures) <= 3:
        raise ValueError("Choose two or three figures.")
    allowed = FIGURE_KINDS[analysis["plan"]["design"]]
    kinds = [item.get("kind") for item in figures]
    if any(kind not in allowed for kind in kinds) or len(set(kinds)) != len(kinds):
        raise ValueError(f"Choose distinct figure kinds from {sorted(allowed)}.")
    required = {"independent_groups": "distribution_ci", "paired": "paired_change", "regression": "scatter_fit"}[analysis["plan"]["design"]]
    if required not in kinds:
        raise ValueError(f"The primary raw-data plot {required} is required.")
    requested = _study().get("report_requirements", {}).get("figure_count")
    if isinstance(requested, int) and len(figures) != requested:
        raise ValueError(f"The user requested exactly {requested} figures.")
    normalized = [{"kind": item["kind"], "title": _english_title(item.get("title", ""))} for item in figures]
    payload = {"analysis_id": analysis_id, "figures": normalized, "theme": "journal", "language": "en",
               "allow_deterministic_continuation": spec.get("allow_deterministic_continuation") is True}
    identifier = put_record("figure_plan", payload, authorized_tools=_authorization(spec, ("render_figures",)))
    return tool_response(identifier, "figure_plan_id", {"figures": normalized})


def _frame(analysis: dict):
    import pandas as pd
    return pd.DataFrame.from_records(analysis["cleaned_records"])


def _column_label(column: str) -> str:
    study = _study()
    label = study.get("column_labels", {}).get(column, column.replace("_", " ").capitalize())
    if isinstance(label, dict):
        label = label.get("en", column.replace("_", " ").capitalize())
    # Font-safe labels, even when a future input provides Chinese-only metadata.
    if not isinstance(label, str) or any(ord(c) > 127 for c in label):
        label = column.replace("_", " ").capitalize()
    unit = study.get("units", {}).get(column)
    if unit and all(ord(c) < 128 for c in str(unit)):
        label += f" ({unit})"
    return label


def _style_axis(ax):
    ax.spines[["right", "top"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#afbac3")
    ax.tick_params(color="#afbac3", labelsize=10)
    ax.grid(axis="y", color="#e8edf1", linewidth=0.7)
    ax.set_axisbelow(True)


def _plot(analysis: dict, item: dict, index: int, directory: Path) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from scipy import stats

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.labelcolor": COLORS["ink"], "text.color": COLORS["ink"],
                         "axes.titleweight": "bold", "svg.fonttype": "none",
                         "pdf.fonttype": 42, "savefig.facecolor": "white",
                         "svg.hashsalt": analysis.get("data_sha256", "research-report")})
    df, plan, metrics = _frame(analysis), analysis["plan"], analysis["metrics_dict"]
    outcome, kind = plan["outcome_column"], item["kind"]
    confidence = float(plan.get("confidence", 0.95))
    confidence_label = f"{confidence * 100:g}%"
    fig, ax = plt.subplots(figsize=(7.4, 4.5), layout="constrained")
    _style_axis(ax)
    rng = np.random.default_rng(721)  # Reproducible display-only jitter; never changes analysis.
    caption = ""
    if kind == "distribution_ci":
        group = plan["group_column"]
        names = [plan["reference_group"], plan["comparison_group"]]
        arrays = [df.loc[df[group] == name, outcome].to_numpy(dtype=float) for name in names]
        for i, (name, values, color) in enumerate(zip(names, arrays, [COLORS["blue"], COLORS["orange"]])):
            ax.scatter(i + rng.uniform(-0.16, 0.16, len(values)), values, s=24, alpha=0.65, color=color, edgecolor="white", linewidth=0.3)
            mean = float(np.mean(values))
            half = float(stats.t.ppf((1 + confidence) / 2, len(values) - 1) * stats.sem(values))
            ax.errorbar(i + 0.25, mean, yerr=half, fmt="D", markersize=6, capsize=5, color=COLORS["ink"], linewidth=1.7)
        ax.set_xticks(range(2), [f"{name}\nn = {len(values)}" for name, values in zip(names, arrays)])
        ax.set_xlim(-0.45, 1.55)
        ax.set_ylabel(_column_label(outcome))
        title = "Observed distributions and group means"
        caption = f"每个点是一条有效观测；菱形为组均值，误差线为各组均值的双侧 {confidence_label} t 置信区间。组间差异的推断以效应区间图和统计表为准。"
    elif kind == "group_ecdf":
        group = plan["group_column"]
        names = [plan["reference_group"], plan["comparison_group"]]
        for name, color in zip(names, [COLORS["blue"], COLORS["orange"]]):
            values = np.sort(df.loc[df[group] == name, outcome].to_numpy(dtype=float))
            ax.step(values, np.arange(1, len(values) + 1) / len(values), where="post", color=color, linewidth=2, label=f"{name} (n = {len(values)})")
        ax.set_xlabel(_column_label(outcome)); ax.set_ylabel("Empirical cumulative proportion")
        ax.set_ylim(0, 1.04); ax.legend(frameon=False, fontsize=9)
        title = "Empirical distributions without binning"
        caption = "经验累积分布直接由排序后的有效观测计算，不依赖直方图分箱；组间曲线差异展示整体分布而不只比较均值。"
    elif kind in {"paired_change", "change_distribution"}:
        group, subject = plan["group_column"], plan["subject_column"]
        names = [plan["reference_group"], plan["comparison_group"]]
        wide = df.pivot(index=subject, columns=group, values=outcome)[names].dropna()
        if kind == "paired_change":
            for values in wide.to_numpy():
                ax.plot([0, 1], values, color=COLORS["gray"], alpha=0.3, linewidth=0.85)
            for i, name in enumerate(names):
                ax.scatter(np.full(len(wide), i), wide[name], s=22, color=[COLORS["blue"], COLORS["orange"]][i], zorder=3, alpha=0.78, edgecolor="white", linewidth=0.3)
            ax.set_xticks([0, 1], names)
            ax.set_xlim(-0.2, 1.2)
            ax.set_ylabel(_column_label(outcome))
            title = f"Paired observations | {len(wide)} complete pairs"
            caption = "同一条线连接同一个体的两次观测；仅纳入完整配对。连线展示个体变化及异质性，不把配对数据当作独立样本。"
        else:
            changes = wide[names[1]].to_numpy() - wide[names[0]].to_numpy()
            ax.hist(changes, bins="fd", color=COLORS["blue"], alpha=0.78, edgecolor="white", linewidth=1)
            ax.axvline(0, color=COLORS["gray"], linestyle="--", linewidth=1.2, label="No change")
            ax.axvline(float(changes.mean()), color=COLORS["orange"], linewidth=2, label="Mean paired change")
            ax.set_xlabel(f"{names[1]} - {names[0]}: " + _column_label(outcome)); ax.set_ylabel("Number of complete pairs")
            ax.legend(frameon=False, fontsize=9)
            title = "Distribution of within-subject changes"
            caption = "先按个体匹配，再计算比较条件减去参照条件的差值；直方图展示变化分布，虚线为零变化，实线为平均变化。分箱采用 Freedman-Diaconis 规则。"
    elif kind == "effect_interval":
        estimate, lo, hi = [float(metrics[key]) for key in ("estimate", "ci_low", "ci_high")]
        ax.axvline(0, color=COLORS["gray"], linestyle="--", linewidth=1)
        ax.errorbar(estimate, 0, xerr=[[estimate - lo], [hi - estimate]], fmt="o", markersize=9, capsize=7, linewidth=2.6, color=COLORS["blue"])
        contrast_label = "Slope" if plan["design"] == "regression" else f"{plan['comparison_group']} - {plan['reference_group']}"
        ax.set_yticks([0], [contrast_label])
        ax.set_ylim(-0.6, 0.6)
        if plan["design"] == "regression":
            units = _study().get("units", {})
            slope_unit = f" ({units.get(outcome, outcome)} / {units.get(plan['predictor_column'], plan['predictor_column'])})"
            ax.set_xlabel("Estimated slope" + slope_unit)
        else:
            ax.set_xlabel(_column_label(outcome) + " difference")
        span = max(hi - lo, abs(estimate) * 0.2, 1e-6)
        ax.set_xlim(min(lo - span * 0.25, -span * 0.12), max(hi + span * 0.25, span * 0.12))
        ax.text(0.02, 0.92, f"Estimate = {estimate:.4g}   {confidence_label} CI [{lo:.4g}, {hi:.4g}]", transform=ax.transAxes, fontsize=11)
        title = "Effect estimate and uncertainty"
        caption = "圆点和区间直接取自统计分析记录；虚线表示零效应。区间表达估计不确定性，不代表个体观测的范围。"
    elif kind in {"scatter_fit", "residuals"}:
        predictor = plan["predictor_column"]
        x, y = df[predictor].to_numpy(dtype=float), df[outcome].to_numpy(dtype=float)
        fit = stats.linregress(x, y)
        fitted = fit.intercept + fit.slope * x
        residuals = y - fitted
        if kind == "scatter_fit":
            grid = np.linspace(float(x.min()), float(x.max()), 200)
            pred = fit.intercept + fit.slope * grid
            residual_sd = math.sqrt(float(np.sum(residuals ** 2) / (len(x) - 2)))
            se = residual_sd * np.sqrt(1 / len(x) + (grid - x.mean()) ** 2 / np.sum((x - x.mean()) ** 2))
            half = stats.t.ppf((1 + confidence) / 2, len(x) - 2) * se
            ax.fill_between(grid, pred - half, pred + half, color=COLORS["blue"], alpha=0.15, label=confidence_label + " CI for mean")
            ax.scatter(x, y, color=COLORS["blue"], s=27, alpha=0.7, edgecolor="white", linewidth=0.35, label=f"Observations (n = {len(x)})")
            ax.plot(grid, pred, color=COLORS["orange"], linewidth=2, label="OLS fit")
            ax.set_xlabel(_column_label(predictor)); ax.set_ylabel(_column_label(outcome))
            ax.legend(frameon=False, fontsize=9)
            title = "Observed relationship and fitted mean"
            caption = f"点为原始有效观测，线为单变量最小二乘拟合，阴影为均值的双侧 {confidence_label} 置信带；该带不是预测区间。相关关系本身不证明因果关系。"
        else:
            ax.axhline(0, color=COLORS["gray"], linestyle="--", linewidth=1)
            ax.scatter(fitted, residuals, color=COLORS["orange"], s=27, alpha=0.72, edgecolor="white", linewidth=0.35)
            ax.set_xlabel("Fitted " + _column_label(outcome)); ax.set_ylabel("Residual (observed - fitted)")
            title = "Residual diagnostic"
            caption = "残差由实际观测值减去拟合值计算。系统弯曲、漏斗形散布或极端点提示模型假设可能不适合；此图不自动证明假设成立。"
    else:
        raise ValueError(f"Unsupported plot: {kind}")
    ax.set_title(item.get("title") or title, loc="left", pad=16, fontsize=13)
    fig.supxlabel("Synthetic benchmark data | fixed input snapshot", fontsize=8, color=COLORS["gray"])
    base = directory / f"figure_{index:02d}_{kind}"
    paths = {}
    for extension in ("png", "svg", "pdf"):
        path = base.with_suffix("." + extension)
        metadata = {"CreationDate": None, "ModDate": None} if extension == "pdf" else {"Date": None} if extension == "svg" else {}
        fig.savefig(path, dpi=300, metadata=metadata)
        paths[extension] = str(path.resolve())
    plt.close(fig)
    return {"kind": kind, "title": item.get("title") or title, "caption": caption,
            "paths": paths, "sha256": {extension: _hash(Path(path)) for extension, path in paths.items()},
            "data_rows": len(df), "analysis_metrics": {key: metrics[key] for key in ("n", "estimate", "ci_low", "ci_high", "p_value")}}


def render_figures(figure_plan_id: str) -> dict:
    """Render the approved figure plan into actual PNG/SVG/PDF files."""
    plan = _payload(figure_plan_id, "figure_plan")
    analysis = _analysis(plan["analysis_id"])
    directory = Path(get_run_dir()) / "artifacts" / figure_plan_id.replace(":", "_")
    directory.mkdir(parents=True, exist_ok=True)
    figures = [_plot(analysis, item, i + 1, directory) for i, item in enumerate(plan["figures"])]
    identifier = put_record("figure_bundle", {"analysis_id": plan["analysis_id"], "plan_id": figure_plan_id,
                            "figures": figures, "synthetic": True},
                            authorized_tools=_authorization(plan, ("verify_figures",)))
    return tool_response(identifier, "figure_bundle_id", {"figures": figures})


def verify_figures(figure_bundle_id: str) -> dict:
    """Inspect saved images, vector files and metric lineage; this is not human review."""
    from PIL import Image, ImageStat
    bundle = _payload(figure_bundle_id, "figure_bundle")
    analysis = _analysis(bundle["analysis_id"])
    checks = []
    for figure in bundle["figures"]:
        paths = {key: Path(value) for key, value in figure["paths"].items()}
        with Image.open(paths["png"]) as image:
            rgb = image.convert("RGB")
            nonblank = max(ImageStat.Stat(rgb).stddev) > 5
            size = list(image.size)
        hashes_ok = all(_hash(path) == figure["sha256"][key] for key, path in paths.items())
        metrics_ok = all(figure["analysis_metrics"][key] == analysis["metrics_dict"][key] for key in figure["analysis_metrics"])
        checks.append({"kind": figure["kind"], "pixels": size, "nonblank": nonblank,
                       "sufficient_resolution": min(size) >= 1000, "file_hashes_match": hashes_ok,
                       "analysis_metrics_match": metrics_ok,
                       "svg_has_vectors": "<path" in paths["svg"].read_text(encoding="utf-8"),
                       "pdf_exists": paths["pdf"].stat().st_size > 1000})
    passed = all(all(value for key, value in item.items() if key not in {"kind", "pixels"}) for item in checks)
    identifier = put_record("figure_verification", {"figure_bundle_id": figure_bundle_id,
                            "quality_passed": passed, "checks": checks,
                            "review_scope": "File, pixel, vector and metric-lineage checks; visual scientific review remains separate."})
    return tool_response(identifier, "figure_verification_id", {"figure_bundle_id": figure_bundle_id, "quality_passed": passed, "checks": checks})


def _format_metric(value: Any, key: str = "") -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int) or key == "n":
        return str(int(value))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite metric {key} cannot appear in a report.")
        if key == "p_value":
            return f"{value:.3g}" if value < 0.001 else f"{value:.4f}"
        return f"{value:.4g}"
    return str(value)


def _render_narrative(narrative: dict, metrics: dict) -> tuple[dict, list[str]]:
    rendered, references = {}, set()
    limits = {"title": 80, "summary": 350, "methods": 350, "findings": 450, "limitations": 400, "next_steps": 300}
    for key in NARRATIVE_FIELDS:
        text = narrative.get(key, "")
        if not isinstance(text, str) or not text.strip() or len(text) > limits[key]:
            raise ValueError(f"narrative.{key} must be nonempty text of at most {limits[key]} characters.")
        names = re.findall(r"\{\{([A-Za-z_]\w*)\}\}", text)
        unknown = set(names) - metrics.keys()
        if unknown:
            raise ValueError(f"Unknown metric references: {sorted(unknown)}; use {sorted(metrics)}.")
        references.update(names)
        stripped = re.sub(r"\{\{[A-Za-z_]\w*\}\}", "", text)
        # Alpha-numeric technical terms such as CO2 are permitted; unlinked
        # quantitative claims are rejected (95% CI and alpha 0.05 are conventions).
        if key != "title":
            numbers = re.findall(r"(?<![A-Za-z_\d])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", stripped)
            illegal_numbers = sorted({number for number in numbers if number not in {"95", "0.05"}})
            if illegal_numbers:
                raise ValueError(f"Unlinked number in narrative.{key}: {illegal_numbers}. Use actual metric placeholders such as {{{{confidence}}}}, {{{{n}}}} or {{{{estimate}}}}. For confidence, write 95% or {{{{confidence}}}}, not a literal 0.95.")
        rendered[key] = re.sub(r"\{\{([A-Za-z_]\w*)\}\}", lambda match: _format_metric(metrics[match.group(1)], match.group(1)), text)
        if "{" in rendered[key] or "}" in rendered[key]:
            raise ValueError(f"Malformed or unresolved placeholder in narrative.{key}. Use exactly two braces on each side, for example {{{{input_rows}}}} or {{{{n}}}}; single-brace placeholders and other braces are not allowed.")
    required = {"estimate", "ci_low", "ci_high", "p_value", "n"}
    if not required.issubset(references):
        raise ValueError(f"Narrative must reference all primary metrics; missing {sorted(required - references)}.")
    return rendered, sorted(references)


def plan_report(analysis_id: str, figure_bundle_id: str, narrative: dict, format: str = "pdf", target_pages: int = 3) -> dict:
    """Write the scientific interpretation in Chinese, then approve PDF export.

    narrative requires six nonempty strings: title,summary,methods,findings,
    limitations,next_steps. Recommend 80-150 Chinese characters per paragraph,
    with a concise title. Put allow_deterministic_continuation=true inside
    narrative to authorize deterministic export and validation only.
    Cite computed numbers with literal placeholders {{estimate}}, {{ci_low}},
    {{ci_high}}, {{p_value}}, {{n}}: all five MUST appear somewhere in narrative.
    Also available: {{effect_size}}, {{excluded_rows}}, {{input_rows}},
    {{confidence}}, and {{r_squared}} for regression. Do NOT invent or directly
    type quantitative claims; only 95 and 0.05 may appear as conventional numbers.
    For confidence write 95% or {{confidence}}, NEVER literal 0.95. Use exactly
    two braces per side: {{input_rows}} is valid; {input_rows} is invalid.
    These templates are rendered from verified metric values, preserving your
    interpretation. Explain missingness, scientific limitations and synthetic
    data. Choose format='pdf' and the user's target_pages, one of 2, 3 or 4.
    The figure bundle must belong to the same analysis record.
    """
    analysis, bundle = _analysis(analysis_id), _payload(figure_bundle_id, "figure_bundle")
    if bundle["analysis_id"] != analysis_id:
        raise ValueError("Figures and report must use the same analysis record.")
    if format.lower() != "pdf" or isinstance(target_pages, bool) or target_pages not in (2, 3, 4):
        raise ValueError("Choose PDF format and a page budget of 2, 3 or 4 pages.")
    if type(narrative.get("allow_deterministic_continuation", False)) is not bool:
        raise ValueError("allow_deterministic_continuation must be a boolean.")
    requested = _study().get("report_requirements", {}).get("pages")
    if isinstance(requested, int) and target_pages != requested:
        raise ValueError(f"The user requested {requested} pages.")
    rendered, references = _render_narrative(narrative, analysis["metrics_dict"])
    identifier = put_record("report_plan", {"analysis_id": analysis_id, "figure_bundle_id": figure_bundle_id,
                            "narrative_template": narrative, "narrative": rendered, "metric_references": references,
                            "format": "pdf", "target_pages": target_pages,
                            "allow_deterministic_continuation": narrative.get("allow_deterministic_continuation") is True},
                            authorized_tools=_authorization(narrative, ("export_report",)))
    return tool_response(identifier, "report_plan_id", {"target_pages": target_pages, "metric_references": references})


def _pdf_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    candidates = [Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
                  Path("/usr/share/fonts/truetype/arphic/ukai.ttc"),
                  Path("C:/Windows/Fonts/msyh.ttc")]
    for path in candidates:
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("ReportCJK", str(path), subfontIndex=0))
                return "ReportCJK"
            except Exception:
                continue
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def _short_json(value: Any) -> str:
    if isinstance(value, dict):
        return "; ".join(f"{key}: {_short_json(item)}" for key, item in value.items())
    if isinstance(value, list):
        return "; ".join(_short_json(item) for item in value)
    if isinstance(value, float):
        return _format_metric(value)
    return str(value)


def _diagnostics_text(analysis: dict) -> str:
    d, design = analysis.get("diagnostics", {}), analysis["plan"]["design"]
    text = (f"输入 {d.get('input_rows', '?')} 行，保留 {d.get('retained_rows', '?')} 行，"
            f"按预先批准的完整案例规则排除 {d.get('excluded_rows', '?')} 行。")
    if design == "paired":
        text += f"最终包含 {analysis['metrics_dict']['n']} 个完整配对；任一条件缺失时，该个体的整对观测均不进入检验。"
    text += "缺失机制未知，删除记录可能引入选择偏差。"
    if "shapiro_p" in d:
        p = float(d["shapiro_p"])
        text += (f"残差的 Shapiro-Wilk 检查：W={float(d['shapiro_w']):.4g}，p={p:.3g}。"
                 + ("该检查提示偏离正态，常规小样本区间需谨慎解释。" if p < 0.05 else "该检查未提供明显偏离正态的证据，但不能证明正态假设成立。"))
    text += "独立性来自采样设计假设，不能由此检验自动证明。"
    if design == "regression":
        text += "线性回归估计关联；应检查残差图的非线性、异方差及异常点，不作因果推断。"
    return text


def _plan_text(plan: dict) -> str:
    names = {"independent_groups": "两组独立样本比较", "paired": "同一实验单元的配对比较", "regression": "带截距的一元线性回归"}
    text = f"分析设计：{names[plan['design']]}。主要结局列：{plan['outcome_column']}。"
    if plan["design"] == "regression":
        text += f"解释变量列：{plan['predictor_column']}。斜率表示解释变量增加一个单位对应的平均结局变化。"
    else:
        text += f"比较方向：{plan['comparison_group']} 减去 {plan['reference_group']}。"
        if plan["design"] == "paired":
            text += f"按 {plan['subject_column']} 对齐同一实验单元。"
    text += f"区间置信水平：{plan.get('confidence', 0.95) * 100:g}%。缺失值采用完整案例策略。"
    text += "研究假设：" + plan.get("hypothesis", "见方法部分")
    return text


def _export_pdf(path: Path, plan: dict, analysis: dict, bundle: dict) -> dict:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import BaseDocTemplate, Frame, Image, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.pdfgen.canvas import Canvas
    from functools import partial
    font, width, height = _pdf_fonts(), *A4
    margin, usable = 44, width - 88
    styles = {
        "title": ParagraphStyle("title", fontName=font, fontSize=21, leading=29, textColor=colors.HexColor(COLORS["ink"]), spaceAfter=14, wordWrap="CJK"),
        "heading": ParagraphStyle("heading", fontName=font, fontSize=12.8, leading=19, textColor=colors.HexColor(COLORS["ink"]), spaceBefore=9, spaceAfter=5, wordWrap="CJK"),
        "body": ParagraphStyle("body", fontName=font, fontSize=9.8, leading=15.4, spaceAfter=7, wordWrap="CJK", alignment=TA_LEFT),
        "small": ParagraphStyle("small", fontName=font, fontSize=8.1, leading=12.3, spaceAfter=5, textColor=colors.HexColor("#536779"), wordWrap="CJK"),
        "caption": ParagraphStyle("caption", fontName=font, fontSize=8.3, leading=12.4, spaceAfter=9, wordWrap="CJK"),
        "cell": ParagraphStyle("cell", fontName=font, fontSize=8.4, leading=12, wordWrap="CJK"),
    }
    def para(text, style="body"):
        return Paragraph(html.escape(str(text)).replace("\n", "<br/>"), styles[style])
    def section(title, text):
        return [para(title, "heading"), para(text)]
    metrics = analysis["metrics_dict"]
    table_rows = [[para("统计量", "cell"), para("实际计算值", "cell")]]
    labels = dict(METRIC_LABELS)
    labels["n"] = "完整配对数" if analysis["plan"]["design"] == "paired" else "有效独立观测数"
    labels["estimate"] = "回归斜率" if analysis["plan"]["design"] == "regression" else "均值差（比较条件减去参照条件）"
    ci_label = f"{analysis['plan'].get('confidence', 0.95) * 100:g}%"
    labels["ci_low"], labels["ci_high"] = ci_label + " 置信区间下界", ci_label + " 置信区间上界"
    for key in ["n", "estimate", "ci_low", "ci_high", "p_value"]:
        table_rows.append([para(labels[key], "cell"), para(_format_metric(metrics[key], key), "cell")])
    table = Table(table_rows, colWidths=[usable * 0.60, usable * 0.40], hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eff4")),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fa")]),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 9),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 5),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    def figure(index, size=1.0):
        item = bundle["figures"][index]
        return [Image(item["paths"]["png"], width=usable * size, height=usable * size * 4.5 / 7.4),
                para(f"图 {index + 1} | {item['caption']}", "caption")]
    narrative, study = plan["narrative"], _study()
    diagnostics_text = _diagnostics_text(analysis)
    provenance = ("本报告使用脚本生成的合成实验数据，仅用于测试科研分析与报告流程，不构成真实学科发现。"
                  f"设计：{analysis['plan']['design']}；统计方法：{analysis['statistics'].get('method', '见分析记录')}。")
    ledger = (f"研究编号：{study.get('id', study.get('study_id', study.get('case_id', '见元数据')))}\n"
              f"数据 SHA-256：{analysis.get('data_sha256', '')}\n"
              f"分析记录：{plan['analysis_id']}\n图集记录：{plan['figure_bundle_id']}\n"
              "报告数值来自锁定的统计记录；LLM 提供叙事和图表/页数选择，确定性工具生成文件。"
              "每张图另存 PNG、SVG 和 PDF。完整工具与模型调用日志由 benchmark runner 另行保存。")
    heading = [para("RESEARCH REPORT / SYNTHETIC BENCHMARK", "small"), para(narrative["title"], "title")]
    pages = []
    count = plan["target_pages"]
    if count == 2:
        pages.append(heading + section("研究摘要", narrative["summary"]) + section("分析方法", narrative["methods"]) + [table, Spacer(1, 9)] + figure(0, 0.88))
        second = section("结果解释", narrative["findings"])
        for index in range(1, len(bundle["figures"])):
            second += figure(index, 0.72 if len(bundle["figures"]) == 3 else 0.86)
        second += section("限制与后续决策", narrative["limitations"] + "\n" + narrative["next_steps"])
        second += [para(provenance, "small"), para(diagnostics_text, "small"), para(ledger, "small")]
        pages.append(second)
    elif count == 3:
        pages.append(heading + section("研究摘要", narrative["summary"]) + section("方法与分析范围", narrative["methods"]) + [table] + section("结果解释", narrative["findings"]) + [para(provenance, "small")])
        pages.append([para("数据与效应可视化", "title")] + figure(0, 0.90) + figure(1, 0.90))
        final = [para("诊断、限制与复现", "title")]
        if len(bundle["figures"]) == 3:
            final += figure(2, 0.83)
        final += section("诊断记录", diagnostics_text) + section("研究限制", narrative["limitations"]) + section("下一步建议", narrative["next_steps"]) + [para(ledger, "small")]
        pages.append(final)
    else:
        pages.append(heading + section("研究摘要", narrative["summary"]) + section("分析方法", narrative["methods"]) + [table] + section("结果解释", narrative["findings"]) + [para(provenance, "small")])
        pages.append([para("原始观测与质量诊断", "title")] + figure(0) + section("数据检查与模型诊断", diagnostics_text) + [para("诊断以实际清洗与分析输出为依据；是否足以支持学科结论仍需研究者审查实验设计和数据来源。", "small")])
        third = [para("效应、不确定性与补充图", "title")]
        for index in range(1, len(bundle["figures"])):
            third += figure(index, 0.86)
        third += [para("图中统计值与前页分析表共享同一分析记录。图片文件的哈希与图像质量检查结果保存在图集验证记录中。", "small")]
        pages.append(third)
        pages.append([para("解释边界与复现记录", "title")] + section("研究限制", narrative["limitations"]) + section("下一步研究决策", narrative["next_steps"]) + section("数据与执行来源", provenance) + [para(ledger, "small")] + section("分析计划", _plan_text(analysis["plan"])) + [para("合成数据仅检验流程可执行性；自动检查覆盖页数、文件一致性、数值引用和版面边界，不能替代专家审稿。", "small")])
    # Fail clearly instead of silently adding pages or truncating LLM content.
    frame_height = height - 104
    for i, items in enumerate(pages):
        used = sum(item.wrap(usable, frame_height)[1] + item.getSpaceBefore() + item.getSpaceAfter() for item in items)
        if used > frame_height - 8:
            raise ValueError(f"Page {i + 1} would overflow ({used:.0f} > {frame_height - 8:.0f} points). Shorten narrative or choose a larger user-approved page budget.")
    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d4e0e8")); canvas.line(margin, 41, width - margin, 41)
        canvas.setFont(font, 8); canvas.setFillColor(colors.HexColor("#64798b"))
        canvas.drawString(margin, 28, "科研数据分析报告 | 合成数据 / Synthetic data")
        canvas.drawRightString(width - margin, 28, f"{doc.page} / {count}")
        canvas.restoreState()
    doc = BaseDocTemplate(str(path), pagesize=A4, leftMargin=margin, rightMargin=margin,
                          topMargin=52, bottomMargin=52, title=narrative["title"], author="Research Report Agent Benchmark")
    frame = Frame(margin, 52, usable, frame_height, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id="report", frames=frame, onPage=decorate))
    story = []
    for i, items in enumerate(pages):
        if i: story.append(PageBreak())
        story.extend(items)
    doc.build(story, canvasmaker=partial(Canvas, invariant=1))
    return {"font": font, "planned_pages": count, "figure_count": len(bundle["figures"])}


def export_report(report_plan_id: str) -> dict:
    """Create a real PDF; preserve approved narrative and actual metric references."""
    plan = _payload(report_plan_id, "report_plan")
    analysis, bundle = _analysis(plan["analysis_id"]), _payload(plan["figure_bundle_id"], "figure_bundle")
    if any(_hash(Path(path)) != item["sha256"][extension] for item in bundle["figures"] for extension, path in item["paths"].items()):
        raise ValueError("A figure changed after rendering; regenerate and review the figure bundle.")
    directory = Path(get_run_dir()) / "artifacts" / report_plan_id.replace(":", "_")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "research_report.pdf"
    metadata = _export_pdf(path, plan, analysis, bundle)
    narrative_path = directory / "narrative_and_metrics.json"
    narrative_path.write_text(json.dumps({"narrative": plan["narrative"], "metrics": analysis["metrics_dict"],
                              "metric_references": plan["metric_references"], "synthetic": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    identifier = put_record("report", {"plan_id": report_plan_id, "analysis_id": plan["analysis_id"],
                            "figure_bundle_id": plan["figure_bundle_id"], "path": str(path.resolve()),
                            "sha256": _hash(path), "narrative_path": str(narrative_path.resolve()),
                            "metadata": metadata, "target_pages": plan["target_pages"], "synthetic": True},
                            authorized_tools=_authorization(plan, ("verify_report",)))
    return tool_response(identifier, "report_id", {"path": str(path.resolve()), "metadata": metadata})


def verify_report(report_id: str) -> dict:
    """Open the saved PDF, check page count/text/metric references and page bounds.

    This is deterministic QA, not a claim that an expert has approved the science.
    """
    import fitz
    report = _payload(report_id, "report")
    plan, analysis = _payload(report["plan_id"], "report_plan"), _analysis(report["analysis_id"])
    path = Path(report["path"])
    pages, overflow, image_count, texts = [], [], 0, []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc):
            text = page.get_text()
            texts.append(text)
            count = len(page.get_images(full=True))
            image_count += count
            pages.append({"page": i + 1, "characters": len(text.strip()), "embedded_images": count})
            for block in page.get_text("dict")["blocks"]:
                x0, y0, x1, y1 = block["bbox"]
                if x0 < 15 or y0 < 15 or x1 > page.rect.width - 15 or y1 > page.rect.height - 15:
                    overflow.append({"page": i + 1, "bbox": [round(x, 2) for x in (x0, y0, x1, y1)]})
    all_text = "\n".join(texts)
    compact_text = re.sub(r"\s", "", all_text)
    metric_checks = {key: _format_metric(analysis["metrics_dict"][key], key) in all_text for key in plan["metric_references"]}
    narrative_checks = {key: re.sub(r"\s", "", value) in compact_text for key, value in plan["narrative"].items()}
    checks = {"file_hash_matches": _hash(path) == report["sha256"],
              "page_count_matches": len(pages) == report["target_pages"],
              "all_pages_have_text": all(item["characters"] >= 50 for item in pages),
              "figure_count_matches": image_count == report["metadata"]["figure_count"],
              "no_page_boundary_overflow": not overflow,
              "synthetic_label_present": "Synthetic data" in all_text,
              "all_metric_references_present": all(metric_checks.values()),
              "all_narrative_fields_present": all(narrative_checks.values()),
              "no_unresolved_placeholders": "{" not in all_text and "}" not in all_text,
              "no_replacement_glyphs": "\ufffd" not in all_text}
    payload = {"report_id": report_id, "quality_passed": all(checks.values()), "checks": checks,
               "pages": pages, "metric_checks": metric_checks, "narrative_checks": narrative_checks,
               "overflow": overflow, "review_scope": "Automated artifact validation; visual and scientific review must be reported separately."}
    identifier = put_record("report_verification", payload)
    return tool_response(identifier, "report_verification_id", payload)
