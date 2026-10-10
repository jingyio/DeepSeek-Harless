"""v3.1: explicit shared statistical-continuation scope, unchanged v3 runtime."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.research_report_agent_v3.generate_cases import generate
from benchmarks.research_report_agent_v3.prepare_experiment import matrices

EXPERIMENT_ID = 'research-report-agent-v31-20261010'
POLICY_ID = 'approved-statistics-continuation-v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')


def prepare(output: Path, seed_offset=2000000, experiment_id=EXPERIMENT_ID):
    output = output.resolve()
    if ROOT / '.local' not in output.parents:
        raise ValueError('Experiment inputs and evidence must remain under repository .local')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a fresh experiment directory; preserve previous evidence')
    output.mkdir(parents=True, exist_ok=True)
    policy = (HERE/'statistics_continuation_policy.txt').read_text(encoding='utf-8').strip()
    policy_sha = hashlib.sha256(policy.encode('utf-8')).hexdigest()
    policy_meta = {'id': POLICY_ID, 'text_sha256': policy_sha,
        'scope': ['run_analysis','verify_analysis','build_evidence'],
        'stops_at': 'build_evidence', 'explicit_model_boolean_required': True,
        'false_remains_valid_and_unchanged': True,
        'method_figures_outline_and_body_are_not_prefilled': True}
    generated = generate(output/'data', seed_offset)
    for case in generated['cases']:
        folder = output/'data/cases'/case['case_id']
        for filename in ('task.txt','request.txt'):
            path = folder/filename
            original = path.read_text(encoding='utf-8').rstrip()
            path.write_text(original+'\n\n'+policy+'\n',encoding='utf-8',newline='\n')
        study = json.loads((folder/'study.json').read_text(encoding='utf-8'))
        study['user_request'] = study['user_request'].rstrip()+'\n\n'+policy
        study['benchmark_execution_policy'] = dict(policy_meta)
        save(folder/'study.json',study)
        case['execution_policy'] = dict(policy_meta)
        case['source_sha256'] = {name:sha(folder/name) for name in ('data.csv','study.json','task.txt')}
        case['request_sha256'] = sha(folder/'request.txt')
        case['task_sha256'] = sha(folder/'task.txt')
    generated.update(generator='research_report_agent_v31; numeric generation imported unchanged from v3',
        experiment_id=experiment_id, execution_policy=policy_meta,
        note='Same public execution-scope instruction in every task and arm; no semantic answer or executable Motif-library edge prefilled. Tool order and permission scope are manually designed.')
    save(output/'data/dataset_manifest.json',generated)
    (output/'statistics_continuation_policy.txt').write_text(policy+'\n',encoding='utf-8',newline='\n')
    training, evaluations = matrices()
    for job in training+evaluations:
        job['name'] = 'v31_'+job['name'].removeprefix('v3_')
    save(output/'training-matrix.json',training)
    save(output/'evaluation-matrix.json',evaluations)
    runtime_dir = HERE.parent/'research_report_agent_v3'
    runtime_hashes = {path.relative_to(ROOT).as_posix():sha(path) for path in sorted(runtime_dir.iterdir())
                      if path.suffix in {'.py','.mjs','.ts','.json'}}
    preparation_hashes = {path.relative_to(ROOT).as_posix():sha(path) for path in sorted(HERE.iterdir())
                          if path.suffix in {'.py','.txt','.mjs'}}
    protocol = {'experiment_id':experiment_id,'experiment_revision':'v3.1',
        'runtime_benchmark_version':3,'runtime':'research_report_agent_v3, unchanged',
        'comparison_protocol':'free_presentation_and_narrative',
        'change_from_v3':'Explicit, shared user authorization for the already deterministic statistical segment. No new numerical algorithm or runtime bypass rule.',
        'execution_policy':policy_meta,'seed_offset':seed_offset,
        'training_cases':[job['case'] for job in training if job['experiment_role']=='train'],
        'certification_case':next(job['case'] for job in training if job['experiment_role']=='certification'),
        'evaluation_cases':list(dict.fromkeys(job['case'] for job in evaluations)),
        'main_runs_denominator':16,'repeats_per_case_per_arm':2,'independent_evaluation_tasks':4,
        'planned_workers':1,'sequence':'Case-parity alternating arm order; reverse each pair in repeat 2.',
        'freshness':'New data seeds, workspaces, sessions, DSH_HOME and recorded source hashes; old v3 evidence remains intact.',
        'semantic_decisions':['approve_analysis','approve_presentation','submit_report_text'],
        'fairness':'Both arms share exactly the same policy, task bytes, tool schemas, model, limits and inputs; presentation and full prose remain freely generated.',
        'learning':'Fresh ordinary baseline train x2 + independent certification x1. Compile only actually observed authorized edges. Missing or false-authorized edges remain absent.',
        'failure_policy':'Keep every failed attempt and its cost; never turn model false into true or replace missing observed edges by a hand-authored library.',
        'quality_policy':'Technical verification plus independent scientific and visual review; tool success alone is not scientific acceptance.',
        'cost_policy':'Shared original CNY100 ledger includes v1/v2/v3/v3.1 development/training/failed attempts; estimates are not provider invoices.',
        'cache_policy':'Natural provider cache; report hit/miss. Main workers=1, no cache clearing.',
        'counter_policy':'DSH tool-call attempts include success and refusal; successful MCP executions and failure kinds are separate. Motif-generated commands are included in attempts.',
        'dataset_manifest_sha256':sha(output/'data/dataset_manifest.json'),
        'training_matrix_sha256':sha(output/'training-matrix.json'),
        'evaluation_matrix_sha256':sha(output/'evaluation-matrix.json'),
        'v3_runtime_sha256':runtime_hashes,'v31_preparation_sha256':preparation_hashes}
    save(output/'preregistration.json',protocol)
    save(output/'source-hashes.json',{'runtime':runtime_hashes,'preparation':preparation_hashes,
                                    'policy':policy_meta,'dataset_manifest_sha256':protocol['dataset_manifest_sha256']})
    return {'output':str(output),'experiment_id':experiment_id,'cases':7,'training_runs':3,'evaluation_runs':16,
            'seed_offset':seed_offset,'policy_sha256':policy_sha,'api_calls':0}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seed-offset',type=int,default=2000000)
    p.add_argument('--experiment-id',default=EXPERIMENT_ID)
    args=p.parse_args()
    print(json.dumps(prepare(args.output,args.seed_offset,args.experiment_id),ensure_ascii=False))
