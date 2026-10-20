"""Preview or independently re-certify the four published File graph shapes.

Historical public attestations supply provenance only. The existing recertifier
requires a new real native witness, two independent guarded actual uses, strict
delivery and complete accounting before a fresh release can be published.
Synthetic compatibility materials are not prospective product-quality evidence.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scenarios/file-management')]
from src.adapters.continuous_rsi import STATE_HOME, PRIVATE_HOME, load_config, initialize, private, records
from src.adapters.management_seed import validate_historical_certificate, publish
from src.adapters.management_recertification import recertify
from src.motif_core.offline.experience_registry import read, sha, durable
from management_prepare import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--previous', default='file-v5')
    parser.add_argument('--release', default='file-v6')
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    experiment = private(args.experiment)
    release = ROOT / 'motif-libraries' / args.previous
    manifest = read(release / 'entry.json')
    for entry in manifest['entries']:
        payload = release / entry['payload']
        validate_historical_certificate(read(payload), release / entry['certificate'], sha(payload))
    if not args.call_model:
        print(json.dumps({'paid': False, 'previous': args.previous, 'candidate': args.release,
                          'shapes': len(manifest['entries']), 'model': 'deepseek-flash', 'reasoning_effort': 'off',
                          'series_cap_usd': 1, 'per_task_cap_usd': 0.05, 'max_steps': 48,
                          'max_output': 3000, 'max_repairs': 0,
                          'historical_evidence': 'provenance_only', 'material_type': 'synthetic_compatibility'}))
        return
    experiment.mkdir(parents=True, exist_ok=True, mode=0o700)
    config = STATE_HOME / (experiment.name + '.json')
    work = PRIVATE_HOME / 'management-copies' / experiment.name
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not config.exists():
        durable(config, {'schema_version': 1, 'format': 'sss-continuous-rsi-v1', 'adapter': 'management_v3',
                         'state_root': str(STATE_HOME / experiment.name), 'workspace_roots': [str(work)],
                         'mode': 'learn', 'provider_mode': 'real', 'series_cap_usd': 1, 'learning_cap_usd': 1,
                         'auto_worker': False, 'allow_material_copy': True,
                         'limits': {'budget_usd': 0.05, 'max_steps': 48, 'max_output': 3000, 'max_repairs': 0}}, exclusive=True)
    cfg = load_config(config)
    initialize(cfg)
    results = []
    for entry in manifest['entries']:
        payload = release / entry['payload']
        policy = read(payload)
        tools = [n['tool'].split('__')[-1] for n in policy['artifact']['nodes']]
        label = '-'.join(tools)
        template = experiment / 'templates' / label
        if not (template / 'task.json').exists():
            pristine = template / 'pristine'
            pristine.mkdir(parents=True, mode=0o700)
            (pristine / 'note.txt').write_text('Independent synthetic note ' + uuid4().hex + '\n', encoding='utf-8')
            if tools[0] in ('pin_files', 'select_files'):
                (pristine / 'second.txt').write_text('Second synthetic note ' + uuid4().hex + '\n', encoding='utf-8')
            objective = ('把 note.txt 重命名为 renamed.txt。完成后核验并提交报告。' if tools[0] == 'preview_actions'
                         else '通读全部文本文件，给出完整读取覆盖清单，不修改任何文件。完成后核验并提交报告。')
            prepare(template, pristine, task_id=uuid4().hex, objective=objective,
                    owner='integration-compatibility', workspace_id=label)
            scenario = read(template / 'scenario.json')
            scenario['acceptance_guard']['max_repairs'] = cfg['limits']['max_repairs']
            durable(template / 'scenario.json', scenario)
            shutil.copyfile(template / 'input.json', template / 'task.json')
            # Explicit diagnostic instructions exercise the historical shape;
            # root selection/arguments and every native call remain real.
            prompt = (template / 'prompt.md').read_text(encoding='utf-8')
            prompt += '\n本次为已有工具链兼容认证。读取实际任务和目录后，用以下工具顺序完成目标：' + ' → '.join(tools)
            prompt += '。所有句柄必须来自真实返回值，中间不要插入其他工具；随后核验并提交完整报告。'
            durable(template / 'enrollment.json', {'prompt': prompt, 'scenario_file': str(template / 'scenario.json')}, exclusive=True)
        historical = experiment / 'historical' / policy['policy_digest']
        historical.mkdir(parents=True, exist_ok=True, mode=0o700)
        original_certificate = release / entry['certificate']
        for source, target in [(payload, historical / 'policy.json'), (original_certificate, historical / 'certificate.json')]:
            if target.exists():
                if sha(target) != sha(source):
                    raise ValueError('Historical provenance changed')
            else:
                shutil.copyfile(source, target)
                target.chmod(0o600)
        result = recertify(config, historical / 'policy.json', historical / 'certificate.json', template, Path(cfg['state_root']) / 'seed-recertification-jobs' / label)
        results.append({'tools': tools, **result})
        durable(experiment / 'progress.json', results)
        print(json.dumps({'tools': tools, 'status': result['status'], 'reason': result.get('reason')}, ensure_ascii=False), flush=True)
        if result['status'] != 'activated':
            raise SystemExit(1)
    current = ROOT / 'motif-libraries' / args.release
    if not current.exists():
        published = publish(config, args.release)
    else:
        published = {'release': args.release, 'entries': len(read(current / 'entry.json')['entries']), 'existing': True}
    outcomes = records(cfg['state_root'])
    summary = {'published': published, 'results': results, 'material_type': 'synthetic_compatibility',
               'requests': sum(r['upstream_requests'] for r in outcomes),
               'estimated_usd': sum(r['cost_usd'] for r in outcomes), 'bill_verified': False,
               'records': [{k: r.get(k) for k in ('session_id', 'role', 'accepted', 'upstream_requests', 'cost_usd',
                                                 'verified_motif_batches', 'observed_usage_complete')} for r in outcomes]}
    durable(experiment / 'summary.json', summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ('results', 'records')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
