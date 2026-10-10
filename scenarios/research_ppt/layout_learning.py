"""历史真实计划的受限布局学习；格式、几何代理与真实渲染不等于审美认证。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
from uuid import uuid4

from .documents import file_hash, inspect_pptx
from .validation import validate_delivery, _read_package

SCENE = Path(__file__).resolve().parent
LIMIT = 3
DEFAULT = {'schema_version': 1, 'media_position': 'right', 'media_fraction': 0.58,
           'body_columns': 1, 'body_font_size': 22, 'table_font_size': 18, 'body_gap': 0.18}


def _private(path: Path) -> Path:
    # 延迟导入，允许 service 委托本模块而不产生循环初始化。
    from .service import private_path
    return private_path(path)


def _node(script: str, payload: dict, *args: str) -> dict:
    from .service import node
    return node(script, payload, *args)


def _read(path: Path) -> dict:
    value = json.loads(_private(path).read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('布局学习记录必须为 JSON 对象')
    return value


def _write(path: Path, value: dict, *, exclusive=False):
    path = _private(path)
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if exclusive:
        with path.open('x', encoding='utf-8') as stream:
            stream.write(raw)
    else:
        temporary = _private(path.with_name(path.name + '.' + uuid4().hex + '.tmp'))
        temporary.write_text(raw, encoding='utf-8')
        temporary.replace(path)


def _freeze(path: Path, value: dict):
    _write(path, value, exclusive=True)
    _private(path.with_name(path.name + '.sha256')).write_text(file_hash(path), encoding='ascii')


def _frozen(path: Path) -> dict:
    path = _private(path)
    expected = _private(path.with_name(path.name + '.sha256')).read_text(encoding='ascii').strip()
    if not re.fullmatch(r'[0-9a-f]{64}', expected) or file_hash(path) != expected:
        raise ValueError('冻结记录已变化，布局认证失效')
    return _read(path)


def _job(job_path: Path, supplied: dict | None = None, *, write=False) -> tuple[dict, Path]:
    path = _private(job_path)
    job = _read(path)
    if supplied is not None and any(supplied.get(key) != job.get(key) for key in
            ('job_id', 'allow_rsi', 'allow_output', 'layout_suite', 'layout_suite_sha256')):
        raise ValueError('任务配置已变化，请重新加载任务')
    if write and (job.get('allow_rsi') is not True or job.get('allow_output') is not True):
        raise ValueError('布局学习需要任务明确允许 RSI 和私有产物输出')
    return job, _private(path.parent / 'layout-rsi')


def _suite(job: dict) -> tuple[dict, str]:
    path = _private(Path(job['layout_suite']))
    if not Path(job['layout_suite']).is_absolute():
        raise ValueError('layout_suite 必须为私有绝对路径')
    digest = file_hash(path)
    if job.get('layout_suite_sha256') is not None and job['layout_suite_sha256'] != digest:
        raise ValueError('布局训练资料版本已变化')
    suite = _read(path)
    if set(suite) != {'schema_version', 'cases'} or suite.get('schema_version') != 1 or not isinstance(suite['cases'], list):
        raise ValueError('布局资料必须使用 suite schema_version=1')
    if not 2 <= len(suite['cases']) <= 30:
        raise ValueError('布局资料需要 2–30 个冻结计划')
    ids, hashes, run_splits, splits = set(), set(), {}, set()
    for case in suite['cases']:
        if (not isinstance(case, dict) or set(case) != {'id', 'split', 'plan', 'sha256', 'run_id'} or
                not isinstance(case['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', case['id']) or
                case['split'] not in {'train', 'heldout'} or not isinstance(case['plan'], str) or
                not isinstance(case['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', case['sha256']) or
                not isinstance(case['run_id'], str) or not 1 <= len(case['run_id']) <= 128):
            raise ValueError('布局资料用例字段无效')
        if case['id'] in ids or case['sha256'] in hashes:
            raise ValueError('布局资料 id 或计划哈希重复')
        if case['run_id'] in run_splits and run_splits[case['run_id']] != case['split']:
            raise ValueError('同一模型运行不能同时属于训练与独立认证')
        ids.add(case['id']); hashes.add(case['sha256']); splits.add(case['split'])
        run_splits[case['run_id']] = case['split']
        _plan(case)
    if splits != {'train', 'heldout'}:
        raise ValueError('布局资料必须同时有 train 和 heldout')
    if file_hash(path) != digest:
        raise ValueError('读取期间布局资料版本变化')
    return suite, digest


def _plan(case: dict) -> dict:
    path = Path(case['plan'])
    if not path.is_absolute() or path.name != 'plan.json':
        raise ValueError('仅接受历史真实 PPTX 同目录的绝对 plan.json 路径')
    path = _private(path)
    if file_hash(path) != case['sha256']:
        raise ValueError('历史模型计划版本变化')
    plan = _read(path)
    if not isinstance(plan.get('slides'), list) or not 1 <= len(plan['slides']) <= 30:
        raise ValueError('历史计划缺少 1–30 页幻灯片')
    if file_hash(path) != case['sha256']:
        raise ValueError('读取期间历史模型计划版本变化')
    return plan


def _version() -> dict:
    names = ['layout_learning.py', 'ts/render.ts', 'dist/render.js', 'ts/layout-policy.ts', 'dist/layout-policy.js',
             'ts/layout-policy-cli.ts', 'dist/layout-policy-cli.js', 'validation.py', 'documents.py', 'package-lock.json']
    return {name: file_hash(SCENE / name) for name in names}


def _policy(value: dict) -> dict:
    checked = _node('layout-policy-cli.js', value)
    if checked.get('valid') is not True:
        raise ValueError(checked.get('error', '布局策略格式无效'))
    return checked


def _used(area: Path) -> int:
    return sum(_private(area / f'attempt-{number}.json').exists() for number in range(1, LIMIT + 1))


def _reserve(area: Path, job: dict) -> int:
    area = _private(area)
    area.mkdir(parents=True, exist_ok=True)
    for number in range(1, LIMIT + 1):
        try:
            _write(area / f'attempt-{number}.json', {'job_id': job.get('job_id'), 'attempt': number}, exclusive=True)
            return number
        except FileExistsError:
            continue
    raise ValueError('布局策略已达持久化 3 次提案上限，失败同样计数')


def _content_hash(plan: dict) -> str:
    unchanged = {key: value for key, value in plan.items() if key != 'layout_policy'}
    return hashlib.sha256(json.dumps(unchanged, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _texts(slide: dict) -> list[str]:
    result = [slide['title'], *slide.get('bullets', [])]
    if slide.get('takeaway'):
        result.append(slide['takeaway'])
    result.extend(text for row in slide.get('table', []) for text in row)
    for side in slide.get('comparison', {}).values():
        result.extend([side['title'], *side['bullets']])
    for step in slide.get('process', {}).get('steps', []):
        result.extend([step['label'], step['detail']])
    return result


def _evidence(row: dict):
    for artifact in row.get('files', []):
        path = _private(Path(artifact['path']))
        if file_hash(path) != artifact['sha256']:
            raise ValueError('布局回放 PPTX/PDF/PNG 或记录版本已变化')
    if row.get('passed') and not {'pptx', 'manifest', 'pdf', 'preview'}.issubset({f['kind'] for f in row.get('files', [])}):
        raise ValueError('布局回放缺少真实渲染证据')


def _replay(case: dict, policy: dict, area: Path, version: dict) -> dict:
    plan = _plan(case)
    directory = _private(area / (case['id'] + '-' + uuid4().hex))
    directory.mkdir(parents=True, exist_ok=False)
    record = {'id': case['id'], 'origin_run_id': case['run_id'], 'source_plan_sha256': case['sha256'],
              'policy_digest': _policy(policy)['policy_digest'], 'renderer_version': version,
              'passed': False, 'diagnostics': [], 'files': [], 'mean_image_area': 0.0,
              'content_sha256': _content_hash(plan), 'record_path': str(directory / 'replay.json')}
    candidate = copy.deepcopy(plan)
    candidate['layout_policy'] = policy
    plan_path = _private(directory / 'plan.json')
    _write(plan_path, candidate, exclusive=True)
    pptx = _private(directory / 'presentation.pptx')
    try:
        if _content_hash(candidate) != record['content_sha256']:
            raise ValueError('策略改变了原计划内容')
        rendered = _node('render.js', {}, str(plan_path), str(pptx))
        if rendered.get('ok') is False:
            raise ValueError(rendered.get('error', '布局生成失败'))
        manifest_path = _private(pptx.with_suffix('.layout.json'))
        manifest = _read(manifest_path)
        if manifest.get('layout_policy_sha256') != record['policy_digest']:
            raise ValueError('渲染器未使用声明的布局策略')
        semantic = manifest.get('semantic_content_sha256')
        if not isinstance(semantic, str) or not re.fullmatch(r'[0-9a-f]{64}', semantic):
            raise ValueError('渲染器没有内容版本证据')
        record['semantic_content_sha256'] = semantic
        inspection = inspect_pptx(pptx)
        if inspection['slide_count'] != len(plan['slides']) or not inspection['each_slide_has_editable_text']:
            raise ValueError('PPTX 页数或可编辑文字回归')
        checked = validate_delivery(pptx, len(plan['slides']), expected_texts=[_texts(s) for s in plan['slides']],
                                    expected_sources=[s['sources'] for s in plan['slides']])
        # 额外检查原 notes；validate_delivery 原有来源检查仍保留。
        native_report = {'errors': [], 'warnings': []}
        _, notes = _read_package(pptx, native_report)
        for index, slide in enumerate(plan['slides']):
            if slide.get('notes') and slide['notes'] not in notes[index]:
                raise ValueError('原讲者 notes 未完整保留')
        areas = [e['w'] * e['h'] for s in manifest['slides'] for e in s['elements'] if e['role'] == 'image']
        record['mean_image_area'] = sum(areas) / len(areas) if areas else 0.0
        record['image_count'] = len(areas)
        record['inspection'] = inspection
        record['validation'] = checked
        record['layout_checks'] = manifest.get('checks', {})
        record['diagnostics'] = [*manifest.get('diagnostics', []), *checked['errors'], *checked['warnings']]
        record['passed'] = checked['passed'] is True and not native_report['errors']
        for kind, path in [('pptx', pptx), ('manifest', manifest_path), ('plan', plan_path),
                           ('validation_report', _private(Path(checked['report_path'])) )]:
            record['files'].append({'kind': kind, 'path': str(path), 'sha256': file_hash(path)})
        for artifact in checked['artifacts']:
            path = _private(Path(artifact['path']))
            record['files'].append({**artifact, 'path': str(path)})
        if file_hash(_private(Path(case['plan']))) != case['sha256'] or _content_hash(_read(plan_path)) != record['content_sha256']:
            raise ValueError('回放期间原计划或候选内容版本变化')
        if _version() != version:
            raise ValueError('回放期间渲染器或验证器版本变化')
    except Exception as exc:
        record['passed'] = False
        record['diagnostics'].append({'code': 'layout_replay_failed', 'message': str(exc)[:1800]})
        for kind, path in [('plan', plan_path), ('pptx', pptx), ('manifest', pptx.with_suffix('.layout.json'))]:
            path = _private(path)
            if path.is_file() and not any(f['path'] == str(path) for f in record['files']):
                record['files'].append({'kind': kind, 'path': str(path), 'sha256': file_hash(path)})
    _write(directory / 'replay.json', record, exclusive=True)
    record['files'].append({'kind': 'replay_record', 'path': str(directory / 'replay.json'),
                            'sha256': file_hash(directory / 'replay.json')})
    return record


def _summary(rows: list[dict]) -> dict:
    images = sum(row.get('image_count', 0) for row in rows)
    return {'cases': len(rows), 'failed': sum(row.get('passed') is not True for row in rows),
            'image_count': images, 'mean_image_area': sum(row.get('mean_image_area', 0) * row.get('image_count', 0)
                                                        for row in rows) / images if images else 0.0}


def _gate(base: list[dict], candidate: list[dict], *, improvement: bool) -> dict:
    old, new = _summary(base), _summary(candidate)
    same = len(base) == len(candidate) and all(
        a['id'] == b['id'] and a['content_sha256'] == b['content_sha256'] and
        (not a.get('semantic_content_sha256') or a['semantic_content_sha256'] == b.get('semantic_content_sha256'))
        for a, b in zip(base, candidate))
    no_regression = same and new['failed'] == 0 and new['image_count'] >= old['image_count']
    reduced_failures = new['failed'] < old['failed']
    area_improved = old['mean_image_area'] > 0 and new['mean_image_area'] >= old['mean_image_area'] * 1.10
    area_not_worse = new['mean_image_area'] + 1e-9 >= old['mean_image_area']
    passed = no_regression and (reduced_failures or (area_improved if improvement else area_not_worse))
    return {'passed': passed, 'baseline': old, 'candidate': new, 'content_unchanged': same,
            'image_area_gain': new['mean_image_area'] / old['mean_image_area'] - 1 if old['mean_image_area'] else None,
            'objective': 'geometry_proxy_only_not_aesthetic_certification'}


def _baseline(job: dict, area: Path, suite: dict, digest: str, version: dict, split: str) -> dict | None:
    path = _private(area / f'{split}-baseline.json')
    if not path.is_file():
        return None
    record = _read(path)
    if record.get('suite_sha256') != digest or record.get('renderer_version') != version:
        return None
    for row in record['rows']:
        _evidence(row)
    if [row['id'] for row in record['rows']] != [case['id'] for case in suite['cases'] if case['split'] == split]:
        raise ValueError('布局基线资料对应关系变化')
    return record


def prepare_training(job_path: Path) -> dict:
    job, area = _job(job_path, write=True)
    suite, digest = _suite(job); version = _version()
    area.mkdir(parents=True, exist_ok=True)
    checked = _policy(DEFAULT)
    cached = _baseline(job, area, suite, digest, version, 'train')
    if cached is None:
        rows = [_replay(case, checked['policy'], area, version) for case in suite['cases'] if case['split'] == 'train']
        cached = {'schema_version': 1, 'suite_sha256': digest, 'renderer_version': version,
                  'policy': checked['policy'], 'policy_digest': checked['policy_digest'], 'schema': checked['schema'], 'rows': rows}
        _write(area / 'train-baseline.json', cached)
    return {'prepared': True, 'training': _summary(cached['rows']), 'baseline_path': str(area / 'train-baseline.json')}


def status(job: dict, job_path: Path) -> dict:
    job, area = _job(job_path, job)
    suite, digest = _suite(job); version = _version()
    cached = _baseline(job, area, suite, digest, version, 'train')
    schema = cached['schema'] if cached else _node('layout-policy-cli.js', {'action': 'schema'})['schema']
    feedback = []
    for path in sorted(area.glob('proposal-*.json')) if area.exists() else []:
        record = _frozen(_private(path))
        feedback.append({'attempt': record['attempt'], 'policy': record.get('policy'),
                         'training_passed': record.get('training_passed', False),
                         'diagnostics': record.get('diagnostics', [])})
    # 不读取/返回 active 或 heldout 认证文件，避免反向泄露认证反馈。
    return {'scope': 'training_layout_geometry_only', 'candidate_schema': schema,
            'attempt_limit': LIMIT, 'attempts_used': _used(area), 'attempts_remaining': max(0, LIMIT - _used(area)),
            'training_prepared': cached is not None, 'training': _summary(cached['rows']) if cached else None,
            'training_diagnostics': [{'id': row['id'], 'origin_run_id': row['origin_run_id'],
                                     'source_plan_sha256': row['source_plan_sha256'], 'passed': row['passed'],
                                     'mean_image_area': row['mean_image_area'], 'diagnostics': row['diagnostics']}
                                    for row in cached['rows']] if cached else [], 'proposal_feedback': feedback,
            'mechanical_certified': False, 'visual_quality_certified': False}


def propose(job: dict, job_path: Path, policy: dict) -> dict:
    job, area = _job(job_path, job, write=True)
    attempt = _reserve(area, job)
    path = _private(area / ('proposal-' + uuid4().hex + '.json'))
    record = {'schema_version': 1, 'job_id': job.get('job_id'), 'attempt': attempt,
              'training_passed': False, 'mechanical_certified': False, 'visual_quality_certified': False,
              'diagnostics': [], 'proposal_path': str(path)}
    try:
        checked = _policy(policy)
        record.update(policy=checked['policy'], policy_digest=checked['policy_digest'])
        suite, digest = _suite(job); version = _version()
        baseline = _baseline(job, area, suite, digest, version, 'train')
        if baseline is None:
            raise ValueError('请先显式 prepare_training 生成当前版本训练基线')
        rows = [_replay(case, checked['policy'], area, version) for case in suite['cases'] if case['split'] == 'train']
        gate = _gate(baseline['rows'], rows, improvement=True)
        record.update(suite_sha256=digest, renderer_version=version, baseline=baseline['rows'], candidate=rows,
                      training=gate, training_passed=gate['passed'],
                      diagnostics=[{'id': row['id'], 'passed': row['passed'], 'mean_image_area': row['mean_image_area'],
                                    'diagnostics': row['diagnostics']} for row in rows])
        if file_hash(_private(Path(job['layout_suite']))) != digest:
            raise ValueError('训练期间资料集版本变化')
    except Exception as exc:
        record['training_passed'] = False
        record['diagnostics'].append({'code': 'proposal_failed', 'message': str(exc)[:1800]})
    _freeze(path, record)
    return {'proposal_path': str(path), 'training_passed': record['training_passed'],
            'policy_digest': record.get('policy_digest'), 'diagnostics': record['diagnostics'],
            'training': record.get('training'), 'attempt': attempt, 'attempts_remaining': LIMIT - _used(area),
            'mechanical_certified': False, 'visual_quality_certified': False}


def certify(job_path: Path, proposal_path: Path) -> dict:
    job, area = _job(job_path, write=True)
    proposal_path = _private(proposal_path)
    if proposal_path.parent != area or not proposal_path.name.startswith('proposal-'):
        raise ValueError('只能认证本任务冻结的布局提案')
    record = _frozen(proposal_path)
    suite, digest = _suite(job); version = _version()
    if (record.get('job_id') != job.get('job_id') or record.get('training_passed') is not True or
            record.get('suite_sha256') != digest or record.get('renderer_version') != version):
        raise ValueError('提案未通过冻结训练或代码/资料版本已变化')
    checked = _policy(record['policy'])
    if checked['policy_digest'] != record['policy_digest']:
        raise ValueError('提案策略摘要变化')
    for row in [*record['baseline'], *record['candidate']]:
        _evidence(row)
    if not _gate(record['baseline'], record['candidate'], improvement=True)['passed']:
        raise ValueError('训练证据不再满足固定晋级目标')
    reservation = _private(area / 'heldout-reservation.json')
    binding = {'proposal_sha256': file_hash(proposal_path), 'suite_sha256': digest, 'renderer_version': version}
    try:
        _write(reservation, binding, exclusive=True)
    except FileExistsError:
        if _read(reservation) != binding:
            raise ValueError('本任务认证集已用于其他候选，不能反馈后继续调参') from None
    baseline = _baseline(job, area, suite, digest, version, 'heldout')
    if baseline is None:
        rows = [_replay(case, DEFAULT, area, version) for case in suite['cases'] if case['split'] == 'heldout']
        baseline = {'schema_version': 1, 'suite_sha256': digest, 'renderer_version': version, 'rows': rows}
        _write(area / 'heldout-baseline.json', baseline)
    rows = [_replay(case, checked['policy'], area, version) for case in suite['cases'] if case['split'] == 'heldout']
    gate = _gate(baseline['rows'], rows, improvement=False)
    output = {'schema_version': 1, 'job_id': job.get('job_id'), 'policy': checked['policy'],
              'policy_digest': checked['policy_digest'], 'mechanical_certified': gate['passed'],
              'visual_quality_certified': False, 'scientific_quality_certified': False,
              'suite_path': job['layout_suite'], 'suite_sha256': digest, 'renderer_version': version,
              'proposal_path': str(proposal_path), 'proposal_sha256': file_hash(proposal_path),
              'training': record['training'], 'heldout': gate, 'heldout_baseline': baseline['rows'],
              'heldout_candidate': rows, 'objective': 'geometry_proxy_only_not_aesthetic_certification'}
    if file_hash(_private(Path(job['layout_suite']))) != digest or _version() != version:
        output['mechanical_certified'] = False
        output['version_failure'] = '认证期间资料或代码变化'
    certificate_path = _private(area / ('certificate-' + uuid4().hex + '.json'))
    _freeze(certificate_path, output)
    if output['mechanical_certified']:
        validate_certificate(certificate_path)
        active = _private(area / 'active-policy.json')
        _write(active, output)
        _private(active.with_name(active.name + '.sha256')).write_text(file_hash(active), encoding='ascii')
    return {'certificate_path': str(certificate_path), 'active_policy_path': str(area / 'active-policy.json')
            if output['mechanical_certified'] else None, 'mechanical_certified': output['mechanical_certified'],
            'visual_quality_certified': False, 'heldout': gate}


def validate_certificate(path: Path) -> dict:
    certificate = _frozen(_private(path))
    if certificate.get('mechanical_certified') is not True or certificate.get('visual_quality_certified') is not False:
        raise ValueError('布局证书未通过机械认证或夸大视觉认证')
    if certificate.get('renderer_version') != _version():
        raise ValueError('布局认证依赖代码已变化')
    suite, digest = _suite({'layout_suite': certificate['suite_path'], 'layout_suite_sha256': certificate['suite_sha256']})
    proposal_path = _private(Path(certificate['proposal_path']))
    if file_hash(proposal_path) != certificate['proposal_sha256']:
        raise ValueError('布局认证引用的提案已变化')
    proposal = _frozen(proposal_path)
    checked = _policy(certificate['policy'])
    if checked['policy_digest'] != certificate.get('policy_digest') or checked['policy_digest'] != proposal.get('policy_digest'):
        raise ValueError('布局证书与提案策略摘要不一致')
    for row in [*proposal['baseline'], *proposal['candidate'], *certificate['heldout_baseline'], *certificate['heldout_candidate']]:
        _evidence(row)
    if not _gate(proposal['baseline'], proposal['candidate'], improvement=True)['passed'] or not _gate(
            certificate['heldout_baseline'], certificate['heldout_candidate'], improvement=False)['passed']:
        raise ValueError('布局真实证据未满足固定认证目标')
    for split, rows in [('train', proposal['candidate']), ('heldout', certificate['heldout_candidate'])]:
        expected = [case for case in suite['cases'] if case['split'] == split]
        if [(r['id'], r['origin_run_id'], r['source_plan_sha256']) for r in rows] != [
                (c['id'], c['run_id'], c['sha256']) for c in expected]:
            raise ValueError('布局认证资料与历史运行引用不一致')
    return certificate


def main():
    parser = argparse.ArgumentParser(description='布局 RSI 离线回放与独立认证，默认只预览')
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--proposal', type=Path)
    parser.add_argument('--prepare-training', action='store_true')
    parser.add_argument('--certify', action='store_true')
    args = parser.parse_args()
    if args.prepare_training and args.certify:
        parser.error('训练准备和独立认证需分开执行')
    if args.certify:
        if args.proposal is None:
            parser.error('--certify 需要 --proposal')
        result = certify(args.job, args.proposal)
    elif args.prepare_training:
        result = prepare_training(args.job)
    else:
        job, _ = _job(args.job)
        result = {'preview': True, **status(job, args.job)}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
