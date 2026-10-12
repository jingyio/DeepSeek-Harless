"""Freeze an explicit v2.2 repair experiment before paid evaluation.

Controlled arms use a shared, reviewed specification, not free semantic output.
The plans reuse historical real-LLM decisions, with disclosed presentation
normalization. Commentary is a reviewer-written cautious template, not an LLM
quality score. Natural-request arms remain separate. No tool order is frozen.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.research_report_agent_v2.generate_cases import generate


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--historical', type=Path, required=True)
    args = parser.parse_args()
    exp = args.experiment.resolve()
    if exp.exists():
        raise ValueError('Use a new experiment directory; never overwrite evidence')
    exp.mkdir(parents=True)
    generate(exp / 'data_training', seed_offset=300000, final_training=True)
    generate(exp / 'data_natural', seed_offset=300000)
    generate(exp / 'data_matched', seed_offset=300000)
    cases = ['auto', 'outline', 'brief', 'technical']
    protocol = {'version': 'v2.2', 'hypothesis': 'Shared tools avoid layout retry loops; observed motifs remove only intermediate real LLM requests.',
                'data': 'Synthetic fresh seeds; actual DSH/Flash/MCP/Python/figures/PDF.',
                'controlled_scope': 'Fixed semantic specification; measures orchestration, not autonomous scientific judgment.',
                'natural_scope': 'Same original technical request in both arms, without fixed decisions; outputs may differ.',
                'acceptance': 'Identical checks in both arms; retain failures/costs and mark unequal pairs rather than selecting reruns.',
                'controlled_cases': []}
    for name in cases:
        case = 'v2_eval_' + name
        source_run = 'v21_eval_' + name + '_baseline_r1'
        files = sorted((args.historical / 'runs' / source_run / 'workspace/records').glob('rra-analysis_plan-*.json'))
        if len(files) != 1:
            raise ValueError('Historical specification must have exactly one successful plan: ' + source_run)
        original = json.loads(files[0].read_text(encoding='utf-8'))['payload']['workflow']
        plan = {k: copy.deepcopy(original[k]) for k in ('analysis', 'figures', 'report', 'interpretation_mode', 'custom_focus', 'allow_deterministic_continuation')}
        plan['analysis'].pop('allow_deterministic_continuation', None)
        folder = exp / 'data_matched/cases' / case
        study = json.loads((folder / 'study.json').read_text(encoding='utf-8'))
        plan['analysis']['design_evidence'] = {'source': 'study_description', 'quote': study['description']}
        # Keep default scientific plot titles. A slope/mean difference CI is not
        # silently labelled as a standardized effect-size interval.
        for figure in plan['figures']:
            figure['title'] = ''
        if name == 'auto':
            plan['interpretation_mode'] = 'standard'
            plan['report']['style'] = 'technical'
        fixed = {'plan': plan}
        if name == 'technical':
            fixed['commentary'] = {
                'paragraphs': [
                    '本次温度斜率估计为{{estimate}}，{{confidence_pct}}%置信区间为[{{ci_low}}, {{ci_high}}]，双侧p={{p_value}}。这些结果描述当前观测数据中的线性关联，不能单独证明温度的因果作用。',
                    '残差的Shapiro-Wilk检验W={{shapiro_w}}、p={{shapiro_p}}，残差标准差为{{residual_sd}}。检验结果不能证明所有假设成立，也不能确定残差偏离的来源；应结合残差图、采样记录与测量过程判断。',
                    '下一轮设计应先明确目标是提高现有范围内斜率的估计精度，还是检验不同地点和时段是否保持类似关联。下列方案是待验证的设计建议，其收益尚未通过本次合成数据之外的新实验检验。'],
                'research_options': [
                    {'name': '温度范围内的分层补样',
                     'rationale': '针对当前斜率估计及其置信区间，可在已有温度范围内安排覆盖更均衡的独立样本，并保留重复测量以评估测量误差；实际精度收益取决于解释变量分布和噪声。',
                     'tradeoff': '补样需要现场资源与一致测量条件。重复观测的相关性必须在设计和分析中处理，不能将同一样本的重复测量冒充独立样本。'},
                    {'name': '不同地点与时段的独立验证',
                     'rationale': '为判断当前关联能否推广，可在预先确定的新地点和时段采样，同时记录可能的混杂因素，再比较关联估计及不确定性。',
                     'tradeoff': '跨环境验证会引入更多异质性；不能保证加入变量或扩大样本就改善残差正态性，且需要另行制定适合重复或分层数据的模型。'}],
                'comparison_summary': '若目标是在当前观测范围内提高估计精度，可优先评估分层补样；若目标是推广到其他环境，则独立验证更直接。两者可互补，但选择应结合预算、采样独立性和科学目标，本报告不能据此承诺因果识别。',
                'allow_deterministic_continuation': True}
        fixed.update(protocol_version=1, decision_sha256=digest(fixed),
                     provenance={'historical_plan_run': source_run, 'historical_plan_sha256': hashlib.sha256(files[0].read_bytes()).hexdigest(),
                                 'edits': 'Exact supplied design quote; default figure titles; auto uses standard technical report; technical custom prose is reviewer-written and frozen.'},
                     instruction='受控执行对照：请从实际输入核实方案；真实提交以下plan和commentary，勿自由改写。若方案与数据有冲突，请说明冲突并停止，不能绕过工具校验。')
        study['benchmark_frozen_decisions'] = fixed
        note = '\n\n本次属于控制方案和正文的执行对照。研究说明中的 benchmark_frozen_decisions 给出共同的展示方案与可选讨论模板；请读取并核实后原样提交，数值只能使用当前数据真实计算的结果。不需再次自由选择章节或改写这份共同模板。'
        task = (folder / 'task.txt').read_text(encoding='utf-8').strip() + note
        study['user_request'] = task
        save(folder / 'study.json', study)
        (folder / 'task.txt').write_text(task + '\n', encoding='utf-8')
        protocol['controlled_cases'].append({'case': case, 'decision_sha256': fixed['decision_sha256'], 'source': fixed['provenance']})
    train = [{'name': 'v22_train_materials', 'case': 'v2_final_train_materials'},
             {'name': 'v22_train_ml', 'case': 'v2_final_train_ml'},
             {'name': 'v22_cert_environment', 'case': 'v2_final_cert_environment'}]
    library = str(exp / 'library.json')
    evaluation = []
    for i, case in enumerate(cases):
        for mode in (('baseline', 'execute') if i % 2 == 0 else ('execute', 'baseline')):
            job = {'name': f'v22_matched_{case}_{mode}', 'case': 'v2_eval_' + case, 'mode': mode}
            if mode == 'execute':
                job['library'] = library
            evaluation.append(job)
    natural = [{'name': 'v22_natural_technical_' + mode, 'case': 'v2_eval_technical', 'mode': mode,
                **({'library': library} if mode == 'execute' else {})} for mode in ('baseline', 'execute')]
    save(exp / 'protocol.json', protocol)
    save(exp / 'training.json', train)
    save(exp / 'evaluation.json', evaluation)
    save(exp / 'natural.json', natural)
    print(json.dumps({'experiment': str(exp), 'training': len(train), 'matched': len(evaluation), 'natural': len(natural)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
