"""Read-only numerical cross-check plus a hash-bound review of one observed experiment.

MANUAL and EXECUTE_REVISIONS are the 2026-10-10 AI reading snapshot, NOT an
automatic scientific classifier or a human-expert/blinded review. They apply
only to the exact report IDs and PDF hashes in SNAPSHOT_BINDINGS. New reports
must receive a new reading; this script refuses to reuse these old comments.
Uses source CSV and separate formulas, never imports benchmark analysis code.
All input artifacts are read-only; two new review JSONs are the only outputs.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics

from scipy import stats

SNAPSHOT_LIBRARY_DIGEST = 'b90b1debfdc27f19102b1fc91467228e9c66184f37044a3571fcdf98a51954d9'
SNAPSHOT_BINDINGS = {
    'train_materials_final': {'report_id': 'rra-report-1d6659e6abfcba978c859f8e1e166ef9', 'pdf_sha256': 'f524a01490f5a6fd0457677ba0fe69f0feddaba5c37d7056cea8cbd4a9c8dc99'},
    'train_ml_final': {'report_id': 'rra-report-557fdf6991abb4bc68449d77b86c1980', 'pdf_sha256': '31524776de5013eca3f90746b006bcc9447e52e7a4d2efd678c7e84919c6d6e4'},
    'cert_environment_final': {'report_id': 'rra-report-468441893e2760032161df8eebe797a2', 'pdf_sha256': 'c01460f32fe324c6b08a5d4f0409f9f222d0e78292200c40e4c153afe7300aef'},
    'eval_biology_baseline': {'report_id': 'rra-report-cf1cc92a8fe499c69d52d9298f9bed10', 'pdf_sha256': 'f9d1decd8750b6777aa5027971f466751cb4a30ed6d7b0c11d900df887b287c5'},
    'eval_biology_execute': {'report_id': 'rra-report-0e8ee08070436fd99256d210813fdbef', 'pdf_sha256': 'e6d4a16910bdd4bc4fbb0421a53010f64fd9458b3d1e79a8d5164e36e5ea24aa'},
    'eval_education_baseline': {'report_id': 'rra-report-f9a01565626088b193d8eba2611e778b', 'pdf_sha256': 'f937cdda87ae8bda6c002013ab8d729fdd027dfb9e809c9e581b5950fc952b48'},
    'eval_education_execute': {'report_id': 'rra-report-9d7a1e5f59b9fe1b0d50232d818c6b4b', 'pdf_sha256': '552d0d1ddf66fd052a51912d6507db0c1dbcbd490d6ab60f2a184242a1cb9084'},
    'eval_energy_baseline': {'report_id': 'rra-report-1fab748110024c0ae769d0baf806d417', 'pdf_sha256': '84477531404b6565e2f356b2d14f6c2d0803263d629fd06ed45b0852e56eac82'},
    'eval_energy_execute': {'report_id': 'rra-report-7d6fd7ffbb48b9e7e3c6b343fbbfa5b7', 'pdf_sha256': '7c03778fc50f2f9e8ae69ff133010e608df8f7c7ec9f9d875684ca47fa466607'},
}
MANUAL = {
    'train_materials_final': {
        'status': 'minor_revision_recommended',
        'design_direction_units_missingness_ci_p_synthetic': 'Checked in final rendered narrative; correct numerical direction and MPa units, n=54 observations, 2 missing rows excluded, two-sided Welch analysis, synthetic and non-causal limits explicit.',
        'findings': [{
            'severity': 'moderate_wording', 'field': 'limitations',
            'quote': '本研究为两组观察性对比,没有随机化与混杂控制',
            'issue': '输入元数据没有明确随机化或混杂控制的信息；不能从未说明推断确实没有。',
            'suggestion': '改为“输入未提供随机分配与混杂控制证据，因此不作因果解释”。',
            'affects_numerical_results': False}],
    },
    'train_ml_final': {
        'status': 'minor_revision_recommended',
        'design_direction_units_missingness_ci_p_synthetic': 'Checked final narrative: paired after-minus-before, fraction-scale Accuracy effect, n=30 pairs rather than 60 independent samples, 4 rows removed for 2 incomplete pairs, two-sided CI/p, synthetic and non-causal limitations explicit.',
        'findings': [{
            'severity': 'moderate_wording', 'field': 'limitations',
            'quote': '且仅覆盖单一训练划分，划分自身的随机性未计入不确定性',
            'issue': '元数据表述每个subject为一个配对实验单元，没有证明32个单元全部来自同一个全局训练划分。单一划分和未计入划分随机性属于超出给定证据的断言。',
            'suggestion': '改为“输入未提供跨划分、随机种子及训练过程的详细层级信息，因此无法评估更广泛的泛化不确定性”。',
            'affects_numerical_results': False}],
    },
    'cert_environment_final': {
        'status': 'no_material_scientific_issue_found_in_text_review',
        'design_direction_units_missingness_ci_p_synthetic': 'Checked final narrative: negative OLS slope in mg/L per deg C, n=50 complete observations from 52 rows, 2 missing outcomes removed, two-sided CI/p and R² correctly described; association not causation, model/missingness uncertainty and synthetic data limits explicit.',
        'findings': [],
    },
}


def issue(field, quote, explanation, suggestion, severity='moderate_wording'):
    return {'severity': severity, 'field': field, 'quote': quote, 'issue': explanation,
            'suggestion': suggestion, 'affects_numerical_results': False}


MANUAL.update({
    'eval_biology_baseline': {
        'status': 'minor_revision_recommended',
        'design_direction_units_missingness_ci_p_synthetic': 'Correct Welch independent-groups design; treatment minus control; n=54 observations with 27 per group, 2 rows removed; CI crosses zero and p=0.0778 correctly fails the 0.05 threshold; does not claim proof of no effect; synthetic label and non-causal caveat present.',
        'findings': [
            issue('limitations', '组间方差不等也提示效应尺度需谨慎解释',
                  'Welch方法不要求方差相等，不代表已经发现组间方差不等；实际样本SD为1.2887和1.2869，十分接近，且没有方差检验证据。',
                  '组间方差未预先假定相等，因此使用Welch方法；不能据此断言已经观察到异方差。'),
            issue('findings', '数据与“处理提高生物量”的假设相容，但不构成支持证据',
                  '未达到预设显著性阈值不等于不存在任何方向性证据；该绝对措辞把连续证据强度二分化。主要非显著结论本身正确。',
                  '数据与正向效应相容，但尚未提供达到预设显著性阈值的充分证据。'),
            issue('limitations', '观察性分组比较只能支持相关描述',
                  '输入未注明随机分配机制，应明确未知而非把未说明的研究设计确定为观察性。',
                  '输入未提供随机分配和混杂控制信息，因此只描述组间差异，不作因果解释。')],
    },
    'eval_biology_execute': {
        'status': 'minor_revision_recommended',
        'design_direction_units_missingness_ci_p_synthetic': 'Core conclusion correct: estimate 0.6305 g, CI [-0.07279,1.334] includes zero, p=0.0778; explicitly says insufficient evidence is not proof of no effect. Independent groups, n=54, missing rows=2, units and synthetic/non-causal boundaries correct.',
        'findings': [
            issue('limitations', '样本量有限，检验效能不足',
                  '没有指定最小重要差异或实施功效分析，不能由p>0.05推断检验效能不足；当前能直接观察的是区间较宽。',
                  '当前置信区间较宽，估计精度有限；本次未针对最小重要差异进行功效分析。'),
            issue('limitations', '因为不存在随机化与混杂控制',
                  '元数据未提供随机分配/混杂控制信息，不等于证明这些措施不存在。',
                  '输入未提供随机分配与混杂控制的证据，因此本报告不作因果解释。')],
    },
    'eval_education_baseline': {
        'status': 'correction_required_before_scientific_release',
        'design_direction_units_missingness_ci_p_synthetic': 'Implemented paired test is correct: after minus before, n=30 complete pairs / 60 retained rows, 4 rows from 2 incomplete pairs excluded; positive CI [2.952,7.923], p=0.000109; synthetic and no-causation labels present. One material narrative assumption contradicts the correct implementation.',
        'findings': [
            issue('limitations', '设计假设个体内独立',
                  '配对t检验不要求同一个体的前后两次测量独立；要求不同个体的配对差值之间独立。原文与methods“不假设两次观测相互独立”直接矛盾。',
                  '设计假设不同学习者的配对差值相互独立，同一学习者的前后测量允许相关。',
                  'major_scientific_wording')],
    },
    'eval_education_execute': {
        'status': 'minor_revision_recommended',
        'design_direction_units_missingness_ci_p_synthetic': 'Correct paired design, after-minus-before direction and points units; 30 complete pairs, 4 excluded rows / 2 incomplete pairs; CI and p correctly indicate evidence against zero mean change; no actual causal claim, synthetic boundary explicit. Statistical-probability and future causal-design wording need tightening.',
        'findings': [
            issue('findings', '配对差值与零的差异超出抽样波动可解释的范围',
                  '小p值不排除随机抽样波动，不是“随机性无法解释”的证明；推断必须条件于检验假设和零均值原假设。',
                  '在检验假设成立时，该样本提供了反对平均配对差值为零的统计证据。'),
            issue('next_steps', '可引入平行对照组或随机分配，从而把条件差异的解释从相关提升到因果',
                  '仅增加一个平行对照组并不足以保证因果识别，随机化也需实施及识别假设成立。',
                  '若目标是因果推断，应设计适当的对照与随机分配，并评估实施偏差等识别假设；仅增加对照组不足以保证因果解释。')],
    },
    'eval_energy_baseline': {
        'status': 'minor_revision_recommended',
        'design_direction_units_missingness_ci_p_synthetic': 'OLS slope, 95% CI, p, R² and n=50 correct; slope units are kWh per percentage point (not relative percent); association is explicitly distinguished from causal or physical-response inference; 2 missing rows excluded and synthetic source clearly stated.',
        'findings': [
            issue('methods', '分析方案、图型与解读均由分析者预先确定',
                  '实际事件时序是先批准分析并计算结果，再由LLM选图和撰写叙述；只有分析计划先于结果，不能把图型和结果解读一并描述为预先确定。',
                  '统计设计在计算前由LLM批准；图型和报告解读在读取统计结果后由LLM确定。本次未基于结果改换统计模型。')],
    },
    'eval_energy_execute': {
        'status': 'minor_revision_recommended',
        'design_direction_units_missingness_ci_p_synthetic': 'Core scientific interpretation correct: positive slope 0.8258 kWh per percentage point; CI [0.7788,0.8729], p=5.6e-36, R²=0.9628, n=50, 2 excluded rows. Explicitly limits conclusions to synthetic association, not causality. Suggested revisions concern unsupported sample-size/design statements and future repeated-measurement advice, not numbers or effect direction.',
        'findings': [
            issue('limitations', '样本量50偏小，对异常值和非线性偏离较敏感',
                  '未提供样本量充分性标准；仅凭n=50不能断言样本量偏小。OLS确需检查异常点和模型形式，但这不依赖一个未定义的小样本标签。',
                  '样本量为50；本研究未评估样本量充分性，仍需检查异常值、非线性及其他模型假设。', 'minor_wording'),
            issue('limitations', '缺少随机化与混杂控制',
                  '元数据不足以证明随机化不存在；能确认的是此处只有一元回归和有限设计信息。',
                  '输入未提供随机分配和混杂控制证据，当前一元回归不支持因果推断。', 'minor_wording'),
            issue('next_steps', '增加重复测量与工况控制以检验独立性',
                  '增加重复测量本身不是独立性检验，反而可能引入同一设备内相关，应明确相关结构。',
                  '记录工况并检查采样单元的独立性；如增加重复测量，应明确建模同一设备内的相关性。', 'minor_wording')],
    },
})

EXECUTE_REVISIONS = {
    'eval_biology_execute': [
        {'field': 'limitations',
         'before': '第三，样本量有限，检验效能不足，p 值偏大只能说明证据不足，不等同于证明处理无效。',
         'after': '第三，当前置信区间较宽，估计精度有限；未针对预设最小重要差异进行功效分析，不能仅凭本次 p 值断言检验效能不足。未达到显著性阈值不等同于证明处理无效。',
         'reason': 'No effect-specific power analysis; preserve the correct non-significant conclusion.'},
        {'field': 'limitations',
         'before': '观察到的组间差异不能解释为处理对生物量的因果效应，因为不存在随机化与混杂控制。',
         'after': '输入未提供随机分配与混杂控制的证据，因此本报告仅描述组间差异，不作因果解释。',
         'reason': 'Missing design information is not proof of absence.'}],
    'eval_education_execute': [
        {'field': 'findings',
         'before': '说明在该合成数据中，配对差值与零的差异超出抽样波动可解释的范围',
         'after': '表明在检验假设成立时，该合成样本提供了反对平均配对差值为零的统计证据',
         'reason': 'Small p does not rule out sampling fluctuation; express conditional evidence.'},
        {'field': 'next_steps',
         'before': '若设计允许，可引入平行对照组或随机分配，从而把条件差异的解释从相关提升到因果',
         'after': '若目标是因果推断，应设计适当的对照与随机分配，并评估实施偏差等识别假设；仅增加平行对照组并不足以保证因果解释',
         'reason': 'A parallel control alone does not establish causal identification.'}],
    'eval_energy_execute': [
        {'field': 'limitations',
         'before': '样本量50偏小，对异常值和非线性偏离较敏感。',
         'after': '样本量为50；本研究未评估样本量充分性，仍需检查异常值、非线性及其他模型假设。',
         'before_template': '样本量{{n}}偏小，对异常值和非线性偏离较敏感。',
         'after_template': '样本量为{{n}}；本研究未评估样本量充分性，仍需检查异常值、非线性及其他模型假设。',
         'reason': 'Remove an unsupported adequacy judgment; retain the same n.'},
        {'field': 'limitations',
         'before': '最后，回归只能刻画统计关联，缺少随机化与混杂控制，无法支持因果推断。',
         'after': '最后，输入未提供随机分配和混杂控制的证据，当前一元回归仅刻画统计关联，不支持因果推断。',
         'reason': 'Unknown randomization is not demonstrably absent randomization.'},
        {'field': 'next_steps',
         'before': '增加重复测量与工况控制以检验独立性',
         'after': '记录工况并检查采样单元的独立性；如增加重复测量，应明确建模同一设备内的相关性',
         'reason': 'Repeated measurements introduce within-device correlation rather than prove independence.'}],
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def recompute(csv_path, plan):
    with csv_path.open(encoding='utf-8', newline='') as stream:
        original = list(csv.DictReader(stream))
    rows = [row for row in original if row[plan['outcome_column']] != '']
    ycol, design = plan['outcome_column'], plan['design']
    confidence = plan['confidence']
    additional = {}
    if design == 'independent_groups':
        a, b = ([float(row[ycol]) for row in rows if row[plan['group_column']] == label]
                for label in (plan['reference_group'], plan['comparison_group']))
        na, nb = len(a), len(b)
        va, vb = statistics.variance(a), statistics.variance(b)
        estimate = statistics.mean(b) - statistics.mean(a)
        se2 = va / na + vb / nb
        se = math.sqrt(se2)
        df = se2**2 / ((va / na)**2 / (na-1) + (vb / nb)**2 / (nb-1))
        n = retained = na + nb
        pooled = math.sqrt(((na-1)*va + (nb-1)*vb)/(n-2))
        effect = estimate / pooled * (1 - 3/(4*(n-2)-1))
        additional['group_n'] = {plan['reference_group']: na, plan['comparison_group']: nb}
        additional['n_unit'] = 'independent observations'
    elif design == 'paired':
        by_unit = {}
        for row in rows:
            by_unit.setdefault(row[plan['subject_column']], {})[row[plan['group_column']]] = float(row[ycol])
        differences = [unit[plan['comparison_group']] - unit[plan['reference_group']]
                       for unit in by_unit.values() if len(unit) == 2]
        n = len(differences)
        estimate, sd = statistics.mean(differences), statistics.stdev(differences)
        se, df = sd/math.sqrt(n), n-1
        effect, retained = estimate/sd, 2*n
        original_units = len({row[plan['subject_column']] for row in original})
        additional.update(n_unit='complete pairs', original_units=original_units,
                          excluded_pairs=original_units-n)
    elif design == 'regression':
        rows = [row for row in rows if row[plan['predictor_column']] != '']
        x, y = ([float(row[col]) for row in rows] for col in (plan['predictor_column'], ycol))
        fit = stats.linregress(x, y)
        estimate, se, n = fit.slope, fit.stderr, len(rows)
        df, effect, retained = n-2, estimate, n
        additional.update(n_unit='independent observations', r_squared=fit.rvalue**2,
                          intercept=fit.intercept)
    else:
        raise ValueError('unsupported review design')
    margin = stats.t.ppf((1+confidence)/2, df)*se
    values = dict(estimate=float(estimate), ci_low=float(estimate-margin), ci_high=float(estimate+margin),
                  p_value=float(2*stats.t.sf(abs(estimate/se), df)), n=n, effect_size=float(effect))
    values.update({key: additional[key] for key in ('r_squared', 'intercept') if key in additional})
    return values, dict(input_rows=len(original), retained_rows=retained,
                        excluded_rows=len(original)-retained, **additional)


def review(run, experiment_root):
    manifest = read(run/'manifest.json')
    records = {r['id']: r for r in (read(path) for path in (run/'workspace/records').glob('*.json'))}
    reports = [r for r in records.values() if r['kind']=='report']
    calls, verified_ids = {}, []
    for line in (run/'agent-events.jsonl').read_text(encoding='utf-8').splitlines():
        event = json.loads(line)
        data = event.get('data', {})
        if event.get('type') == 'tool/call':
            calls[data.get('callId')] = data.get('name')
        elif event.get('type') == 'tool/result':
            message = data.get('message', {})
            if calls.get(message.get('source', {}).get('callId')) != 'mcp__research_report__verify_report':
                continue
            for block in message.get('content', []):
                for item in block.get('content', []):
                    if item.get('type') == 'text':
                        try:
                            value = json.loads(item['text'])
                        except ValueError:
                            continue
                        if value.get('report_id'):
                            verified_ids.append(value['report_id'])
    if not verified_ids or verified_ids[-1] not in records:
        raise ValueError(f'Final report verification missing for {run.name}')
    report = records[verified_ids[-1]]
    report_plan = records[report['payload']['plan_id']]
    expected = SNAPSHOT_BINDINGS.get(run.name)
    if expected is None or report['id'] != expected['report_id'] or report['payload']['sha256'] != expected['pdf_sha256']:
        raise ValueError(f'{run.name}: different report; the recorded narrative review must not be reused')
    report_body = {key: value for key, value in report.items() if key != 'id'}
    if report['id'] != 'rra-report-' + hashlib.sha256(canonical(report_body)).hexdigest()[:32]:
        raise ValueError(f'{run.name}: report receipt content changed')
    old_pdf_path = report['payload']['path'].replace('\\', '/')
    if '/artifacts/' not in old_pdf_path:
        raise ValueError(f'{run.name}: report is outside artifact scope')
    pdf_path = (run/'workspace/artifacts'/old_pdf_path.split('/artifacts/', 1)[1]).resolve()
    if not pdf_path.is_relative_to((run/'workspace').resolve()):
        raise ValueError(f'{run.name}: report escaped artifact scope')
    if hashlib.sha256(pdf_path.read_bytes()).hexdigest() != expected['pdf_sha256']:
        raise ValueError(f'{run.name}: actual PDF differs from the manually reviewed snapshot')
    for finding in MANUAL[run.name]['findings']:
        if report_plan['payload']['narrative'][finding['field']].count(finding['quote']) != 1:
            raise ValueError(f'{run.name}: reviewed quotation is missing or ambiguous')
    analysis = records[report['payload']['analysis_id']]
    payload = analysis['payload']
    case = manifest['case_id']
    csv_path = experiment_root/'data'/'cases'/case/'data.csv'
    actual_hash = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    independent, diagnostics = recompute(csv_path, payload['plan'])
    numeric_checks = {key: {'reported': payload['statistics'][key], 'recomputed': value,
                           'passed': math.isclose(value, payload['statistics'][key], abs_tol=0 if key=='p_value' else 1e-10, rel_tol=1e-9)}
                      for key, value in independent.items()}
    missingness = {key: {'reported': payload['diagnostics'][key], 'recomputed': diagnostics[key],
                        'passed': payload['diagnostics'][key] == diagnostics[key]}
                   for key in ('input_rows', 'retained_rows', 'excluded_rows')}
    metrics_checks = {key: math.isclose(value, payload['metrics_dict'][key], abs_tol=0 if key=='p_value' else 1e-10, rel_tol=1e-9)
                      for key, value in independent.items() if key in payload['metrics_dict']}
    source_ok = actual_hash == payload['data_sha256']
    body = {key: value for key, value in report_plan.items() if key != 'id'}
    plan_digest_ok = report_plan['id'] == 'rra-report_plan-' + hashlib.sha256(canonical(body)).hexdigest()[:32]
    if not plan_digest_ok:
        raise ValueError(f'{run.name}: reviewed report-plan text changed')
    numerical_pass = all(row['passed'] for row in numeric_checks.values()) and all(row['passed'] for row in missingness.values()) and all(metrics_checks.values()) and source_ok
    return {
        'run_directory': run.name, 'run_id': manifest['run_id'], 'case_id': case, 'mode': manifest['mode'],
        'source_csv': str(csv_path), 'source_csv_sha256': actual_hash, 'source_hash_matches_record': source_ok,
        'analysis_id': analysis['id'], 'report_plan_id': report_plan['id'], 'report_id': report['id'],
        'report_plan_content_address_valid': plan_digest_ok,
        'manual_review_snapshot_verified': True, 'snapshot_original_pdf_sha256': expected['pdf_sha256'],
        'report_records_in_run': len(reports), 'report_verification_attempts': len(verified_ids),
        'design': payload['plan']['design'], 'contrast': payload['statistics']['contrast'],
        'numerical_status': 'passed' if numerical_pass else 'failed', 'numeric_checks': numeric_checks,
        'sample_and_missingness_checks': missingness, 'n_unit': diagnostics['n_unit'],
        'metrics_dict_matches_independent_calculation': metrics_checks,
        'extra_sampling_checks': {key: value for key, value in diagnostics.items() if key not in missingness},
        'narrative_review': MANUAL.get(run.name, {'status': 'pending_text_review', 'findings': []}),
        'demonstration_suitability': 'Suitable for demonstrating the real computation/MCP/LLM/report pipeline; retain the stated wording issues alongside the original report.' if numerical_pass else 'Not qualified: numerical failure.',
        'scientific_release_recommendation': ('Correct the contradictory independence statement before external scientific use.'
            if MANUAL.get(run.name, {}).get('status')=='correction_required_before_scientific_release'
            else 'Apply documented wording corrections before external presentation; this remains synthetic-only evidence and is not human-expert approved.'
            if MANUAL.get(run.name, {}).get('findings') else 'No material text issue found in this review; still synthetic-only, not a real scientific finding or human-expert approval.'),
        'report_plan_continuation_authorized': report_plan['payload']['allow_deterministic_continuation'],
        'report_plan_authorized_tools': report_plan['authorized_tools'],
        'report_authorized_tools': report['authorized_tools'],
        'original_artifacts_edited': False,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, help='Defaults to EXPERIMENT_ROOT/review; existing outputs are never overwritten')
    args = parser.parse_args()
    experiment_root = args.experiment_root.resolve(strict=True)
    output_dir = (args.output_dir or experiment_root/'review').resolve()
    if output_dir.is_relative_to(experiment_root/'runs') or output_dir.is_relative_to(experiment_root/'data'):
        raise ValueError('Review output must not be placed inside immutable run or source data directories')
    output_names = ('scientific-review.json', 'execute-narrative-revisions.json')
    if any((output_dir/name).exists() for name in output_names):
        raise FileExistsError('Refusing to overwrite an existing review; choose a fresh --output-dir')
    eligible = [name for name in SNAPSHOT_BINDINGS if (experiment_root/'runs'/name/'metrics.json').exists()]
    if not eligible:
        raise ValueError('No runs matching the observed-review snapshot were found')
    results = [review(experiment_root/'runs'/name, experiment_root) for name in eligible]
    library = read(experiment_root/'library.json')
    if library.get('library_digest') != SNAPSHOT_LIBRARY_DIGEST:
        raise ValueError('Different library: the observed missing-authorization explanation requires a fresh review')
    learned = [{'from_tool': m['from_tool'], 'to_tool': m['to_tool']} for m in library['artifacts']]
    document = {
        'schema_version': 1, 'review_utc': datetime.now(timezone.utc).isoformat(),
        'reviewer': 'AI assistant read-only review; not a human expert endorsement and not blinded',
        'manual_review_snapshot': '2026-10-10 observed reports; report ID, actual PDF hash, report-plan content address and exact quotations verified. Not an automatic scientific classifier.',
        'scope': 'Source CSV independent numerical recalculation plus explicit manual reading of indicated LLM narratives. Visual PDF review is a separate deliverable.',
        'independent_recompute': 'stdlib csv/statistics and explicit Welch/paired formulas; scipy.linregress cross-check against statsmodels OLS; scipy t distribution. No benchmark analysis/verification function imported.',
        'runs_reviewed': results,
        'counts': {'numerical_runs_checked': len(results),
                   'numerical_runs_passed': sum(x['numerical_status']=='passed' for x in results),
                   'narratives_read': sum(x['narrative_review']['status']!='pending_text_review' for x in results),
                   'narratives_requiring_wording_revision': sum(x['narrative_review']['status'] in {'minor_revision_recommended', 'correction_required_before_scientific_release'} for x in results),
                   'narratives_with_major_scientific_wording_error': sum(x['narrative_review']['status']=='correction_required_before_scientific_release' for x in results)},
        'motif_library_audit': {
            'library_digest': library['library_digest'], 'learned_edges': learned,
            'excluded_candidate_edges': [
                {'from_tool': 'plan_report', 'to_tool': 'export_report'},
                {'from_tool': 'export_report', 'to_tool': 'verify_report'}],
            'reason': 'train_ml_final and cert_environment_final report plans did not opt in to deterministic continuation (stored false; authorized_tools=[]). Their report receipts also authorize no continuation. These edges therefore lack two authorized training witnesses plus an authorized independent certification witness and correctly do not enter the library.',
            'interpretation': 'A user task requesting opt-in does not allow the compiler to invent the missing plan authorization. The structural runtime remains conservative; it must return these steps to the LLM. This is a capability/authorization limit, not a manually bypassed failure.'},
        'limits': ['All observations are synthetic; numerical correctness does not establish a real scientific finding.',
                   'Automatic PDF QA and exact numbers cannot validate unsupported statements about the data collection design.',
                   'Scientific/visual assessment is not a blinded independent human review.',
                   'Reports were not edited by this audit; recorded issues remain visible.']}
    output = output_dir/'scientific-review.json'
    revision_rows = []
    for name, replacements in EXECUTE_REVISIONS.items():
        found = next((row for row in results if row['run_directory']==name), None)
        if found is None:
            continue
        run = experiment_root/'runs'/name
        plan_path = run/'workspace/records'/f"{found['report_plan_id']}.json"
        report_path = run/'workspace/records'/f"{found['report_id']}.json"
        plan = read(plan_path)['payload']
        report = read(report_path)['payload']
        for item in replacements:
            assert plan['narrative'][item['field']].count(item['before']) == 1, (name, item)
            template = item.get('before_template', item['before'])
            assert plan['narrative_template'][item['field']].count(template) == 1, (name, item)
        revision_rows.append({'run_directory': name, 'run_id': found['run_id'], 'case_id': found['case_id'],
                              'report_plan_file': str(plan_path), 'original_report_record_file': str(report_path),
                              'original_pdf_sha256': report['sha256'],
                              'replacements': replacements})
    revision_document = {'schema_version': 1, 'label': '审阅修订演示版',
                         'not_part_of_original_benchmark_results': True,
                         'preserve_original_artifacts': True, 'change_numeric_values': False,
                         'change_figures': False, 'change_effect_direction_or_significance': False,
                         'reviewer': 'AI assistant; non-blinded scientific wording review', 'reports': revision_rows}
    output_dir.mkdir(parents=True, exist_ok=True)
    # Write only after all input/version/quotation checks have succeeded.
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    (output_dir/'execute-narrative-revisions.json').write_text(json.dumps(revision_document, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(document['counts'], ensure_ascii=False))
