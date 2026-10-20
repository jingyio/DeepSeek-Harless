"""Current-goal primitive certification, synthetic diagnostics (no model)."""
import copy
import pytest
from src.adapters.evidence_report import structure_issues
from src.adapters.negative_constraint_compiler import certify_current_constraint,shape_issues

def fixture_guard():
    observations=[];failures=[];successes=[]
    for i,count in enumerate([2,3]):
        goal={'title':'approved','note':'keep','rows':['entry']*count}
        args={**goal,'rows':['changed']}
        row={'tool':'mcp__test__export','task_id':str(i),'call_id':'failed','events_sha256':'a'*64,
             'goal':goal,'arguments':args,'result':{'exported':False,'failed_checks':['shape_mismatch'],
                'scope_issues':structure_issues(goal,args),'argument_issues':[{'check':'shape_mismatch'}]}}
        observations.append(row);failures.append({k:row[k] for k in ['task_id','call_id','events_sha256']})
        valid={**row,'call_id':'success','arguments':goal,'result':{'exported':True}}
        observations.append(valid);successes.append({k:valid[k] for k in ['task_id','call_id','events_sha256']})
    rule={'tool':'mcp__test__export','failure_code':'shape_mismatch','certification':{'failures':failures,'success_contrasts':successes}}
    return certify_current_constraint(rule,observations,structure_issues)

def test_current_goal_condition_is_certified_without_historical_counts_or_report_contents():
    guard=fixture_guard()
    assert len(guard['certification']['interventions'])==2
    assert all(x['repair_passed'] and x['reintroduction_failed'] for x in guard['certification']['interventions'])
    assert 'approved' not in str(guard) and 'expected_items' not in str(guard)
    assert shape_issues({'rows':['new']*7},{'rows':['current']*7})==[]
    assert shape_issues({'rows':['new']*7},{'rows':['current']*6})[0]['expected_items']==7

def test_unknown_numeric_shape_and_wrong_validator_cannot_be_certified():
    with pytest.raises(ValueError):shape_issues({'count':1},{'count':1.0})
    with pytest.raises(ValueError):certify_current_constraint({'tool':'x','certification':{'failures':[],'success_contrasts':[]}},[],lambda a,b:[])
