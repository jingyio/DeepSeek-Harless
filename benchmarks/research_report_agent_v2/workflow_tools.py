"""Approved scientific workflow with real calculations, files and bounded layout repair.

Capabilities/standard paragraphs are deliberately hand-designed software; motif
edges must still be learned from actual ordinary DSH trajectories. No oracle or
case-name-to-method routing is used. v1 files and the Harness/core are untouched.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import statistics as stdstats
import sys
import textwrap

try:
    from . import common as context
except ImportError:
    import common as context

get_record, put_record, tool_response = context.get_record, context.put_record, context.tool_response
get_study, get_run_dir = context.get_study, context.get_run_dir


def _legacy(name):
    """Bind unchanged v1 numerical/plot helpers to a private v2 context module.
    Temporary import aliasing happens once at process startup, not per request.
    It does not mutate the v1 module imported by any other benchmark.
    """
    path = Path(__file__).resolve().parents[1] / 'research_report_agent_v1' / f'{name}.py'
    spec = importlib.util.spec_from_file_location('_rra_v2_legacy_' + name, path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get('common')
    sys.modules['common'] = context
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop('common', None)
        else:
            sys.modules['common'] = previous
    return module


statistics_tools = _legacy('data_tools')
plot_helpers = _legacy('report_ops')
_original_clean = statistics_tools._clean


def _clean_with_declared_provenance(frame, plan):
    cleaned, warnings = _original_clean(frame, plan)
    warnings = [item for item in warnings if not item.startswith('All observations are synthetic;')]
    if get_study().get('synthetic') is True:
        warnings.append('Observations are declared synthetic: software demonstration only, not empirical scientific evidence.')
    else:
        warnings.append('Data origin and collection design are taken from supplied metadata; their authenticity has not been independently verified.')
    return cleaned, warnings


statistics_tools._clean = _clean_with_declared_provenance
FIGURE_KINDS = plot_helpers.FIGURE_KINDS
ROLES = {'summary', 'methods', 'results', 'diagnostics', 'limitations', 'next_steps', 'provenance'}
DEFAULT_OUTLINE = [
    {'heading': '研究问题与摘要', 'roles': ['summary']},
    {'heading': '数据与统计方法', 'roles': ['methods']},
    {'heading': '结果与不确定性', 'roles': ['results']},
    {'heading': '诊断与适用条件', 'roles': ['diagnostics']},
    {'heading': '限制与后续工作', 'roles': ['limitations', 'next_steps']},
    {'heading': '来源与可复核记录', 'roles': ['provenance']},
]
BRIEF_OUTLINE = [
    {'heading': '研究问题', 'roles': ['summary']},
    {'heading': '方法与主要结果', 'roles': ['methods', 'results']},
    {'heading': '诊断与限制', 'roles': ['diagnostics', 'limitations']},
    {'heading': '后续与来源', 'roles': ['next_steps', 'provenance']},
]


def _user_headings(value):
    if isinstance(value, str):
        return [re.sub(r'^#{1,6}\s+', '', line.strip()) for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [item if isinstance(item, str) else item['heading'] for item in value]
    raise ValueError('User outline must be newline-separated headings or a list of headings')


def _payload(identifier, kind=None):
    return get_record(identifier, kind)['payload']


def _workflow(plan_id):
    return _payload(plan_id, 'analysis_plan')['workflow']


def _authorized(plan_id, next_tool):
    return [next_tool] if _workflow(plan_id)['allow_deterministic_continuation'] else []


def _clarify(message):
    return {'ok': False, 'clarification_required': True, 'reason': str(message),
            'next_step': 'Ask for missing design information or revise the explicit plan; do not invent assumptions.'}


def _fixed_decisions(study):
    if 'benchmark_frozen_decisions' not in study:
        return None
    try:
        from .matched_protocol import fixed_decisions
    except ImportError:
        from matched_protocol import fixed_decisions
    return fixed_decisions(study)


def _validate_fixed_decision(study, kind, value):
    if 'benchmark_frozen_decisions' not in study:
        return
    try:
        from .matched_protocol import validate_fixed_decision
    except ImportError:
        from matched_protocol import validate_fixed_decision
    validate_fixed_decision(study, kind, value)


def _figure_title(value, index):
    if not isinstance(value, str) or len(value) > 100 or not value.isascii():
        raise ValueError(f'figures[{index}].title must be at most 100 ASCII English characters. '
                         'Omit the optional title field (or use an empty string) for the built-in English title. '
                         'This plot font does not support Chinese titles; Chinese report headings remain supported. '
                         'If a Chinese figure title is explicitly required, clarify this limitation rather than silently replacing it.')
    return value


def _research_options_requirement(study):
    """Narrow request cue, not a general semantic or scientific classifier."""
    request = study.get('user_request', '')
    patterns = [r'(?:比较|对比).{0,12}(?:两|二|2|不同|多种|多项).{0,16}(?:研究|采样|后续).{0,8}(?:方案|选择|设计)',
                r'compare.{0,20}(?:two|2|alternative).{0,24}(?:research|sampling|study).{0,12}(?:options|designs|plans)']
    # Scope the negation to the same clause, so a later affirmative request still
    # counts. This is deliberately a finite cue rule, not language understanding.
    matches = [(clause,m) for clause in re.split(r'[。.!！?？;；,，\n]',request)
               for pattern in patterns for m in re.finditer(pattern, clause, re.I)]
    def negated(clause, match):
        prefix = clause[:match.start()]
        return bool(re.search(r'(?:不需要|无需|不必|不要|不用|不要求|无需再|do\s+not|don.t|no\s+need\s+to)\s*(?:进行|再|进一步|please\s+)?\s*$', prefix, re.I))
    match = next((m for clause,m in matches if not negated(clause,m)), None)
    explicit = study.get('report_requirements', {}).get('research_options_min', 0)
    return {'minimum':max(2 if match else 0, explicit if type(explicit) is int else 0),
            'request_excerpt':match.group() if match else None,
            'scope':'Finite explicit comparison cues or supplied research_options_min; not automatic understanding of arbitrary requests.'}


def inspect_study() -> dict:
    """Read the scoped CSV, metadata and user request. No study ID is required.
    Identify design/columns/missingness and optional outline before approval.
    Unknown units, randomization and source authenticity remain unknown.
    """
    result = statistics_tools.inspect_study(get_study()['study_id'])
    result['user_request'] = (context.get_case_dir() / 'task.txt').read_text(encoding='utf-8')
    result['supported_designs'] = sorted(FIGURE_KINDS)
    result['supported_plot_kinds'] = {key: sorted(value) for key, value in FIGURE_KINDS.items()}
    result['research_options_requirement'] = _research_options_requirement(get_study())
    fixed = _fixed_decisions(get_study())
    if fixed is not None:
        result['benchmark_fixed_decisions'] = fixed
    result['next_step'] = 'approve_workflow: choose the analysis, figures, report outline/requirements and whether standard or custom interpretation is needed.'
    return result


def approve_workflow(study_id: str, plan: dict) -> dict:
    """Approve ONE whole workflow after reading the actual inputs.

    plan={analysis:{design:independent_groups|paired|regression,outcome_column,
      group_column/reference_group/comparison_group and subject_column if paired,
      predictor_column if regression,missing_policy:'complete_case',confidence:0.95,
      hypothesis:'two-sided question',design_evidence:{source:user_request|
      study_description,quote:'exact excerpt supporting the design'}},
      figures:[{kind,title?:ASCII English}],
      report:{title?,outline?:[{heading,roles:[summary|methods|results|diagnostics|
      limitations|next_steps|provenance]}],page_mode:auto|max|exact,pages?:1..6,
      style:brief|technical|paper},interpretation_mode:standard|custom,
      custom_focus?:discussion|research_options,
      allow_deterministic_continuation:true}.
    Include methods/results/diagnostics/limitations roles, combining roles under
    user headings as appropriate. Choose 1-3 distinct design-compatible plots.
    Figure title is optional: OMIT it for a built-in English title. Supplied
    titles must be ASCII English, at most 100 characters; Chinese plot titles
    are unsupported and rejected explicitly, never silently discarded.
    For max/exact one-page reports, this full-width layout supports at most one
    figure; prefer one figure and combine headings. If the user explicitly
    requires more figures on one page, explain the layout constraint conflict
    rather than silently deleting a requested figure or changing the page limit.
    A one-page brief supports at most four outline headings. Combine your own
    proposed headings before approval; do not remove explicit user headings.
    If the user asks to compare research/sampling alternatives, use custom mode
    with custom_focus=research_options; later provide at least two structured
    research_options and a comparison_summary based on the actual results.
    Standard mode fills scientific paragraphs from verified values and explicit
    design rules without further LLM writing; custom mode pauses after evidence
    for approve_interpretation. Approval grants only this scoped plan's work.
    If the request/context does not establish how observations are related,
    ask the user; do not infer independence/pairing from columns or filenames.
    """
    try:
        study = get_study()
        _validate_fixed_decision(study, 'plan', plan)
        if study_id != study['study_id']:
            raise ValueError('study_id is outside the selected input scope')
        if not isinstance(plan, dict) or type(plan.get('allow_deterministic_continuation', False)) is not bool:
            raise ValueError('Explicit boolean allow_deterministic_continuation required')
        permitted = plan.get('allow_deterministic_continuation', False)
        analysis = dict(plan.get('analysis') or {})
        analysis['allow_deterministic_continuation'] = permitted
        basis = analysis.get('design_evidence')
        if not isinstance(basis, dict) or basis.get('source') not in {'user_request', 'study_description'}:
            raise ValueError('analysis.design_evidence must cite user_request or study_description')
        source = study.get('user_request', '') if basis['source'] == 'user_request' else study.get('description', '')
        quote = basis.get('quote')
        if (not isinstance(quote, str) or not 8 <= len(quote.strip()) <= 1500 or quote not in source
                or source.startswith('未提供研究设计说明')):
            raise ValueError('Design evidence needs an exact supplied excerpt, not invented or missing context')
        analysis = statistics_tools._validate_plan(statistics_tools._frame(), analysis)
        # Independence information cannot be inferred from the topic or case ID.
        if analysis['design'] == 'paired' and not analysis.get('subject_column'):
            raise ValueError('Paired design requires an observed pairing identifier')
        figures = plan.get('figures', [])
        if not isinstance(figures, list) or not 1 <= len(figures) <= 3:
            raise ValueError('Choose 1-3 distinct figures')
        kinds = [item.get('kind') for item in figures if isinstance(item, dict)]
        if len(kinds) != len(figures) or len(set(kinds)) != len(kinds) or not set(kinds) <= FIGURE_KINDS[analysis['design']]:
            raise ValueError(f"Compatible figure kinds: {sorted(FIGURE_KINDS[analysis['design']])}")
        primary = {'independent_groups': 'distribution_ci', 'paired': 'paired_change', 'regression': 'scatter_fit'}[analysis['design']]
        if primary not in kinds:
            raise ValueError(f'Include the primary raw-data plot {primary}')
        normalized_figures = [{'kind': item['kind'], 'title': _figure_title(item.get('title', ''), index)}
                              for index, item in enumerate(figures)]
        report = dict(plan.get('report') or {})
        report.setdefault('title', study.get('title', '科研数据分析报告'))
        if not isinstance(report['title'], str) or not 1 <= len(report['title']) <= 180:
            raise ValueError('Report title must be 1-180 characters')
        report.setdefault('page_mode', 'auto'); report.setdefault('pages', None); report.setdefault('style', 'technical')
        if report['page_mode'] not in {'auto', 'max', 'exact'} or report['style'] not in {'brief', 'technical', 'paper'}:
            raise ValueError('Supported page_mode: auto/max/exact; style: brief/technical/paper')
        if report['page_mode'] != 'auto' and (type(report['pages']) is not int or not 1 <= report['pages'] <= 6):
            raise ValueError('max/exact page modes require pages=1..6')
        if report['page_mode'] == 'auto':
            report['pages'] = None
        required = study.get('report_requirements', {})
        if required.get('figure_count') is not None and len(figures) != required['figure_count']:
            raise ValueError(f"Requested figure_count is {required['figure_count']}")
        for key in ('style', 'page_mode'):
            if key in required and report[key] != required[key]:
                raise ValueError(f"User requested report {key}={required[key]}")
        if required.get('pages') is not None and report['pages'] != required['pages']:
            raise ValueError(f"User requested pages={required['pages']}")
        if report['page_mode'] in {'max', 'exact'} and report['pages'] == 1 and len(figures) > 1:
            raise ValueError('Current single-column full-width one-page layout supports at most one figure. '
                             'Choose one figure only if the user permits it, or clarify the conflict between '
                             'the requested figure count and one-page limit; do not silently remove figures.')
        outline = report.get('outline') or (BRIEF_OUTLINE if report['style'] == 'brief' else DEFAULT_OUTLINE)
        normalized_outline, covered = [], set()
        if not isinstance(outline, list) or not 1 <= len(outline) <= 10:
            raise ValueError('Outline must contain 1-10 heading-to-role mappings')
        for item in outline:
            if not isinstance(item, dict) or not isinstance(item.get('heading'), str) or not 1 <= len(item['heading']) <= 90:
                raise ValueError('Each outline heading needs a short text heading')
            roles = item.get('roles', [item.get('role')])
            if not isinstance(roles, list) or not roles or not set(roles) <= ROLES:
                raise ValueError(f'Outline roles must come from {sorted(ROLES)}')
            if covered.intersection(roles):
                raise ValueError('Each scientific role must appear once, not in duplicate sections')
            covered.update(roles); normalized_outline.append({'heading': item['heading'], 'roles': roles})
        if not {'methods', 'results', 'diagnostics', 'limitations'} <= covered:
            raise ValueError('Outline must cover methods/results/diagnostics/limitations; combine roles when using fewer headings')
        if study.get('user_outline'):
            requested_headings = _user_headings(study['user_outline'])
            if [item['heading'] for item in normalized_outline] != requested_headings:
                raise ValueError('Preserve the user outline headings and their order exactly: ' + repr(requested_headings))
        if report['style'] == 'brief' and report['page_mode'] in {'max','exact'} and report['pages'] == 1 and len(normalized_outline) > 4:
            raise ValueError('One-page brief profile supports at most four headings. '
                             'Combine model-proposed headings and resubmit the plan. If these headings were explicitly '
                             'required by the user, explain the capacity conflict; do not silently delete them.')
        report['outline'] = normalized_outline
        mode = plan.get('interpretation_mode', 'standard')
        if mode not in {'standard', 'custom'}:
            raise ValueError('interpretation_mode must be standard or custom')
        requirement = _research_options_requirement(study)
        focus = plan.get('custom_focus', 'research_options' if requirement['minimum'] else 'discussion')
        if focus not in {'discussion','research_options'}:
            raise ValueError('custom_focus must be discussion or research_options')
        if requirement['minimum'] and (mode != 'custom' or focus != 'research_options'):
            raise ValueError('The supplied request explicitly asks to compare research alternatives: '+str(requirement['request_excerpt'])+
                             '. Approve custom mode with custom_focus=research_options; the tool validates structure, not scientific correctness.')
        minimum_options = max(2,requirement['minimum']) if focus == 'research_options' else 0
        workflow = {'analysis': analysis, 'figures': normalized_figures, 'report': report,
                    'interpretation_mode': mode, 'custom_focus':focus, 'research_options_min':minimum_options,
                    'research_options_requirement':requirement, 'allow_deterministic_continuation': permitted}
        identifier = put_record('analysis_plan', {'study_id': study_id, 'plan': analysis, 'workflow': workflow},
                                ['run_analysis'] if permitted else [])
        return tool_response(identifier, 'plan_id', {'approved_workflow': workflow,
                             'next_step': 'run_analysis(plan_id); follow returned continuation instructions and stop for any semantic handoff.'})
    except (ValueError, TypeError, KeyError) as error:
        return _clarify(error)


def run_analysis(plan_id: str) -> dict:
    """Execute the approved statistics on real CSV bytes; do not select a new design."""
    _workflow(plan_id)
    result = statistics_tools.run_analysis(plan_id)
    result['next_step'] = 'verify_analysis(analysis_id); follow the approved workflow receipts.'
    return result


def _verify_auxiliary_statistics(analysis):
    """Re-read CSV via Python formulas, independently of the pandas/OLS fit.

    Shapiro uses the same scipy test implementation on reconstructed residuals;
    this is a lineage/recomputation check, not another normality-test algorithm.
    """
    from scipy import stats
    plan = analysis['plan']
    with (context.get_case_dir() / 'data.csv').open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    usable = []
    for row in rows:
        try:
            y = float(row[plan['outcome_column']])
            if not math.isfinite(y):
                continue
            if plan['design'] == 'regression':
                x = float(row[plan['predictor_column']])
                if math.isfinite(x):
                    usable.append((x, y))
            elif row[plan['group_column']] and (plan['design'] != 'paired' or row[plan['subject_column']]):
                usable.append((row, y))
        except (ValueError, TypeError):
            continue
    extras = {}
    if plan['design'] == 'regression':
        xs, ys = zip(*usable, strict=True)
        n, mx, my = len(usable), stdstats.mean(xs), stdstats.mean(ys)
        sxx = sum((x - mx)**2 for x in xs)
        estimate = sum((x-mx)*(y-my) for x,y in usable) / sxx
        intercept = my-estimate*mx
        residuals = [y-intercept-estimate*x for x,y in usable]
        variance = sum(x*x for x in residuals)/(n-2)
        se, df, retained = math.sqrt(variance/sxx), n-2, n
        extras['residual_sd'] = math.sqrt(variance)
    else:
        ref, comp = plan['reference_group'], plan['comparison_group']
        if plan['design'] == 'paired':
            pairs = {}
            for row,y in usable:
                pairs.setdefault(row[plan['subject_column']], {})[row[plan['group_column']]] = y
            complete = [pair for pair in pairs.values() if ref in pair and comp in pair]
            a, b = [pair[ref] for pair in complete], [pair[comp] for pair in complete]
            changes = [y-x for x,y in zip(a,b,strict=True)]
            estimate = stdstats.mean(changes)
            se, df, retained = stdstats.stdev(changes)/math.sqrt(len(changes)), len(changes)-1, 2*len(changes)
            residuals = [value-estimate for value in changes]
        else:
            a = [y for row,y in usable if row[plan['group_column']] == ref]
            b = [y for row,y in usable if row[plan['group_column']] == comp]
            ma, mb, va, vb = stdstats.mean(a), stdstats.mean(b), stdstats.variance(a), stdstats.variance(b)
            se2 = va/len(a) + vb/len(b)
            estimate, se, retained = mb-ma, math.sqrt(se2), len(a)+len(b)
            df = se2**2 / ((va/len(a))**2/(len(a)-1) + (vb/len(b))**2/(len(b)-1))
            residuals = [x-ma for x in a] + [x-mb for x in b]
        for name, values in (('reference',a), ('comparison',b)):
            extras.update({name+'_n':len(values), name+'_mean':stdstats.mean(values), name+'_sd':stdstats.stdev(values)})
    normality = stats.shapiro(residuals)
    checked = {'standard_error':se, 'statistic':estimate/se, 'df':df,
               'shapiro_w':float(normality.statistic), 'shapiro_p':float(normality.pvalue),
               'input_rows':len(rows), 'retained_rows':retained, 'excluded_rows':len(rows)-retained, **extras}
    observed = {key:analysis['statistics'][key] for key in ('standard_error','statistic','df')}
    observed.update({key:analysis['diagnostics'][key] for key in ('shapiro_w','shapiro_p','input_rows','retained_rows','excluded_rows')})
    if plan['design'] == 'regression':
        observed['residual_sd'] = analysis['statistics']['residual_sd']
    else:
        groups = {item['group']:item for item in analysis['statistics']['group_summaries']}
        for prefix, group in (('reference',plan['reference_group']), ('comparison',plan['comparison_group'])):
            observed.update({prefix+'_'+key:groups[group][key] for key in ('n','mean','sd')})
    mismatches = {key:{'observed':observed[key], 'recomputed':value} for key,value in checked.items()
                  if not math.isclose(value, observed[key], rel_tol=1e-7, abs_tol=1e-10)}
    if mismatches:
        raise ValueError('Auxiliary statistic/diagnostic verification failed: ' + str(mismatches))
    return checked


def verify_analysis(analysis_id: str) -> dict:
    """Independently re-read and recompute CSV results, then return a verified receipt."""
    checked = statistics_tools.verify_analysis(analysis_id)
    analysis = _payload(analysis_id, 'analysis')
    auxiliary = _verify_auxiliary_statistics(analysis)
    identifier = put_record('verified_analysis', {'analysis_id': analysis_id, 'plan_id': analysis['plan_id'],
                            'check_id': checked['verification_id'], 'checked_metrics': checked['checked_metrics'],
                            'checked_auxiliary': auxiliary, 'passed': True},
                            _authorized(analysis['plan_id'], 'build_evidence'))
    return tool_response(identifier, 'verified_id', {'passed': True, 'next_step': 'build_evidence(verified_id)'})


_METRIC_MEANINGS = {
    'estimate':'comparison minus reference, or OLS slope; see approved design',
    'ci_low':'lower bound of the effect confidence interval', 'ci_high':'upper bound of the effect confidence interval',
    'p_value':'two-sided test p value', 'n':'complete pairs for paired design; otherwise complete observations',
    'effect_size':'Hedges g / Cohen dz / OLS slope according to design',
    'confidence':'approved confidence proportion', 'confidence_pct':'approved confidence percentage; append % after token',
    'alpha':'two-sided decision threshold, one minus approved confidence', 'null_value':'null effect tested by these methods',
    'unit_increment':'defined one-unit increase in the original predictor scale; not an empirical result or a unit conversion',
    'input_rows':'raw CSV row count', 'retained_rows':'retained complete-case CSV rows', 'excluded_rows':'excluded CSV rows',
    'statistic':'signed t statistic for the specified contrast or slope', 'df':'test degrees of freedom',
    'standard_error':'standard error of the effect estimate', 'shapiro_w':'Shapiro-Wilk W on reconstructed residuals',
    'shapiro_p':'Shapiro-Wilk p on reconstructed residuals; not the effect p value',
    'intercept':'OLS intercept', 'r_squared':'OLS coefficient of determination', 'residual_sd':'OLS residual standard deviation',
    'reference_n':'complete observations in reference condition', 'comparison_n':'complete observations in comparison condition',
    'reference_mean':'mean in reference condition', 'comparison_mean':'mean in comparison condition',
    'reference_sd':'sample standard deviation in reference condition', 'comparison_sd':'sample standard deviation in comparison condition',
}


def _placeholder_catalog(analysis, verified):
    metrics = {**analysis['metrics_dict'], **verified['checked_metrics'], **verified['checked_auxiliary']}
    confidence = analysis['plan']['confidence']
    metrics.update(confidence=confidence, confidence_pct=confidence*100, alpha=1-confidence, null_value=0, unit_increment=1)
    return {name:{'token':'{{'+name+'}}', 'value':value, 'display':_number(value),
                  'meaning':_METRIC_MEANINGS[name],
                  'source':('approved_plan.confidence' if name in {'confidence','confidence_pct','alpha'} else
                            'supported_test.null_effect_constant' if name == 'null_value' else
                            'supported_model.per_original_unit_definition' if name == 'unit_increment' else
                            'verified_analysis.checked_auxiliary' if name in verified['checked_auxiliary'] else
                            'verified_analysis.checked_metrics' if name in verified['checked_metrics'] else
                            'source_bound_analysis.metrics_dict')}
            for name,value in metrics.items()}


def _commentary_contract(evidence_id, payload=None):
    minimum = (payload or {}).get('workflow', {}).get('research_options_min', 0)
    result = {'paragraph_count':'1-8', 'characters_per_paragraph':'10-800 before binding; total custom text at most 8000 characters; one-page briefs also undergo measured final-text capacity checks',
            'required_flag':'allow_deterministic_continuation must explicitly be true',
            'number_rule':'Use only exact {{name}} tokens from available_placeholders for quantitative claims. '
                          'Write {{confidence_pct}}% for confidence percentage, {{alpha}} for the decision threshold, '
                          'and {{null_value}} for the tested zero. Plain numeric claims are rejected. '
                          'For a regression slope, write 每升高{{unit_increment}}个原始单位; unit_increment is the defined constant one, not estimated data. '
                          'Optional paragraph prefixes 1. through 8. are formatting only and must match paragraph order.',
            'example':{'evidence_id':evidence_id, 'commentary':{
                'paragraphs':['效应估计为{{estimate}}，{{confidence_pct}}%置信区间为[{{ci_low}}, {{ci_high}}]，双侧p={{p_value}}。'
                              'Shapiro–Wilk W={{shapiro_w}}、p={{shapiro_p}}；诊断不能证明所有模型假设成立，进一步研究仍需审查采样设计。'],
                'allow_deterministic_continuation':True}}}
    result['unit_slope_example'] = '解释变量每升高{{unit_increment}}个原始单位，拟合平均结局变化为{{estimate}}；该表述不证明因果。'
    result['scientific_wording_constraints'] = [
        'The observed range is not a validated extrapolation interval; distinguish within-range association from extrapolation.',
        'A p value or normality diagnostic does not prove model assumptions, causality, or that adding repeats/covariates will improve normality.',
        'Report effect_size as an estimate; never compare it with its own value as if that value were an independent threshold.',
        'Describe untested design changes as hypotheses. These rules and numeric binding are not expert scientific approval.']
    result['research_options'] = {'required_minimum':minimum,
        'format':'research_options: [{name:2-80 chars,rationale:10-600 chars,tradeoff:10-400 chars}], comparison_summary:20-700 chars',
        'note':'If required, supply at least two distinct research/sampling alternatives and an explicit comparison of objectives or trade-offs. Structure is checked; scientific merit still needs review.'}
    if minimum:
        result['example']['commentary'].update(research_options=[
            {'name':'研究选项甲','rationale':'结合本次{{estimate}}及诊断说明该方案服务的目标。','tradeoff':'说明资源代价与适用限制，不保证改善正态性。'},
            {'name':'研究选项乙','rationale':'结合置信区间与本次研究问题提出另一种不同的研究安排。','tradeoff':'说明相对第一种方案的代价或局限，并标明待验证条件。'}],
            comparison_summary='请用本次结果比较两个方案的目标与取舍，并说明选择依据；这是格式示例，实际内容由模型填写。')
    return result


def build_evidence(verified_id: str) -> dict:
    """Assemble verified numeric evidence. Standard mode continues; custom mode
    stops here for an LLM approve_interpretation call after observing results.
    Returns available_placeholders with exact tokens, values, meanings and
    source fields, plus interpretation_contract with a valid call example.
    Use that contract, including its explicit true continuation flag.
    """
    verified = _payload(verified_id, 'verified_analysis')
    analysis = _payload(verified['analysis_id'], 'analysis')
    workflow = _workflow(verified['plan_id'])
    catalog = _placeholder_catalog(analysis, verified)
    payload = {**verified, 'verified_id': verified_id, 'workflow': workflow,
               'interpretation_approved': workflow['interpretation_mode'] == 'standard',
               'custom_commentary': [], 'metrics': {key:item['value'] for key,item in catalog.items()},
               'available_placeholders': catalog, 'diagnostics': analysis['diagnostics']}
    allowed = _authorized(verified['plan_id'], 'render_figures') if payload['interpretation_approved'] else []
    identifier = put_record('evidence', payload, allowed)
    result = tool_response(identifier, 'evidence_id', {'statistics': analysis['statistics'], 'diagnostics': analysis['diagnostics'],
        'available_placeholders': catalog, 'interpretation_contract': _commentary_contract(identifier,payload),
        'semantic_handoff_required': not payload['interpretation_approved'],
        'next_step': 'render_figures(evidence_id)' if payload['interpretation_approved'] else
                     'LLM: inspect the results, then approve_interpretation(evidence_id, commentary).'})
    fixed = _fixed_decisions(get_study())
    if fixed is not None and fixed.get('commentary') is not None:
        result['benchmark_fixed_commentary'] = fixed['commentary']
    return result


def approve_interpretation(evidence_id: str, commentary: dict) -> dict:
    """Custom-mode semantic checkpoint AFTER actual results.
    REQUIRED commentary={paragraphs:[1-8 strings, each 10-800 characters],
    allow_deterministic_continuation:true,research_options?:[{name,rationale,
    tradeoff}],comparison_summary?:str}. For research_options focus, supply at
    least two distinct options plus an explicit comparison_summary; all their
    numeric claims follow the SAME token rule. Custom text is inserted into an
    existing outline section. One-page briefs undergo final-text height checks
    before approval; shorten commentary using the SAME evidence_id after errors,
    without rerunning statistics. Copy the valid structure returned
    by build_evidence.interpretation_contract. All quantitative claims use exact
    tokens from available_placeholders: e.g. {{estimate}}, {{confidence_pct}}%,
    {{alpha}}, {{null_value}}, {{statistic}}, {{df}}, {{shapiro_w}}, {{shapiro_p}}.
    For per-unit slopes use 每升高{{unit_increment}}个原始单位 (the defined one-unit
    increment); never invent measurement units. Total custom text is capped at
    8000 characters as a resource limit; actual layout constraints still apply.
    Do not type literal confidence levels, p values, sample sizes or thresholds.
    Optional paragraph prefixes 1. through 8. must match paragraph order. Failures
    return ALL detected errors with paragraph locations and replacement hints;
    fix every listed issue in one call, retaining the explicit true flag.
    Scientific meaning of free prose remains unverified and labeled for review.
    """
    payload = _payload(evidence_id, 'evidence')
    try:
        _validate_fixed_decision(get_study(), 'commentary', commentary)
    except ValueError as error:
        return _clarify(error)
    if payload['workflow']['interpretation_mode'] != 'custom':
        return _clarify('This approved workflow uses standard interpretation; custom authorization was not requested')
    metrics = payload['metrics']
    catalog = payload['available_placeholders']
    errors, bindings, rendered, rendered_fields = [], [], [], {}
    if not isinstance(commentary, dict):
        commentary = {}
        errors.append({'code':'commentary_type', 'field':'commentary', 'message':'Must be an object with paragraphs and allow_deterministic_continuation.'})
    paragraphs = commentary.get('paragraphs')
    if not isinstance(paragraphs, list):
        errors.append({'code':'paragraphs_type', 'field':'commentary.paragraphs', 'message':'Must be a list of 1-8 strings.'})
        paragraphs = []
    elif not 1 <= len(paragraphs) <= 8:
        errors.append({'code':'paragraph_count', 'field':'commentary.paragraphs', 'actual':len(paragraphs),
                       'message':'Use 1-8 paragraphs. The final text must also satisfy the actual requested page capacity.'})
    minimum_options = payload['workflow'].get('research_options_min',0)
    options = commentary.get('research_options',[])
    if not isinstance(options,list):
        errors.append({'code':'research_options_type','field':'commentary.research_options','message':'Use a list of objects with name, rationale and tradeoff.'})
        options = []
    if (minimum_options and len(options)<minimum_options) or len(options)>4:
        errors.append({'code':'research_options_count','field':'commentary.research_options','actual':len(options),
                       'required_minimum':minimum_options,'message':'Supply at least the required number of distinct options, at most four; a list of analysis methods alone is not a comparison of study designs.'})
    text_items = [(f'paragraphs[{i}]',p,10,800,i+1) for i,p in enumerate(paragraphs)]
    for i,option in enumerate(options):
        if not isinstance(option,dict):
            errors.append({'code':'research_option_shape','field':f'research_options[{i}]','message':'Each option needs name, rationale, tradeoff.'})
            continue
        for field,low,high in [('name',2,80),('rationale',10,600),('tradeoff',10,400)]:
            text_items.append((f'research_options[{i}].{field}',option.get(field),low,high,None))
    names = [option.get('name') for option in options if isinstance(option,dict) and isinstance(option.get('name'),str)]
    if len(set(names)) != len(names):
        errors.append({'code':'duplicate_research_option','field':'research_options','message':'Option names must be distinct; distinct names alone do not prove different scientific designs.'})
    if minimum_options or options or commentary.get('comparison_summary') is not None:
        text_items.append(('comparison_summary',commentary.get('comparison_summary'),20,700,None))
    total_characters = sum(len(value) for _,value,*_ in text_items if isinstance(value,str))
    if total_characters > 8000:
        errors.append({'code':'custom_text_resource_limit','field':'commentary','actual_characters':total_characters,
                       'maximum_characters':8000,'message':'Total custom text must not exceed 8000 characters; this resource bound does not replace final page-capacity checks.'})
    if commentary.get('allow_deterministic_continuation') is not True:
        errors.append({'code':'explicit_authorization_required', 'field':'commentary.allow_deterministic_continuation',
                       'message':'Set the JSON boolean true explicitly if approving this interpretation and continuation. It is never inserted automatically.'})
    placeholder = re.compile(r'\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}')
    for field,paragraph,minimum_length,maximum_length,index in text_items:
        first_error = len(errors)
        if not isinstance(paragraph, str) or not minimum_length <= len(paragraph) <= maximum_length:
            errors.append({'code':'paragraph_length', 'paragraph':index,
                           'field':field,
                           'actual_characters':len(paragraph) if isinstance(paragraph,str) else None,
                           'message':f'{field} must be a string of {minimum_length}-{maximum_length} characters.'})
            if not isinstance(paragraph, str):
                continue
        names = placeholder.findall(paragraph)
        unknown = sorted(set(names)-metrics.keys())
        if unknown:
            errors.append({'code':'unknown_placeholder', 'paragraph':index, 'names':unknown,
                           'message':'Use only names listed in available_placeholders; e.g. shapiro_p is distinct from p_value.'})
        remaining = placeholder.sub('', paragraph)
        if '{' in remaining or '}' in remaining:
            errors.append({'code':'malformed_placeholder', 'paragraph':index,
                           'fragments':re.findall(r'[{}]+[^{}]*[{}]+', remaining)[:8],
                           'message':'Use exactly two braces on each side and a listed snake_case name, e.g. {{shapiro_p}}. Single braces, spaces and expressions are invalid.'})
        # Correctly ordered leading paragraph numbers are structural labels,
        # never accepted as scientific constants elsewhere in the prose.
        if index is not None:
            remaining = re.sub(r'^\s*' + str(index) + r'[.)、]\s*', '', remaining)
        for match in re.finditer(r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?[%％]?', remaining):
            literal = match.group()
            percentage = literal.endswith(('%','％'))
            value = float(literal.rstrip('%％'))
            hints = [item['token'] + ('%' if percentage else '') for name,item in catalog.items()
                     if math.isclose(float(item['value']), value, rel_tol=1e-9, abs_tol=1e-10)
                     and (not percentage or name == 'confidence_pct')]
            errors.append({'code':'unbound_number', 'paragraph':index, 'literal':literal,
                           'context':remaining[max(0,match.start()-14):match.end()+14], 'replacement_hints':hints,
                           'message':'Replace a quantitative value with its corresponding verified token; remove unsupported claims. Use nonnumeric bullets for formatting.'})
        if not unknown:
            value = placeholder.sub(lambda m: _number(metrics[m.group(1)]), paragraph)
            rendered_fields[field] = value
            if index is not None:
                rendered.append(value)
        if re.search(r'(?:效应量|效应大小).{0,35}(?:大于|超过|高于|小于|低于).{0,12}\{\{effect_size\}\}',paragraph):
            errors.append({'code':'self_effect_comparison','paragraph':index,
                           'message':'Do not compare effect_size against itself as a benchmark. Report the estimate and separate any externally justified importance threshold.'})
        for error in errors[first_error:]:
            error.setdefault('field',field)
        bindings.append({'paragraph':index,'field':field,'names':sorted(set(names)), 'source_evidence_id':evidence_id})
    if errors:
        return {'ok':False, 'clarification_required':True, 'reason':'Interpretation validation failed; fix every listed issue before retrying.',
                'validation_errors':errors, 'available_placeholders':catalog,
                'interpretation_contract':_commentary_contract(evidence_id,payload),
                'next_step':'Revise commentary in one call using the returned example, 1-8 paragraphs, bound numeric tokens and explicit true authorization. No continuation was authorized.'}
    candidate = {**payload, 'parent_evidence_id': evidence_id, 'custom_commentary': rendered,
                 'custom_commentary_template':paragraphs, 'custom_bindings':bindings,
                 'research_options':[{'name':rendered_fields[f'research_options[{i}].name'],
                                      'rationale':rendered_fields[f'research_options[{i}].rationale'],
                                      'tradeoff':rendered_fields[f'research_options[{i}].tradeoff']} for i in range(len(options))],
                 'research_options_template':options, 'comparison_summary':rendered_fields.get('comparison_summary'),
                 'comparison_summary_template':commentary.get('comparison_summary'), 'interpretation_approved':True}
    capacity = _check_interpretation_capacity(candidate)
    if capacity and not capacity['fits_one_page']:
        return {'ok':False,'clarification_required':True,'reason':'Expanded one-page report exceeds the measured layout capacity.',
                'validation_errors':[{'code':'one_page_text_capacity','field':'commentary','capacity':capacity,
                                      'message':'Shorten your commentary/options while preserving the requested content. Retry approve_interpretation with this same evidence_id; statistics do not need to be rerun. Do not silently drop user requirements.'}],
                'interpretation_contract':_commentary_contract(evidence_id,payload),
                'next_step':'Use current rendered character count and measured height budget to shorten commentary; this is a preflight estimate, not final PDF acceptance. No continuation authorized.'}
    payload = {**candidate,'capacity_preflight':capacity}
    identifier = put_record('evidence', payload, _authorized(payload['plan_id'], 'render_figures'))
    return tool_response(identifier, 'evidence_id', {'custom_prose_scientifically_verified': False,
                         'next_step': 'render_figures(evidence_id)'})


def render_figures(evidence_id: str) -> dict:
    """Render the approved plots into real PNG/SVG/PDF files without LLM codegen."""
    evidence = _payload(evidence_id, 'evidence')
    if not evidence['interpretation_approved']:
        raise ValueError('Custom interpretation is not approved; return to the LLM')
    analysis = _payload(evidence['analysis_id'], 'analysis')
    directory = context.artifact_path(f'artifacts/{evidence_id}/figures')
    directory.mkdir(parents=True, exist_ok=True)
    figures = [_draw_figure(analysis, item, index + 1, directory)
               for index, item in enumerate(evidence['workflow']['figures'])]
    identifier = put_record('figure_bundle', {'plan_id': evidence['plan_id'], 'analysis_id': evidence['analysis_id'],
                            'evidence_id': evidence_id, 'figures': figures}, _authorized(evidence['plan_id'], 'verify_figures'))
    return tool_response(identifier, 'figure_bundle_id', {'figure_count': len(figures), 'next_step': 'verify_figures(figure_bundle_id)'})


def verify_figures(figure_bundle_id: str) -> dict:
    """Re-open image/vector files and check hashes, resolution and metric lineage."""
    checked = plot_helpers.verify_figures(figure_bundle_id)
    bundle = _payload(figure_bundle_id, 'figure_bundle')
    passed = checked['quality_passed'] is True
    identifier = put_record('evidence_packet', {'plan_id': bundle['plan_id'], 'analysis_id': bundle['analysis_id'],
                            'evidence_id': bundle['evidence_id'], 'figure_bundle_id': figure_bundle_id,
                            'figure_check_id': checked['figure_verification_id'], 'quality_passed': passed},
                            _authorized(bundle['plan_id'], 'compose_report') if passed else [])
    return tool_response(identifier, 'packet_id', {'quality_passed': passed, 'checks': checked['checks'],
                         'next_step': 'compose_report(packet_id)' if passed else 'Clarify or repair failed figure generation.'})


def _number(value):
    return str(value) if isinstance(value, int) else f'{value:.5g}'


def _standard_paragraphs(analysis, study):
    """Finite, explicit scientific statements; no inference about unknown design."""
    p, s, d = analysis['plan'], analysis['statistics'], analysis['diagnostics']
    unit = study.get('units', {}).get(p['outcome_column'], '原始结局单位（元数据未注明）')
    ci = f"{p['confidence']*100:g}% 置信区间 [{_number(s['ci_low'])}, {_number(s['ci_high'])}]"
    significance = ('在预设双侧阈值下提供了反对零效应的统计证据。' if s['p_value'] < 1-p['confidence'] else
                    '未达到预设双侧显著性阈值；这不是无效应或等效性的证明。')
    source = ('输入明确标注为合成数据，仅用于软件与分析流程演示，不构成真实学科发现。'
              if study.get('synthetic') is True else
              '本报告分析用户提供的文件；数据采集过程、来源真实性及代表性未经独立核实。')
    if p['design'] == 'paired':
        design = f"按 {p['subject_column']} 对齐两个条件，以 {p['comparison_group']} 减 {p['reference_group']} 计算每个单元的差值，使用双侧配对 t 检验。"
        sampling = f"共纳入 {s['n']} 个完整配对（{d['retained_rows']} 行）；任一条件缺失即排除整对，不将两次测量当作独立样本。"
        independence = '要求不同实验单元的配对差值相互独立；同一单元的两次测量允许相关。差值分布的近似正态性是小样本推断的适用条件。'
        effect = f"平均配对差值为 {_number(s['estimate'])} {unit}；{ci} {unit}；双侧 p={_number(s['p_value'])}；Cohen dz={_number(s['effect_size'])}。"
    elif p['design'] == 'independent_groups':
        design = f"比较 {p['comparison_group']} 与 {p['reference_group']} 两个独立组，方向为比较组减参照组，采用双侧 Welch t 检验，不预先假定方差相等。"
        sampling = '纳入 ' + str(s['n']) + ' 个独立观测；' + '；'.join(f"{x['group']}：n={x['n']}，均值={_number(x['mean'])}，SD={_number(x['sd'])}" for x in s['group_summaries']) + '。'
        independence = '观测之间的独立性来自实验设计信息，不能由本检验证明；使用Welch方法不意味着已经发现组间方差不等。'
        effect = f"均值差为 {_number(s['estimate'])} {unit}；{ci} {unit}；双侧 p={_number(s['p_value'])}；Hedges g={_number(s['effect_size'])}。"
    else:
        xunit = study.get('units', {}).get(p['predictor_column'], '原始解释变量单位（元数据未注明）')
        design = f"以 {p['predictor_column']} 为解释变量、{p['outcome_column']} 为结局，拟合带截距的一元普通最小二乘回归；斜率表示解释变量每增加一个原始单位时平均结局的变化。"
        sampling = f"纳入 {s['n']} 个完整观测；本模型只有一个解释变量，并未进行多变量混杂调整。"
        independence = '线性关系、误差独立性及常规标准误所需的方差条件需要结合设计和残差图判断；回归拟合优度不能证明因果或模型正确。'
        effect = f"斜率为 {_number(s['estimate'])} {unit}/{xunit}；{ci}；双侧 p={_number(s['p_value'])}；R²={_number(s['r_squared'])}。"
    missing = f"原始 {d['input_rows']} 行，完整案例处理后保留 {d['retained_rows']} 行、排除 {d['excluded_rows']} 行；不填充或插补。缺失机制未知，不能保证删除不会引入选择偏差。"
    normality = (f"Shapiro–Wilk 诊断 W={_number(d['shapiro_w'])}，p={_number(d['shapiro_p'])}。"
                 + ('诊断提示偏离正态，常规小样本区间需谨慎解释。' if d['shapiro_p'] < .05 else
                    '未检出明显偏离不等于证明正态；该诊断不是所有假设的验证。'))
    return {'summary': [study.get('research_question') or study.get('description') or '对给定数据执行已批准的统计分析与报告。', source, effect],
            'methods': [design, sampling, missing], 'results': [effect, significance,
                '区间表示参数估计的不确定性，不是单个观测或未来预测的取值范围。统计显著性与实际重要性应分开判断。'],
            'diagnostics': [independence, normality],
            'limitations': [source, '当前分析未建立因果识别或进行混杂控制，本报告只描述条件差异或统计关联。',
                '置信区间以当前统计模型和采样假设为条件，未覆盖所有模型形式与缺失机制偏差。没有针对预先设定最小重要效应的功效分析，不能仅凭不显著结果断言效能不足。'],
            'next_steps': ['明确目标人群、最小重要差异与采样/随机化过程后设计后续研究；在适当条件下进行缺失敏感性分析和模型诊断。若增加重复测量，应建模同一单元内相关。'],
            'provenance': [f"CSV SHA-256：{analysis['data_sha256']}。统计方案先于计算获批；正文标准段落与图件由可复核代码根据批准方案和实际数值生成。"]}


def _brief_paragraphs(analysis, study):
    """Evidence-preserving short form; layout never deletes text to fit pages."""
    p, s, d = analysis['plan'], analysis['statistics'], analysis['diagnostics']
    units = study.get('units', {})
    yunit = units.get(p['outcome_column'], '结局原始单位')
    if p['design'] == 'regression':
        method = f"带截距的一元OLS回归：{p['predictor_column']} → {p['outcome_column']}。斜率单位为 {yunit}/{units.get(p['predictor_column'], '解释变量原始单位')}；n={s['n']}。"
        estimate = '斜率'
        assumption = '推断依赖线性、误差独立与方差假设；仅反映关联，未调整混杂。'
        extra = f"R²={_number(s['r_squared'])}。"
    elif p['design'] == 'paired':
        method = f"以 {p['subject_column']} 匹配，计算 {p['comparison_group']}−{p['reference_group']}，双侧配对t检验；n={s['n']} 对，单位 {yunit}。"
        estimate, extra = '配对均值差', f"Cohen dz={_number(s['effect_size'])}。"
        assumption = '不同单元的差值需独立，同一单元内测量允许相关；缺失时整对排除。'
    else:
        method = f"双侧Welch检验：{p['comparison_group']}−{p['reference_group']}，均值差单位 {yunit}；n={s['n']}。"
        estimate, extra = '均值差', f"Hedges g={_number(s['effect_size'])}。"
        assumption = '要求观测独立，不预设两组方差相等；本检验不能验证实验独立性。'
    outcome = (f"{estimate}={_number(s['estimate'])}，{p['confidence']*100:g}% CI [{_number(s['ci_low'])}, {_number(s['ci_high'])}]；"
               f"双侧p={_number(s['p_value'])}。" + extra)
    conclusion = ('达到预设显著性阈值，仍需评估实际重要性。' if s['p_value'] < 1-p['confidence'] else
                  '未达到显著性阈值，不证明无效应或等效。')
    source = ('数据明确为合成，仅用于软件演示。' if study.get('synthetic') is True else
              '用户提供的数据，来源真实性与代表性未独立核实。')
    return {'summary': [f"分析 {p['outcome_column']} 的条件差异或关联及其不确定性。"],
            'methods': [method + f"完整案例：原始{d['input_rows']}行，保留{d['retained_rows']}行，排除{d['excluded_rows']}行；不插补。"],
            'results': [outcome + conclusion],
            'diagnostics': [assumption + f"残差Shapiro–Wilk p={_number(d['shapiro_p'])}；单一诊断不能证明模型成立。"],
            'limitations': [source + '置信区间依赖模型与采样假设；缺失机制未知，不排除选择偏差；本分析不建立因果。'],
            'next_steps': ['后续需明确采样设计与最小重要效应，并复核异常值及缺失敏感性。'],
            'provenance': [f"输入与复算记录：{analysis['data_sha256'][:12]}；完整哈希见运行记录。"]}


def _interpretation_paragraphs(evidence):
    paragraphs = list(evidence.get('custom_commentary',[]))
    for option in evidence.get('research_options',[]):
        paragraphs.append(f"研究选择「{option['name']}」：理由：{option['rationale']} 取舍：{option['tradeoff']}")
    if evidence.get('comparison_summary'):
        paragraphs.append('方案比较：'+evidence['comparison_summary'])
    return paragraphs


def _document_payload(evidence, analysis, figures):
    """Shared exact text for preflight and final render; preflight never edits it."""
    workflow, study = evidence['workflow'], get_study()
    is_brief = workflow['report']['style'] == 'brief'
    role_text = _brief_paragraphs(analysis, study) if is_brief else _standard_paragraphs(analysis, study)
    sections = []
    attached = False
    for index, item in enumerate(workflow['report']['outline']):
        section = {'id': f'section-{index+1}', 'heading': item['heading'],
                   'paragraphs': [text for role in item['roles'] for text in role_text[role]]}
        if 'results' in item['roles'] and not attached:
            section['figure_indices'] = list(range(len(figures))); attached = True
        sections.append(section)
    discussion = _interpretation_paragraphs(evidence)
    if discussion:
        target = next((i for role in ('next_steps','limitations','results')
                       for i,item in enumerate(workflow['report']['outline']) if role in item['roles']),None)
        discussion[0] = '模型讨论（需科研复核）：'+discussion[0]
        sections[target]['paragraphs'].extend(discussion)
    document = {'title': workflow['report']['title'], 'subtitle': '可追溯科研数据分析报告',
                'sections': sections, 'figures': figures,
                'metrics': [{'label': label, 'value': _number(analysis['metrics_dict'][key])}
                            for key, label in [('n','有效配对数' if analysis['plan']['design']=='paired' else '有效观测数'),
                                               ('estimate','效应估计'),('ci_low','置信下界'),('ci_high','置信上界'),('p_value','双侧p值')]],
                'requirements': {key: workflow['report'][key] for key in ('page_mode','pages','style')},
                'synthetic': study.get('synthetic') is True,
                'provenance': (f"Input: {analysis['data_sha256'][:12]} | Full provenance: run records" if is_brief else
                               f"Study: {study['study_id']} | CSV SHA256: {analysis['data_sha256']}")}
    return document


def _figure_caption(kind, confidence):
    confidence_label = f'{confidence*100:g}%'
    return {
        'distribution_ci':f'每个点是一条有效观测；菱形为组均值，误差线为各组均值的双侧 {confidence_label} t 置信区间。组间差异的推断以本报告统计表中的均值差及其置信区间为准。',
        'group_ecdf':'经验累积分布直接由排序后的有效观测计算，不依赖直方图分箱；组间曲线差异展示整体分布而不只比较均值。',
        'paired_change':'同一条线连接同一个体的两次观测；仅纳入完整配对。连线展示个体变化及异质性，不把配对数据当作独立样本。',
        'change_distribution':'先按个体匹配，再计算比较条件减去参照条件的差值；直方图展示变化分布，虚线为零变化，实线为平均变化。分箱采用 Freedman-Diaconis 规则。',
        'effect_interval':'圆点和区间直接取自统计分析记录；虚线表示零效应。区间表达估计不确定性，不代表个体观测的范围。',
        'scatter_fit':f'点为原始有效观测，线为单变量最小二乘拟合，阴影为均值的双侧 {confidence_label} 置信带；该带不是预测区间。相关关系本身不证明因果关系。',
        'residuals':'残差由实际观测值减去拟合值计算。系统弯曲、漏斗形散布或极端点提示模型假设可能不适合；此图不自动证明假设成立。',
    }[kind]


def _check_interpretation_capacity(candidate):
    req = candidate['workflow']['report']
    if req['style'] != 'brief' or req['page_mode'] not in {'exact','max'} or req['pages'] != 1:
        return None
    analysis = _payload(candidate['analysis_id'],'analysis')
    figures = [{'kind':item['kind'],'aspect_ratio':7.4/4.5,
                'caption':_figure_caption(item['kind'],analysis['plan']['confidence'])}
               for item in candidate['workflow']['figures']]
    document = _document_payload(candidate,analysis,figures)
    measured = _engine().measure_capacity(document)
    custom = _interpretation_paragraphs(candidate)
    count = sum(map(len,custom))
    measured.update(rendered_custom_characters=count,
                    rendered_total_body_characters=sum(len(p) for section in document['sections'] for p in section['paragraphs']),
                    scope='Same-font paragraph/table/figure-height preflight estimate. Final PDF audit is still required; no text was removed or silently rewritten.')
    if not measured['fits_one_page']:
        empty = {**candidate,'custom_commentary':[],'research_options':[],'comparison_summary':None}
        base = _engine().measure_capacity(_document_payload(empty,analysis,figures))
        extra_height = max(0,measured['height_pt']-base['height_pt'])
        available_for_custom = max(0,measured['available_height_pt']-base['height_pt'])
        measured.update(base_content_height_pt=base['height_pt'],available_for_custom_height_pt=available_for_custom,
                        suggested_custom_character_budget=max(0,math.floor(count*min(1,available_for_custom/max(extra_height,1))*.9)),
                        budget_note='Character suggestion is conservatively scaled from this actual expanded payload and measured height, not a universal limit or acceptance guarantee. Preserve meaning when rewriting.')
    return measured


def compose_report(packet_id: str) -> dict:
    """Generate verified standard text and integrate custom discussion inside the
    approved outline. No new headings or LLM-written numbers are invented.
    """
    packet = _payload(packet_id, 'evidence_packet')
    if packet['quality_passed'] is not True:
        raise ValueError('Figure checks must pass before report composition')
    evidence = _payload(packet['evidence_id'], 'evidence')
    analysis = _payload(packet['analysis_id'], 'analysis')
    bundle = _payload(packet['figure_bundle_id'], 'figure_bundle')
    figures = [{'path':item['paths']['png'],'caption':item['caption'],'kind':item['kind']} for item in bundle['figures']]
    document = _document_payload(evidence,analysis,figures)
    identifier = put_record('report_draft', {'plan_id': packet['plan_id'], 'packet_id': packet_id,
                            'analysis_id': packet['analysis_id'], 'document': document}, _authorized(packet['plan_id'], 'layout_report'))
    return tool_response(identifier, 'draft_id', {'section_count': len(document['sections']), 'composition_mode': evidence['workflow']['interpretation_mode'],
                         'next_step': 'layout_report(draft_id)'})


def _engine():
    try:
        from . import document_engine
    except ImportError:
        import document_engine
    return document_engine


def layout_report(draft_id: str) -> dict:
    """Render an actual PDF and perform bounded deterministic layout repairs.
    The same draft and engine version reuse a source/file-hash-checked receipt,
    including failed results; retries never redraw an unchanged draft. Failed
    attempts remain recorded; no text is silently rewritten to force page count.
    """
    draft = _payload(draft_id, 'report_draft')
    packet = _payload(draft['packet_id'], 'evidence_packet')
    bundle = _payload(packet['figure_bundle_id'], 'figure_bundle')
    for figure in bundle['figures']:
        for extension,filename in figure['paths'].items():
            path = Path(filename).resolve()
            if (not path.is_relative_to(get_run_dir()) or not path.is_file()
                    or context.sha256_file(path) != figure['sha256'][extension]):
                raise ValueError('Layout source figure changed or escaped this workspace')
    version = _engine().ENGINE_VERSION
    version_key = hashlib.sha256(version.encode()).hexdigest()[:16]
    destination = context.artifact_path(f'artifacts/{draft_id}/report/{version_key}')
    receipt_path = destination/'layout_receipt.json'
    reused = receipt_path.exists()
    if reused:
        identifier = json.loads(receipt_path.read_text(encoding='utf-8'))['layout_id']
        layout = _payload(identifier, 'report_layout')
        if layout.get('draft_id') != draft_id or layout.get('engine_version') != version:
            raise ValueError('Cached layout receipt does not match the requested draft and engine version')
        result = layout['engine']
        result_path = Path(layout['engine_result_path']).resolve()
        if (not result_path.is_relative_to(destination.resolve()) or not result_path.is_file()
                or context.sha256_file(result_path) != layout['engine_result_sha256']):
            raise ValueError('Cached engine result changed or escaped its artifact directory')
        if result.get('path') is not None:
            audit, _ = _audit_engine_record(layout)
            if not audit.get('checks',{}).get('figure_sources_unchanged',False):
                raise ValueError('Cached layout source figures changed')
        elif result.get('quality_passed'):
            raise ValueError('Cached successful layout has no PDF')
        for attempt in result.get('attempts',[]):
            if attempt.get('sha256'):
                path = Path(attempt['path']).resolve()
                if (not path.is_relative_to(destination.resolve()) or not path.is_file()
                        or context.sha256_file(path) != attempt['sha256']):
                    raise ValueError('Cached layout attempt changed')
    else:
        result = _engine().build_document(draft['document'], destination, repair=True)
        result_path = destination/'layout_result.json'
        identifier = put_record('report_layout', {'plan_id': draft['plan_id'], 'draft_id': draft_id,
                                'engine_version':version,'engine': result,
                                'engine_result_path':str(result_path.resolve()),
                                'engine_result_sha256':context.sha256_file(result_path)},
                                _authorized(draft['plan_id'], 'audit_layout') if result['quality_passed'] else [])
        receipt_path.write_bytes(context.canonical({'layout_id':identifier}))
    audit = result.get('audit',{})
    warnings = audit.get('soft_warnings',audit.get('warnings',[]))
    failed = [name for name,passed in audit.get('checks',{}).items() if not passed]
    return tool_response(identifier, 'layout_id', {'layout_generated': result.get('path') is not None,
                         'quality_passed':result['quality_passed'],
                         'layout_candidate_passed': result['quality_passed'], 'cache_reused':reused,
                         'warnings':warnings,'failed_checks':failed,
                         'attempt_count': len(result['attempts']),
                         'next_step': 'audit_layout(layout_id); retained soft warnings do not block delivery.' if result['quality_passed'] else
                         'Hard layout failure: report the unresolved constraints and failed checks. Do not retry the same draft or rerun statistics. Revise approved content/constraints only through an explicit semantic decision; do not silently delete or rewrite scientific claims.'})


def _audit_engine_record(layout):
    draft = _payload(layout['draft_id'], 'report_draft')
    engine = layout['engine']
    if engine.get('path') is None:
        raise ValueError('No PDF was generated; report this layout limitation or approve a revised document, not another identical layout attempt')
    path = Path(engine['path']).resolve()
    if not path.is_relative_to(get_run_dir()) or context.sha256_file(path) != engine['sha256']:
        raise ValueError('Rendered PDF changed or escaped this workspace')
    manifest_path = Path(engine['manifest_path']).resolve()
    if not manifest_path.is_relative_to(get_run_dir()):
        raise ValueError('Layout manifest escaped this workspace')
    if context.sha256_file(manifest_path) != engine['manifest_sha256']:
        raise ValueError('Saved layout manifest changed')
    if engine.get('audit_path') and engine.get('audit_sha256'):
        audit_path = Path(engine['audit_path']).resolve()
        if not audit_path.is_relative_to(get_run_dir()) or context.sha256_file(audit_path) != engine['audit_sha256']:
            raise ValueError('Saved layout audit changed')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    # The engine manifest may wrap the measured layout under layout_manifest.
    measured = manifest.get('layout_manifest', manifest)
    audit = _engine().audit_document(path, measured, draft['document']['requirements'])
    return audit, draft


def audit_layout(layout_id: str) -> dict:
    """Re-open the actual final PDF and independently apply the saved layout checks."""
    layout = _payload(layout_id, 'report_layout')
    audit, draft = _audit_engine_record(layout)
    passed = audit.get('quality_passed') is True
    identifier = put_record('report', {'plan_id': layout['plan_id'], 'layout_id': layout_id,
                            'draft_id': layout['draft_id'], 'path': layout['engine']['path'],
                            'sha256': layout['engine']['sha256'], 'audit': audit, 'quality_passed': passed},
                            _authorized(layout['plan_id'], 'verify_report') if passed else [])
    return tool_response(identifier, 'report_id', {'quality_passed': passed, 'audit': audit,
        'next_step': 'verify_report(report_id); retain reported soft warnings.' if passed else
        'Hard layout failure: report the failed checks and unresolved constraints. Repeating layout of this unchanged draft reuses the same result. Any content/constraint revision requires an explicit semantic decision; do not silently rewrite scientific claims.'})


def verify_report(report_id: str) -> dict:
    """Verify final PDF hash, repeated layout checks and source-bound analysis receipt."""
    report = _payload(report_id, 'report')
    layout = _payload(report['layout_id'], 'report_layout')
    audit, draft = _audit_engine_record(layout)
    evidence_packet = _payload(draft['packet_id'], 'evidence_packet')
    _payload(evidence_packet['analysis_id'], 'analysis')
    passed = report['quality_passed'] is True and audit.get('quality_passed') is True
    identifier = put_record('report_verification', {'plan_id': report['plan_id'], 'report_id': report_id,
                            'quality_passed': passed, 'path': report['path'], 'sha256': report['sha256'], 'audit': audit},
                            _authorized(report['plan_id'], 'deliver_report') if passed else [])
    return tool_response(identifier, 'verification_id', {'quality_passed': passed,
                         'next_step': 'deliver_report(verification_id)' if passed else 'Report verification failed; do not claim delivery or repeat the unchanged draft. Report the limitation and obtain an explicit semantic revision if needed.'})


def deliver_report(verification_id: str) -> dict:
    """Return a verified artifact location. This is the task completion boundary;
    stop and tell the user the PDF path and any synthetic/custom-review limits.
    """
    verified = _payload(verification_id, 'report_verification')
    if verified['quality_passed'] is not True or context.sha256_file(Path(verified['path'])) != verified['sha256']:
        raise ValueError('Cannot deliver an unverified or changed PDF')
    report = _payload(verified['report_id'], 'report')
    layout = _payload(report['layout_id'], 'report_layout')
    mode = _workflow(verified['plan_id'])['interpretation_mode']
    warnings = verified['audit'].get('soft_warnings',verified['audit'].get('warnings',[]))
    identifier = put_record('delivery', {'plan_id': verified['plan_id'], 'verification_id': verification_id,
                            'report_id': verified['report_id'], 'page_count': layout['engine']['page_count'],
                            'interpretation_mode': mode, 'path': verified['path'], 'sha256': verified['sha256'],
                            'quality_passed': True, 'delivered': True, 'warnings':warnings})
    return tool_response(identifier, 'delivery_id', {'quality_passed': True, 'delivered': True,
                         'path': verified['path'], 'sha256': verified['sha256'],
                         'report_id': verified['report_id'], 'page_count': layout['engine']['page_count'],
                         'interpretation_mode': mode, 'custom_prose_scientifically_verified': False if mode == 'custom' else None,
                         'warnings':warnings,
                         'next_step': 'Task complete: report the file location and retained warnings. Automatic checks are not independent expert review.'})


# Local copy of the existing v1 plot algorithm follows. Only provenance footer
# and the unsupported effect-plot cross-reference are adapted; no v1 file edits.
COLORS = plot_helpers.COLORS
_style_axis = plot_helpers._style_axis
_column_label = plot_helpers._column_label
_frame = plot_helpers._frame
_study = plot_helpers._study
_hash = plot_helpers._hash


def _draw_figure(analysis: dict, item: dict, index: int, directory: Path) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    import numpy as np
    from scipy import stats

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 16,
                         "axes.labelsize":16, "xtick.labelsize":15, "ytick.labelsize":15,
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
    ax.tick_params(labelsize=15)
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
        caption = f"每个点是一条有效观测；菱形为组均值，误差线为各组均值的双侧 {confidence_label} t 置信区间。组间差异的推断以本报告统计表中的均值差及其置信区间为准。"
    elif kind == "group_ecdf":
        group = plan["group_column"]
        names = [plan["reference_group"], plan["comparison_group"]]
        for name, color in zip(names, [COLORS["blue"], COLORS["orange"]]):
            values = np.sort(df.loc[df[group] == name, outcome].to_numpy(dtype=float))
            ax.step(values, np.arange(1, len(values) + 1) / len(values), where="post", color=color, linewidth=2, label=f"{name} (n = {len(values)})")
        ax.set_xlabel(_column_label(outcome)); ax.set_ylabel("Empirical cumulative proportion")
        ax.set_ylim(0, 1.04); ax.legend(frameon=False, fontsize=15)
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
            ax.legend(frameon=False, fontsize=15)
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
        ax.text(0.02, 0.92, f"Estimate = {estimate:.4g}\n{confidence_label} CI [{lo:.4g}, {hi:.4g}]", transform=ax.transAxes, fontsize=15, va="top")
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
            ax.legend(frameon=False, fontsize=15)
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
    if kind not in {"distribution_ci", "paired_change"}:
        ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
    if kind != "effect_interval":
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.set_title(textwrap.fill(item.get("title") or title,width=33), loc="left", pad=16, fontsize=18)
    fig.supxlabel(("Synthetic benchmark data | fixed input snapshot" if get_study().get("synthetic") is True else "Input data | provenance as supplied | fixed snapshot"), fontsize=12, color=COLORS["gray"])
    base = directory / f"figure_{index:02d}_{kind}"
    paths = {}
    for extension in ("png", "svg", "pdf"):
        path = base.with_suffix("." + extension)
        metadata = {"CreationDate": None, "ModDate": None} if extension == "pdf" else {"Date": None} if extension == "svg" else {}
        fig.savefig(path, dpi=300, metadata=metadata)
        paths[extension] = str(path.resolve())
    plt.close(fig)
    return {"kind": kind, "title": item.get("title") or title, "caption": _figure_caption(kind,confidence),
            "paths": paths, "sha256": {extension: _hash(Path(path)) for extension, path in paths.items()},
            "source_font_profile":{"axis_labels_pt":16,"ticks_pt":15,"legend_pt":15,"title_pt":18,"figure_height_in":4.5},
            "data_rows": len(df), "analysis_metrics": {key: metrics[key] for key in ("n", "estimate", "ci_low", "ci_high", "p_value")}}

