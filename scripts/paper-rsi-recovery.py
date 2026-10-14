"""Second frozen condition: learned query envelopes + completed frontier guards.

Same ten paper variants, not ten new independent tasks. Shadow only, no execute.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.file_lock import exclusive_lock
spec=importlib.util.spec_from_file_location('recovery_night',ROOT/'scripts/paper-rsi-overnight.py')
n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
from src.adapters.paper_query_recovery import compile_recovery_queries,validate_queries
r=n.rsi
PREVIOUS=n.EXP
EXP=ROOT/'.local/paper-reference/paper-rsi-overnight-20261011-v2'
n.EXP=EXP


def setup():
    EXP.mkdir(parents=True,exist_ok=True,mode=0o700)
    inputs=json.loads((PREVIOUS/'inputs.json').read_text())
    if not (EXP/'inputs.json').exists():r.save(EXP/'inputs.json',inputs)
    query=EXP/'query-library.json'
    if not query.exists():
        lib=compile_recovery_queries([PREVIOUS/'runs'/('baseline-'+c) for c in n.TASKS[:3]])
        validate_queries(lib)
        if not lib['prototypes']:raise ValueError('no normally witnessed query envelopes; no invented recovery route')
        r.save(query,lib)
    else:lib=json.loads(query.read_text());validate_queries(lib)
    budget=r.load_budget_record(PREVIOUS/'authorized-budget.json')
    r.ARXIV_BATCH=r.BOUNDED_EVIDENCE=r.FLOW_DELIVERY=r.FORMAL_METADATA=True
    r.QUERY_RECOVERY_LIBRARY=query;r.TRACK_COMPLETED_FRONTIER=True
    return inputs,budget,query


def run(case,mode,lib=None):
    inputs,budget,query=setup();r.DELIVERY_CHECK='off' if mode=='baseline' else 'shadow';r.FLOW_SHADOW_LIBRARY=lib
    if mode=='shadow' and lib is None:raise ValueError('frozen flow library required')
    if ROOT!=Path('/root/autodl-tmp/jjy') or not r.os.environ.get('DEEPSEEK_API_KEY'):raise ValueError('real server API required')
    with exclusive_lock((ROOT/'.local/paper-motif/.budget.lock')) as lock:
        m=r.run(EXP,inputs,case,mode,budget,mode+'-'+case)
    if m['status']!='completed' or not m['delivery_check_passed']:raise ValueError('preserve failed run for diagnosis')
    if mode=='shadow':n.score(EXP/'runs'/('shadow-'+case))
    return m


def compile_library():
    runs=[EXP/'runs'/('baseline-'+c) for c in n.TASKS[:3]]
    lib=n.compile_flow_shadow(runs);path=EXP/'libraries/v01/library.json'
    if path.exists():raise ValueError('preserve frozen flow library')
    r.save(path,lib);return path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--phase',choices=['preview','setup','baseline','compile','shadow','score'],default='preview')
    ap.add_argument('--case',choices=n.TASKS);ap.add_argument('--call-model',action='store_true');a=ap.parse_args()
    if a.phase=='preview':
        _,prior,_=r.reference.budget.account(EXP)
        print(json.dumps({'cumulative_cap_usd':8,'cumulative_estimated_usd':prior,'paid_enabled':False,'condition':'query recovery + frontier; same-paper repeat validation'}));return
    if a.phase=='setup':
        inputs,budget,query=setup();lib=json.loads(query.read_text());print(json.dumps({'query_protocols':len(lib['prototypes']),'query_digest':lib['manifest_digest'],'training_runs':3}));return
    if a.phase=='compile':print(str(compile_library().relative_to(ROOT)));return
    if not a.case:raise ValueError('case required')
    if a.phase=='score':print(json.dumps(n.score(EXP/'runs'/('shadow-'+a.case))));return
    if not a.call_model:raise ValueError('explicit model call required')
    print(json.dumps(run(a.case,a.phase,EXP/'libraries/v01/library.json' if a.phase=='shadow' else None)))


if __name__=='__main__':main()
