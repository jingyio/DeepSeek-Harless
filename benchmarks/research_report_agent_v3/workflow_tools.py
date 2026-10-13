"""Three LLM decisions, separated by scoped deterministic receipt segments.

v3 reuses the frozen v2 numerical/plot/PDF implementation. It never invokes a
model, rewrites scientific prose, selects figures, or uses a prefilled workflow.
Motif edges are learned outside these tools from actual ordinary DSH traces.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError

# Also support `python /absolute/path/server.py` in a scoped MCP subprocess.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from benchmarks.research_report_agent_v2 import common as context
from benchmarks.research_report_agent_v2 import workflow_tools as reusable
from benchmarks.research_report_agent_v2 import document_engine

get_record, put_record, tool_response = context.get_record, context.put_record, context.tool_response
get_study, get_run_dir = context.get_study, context.get_run_dir
TOKEN = re.compile(r'\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}')
FIGURE_KINDS = reusable.FIGURE_KINDS
ROLES = reusable.ROLES
REQUIRED_ROLES = {'methods', 'results', 'diagnostics', 'limitations'}
BODY_REQUIRED_TOKENS = {'estimate', 'ci_low', 'ci_high', 'p_value', 'n', 'excluded_rows'}
METHODS = {'independent_groups': '双侧 Welch t 检验', 'paired': '双侧配对 t 检验',
           'regression': '带截距的一元 OLS 回归'}
METRIC_LABELS = {'estimate': '效应估计', 'ci_low': 'CI 下界', 'ci_high': 'CI 上界',
    'p_value': '双侧 p', 'n': '有效样本', 'effect_size': '标准化效应/斜率',
    'r_squared': 'R²', 'residual_sd': '残差 SD', 'standard_error': '标准误',
    'input_rows': '原始行', 'excluded_rows': '排除行', 'shapiro_p': 'Shapiro p'}


BodyParagraph = Annotated[str, Field(strict=True, min_length=1, max_length=2000)]


class ReportSection(BaseModel):
    """One body section, in the already approved order. No extra fields."""
    model_config = ConfigDict(extra='forbid', strict=True)
    heading: str = Field(description='Copy the exact corresponding approved outline heading. Put scientific roles only in presentation.report.outline, not here.')
    paragraphs: list[BodyParagraph] = Field(min_length=1, max_length=12, description=
        'Write the complete body yourself. Bind ALL scientific numbers to available {{name}} tokens. '
        'Legal existing figure labels such as 图1/Figure 1 and consecutive list markers such as （1）…；（2）… are formatting. '
        'Do not write source hashes or paths in prose; they are retained automatically in sidecar records.')
    figure_indices: list[Annotated[StrictInt, Field(ge=0)]] = Field(description=
        'Required zero-based indexes of actual approved figures placed in this section. Use [] if none. '
        'Across all sections include every actual figure exactly once. Body references 图1/Figure 1 use one-based labels.')


class ResearchOption(BaseModel):
    """An LLM-written study choice; this schema does not judge its merit."""
    model_config = ConfigDict(extra='forbid', strict=True)
    name: BodyParagraph = Field(description='A distinct research/sampling option name; do not add fields beyond name,rationale,tradeoff.')
    rationale: BodyParagraph = Field(description='Explain why this option serves the actual findings/question. All quantitative values use verified {{name}} tokens.')
    tradeoff: BodyParagraph = Field(description='Explain costs, assumptions and limitations; describe untested scientific benefits as conditional hypotheses.')


class ReportText(BaseModel):
    """Full model-written body, not a template or permission to invent numbers."""
    model_config = ConfigDict(extra='forbid', strict=True)
    sections: list[ReportSection] = Field(min_length=1, max_length=10, description=
        'Exactly the approved headings in order. Write methods, results, interpretation, diagnostics and limitations. '
        'Across the body use {{estimate}},{{ci_low}},{{ci_high}},{{p_value}},{{n}},{{excluded_rows}}. '
        'State synthetic-data limitations when source metadata says synthetic and state that this analysis does not establish causality. '
        'Use {{confidence_pct}}%, {{null_value}} and {{unit_increment}} instead of literal confidence/zero/unit-count numbers.')
    allow_deterministic_continuation: StrictBool = Field(description=
        'REQUIRED explicit JSON boolean, no default. true authorizes assembly, layout and verification of THIS submitted text; '
        'false leaves continuation to the model. It never authorizes changing scientific prose.')
    research_options: list[ResearchOption] = Field(default_factory=list, max_length=4, description=
        'Supply at least the returned research_options_min when the user requests alternative studies; otherwise may omit. '
        'These model-written fields are inserted into an existing approved next_steps/limitations section.')
    comparison_summary: BodyParagraph | None = Field(default=None, description=
        'Required when research_options is nonempty: compare their objectives and trade-offs using actual evidence; '
        'all scientific numbers use {{name}} tokens. Otherwise omit this field or put ordinary discussion in sections.')


def _payload(identifier, kind=None):
    return get_record(identifier, kind)['payload']


def _clarify(message, *, errors=None, next_step=None):
    result = {'ok': False, 'clarification_required': True, 'reason': str(message),
              'next_step': next_step or 'Revise this semantic submission using the same input receipt; do not rerun valid statistics.'}
    if errors:
        result['validation_errors'] = errors
    return result


def _boolean(value):
    if not isinstance(value, dict) or type(value.get('allow_deterministic_continuation')) is not bool:
        raise ValueError('Supply explicit JSON boolean allow_deterministic_continuation; permission is never inserted automatically.')
    return value['allow_deterministic_continuation']


def _allowed(value, next_tool):
    return [next_tool] if value['allow_deterministic_continuation'] else []


def _semantic(tool, arguments):
    return {'tool': tool, 'arguments': copy.deepcopy(arguments)}


def _require_v3_plan(plan_id):
    plan = _payload(plan_id, 'analysis_plan')
    if plan.get('semantic_approval', {}).get('tool') != 'approve_analysis':
        raise ValueError('A v3 approve_analysis receipt is required; old workflow approvals cannot skip semantic checkpoints.')
    return plan


def inspect_study() -> dict:
    """Read the actual scoped CSV, metadata and request. First choose ONLY the
    statistical design; figure/table/outline decisions must wait for results.
    Unknown design, units, randomization and provenance stay unknown.
    """
    study = get_study()
    if 'benchmark_frozen_decisions' in study:
        raise ValueError('v3 natural tasks reject benchmark_frozen_decisions; do not replay prefilled presentation or prose.')
    result = reusable.statistics_tools.inspect_study(study['study_id'])
    result.update(user_request=(context.get_case_dir()/'task.txt').read_text(encoding='utf-8'),
                  supported_designs=sorted(FIGURE_KINDS),
                  next_step='LLM: approve_analysis(study_id, plan); do not select figures or write report text before actual statistics.')
    return result


def approve_analysis(study_id: str, plan: dict) -> dict:
    """LLM decision ONE, statistical design only. Required plan={analysis:{
    design:independent_groups|paired|regression,outcome_column,missing_policy:
    'complete_case',confidence:0.95,hypothesis:'two-sided question',design_evidence:
    {source:user_request|study_description,quote:'exact supplied excerpt'},
    group_column/reference_group/comparison_group for groups; subject_column for
    pairs; predictor_column for regression},allow_deterministic_continuation:bool}.
    Cite actual supplied design evidence; do not infer independence from names.
    This approval cannot authorize presentation choice or report writing.
    """
    try:
        study = get_study()
        if 'benchmark_frozen_decisions' in study:
            raise ValueError('Frozen benchmark decisions are not accepted in v3.')
        if study_id != study['study_id']:
            raise ValueError('study_id is outside this source scope')
        permitted = _boolean(plan)
        if set(plan) - {'analysis', 'allow_deterministic_continuation'}:
            raise ValueError('approve_analysis accepts analysis and continuation only; choose presentation after build_evidence.')
        proposed = copy.deepcopy(plan.get('analysis') or {})
        basis = proposed.get('design_evidence', {})
        source = {'user_request': study.get('user_request', ''), 'study_description': study.get('description', '')}.get(basis.get('source'), '')
        quote = basis.get('quote')
        if not isinstance(quote, str) or not 8 <= len(quote) <= 1500 or quote not in source or source.startswith('未提供研究设计说明'):
            raise ValueError('analysis.design_evidence needs an exact supplied user_request/study_description excerpt; missing design context requires clarification.')
        proposed['allow_deterministic_continuation'] = permitted
        analysis = reusable.statistics_tools._validate_plan(reusable.statistics_tools._frame(), proposed)
        payload = {'study_id': study_id, 'plan': analysis,
                   # Compatibility only for unchanged v2 verification helpers.
                   # No figure/report plan or default prose is stored here.
                   'workflow': {'analysis': analysis, 'allow_deterministic_continuation': permitted},
                   'semantic_approval': _semantic('approve_analysis', {'study_id': study_id, 'plan': plan})}
        identifier = put_record('analysis_plan', payload, ['run_analysis'] if permitted else [])
        return tool_response(identifier, 'plan_id', {'approved_analysis': analysis,
                             'next_step': 'run_analysis(plan_id); statistics and verification stop at an LLM presentation decision.'})
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        return _clarify(error)


def run_analysis(plan_id: str) -> dict:
    """Calculate the approved statistics from real CSV bytes. No model decision."""
    _require_v3_plan(plan_id)
    response = reusable.statistics_tools.run_analysis(plan_id)
    return tool_response(response['analysis_id'], 'analysis_id',
                         {'calculated': True, 'next_step': 'verify_analysis(analysis_id)'})


def verify_analysis(analysis_id: str) -> dict:
    """Independently recompute actual CSV values and auxiliary statistics."""
    _require_v3_plan(_payload(analysis_id, 'analysis')['plan_id'])
    return reusable.verify_analysis(analysis_id)


def _catalog(analysis, verified):
    catalog = reusable._placeholder_catalog(analysis, verified)
    plan, study = analysis['plan'], get_study()
    units = study.get('units', {})
    outcome_unit = units.get(plan['outcome_column'], '原始结局单位（未提供单位）')
    predictor_unit = units.get(plan.get('predictor_column'), '原始解释变量单位（未提供单位）')
    strings = {'outcome_unit': outcome_unit, 'predictor_unit': predictor_unit,
               'effect_unit': f'{outcome_unit}/{predictor_unit}' if plan['design'] == 'regression' else outcome_unit,
               'method_name': METHODS[plan['design']],
               'sample_unit': '完整配对' if plan['design'] == 'paired' else '完整观测',
               'contrast_name': '解释变量每原始单位的拟合斜率' if plan['design'] == 'regression' else f"{plan['comparison_group']} 减 {plan['reference_group']}"}
    for name, value in strings.items():
        catalog[name] = {'token': '{{'+name+'}}', 'value': str(value), 'display': str(value),
                         'meaning': name, 'source': 'approved_design_or_supplied_units', 'value_type': 'string'}
    return catalog


def _compact_catalog(catalog):
    return {name: {'value': item['value'], 'display': item['display'], 'meaning': item['meaning']}
            for name, item in catalog.items()}


def _scientific_guidance(analysis):
    plan = analysis['plan']
    return {'design': plan['design'], 'contrast': ('OLS slope, not a standardized effect' if plan['design'] == 'regression' else
            f"{plan['comparison_group']} minus {plan['reference_group']}"),
            'sample_unit': 'complete pairs; do not count rows as independent subjects' if plan['design'] == 'paired' else 'complete observations',
            'missingness': 'complete-case deletion; paired design removes the entire incomplete pair; mechanism unknown',
            'limits': ['CI concerns the estimated parameter, not observation/prediction range.',
                       'p or Shapiro cannot prove assumptions/causality; significance does not establish practical importance.',
                       'Do not infer sample-size gains, normality improvement or causal effects from current p/SE alone.',
                       'Regression slope and residual SD have different dimensions: specify a meaningful predictor difference before comparing.',
                       'Sampling-design recommendations are conditional hypotheses; report costs, independence and coverage trade-offs.'],
            'synthetic': get_study().get('synthetic') is True,
            'scientific_merit_automatically_verified': False}


def build_evidence(verified_id: str) -> dict:
    """Expose actual verified results, then STOP for LLM figure/table selection.
    This receipt deliberately authorizes no deterministic continuation.
    """
    verified = _payload(verified_id, 'verified_analysis')
    _require_v3_plan(verified['plan_id'])
    if verified.get('passed') is not True:
        raise ValueError('Verified statistical evidence is required')
    analysis = _payload(verified['analysis_id'], 'analysis')
    catalog = _catalog(analysis, verified)
    guidance = _scientific_guidance(analysis)
    identifier = put_record('evidence', {**verified, 'verified_id': verified_id,
        'metrics': {k: v['value'] for k, v in catalog.items()}, 'available_placeholders': catalog,
        'diagnostics': analysis['diagnostics'], 'scientific_guidance': guidance})
    return tool_response(identifier, 'evidence_id', {'results': _compact_catalog(catalog),
        'scientific_guidance': guidance, 'compatible_figures': sorted(FIGURE_KINDS[analysis['plan']['design']]),
        'semantic_handoff_required': True,
        'next_step': 'LLM: use these observed results and the user request to approve_presentation(evidence_id,presentation), including reasons for figures/tables.'})


def _presentation_report(proposed, figures):
    study = get_study()
    report = copy.deepcopy(proposed)
    if not isinstance(report, dict):
        raise ValueError('presentation.report must be an object')
    report.setdefault('title', study.get('title', '科研数据分析报告'))
    report.setdefault('page_mode', 'auto'); report.setdefault('pages', None); report.setdefault('style', 'technical')
    if not isinstance(report['title'], str) or not 1 <= len(report['title']) <= 160:
        raise ValueError('Report title must contain 1-160 characters')
    if report['style'] not in {'brief', 'technical', 'paper'} or report['page_mode'] not in {'auto', 'max', 'exact'}:
        raise ValueError('style: brief|technical|paper; page_mode: auto|max|exact')
    if report['page_mode'] == 'auto':
        report['pages'] = None
    elif type(report['pages']) is not int or not 1 <= report['pages'] <= 6:
        raise ValueError('max/exact pages must be an integer from 1 to 6')
    required = study.get('report_requirements', {})
    for key in ('style', 'page_mode', 'pages'):
        if required.get(key) is not None and report[key] != required[key]:
            raise ValueError(f'User requires {key}={required[key]}')
    if required.get('figure_count') is not None and len(figures) != required['figure_count']:
        raise ValueError(f"User requires figure_count={required['figure_count']}")
    outline, covered, normalized = report.get('outline'), set(), []
    if not isinstance(outline, list) or not 1 <= len(outline) <= 10:
        raise ValueError('Supply 1-10 outline entries {heading,roles}; no default outline is silently chosen')
    for item in outline:
        if not isinstance(item, dict) or not isinstance(item.get('heading'), str) or not 1 <= len(item['heading']) <= 90:
            raise ValueError('Every outline entry requires a short heading')
        roles = item.get('roles')
        if not isinstance(roles, list) or not roles or not set(roles) <= ROLES or covered.intersection(roles):
            raise ValueError('Use each scientific role once: summary,methods,results,diagnostics,limitations,next_steps,provenance; combine roles under headings')
        covered.update(roles); normalized.append({'heading': item['heading'], 'roles': roles})
    if not REQUIRED_ROLES <= covered:
        raise ValueError('Outline must cover methods,results,diagnostics,limitations; combine roles for short reports')
    if study.get('user_outline') and [s['heading'] for s in normalized] != reusable._user_headings(study['user_outline']):
        raise ValueError('Preserve all supplied user outline headings and their order exactly')
    if report['page_mode'] in {'max', 'exact'} and report['pages'] == 1:
        if len(figures) > 1 or len(normalized) > 4:
            raise ValueError('Current one-page profile supports one figure and at most four headings. Combine only model-proposed headings; clarify explicit user constraint conflicts instead of deleting requested material.')
    report['outline'] = normalized
    return report


def approve_presentation(evidence_id: str, presentation: dict) -> dict:
    """LLM decision TWO, AFTER actual verified statistics. Required presentation=
    {figures:[{kind,title?:ASCII English,reason:'why this plot fits actual results'}],
    tables:[{kind:'key_metrics',metrics:['estimate','ci_low','ci_high','p_value','n'],
    reason:'why these quantities'}] or [],report:{title?,outline:[{heading,roles:
    [methods|results|diagnostics|limitations|summary|next_steps|provenance]}],
    style:brief|technical|paper,page_mode:auto|max|exact,pages?:1..6},
    reason:'result-sensitive presentation decision',allow_deterministic_continuation:bool}.
    Pick 1-3 distinct compatible plots with at least one raw-data plot. Optional
    titles must describe actual graphical elements: omit to use accurate built-in
    English titles. At most one key_metrics table (up to 12 selected numeric keys).
    One-page reports support one figure/up to four headings; preserve explicit
    user headings. This approval authorizes drawing/checks, NEVER prose writing.
    """
    evidence = _payload(evidence_id, 'evidence')
    analysis = _payload(evidence['analysis_id'], 'analysis')
    try:
        _boolean(presentation)
        if not isinstance(presentation.get('reason'), str) or not 8 <= len(presentation['reason']) <= 1500:
            raise ValueError('Explain the presentation decision using actual results in reason (8-1500 characters)')
        figures = presentation.get('figures')
        if not isinstance(figures, list) or not 1 <= len(figures) <= 3:
            raise ValueError('Choose 1-3 distinct compatible figures')
        kinds = [f.get('kind') for f in figures if isinstance(f, dict)]
        design = analysis['plan']['design']
        if len(kinds) != len(figures) or len(set(kinds)) != len(kinds) or not set(kinds) <= FIGURE_KINDS[design]:
            raise ValueError(f'Compatible kinds: {sorted(FIGURE_KINDS[design])}')
        raw = {'independent_groups': {'distribution_ci', 'group_ecdf'}, 'paired': {'paired_change', 'change_distribution'}, 'regression': {'scatter_fit'}}[design]
        if not set(kinds).intersection(raw):
            raise ValueError(f'Include at least one actual observation/distribution plot from {sorted(raw)}')
        for index, item in enumerate(figures):
            reusable._figure_title(item.get('title', ''), index)
            if not isinstance(item.get('reason'), str) or not 5 <= len(item['reason']) <= 600:
                raise ValueError(f'figures[{index}].reason must explain the choice (5-600 characters)')
        tables = presentation.get('tables')
        if not isinstance(tables, list) or len(tables) > 1:
            raise ValueError('Explicit tables=[] or one key_metrics table is required')
        for table in tables:
            names = table.get('metrics')
            if table.get('kind') != 'key_metrics' or not isinstance(names, list) or not 1 <= len(names) <= 12 or len(set(names)) != len(names):
                raise ValueError('key_metrics table requires 1-12 distinct numeric metric names')
            if any(name not in evidence['metrics'] or isinstance(evidence['metrics'][name], str) for name in names):
                raise ValueError('Tables can select only actual numeric names from results')
            if not isinstance(table.get('reason'), str) or not 5 <= len(table['reason']) <= 600:
                raise ValueError('Table selection needs a short reason')
        report = _presentation_report(presentation.get('report'), figures)
        normalized = copy.deepcopy(presentation); normalized['report'] = report
        payload = {'plan_id': evidence['plan_id'], 'analysis_id': evidence['analysis_id'],
                   'evidence_id': evidence_id, 'presentation': normalized,
                   'semantic_approval': _semantic('approve_presentation', {'evidence_id': evidence_id, 'presentation': presentation})}
        identifier = put_record('presentation_plan', payload, _allowed(presentation, 'render_figures'))
        return tool_response(identifier, 'presentation_id', {'figure_kinds': kinds, 'table_count': len(tables),
            'next_step': 'render_figures(presentation_id); after verify_figures an LLM must write every report section.'})
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return _clarify(error)


def render_figures(presentation_id: str) -> dict:
    """Draw the result-dependent LLM-approved figure selection to PNG/SVG/PDF."""
    approved = _payload(presentation_id, 'presentation_plan')
    analysis = _payload(approved['analysis_id'], 'analysis')
    directory = context.artifact_path(f'artifacts/{presentation_id}/figures')
    directory.mkdir(parents=True, exist_ok=True)
    figures = [reusable._draw_figure(analysis, item, index+1, directory)
               for index, item in enumerate(approved['presentation']['figures'])]
    identifier = put_record('figure_bundle', {'plan_id': approved['plan_id'], 'analysis_id': approved['analysis_id'],
        'evidence_id': approved['evidence_id'], 'presentation_id': presentation_id, 'figures': figures},
        _allowed(approved['presentation'], 'verify_figures'))
    return tool_response(identifier, 'figure_bundle_id', {'figure_count': len(figures), 'next_step': 'verify_figures(figure_bundle_id)'})


def _text_contract(approved, evidence):
    return {'outline': approved['presentation']['report']['outline'],
        'numeric_rule': 'All quantitative prose uses exact {{name}} placeholders from available_placeholders; units may use {{outcome_unit}}/{{effect_unit}}. unit_increment is the defined constant one. Ordinary R² is notation. Source condition names containing digits can use {{contrast_name}}. Existing 图1/Figure 1 references and consecutive parenthesized list markers （1）…；（2）… are formatting, not scientific values. Unknown figure labels and bare scientific numbers are rejected.',
        'required_body_tokens': sorted(BODY_REQUIRED_TOKENS),
        'research_options_min': reusable._research_options_requirement(get_study())['minimum'],
        'format': {'sections': [{'heading': 'EXACT approved heading', 'paragraphs': ['Write this section yourself with evidence tokens'], 'figure_indices': []}],
            'research_options': 'Only if requested: [{name,rationale,tradeoff}, ...] and comparison_summary; all text follows token rules.',
            'allow_deterministic_continuation': 'REQUIRED explicit JSON boolean; true authorizes assembly/layout/verification only'},
        'shape_rules': 'Every section requires heading,paragraphs,figure_indices. Put no roles or extra fields in submitted sections. [] means no figures there; assign each actual zero-based figure index exactly once elsewhere.',
        'scope': 'Write complete methods, results, interpretation, diagnostics and limitations. No standard paragraphs will be added. Figure captions and the selected metrics table are deterministic provenance labels, not LLM prose. Explicitly disclose synthetic data when declared and the noncausal interpretation boundary. Do not copy record IDs, SHA hashes or filesystem paths into body text: the artifacts preserve them automatically.',
        'quality_requirements': evidence['scientific_guidance'],
        'length': '1-12 paragraphs per section, at most 2000 characters each; total text at most 18000 characters. One-page capacity is measured with the exact supplied text; revise this same packet after any capacity failure.'}


def verify_figures(figure_bundle_id: str) -> dict:
    """Check actual image/vector files and metrics, then STOP for LLM full prose."""
    checked = reusable.plot_helpers.verify_figures(figure_bundle_id)
    bundle = _payload(figure_bundle_id, 'figure_bundle')
    approved = _payload(bundle['presentation_id'], 'presentation_plan')
    evidence = _payload(bundle['evidence_id'], 'evidence')
    passed = checked['quality_passed'] is True
    identifier = put_record('evidence_packet', {**{k: bundle[k] for k in ('plan_id','analysis_id','evidence_id','presentation_id')},
        'figure_bundle_id': figure_bundle_id, 'figure_check_id': checked['figure_verification_id'], 'quality_passed': passed})
    return tool_response(identifier, 'packet_id', {'quality_passed': passed, 'semantic_handoff_required': True,
        'figures': [{'index': i, 'kind': f['kind'], 'title': f['title'], 'caption': f['caption']} for i,f in enumerate(bundle['figures'])],
        'available_placeholders': _compact_catalog(evidence['available_placeholders']),
        'report_text_contract': _text_contract(approved, evidence),
        'next_step': 'LLM: submit_report_text(packet_id,report_text), writing the complete report based on results and these actual figure descriptions.' if passed else 'Figure verification failed; do not compose or claim completion.'})


def _formatting_numbers(text, field, figure_count, errors):
    """Mask only bounded diagram references and visibly ordered list markers.

    Validation-only masking never changes rendered prose. This is a finite
    formatting recognizer, not an assessment of a sentence's scientific merit.
    """
    references = []
    figure_pattern = re.compile(
        r'(?:图|Figure\b|Fig\.)\s*(\d+(?:\s*[/／、,]\s*\d+)*)(?![\d.])', re.I)

    def figure(match):
        indices = [int(value) for value in re.findall(r'\d+', match.group(1))]
        invalid = [value for value in indices if not 1 <= value <= figure_count]
        if invalid:
            errors.append({'field': field, 'code': 'unknown_figure_reference', 'labels': invalid,
                'available_figure_labels': list(range(1, figure_count+1)),
                'message': 'Reference only actually approved figures; body labels are one-based, figure_indices is zero-based.'})
        references.append({'kind': 'figure_reference', 'text': match.group(), 'labels': indices,
                           'validated_against_actual_figure_count': figure_count, 'passed': not invalid})
        return ' ' * len(match.group())

    masked = figure_pattern.sub(figure, text)
    # Full parentheses clearly delimit an ordinal; bare digits require a
    # paragraph/punctuation boundary and a list delimiter. A decimal like 1.5
    # is never an ordinal. Sequential multi-item numbering must start at one.
    marker_pattern = re.compile(r'[（(](\d{1,2})[）)]|(?:^|(?<=[；;。\n：:]))\s*(\d{1,2})[)）、]|(?:^|(?<=[；;。\n：:]))\s*(\d{1,2})\.\s+(?!\d)')
    markers = list(marker_pattern.finditer(masked))
    values = [int(next(group for group in m.groups() if group is not None)) for m in markers]
    consecutive = len(markers) >= 2 and values == list(range(1, len(markers)+1))
    # A single leading marker is allowed only as a genuine paragraph prefix;
    # a lone parenthesized value in the middle of a claim remains quantitative.
    leading = len(markers) == 1 and values[0] >= 1 and not masked[:markers[0].start()].strip()
    if consecutive or leading:
        for match, value in reversed(list(zip(markers, values))):
            references.append({'kind': 'list_ordinal', 'text': match.group(), 'ordinal': value,
                               'sequence': values, 'passed': True})
            masked = masked[:match.start()] + ' '*len(match.group()) + masked[match.end():]
    return masked, references


def _bind(text, field, evidence, errors, bindings, figure_count=0):
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        errors.append({'field': field, 'code': 'text_size', 'message': 'Use nonempty text, at most 2000 characters per field.'})
        return ''
    catalog = evidence['available_placeholders']
    names = TOKEN.findall(text)
    unknown = sorted(set(names)-catalog.keys())
    remaining = TOKEN.sub('', text)
    if unknown:
        errors.append({'field': field, 'code': 'unknown_placeholder', 'names': unknown, 'message': 'Use only available_placeholders names.'})
    if '{' in remaining or '}' in remaining:
        errors.append({'field': field, 'code': 'malformed_placeholder', 'message': 'Use exactly {{name}} with no expressions or single braces.'})
    remaining, formatting = _formatting_numbers(remaining, field, figure_count, errors)
    numbers = re.findall(r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?[%％]?', remaining)
    if numbers:
        errors.append({'field': field, 'code': 'unbound_number', 'literals': numbers,
            'message': 'Bind quantitative claims to verified tokens, e.g. {{confidence_pct}}%, {{n}}, {{null_value}}, {{unit_increment}}. Unsupported thresholds cannot be invented.'})
    rendered = TOKEN.sub(lambda m: str(catalog[m[1]]['display']) if m[1] in catalog else m[0], text)
    bindings.append({'field': field, 'template': text, 'rendered': rendered,
                     'formatting_references': formatting,
                     'tokens': {name: {'value': catalog[name]['value'], 'display': catalog[name]['display'], 'source': catalog[name]['source']}
                                for name in sorted(set(names)) if name in catalog}})
    return rendered


def _figures_unchanged(bundle):
    for figure in bundle['figures']:
        for extension, filename in figure['paths'].items():
            path = Path(filename).resolve()
            if not path.is_relative_to(get_run_dir()) or not path.is_file() or context.sha256_file(path) != figure['sha256'][extension]:
                raise ValueError('Source figure changed or escaped this workspace')


def _document(approved, evidence, bundle, sections):
    presentation = approved['presentation']
    metrics = []
    for table in presentation['tables']:
        for name in table['metrics']:
            metrics.append({'label': METRIC_LABELS.get(name, name), 'value': evidence['available_placeholders'][name]['display']})
    return {'title': presentation['report']['title'],
        'subtitle': '数据分析结果与研究讨论',
        'sections': copy.deepcopy(sections), 'metrics': metrics,
        'figures': [{'path': f['paths']['png'], 'caption': f['caption'], 'kind': f['kind']} for f in bundle['figures']],
        'requirements': {k: presentation['report'][k] for k in ('style', 'page_mode', 'pages')},
        'synthetic': get_study().get('synthetic') is True,
        'provenance': f"来源与工具记录：{approved['plan_id'][-12:]}；完整哈希见交付旁证。"}


def submit_report_text(packet_id: str, report_text: ReportText) -> dict:
    """LLM decision THREE: write ALL report body after actual figure checks.
    report_text={sections:[{heading:'exact approved heading',paragraphs:[strings],
    figure_indices:[zero-based figure indexes; [] if none]}],research_options?:[{name,
    rationale,tradeoff}],comparison_summary?:str,allow_deterministic_continuation:bool}.
    Use each approved heading in order; include each figure exactly once in a
    section. Every scientific number uses {{name}} from available_placeholders;
    whole body must use estimate,ci_low,ci_high,p_value,n,excluded_rows. Units
    may use effect_unit/outcome_unit tokens, confidence uses {{confidence_pct}}%.
    No generated standard paragraph replaces your prose. Describe the actual
    design/contrast, complete-case treatment, CI/p/sample unit, diagnostics,
    synthetic or unknown source status, noncausal limits and conditional future
    work. A request comparing research choices requires research_options with
    name/rationale/tradeoff and comparison_summary; these are inserted verbatim
    (after token binding) into an existing next_steps/limitations section.
    Exact one-page text is measured before approval. On failure revise THIS
    packet's text, never repeat statistics. Validation is structural/numeric;
    free scientific claims still need independent reading.
    """
    packet = _payload(packet_id, 'evidence_packet')
    if packet['quality_passed'] is not True:
        raise ValueError('Actual figure verification must pass before report writing')
    approved = _payload(packet['presentation_id'], 'presentation_plan')
    evidence = _payload(packet['evidence_id'], 'evidence')
    bundle = _payload(packet['figure_bundle_id'], 'figure_bundle')
    _figures_unchanged(bundle)
    try:
        validated = report_text if isinstance(report_text, ReportText) else ReportText.model_validate(report_text)
        # exclude_unset preserves the actual submission for protocol recovery:
        # optional fields are never silently inserted into semantic_approval.
        report_text = validated.model_dump(exclude_unset=True)
    except ValidationError as error:
        errors = [{'field': 'report_text.'+'.'.join(str(part) for part in item['loc']),
                   'code': item['type'], 'message': item['msg']}
                  for item in error.errors(include_url=False, include_input=False, include_context=False)]
        return _clarify('Report-text structure is invalid. Correct all required/extra/type fields together; no permission or prose was inserted.',
                        errors=errors, next_step='Resubmit the complete report_text object with required sections/heading/paragraphs/figure_indices and explicit boolean allow_deterministic_continuation using this same packet_id.')
    errors, bindings, rendered, transformations = [], [], [], []
    try:
        _boolean(report_text)
        if set(report_text) - {'sections', 'research_options', 'comparison_summary', 'allow_deterministic_continuation'}:
            raise ValueError('Unknown report_text fields would be silently discarded; put all body prose inside sections/research_options/comparison_summary')
        sections = report_text.get('sections')
        outline = approved['presentation']['report']['outline']
        if not isinstance(sections, list) or len(sections) != len(outline):
            raise ValueError('sections must match the approved outline heading count and order')
        figure_indices = []
        for i, (section, expected) in enumerate(zip(sections, outline)):
            if not isinstance(section, dict) or section.get('heading') != expected['heading']:
                raise ValueError(f"sections[{i}].heading must exactly equal {expected['heading']!r}")
            if set(section) - {'heading', 'paragraphs', 'figure_indices'}:
                raise ValueError(f'sections[{i}] accepts heading,paragraphs,figure_indices only; no submitted prose is silently dropped')
            paragraphs = section.get('paragraphs')
            if not isinstance(paragraphs, list) or not 1 <= len(paragraphs) <= 12:
                raise ValueError(f'sections[{i}].paragraphs must have 1-12 actual LLM-written paragraphs')
            indices = section.get('figure_indices', [])
            if not isinstance(indices, list) or any(type(x) is not int or not 0 <= x < len(bundle['figures']) for x in indices):
                raise ValueError('figure_indices must name actual zero-based figure indexes')
            figure_indices.extend(indices)
            rendered.append({'id': f'section-{i+1}', 'heading': expected['heading'],
                'paragraphs': [_bind(text, f'sections[{i}].paragraphs[{j}]', evidence, errors, bindings, len(bundle['figures'])) for j,text in enumerate(paragraphs)],
                'figure_indices': indices})
        if sorted(figure_indices) != list(range(len(bundle['figures']))):
            raise ValueError('Include every approved figure exactly once via section figure_indices')
        options = report_text.get('research_options', [])
        minimum = reusable._research_options_requirement(get_study())['minimum']
        if not isinstance(options, list) or not minimum <= len(options) <= 4:
            raise ValueError(f'research_options must contain {minimum}-4 objects; explicit comparison requests need at least two actual study choices')
        if not options and report_text.get('comparison_summary') is not None:
            raise ValueError('comparison_summary needs corresponding research_options, or place this prose in the appropriate section instead')
        option_text = []
        names = []
        for i, option in enumerate(options):
            names.append(option.get('name'))
            values = [_bind(option.get(k), f'research_options[{i}].{k}', evidence, errors, bindings, len(bundle['figures'])) for k in ('name','rationale','tradeoff')]
            option_text.append(f'{values[0]}：{values[1]} 取舍与限制：{values[2]}')
        if len(set(names)) != len(names):
            raise ValueError('Research option names must be distinct; scientific merit still requires review')
        if options:
            comparison = _bind(report_text.get('comparison_summary'), 'comparison_summary', evidence, errors, bindings, len(bundle['figures']))
            target = next((i for i,item in enumerate(outline) if 'next_steps' in item['roles']),
                          next(i for i,item in enumerate(outline) if 'limitations' in item['roles']))
            rendered[target]['paragraphs'].extend(option_text+[comparison])
            transformations.append({'operation': 'append_model_research_options_to_existing_section', 'section_index': target,
                'added_paragraphs': option_text+[comparison], 'source_fields': ['research_options','comparison_summary']})
        all_tokens = {name for item in bindings for name in item['tokens']}
        missing = BODY_REQUIRED_TOKENS-all_tokens
        if missing:
            errors.append({'code': 'missing_core_evidence', 'field': 'report_text', 'missing_tokens': sorted(missing),
                           'message': 'Report actual effect, CI, p, sample unit and excluded rows using these evidence tokens.'})
        text = '\n'.join(p for section in rendered for p in section['paragraphs'])
        if len(text) > 18000:
            errors.append({'code': 'total_text_resource_limit', 'actual_characters': len(text), 'maximum': 18000})
        if get_study().get('synthetic') is True and not re.search(r'合成|synthetic', text, re.I):
            errors.append({'code': 'missing_source_disclosure', 'field': 'report_text', 'message': 'The metadata explicitly says synthetic; disclose it and its scientific limitation in your own body text.'})
        if not re.search(r'(?:不|未|非|不能|并非).{0,8}因果|not.{0,15}causal|no.{0,10}causal', text, re.I):
            errors.append({'code': 'missing_causal_boundary', 'field': 'report_text', 'message': 'Explicitly state that this analysis does not establish causality. This keyword screen is not scientific proof.'})
        if errors:
            return _clarify('Report text needs the listed corrections; no continuation authorized.', errors=errors,
                            next_step='Resubmit submit_report_text with this same packet_id, fixing every listed field. Statistics and figures remain valid.')
        document = _document(approved, evidence, bundle, rendered)
        requirements = document['requirements']
        capacity = None
        if requirements['page_mode'] in {'max','exact'} and requirements['pages'] == 1:
            capacity = document_engine.measure_capacity(document)
            if not capacity['fits_one_page']:
                return {**_clarify('The exact submitted text/figures exceed the measured one-page capacity. Compress your text without dropping required evidence or changing explicit user constraints.'),
                    'capacity_preflight': capacity, 'actual_body_characters': len(text),
                    'next_step': 'Shorten model-written paragraphs and resubmit THIS packet_id. Do not rerun statistics or drawing. If the user constraints cannot fit, explain the conflict.'}
        transformations.insert(0, {'operation': 'verified_token_substitution_only', 'fields': [b['field'] for b in bindings]})
        payload = {**{k: packet[k] for k in ('plan_id','analysis_id','evidence_id','presentation_id')},
            'packet_id': packet_id, 'submitted_report_text': copy.deepcopy(report_text), 'rendered_sections': rendered,
            'bindings': bindings, 'transformations': transformations, 'capacity_preflight': capacity,
            'allow_deterministic_continuation': report_text['allow_deterministic_continuation'],
            'scientific_prose_automatically_verified': False,
            'semantic_approval': _semantic('submit_report_text', {'packet_id': packet_id, 'report_text': report_text})}
        identifier = put_record('report_text', payload, _allowed(report_text, 'compose_report'))
        return tool_response(identifier, 'text_id', {'text_approved_for_assembly': True, 'scientific_prose_verified': False,
            'section_count': len(rendered), 'body_characters': len(text),
            'next_step': 'compose_report(text_id); deterministic assembly may only bind and place the submitted text.'})
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return _clarify(error)


def compose_report(text_id: str) -> dict:
    """Assemble only approved LLM prose, actual figures and selected metrics.
    No standard body, semantic rewrite, model call or silent deletion is used.
    """
    text = _payload(text_id, 'report_text')
    packet = _payload(text['packet_id'], 'evidence_packet')
    if packet['quality_passed'] is not True:
        raise ValueError('Verified figures required')
    approved = _payload(text['presentation_id'], 'presentation_plan')
    evidence = _payload(text['evidence_id'], 'evidence')
    bundle = _payload(packet['figure_bundle_id'], 'figure_bundle')
    _figures_unchanged(bundle)
    document = _document(approved, evidence, bundle, text['rendered_sections'])
    identifier = put_record('report_draft', {'plan_id': text['plan_id'], 'analysis_id': text['analysis_id'],
        'packet_id': text['packet_id'], 'text_id': text_id, 'presentation_id': text['presentation_id'],
        'document': document, 'composition_mode': 'llm_full_text_token_binding_only'}, _allowed(text, 'layout_report'))
    return tool_response(identifier, 'draft_id', {'section_count': len(document['sections']),
        'next_step': 'layout_report(draft_id)'})


def _text_authorization(draft, next_tool):
    return _allowed(_payload(draft['text_id'], 'report_text'), next_tool)


def layout_report(draft_id: str) -> dict:
    """Render and measure the PDF with bounded layout-only repair. Same draft +
    engine version reuses even failed results after artifact/source hash checks.
    A hard failure must return to explicit content/constraint revision, never
    repeated statistics or silent rewriting. Soft warnings remain reportable.
    """
    draft = _payload(draft_id, 'report_draft')
    packet = _payload(draft['packet_id'], 'evidence_packet')
    _figures_unchanged(_payload(packet['figure_bundle_id'], 'figure_bundle'))
    version = document_engine.ENGINE_VERSION
    version_key = hashlib.sha256(version.encode()).hexdigest()[:16]
    destination = context.artifact_path(f'artifacts/{draft_id}/report/{version_key}')
    receipt = destination/'layout_receipt.json'
    reused = receipt.exists()
    if reused:
        identifier = json.loads(receipt.read_text(encoding='utf-8'))['layout_id']
        layout = _payload(identifier, 'report_layout')
        if layout['draft_id'] != draft_id or layout['engine_version'] != version:
            raise ValueError('Cached layout receipt does not match draft/engine')
        result = layout['engine']
        result_path = Path(layout['engine_result_path']).resolve()
        if not result_path.is_relative_to(destination.resolve()) or context.sha256_file(result_path) != layout['engine_result_sha256']:
            raise ValueError('Cached engine result changed')
        if result.get('path'):
            reusable._audit_engine_record(layout)
        elif result['quality_passed']:
            raise ValueError('Successful cached layout has no PDF')
        for attempt in result.get('attempts', []):
            if attempt.get('sha256'):
                path = Path(attempt['path']).resolve()
                if not path.is_relative_to(destination.resolve()) or context.sha256_file(path) != attempt['sha256']:
                    raise ValueError('Cached layout attempt changed')
    else:
        result = document_engine.build_document(draft['document'], destination, repair=True)
        result_path = destination/'layout_result.json'
        identifier = put_record('report_layout', {'plan_id': draft['plan_id'], 'draft_id': draft_id,
            'engine_version': version, 'engine': result, 'engine_result_path': str(result_path.resolve()),
            'engine_result_sha256': context.sha256_file(result_path)},
            _text_authorization(draft, 'audit_layout') if result['quality_passed'] else [])
        receipt.write_bytes(context.canonical({'layout_id': identifier}))
    audit = result.get('audit', {})
    return tool_response(identifier, 'layout_id', {'quality_passed': result['quality_passed'], 'cache_reused': reused,
        'page_count': result.get('page_count'), 'attempt_count': len(result.get('attempts', [])),
        'warnings': audit.get('soft_warnings', audit.get('warnings', [])),
        'failed_checks': [k for k,v in audit.get('checks', {}).items() if not v],
        'next_step': 'audit_layout(layout_id)' if result['quality_passed'] else
        'Hard layout failure: report failed constraints; revise report_text using its existing packet_id or explicitly revise presentation constraints. Do not retry this unchanged draft or rerun statistics.'})


def audit_layout(layout_id: str) -> dict:
    """Reopen final PDF and repeat real layout/content/hash checks."""
    layout = _payload(layout_id, 'report_layout')
    audit, draft = reusable._audit_engine_record(layout)
    passed = audit.get('quality_passed') is True
    identifier = put_record('report', {'plan_id': layout['plan_id'], 'layout_id': layout_id,
        'draft_id': layout['draft_id'], 'text_id': draft['text_id'], 'path': layout['engine']['path'],
        'sha256': layout['engine']['sha256'], 'quality_passed': passed, 'audit': audit},
        _text_authorization(draft, 'verify_report') if passed else [])
    return tool_response(identifier, 'report_id', {'quality_passed': passed,
        'warnings': audit.get('soft_warnings', []), 'failed_checks': [k for k,v in audit.get('checks', {}).items() if not v],
        'next_step': 'verify_report(report_id)' if passed else 'Report the failed layout checks and obtain an explicit semantic revision.'})


def verify_report(report_id: str) -> dict:
    """Verify final artifact and source-bound narrative lineage; scientific prose
    remains subject to independent reading even when these checks all pass.
    """
    report = _payload(report_id, 'report')
    layout = _payload(report['layout_id'], 'report_layout')
    audit, draft = reusable._audit_engine_record(layout)
    text = _payload(draft['text_id'], 'report_text')
    packet = _payload(text['packet_id'], 'evidence_packet')
    _payload(packet['analysis_id'], 'analysis')
    if draft['document']['sections'] != text['rendered_sections']:
        raise ValueError('Assembled body differs from approved LLM text')
    passed = report['quality_passed'] is True and audit.get('quality_passed') is True
    identifier = put_record('report_verification', {'plan_id': report['plan_id'], 'report_id': report_id,
        'text_id': draft['text_id'], 'quality_passed': passed, 'path': report['path'], 'sha256': report['sha256'],
        'audit': audit, 'scientific_prose_verified': False}, _text_authorization(draft, 'deliver_report') if passed else [])
    return tool_response(identifier, 'verification_id', {'quality_passed': passed, 'scientific_prose_verified': False,
        'next_step': 'deliver_report(verification_id)' if passed else 'Do not claim delivery; report failed checks.'})


def deliver_report(verification_id: str) -> dict:
    """Task completion: deliver the verified PDF and retain review limitations."""
    verified = _payload(verification_id, 'report_verification')
    if verified['quality_passed'] is not True:
        raise ValueError('Cannot deliver a failed report')
    report = _payload(verified['report_id'], 'report')
    layout = _payload(report['layout_id'], 'report_layout')
    audit, draft = reusable._audit_engine_record(layout)
    if audit.get('quality_passed') is not True:
        raise ValueError('Cannot deliver changed or failed final artifacts')
    warnings = audit.get('soft_warnings', audit.get('warnings', []))
    payload = {'plan_id': verified['plan_id'], 'verification_id': verification_id, 'report_id': verified['report_id'],
        'text_id': draft['text_id'], 'page_count': layout['engine']['page_count'], 'path': verified['path'],
        'sha256': verified['sha256'], 'quality_passed': True, 'delivered': True,
        'interpretation_mode': 'llm_full_text', 'scientific_prose_verified': False, 'warnings': warnings}
    identifier = put_record('delivery', payload)
    return tool_response(identifier, 'delivery_id', {**{k:v for k,v in payload.items() if k not in {'plan_id','verification_id','text_id'}},
        'next_step': 'Task complete. Show PDF path and limitations. Full prose was written by the LLM; numeric/layout checks do not certify its scientific reasoning.'})
