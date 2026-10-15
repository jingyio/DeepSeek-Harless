"""Cost ledger boundaries and goal diagnostics cannot consume or modify final learning data."""
import importlib.util
import json
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]/'scenarios/file-management'


def module(monkeypatch,name):
    monkeypatch.syspath_prepend(str(HERE))
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));value=importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules,name,value);spec.loader.exec_module(value)
    return value


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))


def test_goal_rewrite_changes_objective_without_rule_permission_or_oracle(monkeypatch,tmp_path):
    m=module(monkeypatch,'fallback_rsi');td=tmp_path/'template';td.mkdir()
    original={'objective':'old','workflow_contract':{'source_paths':['a'],'allowed_reads':['rules']},'initial_snapshot':{'a':'hash'},'allowed_operations':['copy'],'workflow_oracle_sha256':'old-sha'}
    write(td/'input-template.json',original);(td/'prompt.md').write_text('original task')
    t={'task_dir':str(td)};m.rewrite_goal(t,'new independently phrased objective')
    changed=json.loads((td/'input-template.json').read_text())
    assert {k:v for k,v in changed.items() if k!='objective'}=={k:v for k,v in original.items() if k!='objective'}
    assert changed['objective'] in (td/'prompt.md').read_text()


def test_old_learning_cost_reads_only_nonholdout_outcomes(monkeypatch,tmp_path):
    m=module(monkeypatch,'continual_rsi');out=tmp_path/'ordinary/attempts/one/outcome.json'
    write(out,{'role':'explore','run':{'budget_accounted_usd':0.25}})
    write(tmp_path/'exploration-1-materials.json',{'tasks':[{'task_dir':str(tmp_path/'ordinary')}]})
    (tmp_path/'final-materials.json').write_text('must not be opened: invalid JSON')
    write(tmp_path/'final/attempts/one/outcome.json',{'role':'holdout','run':{'budget_accounted_usd':900}})
    result=m.old_learning_cost(tmp_path,{})
    assert result['cost_usd']==0.25 and list(result['outcomes'])==[str(out)]


def test_failed_learning_and_common_diagnostics_are_charged_in_full_cost(monkeypatch,tmp_path):
    m=module(monkeypatch,'continual_rsi')
    write(tmp_path/'seed-lock.json',{'historical_seed_cost_usd':1,'prior_upgrade_build_cost_usd':2,'fresh_seed_cost_usd':3})
    def outcome(arm,role,cost,passed):
        return {'task_id':arm+role,'arm':arm,'role':role,'condition':'normal','acceptance':{'passed':passed},'acceptance_repairs':2 if not passed else 0,'run':{'budget_accounted_usd':cost,'upstream_requests':10}}
    write(tmp_path/'tasks/F-observe/attempts/a/outcome.json',outcome('F','observe',0.3,True))
    write(tmp_path/'tasks/R-observe/attempts/a/outcome.json',outcome('R','observe',0.1,True))
    write(tmp_path/'tasks/H-explore/attempts/a/outcome.json',outcome('H','explore',0.5,False))
    p={'seeds':[],'diagnostic_cost_sources':[{'cost_usd':0.2}]}
    report=m.summarize(tmp_path,p)
    assert abs(report['arms']['F']['full_api_cost_usd']-6.5)<1e-8
    assert abs(report['arms']['R']['full_api_cost_usd']-6.8)<1e-8
    assert report['arms']['R']['new_learning_certification_failures_cost_usd']==0.5
    assert not report['observed_net_API_benefit'] and not report['equal_delivery_quality_F_R']
