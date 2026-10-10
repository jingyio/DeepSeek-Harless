"""Prepare immutable v3 inputs and counterbalanced matrices without any API call."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.research_report_agent_v3.generate_cases import CASES, generate

EXPERIMENT_ID = 'research-report-agent-v3-20261010'


def matrices() -> tuple[list, list]:
    training = [{"name": case['id'] + '_baseline', "case": case['id'], "mode": "baseline",
                 "experiment_role": case['split'], "repeat_id": 1, "matrix_order": index + 1}
                for index, case in enumerate(case for case in CASES if case['split'] != 'evaluation')]
    evaluations = [case for case in CASES if case['split'] == 'evaluation']
    jobs = []
    for repeat in (1, 2):
        for index, case in enumerate(evaluations):
            modes = ('baseline', 'execute') if (index + repeat) % 2 else ('execute', 'baseline')
            for mode in modes:
                jobs.append({"name": f"{case['id']}_r{repeat}_{mode}", "case": case['id'], "mode": mode,
                             "experiment_role": "evaluation", "repeat_id": repeat, "matrix_order": len(jobs) + 1,
                             **({'library': 'library.json'} if mode == 'execute' else {})})
    return training, jobs


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def prepare(output: Path, seed_offset: int = 0, experiment_id: str = EXPERIMENT_ID):
    output = output.resolve()
    if (ROOT / '.local') not in output.parents:
        raise ValueError('Experiment data and evidence must be under repository .local')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Experiment directory must be fresh; old evidence cannot be overwritten')
    output.mkdir(parents=True, exist_ok=True)
    generated = generate(output / 'data', seed_offset)
    training, evaluations = matrices()
    save(output / 'training-matrix.json', training)
    save(output / 'evaluation-matrix.json', evaluations)
    protocol = {
        'experiment_id': experiment_id, 'benchmark_version': 3,
        'comparison_protocol': 'free_presentation_and_narrative',
        'dataset_manifest_sha256': hashlib.sha256((output / 'data/dataset_manifest.json').read_bytes()).hexdigest(),
        'training_cases': [row['case'] for row in training if row['experiment_role'] == 'train'],
        'certification_case': next(row['case'] for row in training if row['experiment_role'] == 'certification'),
        'evaluation_cases': [case['id'] for case in CASES if case['split'] == 'evaluation'],
        'main_runs_denominator': 16, 'repeats_per_case_per_arm': 2, 'independent_evaluation_tasks': 4,
        'planned_workers': 1,
        'sequence': 'Case-parity alternating arm order in repeat 1; reverse each pair in repeat 2.',
        'freshness': 'Each run has a new workspace, session, DSH_HOME and artifacts; source bytes are shared across each paired arm.',
        'cache_policy': 'Provider caching is natural, not cleared. Actual hit/miss usage is reported. No parallel main-experiment runs.',
        'semantic_decisions': ['analysis approval', 'presentation after statistics', 'full prose after figures'],
        'main_fairness': 'Both arms receive identical source bytes, task, schema, model, budgets and output caps. Both independently choose presentation and write narrative. No frozen wording or hidden baseline handicap.',
        'learning': 'Only actual successful baseline transfers observed in >=2 training cases and an independent certification are compiled. Missing edges remain absent. Tool boundaries and permissions are manually designed.',
        'failure_policy': 'Keep every declared evaluation attempt in the denominator. Do not silently replace failures. Implementation changes require a new declared snapshot and separate developmental runs.',
        'quality_policy': 'Tool verification plus independent scientific/narrative/visual review; tool success alone is not final report quality.',
        'cost_policy': 'Report all upstream attempts, tokens by cache status, actual elapsed time, usage completeness, and estimates. Compare accepted delivery cost with all failures accounted for; proxy estimates are not provider-bill proof.',
        'scope': 'Synthetic numeric data; real DSH, DeepSeek Flash, stdio MCP, statistics, plots and PDF tools.',
        'training_matrix_sha256': hashlib.sha256((output / 'training-matrix.json').read_bytes()).hexdigest(),
        'evaluation_matrix_sha256': hashlib.sha256((output / 'evaluation-matrix.json').read_bytes()).hexdigest(),
    }
    save(output / 'preregistration.json', protocol)
    return {'output': str(output), 'cases': len(generated['cases']), 'training_runs': len(training),
            'main_runs': len(evaluations), 'api_calls': 0, 'experiment_id': experiment_id}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed-offset', type=int, default=0)
    parser.add_argument('--experiment-id', default=EXPERIMENT_ID)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output, args.seed_offset, args.experiment_id), ensure_ascii=False))
