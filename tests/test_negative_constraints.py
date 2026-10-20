"""Current-goal primitive certification, synthetic diagnostics (no model)."""
import copy
import pytest
from src.adapters.evidence_report import structure_issues
from src.adapters.negative_constraint_compiler import certify_current_constraint,shape_issues,recertify_current_constraints
from src.adapters.script_negative_compiler import digest

def fixture_observations():
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
    rule={'tool':'mcp__test__export','failure_code':'shape_mismatch','failure_source':'failed_checks',
          'certification':{'failures':failures,'success_contrasts':successes}}
    return rule,observations

def fixture_guard():
    rule,observations=fixture_observations()
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


def test_recertification_retains_only_current_certified_conditions_and_preserves_old_provenance():
    rule,observations=fixture_observations();rule['id']='old-shape'
    unsupported={**rule,'id':'old-page','failure_code':'page_limit'}
    library={'rules':[rule,unsupported],'implementation_locks':{'validator.py':'a'*64},'digest':'old'}
    history=[{'task_id':'old','events_sha256':'b'*64,'implementation_locks':{'validator.py':'c'*64}}]
    original=copy.deepcopy(library)
    result=recertify_current_constraints(library,observations,structure_issues,'validator.py:check',history)
    assert library==original
    assert len(result['rules'])==1 and result['rules'][0]['retry_policy']=='warn_then_current_constraint'
    assert result['rules'][0]['argument_guard']['validator_sha256']=='a'*64
    assert result['recertification']['historical_sources']==history
    assert result['recertification']['dropped_rules'][0]['rule_id']=='old-page'
    assert result['digest']==digest({k:v for k,v in result.items() if k!='digest'})


@pytest.mark.parametrize('failure', ['no_success', 'single_failure', 'wrong_predicate', 'wrong_receipt', 'opaque_failure'])
def test_recertification_rejects_missing_or_disagreeing_witnesses(failure):
    rule,observations=fixture_observations();rule['id']='old'
    validator=structure_issues
    if failure=='no_success':observations=[r for r in observations if r['call_id']!='success']
    if failure=='single_failure':observations=[r for r in observations if r['task_id']=='0']
    if failure=='wrong_predicate':validator=lambda a,b:[]
    if failure=='wrong_receipt':
        for row in observations:row['result']['scope_issues']=[]
    if failure=='opaque_failure':rule['failure_source']='opaque'
    library={'rules':[rule],'implementation_locks':{'validator.py':'a'*64}}
    with pytest.raises(ValueError,match='no_current_constraints_recertified'):
        recertify_current_constraints(library,observations,validator,'validator.py:check',[{'task_id':'old'}])


def test_recertification_requires_explicit_locked_validator_and_history():
    library={'implementation_locks':{},'rules':[]}
    with pytest.raises(ValueError,match='validator_and_history_required'):
        recertify_current_constraints(library,[],structure_issues,'validator.py:check',[])
