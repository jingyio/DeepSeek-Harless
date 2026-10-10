"""Review-only CSV recomputation; no import of benchmark numerical helpers."""
from __future__ import annotations

import csv
import math
from pathlib import Path
import statistics


def recompute(csv_path, plan):
    # Explicit elementary formulas; scipy supplies distribution functions and
    # Shapiro-Wilk, not the pandas/statsmodels fit used by the task tools.
    from scipy import stats
    with Path(csv_path).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    design = plan["design"]
    ycol = plan["outcome_column"]
    usable = []
    for row in rows:
        try:
            y = float(row[ycol])
            if not math.isfinite(y):
                continue
            if design == "regression":
                x = float(row[plan["predictor_column"]])
                if math.isfinite(x):
                    usable.append((x, y))
            elif row[plan["group_column"]] in (plan["reference_group"], plan["comparison_group"]):
                if design != "paired" or row[plan["subject_column"]]:
                    usable.append((row, y))
        except (ValueError, TypeError):
            continue
    summaries, extras = [], {}
    if design == "paired":
        grouped = {}
        for row, y in usable:
            subject, group = row[plan["subject_column"]], row[plan["group_column"]]
            bucket = grouped.setdefault(subject, {})
            if group in bucket:
                raise ValueError("Duplicate subject-condition data cannot be silently paired")
            bucket[group] = y
        pairs = [(values[plan["reference_group"]], values[plan["comparison_group"]])
                 for _, values in sorted(grouped.items())
                 if plan["reference_group"] in values and plan["comparison_group"] in values]
        a, b = [x[0] for x in pairs], [x[1] for x in pairs]
        differences = [right - left for left, right in pairs]
        n = len(differences)
        estimate, sd = statistics.mean(differences), statistics.stdev(differences)
        se, df, retained = sd / math.sqrt(n), n - 1, 2 * n
        effect = estimate / sd
        residuals = [value - estimate for value in differences]
    elif design == "independent_groups":
        a = [y for row, y in usable if row[plan["group_column"]] == plan["reference_group"]]
        b = [y for row, y in usable if row[plan["group_column"]] == plan["comparison_group"]]
        n, retained = len(a) + len(b), len(a) + len(b)
        ma, mb = statistics.mean(a), statistics.mean(b)
        va, vb = statistics.variance(a), statistics.variance(b)
        estimate, se2 = mb - ma, va / len(a) + vb / len(b)
        se = math.sqrt(se2)
        df = se2 ** 2 / ((va / len(a)) ** 2 / (len(a) - 1) + (vb / len(b)) ** 2 / (len(b) - 1))
        pooled = math.sqrt(((len(a) - 1) * va + (len(b) - 1) * vb) / (n - 2))
        effect = estimate / pooled * (1 - 3 / (4 * (n - 2) - 1))
        residuals = [v - ma for v in a] + [v - mb for v in b]
    elif design == "regression":
        n, retained = len(usable), len(usable)
        xs, ys = zip(*usable)
        mx, my = statistics.mean(xs), statistics.mean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        estimate = sum((x - mx) * (y - my) for x, y in usable) / sxx
        intercept = my - estimate * mx
        residuals = [y - (intercept + estimate * x) for x, y in usable]
        sse = sum(e * e for e in residuals)
        df = n - 2
        residual_sd = math.sqrt(sse / df)
        se, effect = residual_sd / math.sqrt(sxx), estimate
        extras = {"intercept": intercept, "r_squared": 1 - sse / sum((y - my) ** 2 for y in ys), "residual_sd": residual_sd}
    else:
        raise ValueError("Unsupported design: " + str(design))
    if design in ("independent_groups", "paired"):
        for name, values in ((plan["reference_group"], a), (plan["comparison_group"], b)):
            sd = statistics.stdev(values)
            summaries.append({"group": name, "n": len(values), "mean": statistics.mean(values), "sd": sd, "sem": sd / math.sqrt(len(values))})
    tvalue = estimate / se
    margin = float(stats.t.ppf((1 + plan["confidence"]) / 2, df)) * se
    sw = stats.shapiro(residuals)
    return {"statistics": {"estimate": estimate, "standard_error": se, "statistic": tvalue,
                            "df": df, "ci_low": estimate - margin, "ci_high": estimate + margin,
                            "p_value": float(2 * stats.t.sf(abs(tvalue), df)), "n": n,
                            "effect_size": effect, **extras, **({"group_summaries": summaries} if summaries else {})},
            "diagnostics": {"input_rows": len(rows), "retained_rows": retained,
                            "excluded_rows": len(rows) - retained, "shapiro_w": float(sw.statistic), "shapiro_p": float(sw.pvalue)},
            "method_note": "Separate CSV + elementary formulas; scipy t CDF/quantile and Shapiro implementation are shared mathematical dependencies, not independent statistical methods."}


def numeric_differences(expected, actual, prefix="$", relative=1e-7, absolute=1e-10):
    """Only compare recomputed numeric keys; don't hide unexpected/missing values."""
    errors = []
    if isinstance(expected, dict):
        for key, value in expected.items():
            if key == "method_note":
                continue
            if not isinstance(actual, dict) or key not in actual:
                errors.append({"field": prefix + "." + key, "error": "missing", "expected": value})
            else:
                errors.extend(numeric_differences(value, actual[key], prefix + "." + key, relative, absolute))
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            errors.append({"field": prefix, "error": "list size differs"})
        else:
            for i, (left, right) in enumerate(zip(expected, actual)):
                errors.extend(numeric_differences(left, right, f"{prefix}[{i}]", relative, absolute))
    elif isinstance(expected, (int, float)):
        # Tiny probabilities must not pass merely because their absolute value
        # is below the tolerance used for dimensional quantities.
        tolerance = 1e-300 if prefix.endswith((".p_value", ".shapiro_p")) else absolute
        if not isinstance(actual, (int, float)) or not math.isfinite(actual) or not math.isclose(expected, actual, rel_tol=relative, abs_tol=tolerance):
            errors.append({"field": prefix, "expected": expected, "actual": actual})
    elif expected != actual:
        errors.append({"field": prefix, "expected": expected, "actual": actual})
    return errors
