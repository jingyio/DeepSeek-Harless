"""Real CSV inspection, statistical computation and independent numeric checks."""
from __future__ import annotations

import csv
import math
import statistics as stdstats

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm

from common import (get_case_dir, get_record, get_study, put_record,
                    sha256_file, study_version, tool_response)


def _study(identifier: str) -> dict:
    result = get_study()
    if identifier != result["study_id"]:
        raise ValueError("study is outside this task's scope")
    return result


def _frame() -> pd.DataFrame:
    result = pd.read_csv(get_case_dir() / "data.csv")
    if not 3 <= len(result) <= 100000:
        raise ValueError("dataset row count is outside this benchmark's bounds")
    return result


def inspect_study(study_id: str) -> dict:
    """Read actual scoped CSV/schema/missingness before choosing an analysis plan."""
    study = _study(study_id)
    frame = _frame()
    preview = frame.head(6).astype(object).where(pd.notna(frame.head(6)), None).to_dict("records")
    payload = {"study_id": study_id, "study": study, "row_count": len(frame),
               "schema": {col: str(dtype) for col, dtype in frame.dtypes.items()},
               "missing_by_column": {col: int(count) for col, count in frame.isna().sum().items()},
               "unique_values": {col: frame[col].dropna().unique().tolist()
                                 for col in frame if frame[col].nunique() <= 8},
               "preview": preview}
    identifier = put_record("inspection", payload)
    return tool_response(identifier, "inspection_id", payload)


def _validate_plan(frame: pd.DataFrame, proposed: dict) -> dict:
    if not isinstance(proposed, dict):
        raise ValueError("plan must be an object")
    plan = dict(proposed)
    design = plan.get("design")
    if design not in {"independent_groups", "paired", "regression"}:
        raise ValueError("design must be independent_groups, paired or regression")
    if plan.get("missing_policy") != "complete_case":
        raise ValueError("explicit missing_policy=complete_case is required; do not silently impute")
    confidence = plan.get("confidence", 0.95)
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0.8 <= confidence <= 0.99:
        raise ValueError("confidence must be a proportion from 0.80 to 0.99")
    plan["confidence"] = float(confidence)
    if not isinstance(plan.get("hypothesis"), str) or not plan["hypothesis"].strip():
        raise ValueError("hypothesis must explain the statistical comparison")
    if type(plan.get("allow_deterministic_continuation", False)) is not bool:
        raise ValueError("allow_deterministic_continuation must be a boolean")
    plan.setdefault("allow_deterministic_continuation", False)
    required = ["outcome_column"]
    if design == "regression":
        required.append("predictor_column")
    else:
        required.append("group_column")
        if design == "paired":
            required.append("subject_column")
    for key in required:
        if not isinstance(plan.get(key), str) or plan[key] not in frame:
            raise ValueError(f"{key} must name an existing CSV column")
    if not pd.api.types.is_numeric_dtype(frame[plan["outcome_column"]]):
        raise ValueError("outcome must be numeric")
    if design == "regression":
        if not pd.api.types.is_numeric_dtype(frame[plan["predictor_column"]]):
            raise ValueError("predictor must be numeric")
        if plan["outcome_column"] == plan["predictor_column"]:
            raise ValueError("predictor and outcome must differ")
    else:
        labels = frame[plan["group_column"]].dropna().unique().tolist()
        if len(labels) != 2 or set(labels) != {plan.get("reference_group"), plan.get("comparison_group")}:
            raise ValueError("reference_group and comparison_group must name the two actual conditions")
        if design == "paired":
            if frame.duplicated([plan["subject_column"], plan["group_column"]]).any():
                raise ValueError("duplicate subject-condition rows require semantic resolution")
        else:
            unit = get_study().get("sampling_unit_column")
            if unit in frame and frame[unit].duplicated().any():
                raise ValueError("repeated sampling units require paired analysis, not independent groups")
    return plan


def plan_analysis(study_id: str, plan: dict) -> dict:
    """Approve a semantic statistical plan. Required plan keys: design (one of
    independent_groups, paired, regression), outcome_column, missing_policy
    (complete_case), confidence (e.g. 0.95), hypothesis (a two-sided research
    question). For group designs set group_column, reference_group,
    comparison_group; paired also needs subject_column. For regression set
    predictor_column. The estimand is comparison minus reference, or OLS slope.
    All implemented significance tests are two-sided. Set
    allow_deterministic_continuation=true only to authorize this plan's calculation
    and verification, never selection of another analysis or interpretation.
    """
    _study(study_id)
    plan = _validate_plan(_frame(), plan)
    permissions = ["run_analysis"] if plan["allow_deterministic_continuation"] else []
    identifier = put_record("analysis_plan", {"study_id": study_id, "plan": plan}, permissions)
    return tool_response(identifier, "plan_id", {"approved_plan": plan,
                         "next_step": "run_analysis with this plan_id; after verification interpret the results"})


def _clean(frame: pd.DataFrame, plan: dict) -> tuple[pd.DataFrame, list[str]]:
    keys = [plan["outcome_column"]]
    numeric = keys[:]
    if plan["design"] == "regression":
        keys += [plan["predictor_column"]]
        numeric += [plan["predictor_column"]]
    else:
        keys += [plan["group_column"]]
        if plan["design"] == "paired":
            keys += [plan["subject_column"]]
    frame = frame.copy()
    for col in numeric:
        frame[col] = pd.to_numeric(frame[col], errors="raise").replace([np.inf, -np.inf], np.nan)
    cleaned = frame.dropna(subset=keys).copy()
    warnings = []
    if plan["design"] == "paired":
        counts = cleaned.groupby(plan["subject_column"])[plan["group_column"]].nunique()
        complete = counts[counts == 2].index
        cleaned = cleaned[cleaned[plan["subject_column"]].isin(complete)].copy()
    dropped = len(frame) - len(cleaned)
    if dropped:
        warnings.append(f"Complete-case policy excluded {dropped} of {len(frame)} rows; missingness assumptions are unverified.")
    warnings.append("All observations are synthetic; the result demonstrates an analysis workflow, not substantive scientific evidence.")
    return cleaned, warnings


def run_analysis(plan_id: str) -> dict:
    """Execute the approved plan with pandas/scipy/statsmodels on real CSV bytes."""
    parent = get_record(plan_id, "analysis_plan")
    plan = parent["payload"]["plan"]
    original = _frame()
    data, warnings = _clean(original, plan)
    ycol, design = plan["outcome_column"], plan["design"]
    confidence = plan["confidence"]
    alpha = 1.0 - confidence
    group_summaries = []
    if design in {"independent_groups", "paired"}:
        gcol, ref, comp = plan["group_column"], plan["reference_group"], plan["comparison_group"]
        arrays = {group: data.loc[data[gcol] == group, ycol].to_numpy(dtype=float) for group in (ref, comp)}
        if min(map(len, arrays.values())) < 4:
            raise ValueError("at least four complete units per condition are required")
        for group, values in arrays.items():
            group_summaries.append({"group": group, "n": len(values), "mean": float(np.mean(values)),
                                    "sd": float(np.std(values, ddof=1)),
                                    "sem": float(stats.sem(values))})
        if design == "independent_groups":
            a, b = arrays[ref], arrays[comp]
            result = stats.ttest_ind(b, a, equal_var=False)
            estimate = float(b.mean() - a.mean())
            va, vb = float(a.var(ddof=1)), float(b.var(ddof=1))
            se2 = va / len(a) + vb / len(b)
            df = se2 ** 2 / ((va / len(a)) ** 2 / (len(a) - 1) + (vb / len(b)) ** 2 / (len(b) - 1))
            se = math.sqrt(se2)
            pooled = math.sqrt(((len(a) - 1) * va + (len(b) - 1) * vb) / (len(a) + len(b) - 2))
            correction = 1.0 - 3.0 / (4.0 * (len(a) + len(b) - 2) - 1.0)
            effect_size = estimate / pooled * correction
            effect_name, method, n = "Hedges g", "Welch independent-samples t-test", len(data)
            residuals = np.concatenate((a - a.mean(), b - b.mean()))
        else:
            wide = data.pivot(index=plan["subject_column"], columns=gcol, values=ycol)
            a, b = wide[ref].to_numpy(), wide[comp].to_numpy()
            difference = b - a
            if np.std(difference, ddof=1) == 0:
                raise ValueError("zero variance of paired differences requires semantic review")
            result = stats.ttest_rel(b, a)
            estimate, se = float(difference.mean()), float(stats.sem(difference))
            df, n = len(difference) - 1, len(difference)
            effect_size = estimate / float(np.std(difference, ddof=1))
            effect_name, method, residuals = "Cohen dz", "Paired t-test", difference - difference.mean()
        margin = float(stats.t.ppf(1 - alpha / 2, df)) * se
        computed = {"method": method, "estimate": estimate, "ci_low": estimate - margin,
                    "ci_high": estimate + margin, "p_value": float(result.pvalue), "n": n,
                    "effect_name": effect_name, "effect_size": float(effect_size), "df": float(df),
                    "standard_error": se, "statistic": float(result.statistic),
                    "contrast": f"{comp} minus {ref}", "group_summaries": group_summaries}
    else:
        if len(data) < 6 or data[plan["predictor_column"]].nunique() < 3:
            raise ValueError("regression requires at least six rows and three distinct predictor values")
        x = data[plan["predictor_column"]].to_numpy(dtype=float)
        y = data[ycol].to_numpy(dtype=float)
        fitted = sm.OLS(y, sm.add_constant(x)).fit()
        interval = fitted.conf_int(alpha=alpha)[1]
        residuals = fitted.resid
        computed = {"method": "Ordinary least squares with intercept", "estimate": float(fitted.params[1]),
                    "ci_low": float(interval[0]), "ci_high": float(interval[1]),
                    "p_value": float(fitted.pvalues[1]), "n": len(data), "effect_name": "Slope",
                    "effect_size": float(fitted.params[1]), "df": float(fitted.df_resid),
                    "standard_error": float(fitted.bse[1]), "statistic": float(fitted.tvalues[1]),
                    "intercept": float(fitted.params[0]), "r_squared": float(fitted.rsquared),
                    "residual_sd": math.sqrt(float(fitted.mse_resid)),
                    "contrast": f"change in {ycol} per unit {plan['predictor_column']}"}
        warnings.append("Regression estimates association; no causal conclusion is warranted.")
    shapiro = stats.shapiro(np.asarray(residuals))
    diagnostics = {"normality_check": "Shapiro-Wilk on within-group/paired/regression residuals",
                   "shapiro_w": float(shapiro.statistic), "shapiro_p": float(shapiro.pvalue),
                   "input_rows": len(original), "retained_rows": len(data),
                   "excluded_rows": len(original) - len(data),
                   "independence": "Assumed from study design; not statistically proved"}
    if shapiro.pvalue < 0.05:
        warnings.append("Residual normality check flagged a departure; interpret small-sample t intervals cautiously.")
    metrics = {key: computed[key] for key in ("estimate", "ci_low", "ci_high", "p_value", "n", "effect_size")}
    metrics.update({"excluded_rows": diagnostics["excluded_rows"], "input_rows": len(original),
                    "confidence": confidence})
    if "r_squared" in computed:
        metrics["r_squared"] = computed["r_squared"]
    payload = {"study_id": parent["payload"]["study_id"], "plan_id": plan_id, "plan": plan,
               "cleaned_records": data.astype(object).where(pd.notna(data), None).to_dict("records"),
               "statistics": computed, "metrics_dict": metrics, "diagnostics": diagnostics,
               "warnings": warnings, "data_sha256": sha256_file(get_case_dir() / "data.csv"),
               "source_csv": str(get_case_dir() / "data.csv"), "source_version": study_version()}
    allowed = ["verify_analysis"] if plan["allow_deterministic_continuation"] else []
    identifier = put_record("analysis", payload, allowed)
    return tool_response(identifier, "analysis_id", {"statistics": computed, "metrics_dict": metrics,
                        "diagnostics": diagnostics, "warnings": warnings,
                        "next_step": "verify_analysis, then use the LLM to choose figures and interpret results"})


def _independent_recompute(plan: dict) -> dict:
    """Separate csv + Python statistics/formula route, no pandas/statsmodels fit reuse."""
    with (get_case_dir() / "data.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    design, ycol = plan["design"], plan["outcome_column"]
    usable = []
    for row in rows:
        try:
            y = float(row[ycol])
            if not math.isfinite(y):
                continue
            if design == "regression":
                x = float(row[plan["predictor_column"]])
                if not math.isfinite(x):
                    continue
                usable.append((x, y))
            elif row[plan["group_column"]] and (design != "paired" or row[plan["subject_column"]]):
                usable.append((row, y))
        except (ValueError, TypeError):
            continue
    if design == "independent_groups":
        a = [value for row, value in usable if row[plan["group_column"]] == plan["reference_group"]]
        b = [value for row, value in usable if row[plan["group_column"]] == plan["comparison_group"]]
        n = len(a) + len(b)
        estimate = stdstats.mean(b) - stdstats.mean(a)
        va, vb = stdstats.variance(a), stdstats.variance(b)
        se2 = va / len(a) + vb / len(b)
        se = math.sqrt(se2)
        df = se2 ** 2 / ((va / len(a)) ** 2 / (len(a) - 1) + (vb / len(b)) ** 2 / (len(b) - 1))
        retained_rows = n
        pooled = math.sqrt(((len(a) - 1) * va + (len(b) - 1) * vb) / (n - 2))
        effect_size = estimate / pooled * (1 - 3 / (4 * (n - 2) - 1))
        extras = {}
    elif design == "paired":
        by_subject = {}
        for row, value in usable:
            by_subject.setdefault(row[plan["subject_column"]], {})[row[plan["group_column"]]] = value
        differences = [group[plan["comparison_group"]] - group[plan["reference_group"]]
                       for group in by_subject.values()
                       if plan["reference_group"] in group and plan["comparison_group"] in group]
        n = len(differences)
        estimate = stdstats.mean(differences)
        se, df = stdstats.stdev(differences) / math.sqrt(n), n - 1
        effect_size, retained_rows, extras = estimate / stdstats.stdev(differences), 2 * n, {}
    else:
        n = len(usable)
        xs, ys = zip(*usable, strict=True)
        mx, my = stdstats.mean(xs), stdstats.mean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in usable) / sxx
        intercept = my - slope * mx
        sse = sum((y - (intercept + slope * x)) ** 2 for x, y in usable)
        sst = sum((y - my) ** 2 for y in ys)
        estimate, se, df = slope, math.sqrt(sse / (n - 2) / sxx), n - 2
        effect_size, retained_rows = slope, n
        extras = {"intercept": intercept, "r_squared": 1 - sse / sst}
    critical = float(stats.t.ppf((1 + plan["confidence"]) / 2, df))
    return {"estimate": estimate, "ci_low": estimate - critical * se,
            "ci_high": estimate + critical * se, "p_value": float(2 * stats.t.sf(abs(estimate / se), df)),
            "n": n, "effect_size": effect_size, "retained_rows": retained_rows, **extras}


def verify_analysis(analysis_id: str) -> dict:
    """Independently re-read CSV, recompute formulas and verify version/numeric results.
    This returns to the LLM for scientific interpretation and figure selection.
    """
    record = get_record(analysis_id, "analysis")
    payload = record["payload"]
    if payload["data_sha256"] != sha256_file(get_case_dir() / "data.csv"):
        raise ValueError("analysis source bytes changed")
    independent = _independent_recompute(payload["plan"])
    errors = {}
    for key, value in independent.items():
        actual = payload["diagnostics"][key] if key == "retained_rows" else payload["statistics"][key]
        if not math.isclose(value, actual, rel_tol=1e-9, abs_tol=1e-10):
            errors[key] = {"independent": value, "analysis": actual}
    if errors:
        raise ValueError(f"independent numeric verification failed: {errors}")
    identifier = put_record("analysis_verification", {"analysis_id": analysis_id,
                            "plan_id": payload["plan_id"], "passed": True,
                            "independent_method": "csv + Python statistics + explicit formulas; scipy t distribution only",
                            "checked_metrics": independent, "tolerance": {"relative": 1e-9, "absolute": 1e-10}})
    return tool_response(identifier, "verification_id", {"passed": True, "checked_metrics": independent,
                        "next_step": "LLM must interpret the verified results and choose a figure plan"})
