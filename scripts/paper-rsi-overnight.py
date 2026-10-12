"""Server-only, cumulative-budget, prequential paper shadow experiment.

Ten tasks are variants of ONE private paper. No execution arm. Defaults preview.
Baselines alone train the frozen library; new tasks are scored before inclusion.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.file_lock import exclusive_lock
import importlib.util
spec=importlib.util.spec_from_file_location('overnight_citation',ROOT/'scripts/paper-citation-rsi.py')
rsi=importlib.util.module_from_spec(spec);spec.loader.exec_module(rsi)
from src.adapters.paper_flow_shadow_compiler import compile_flow_shadow,steps
from src.adapters.paper_bibliography import bib_records

EXPERIMENT='paper-rsi-overnight-20261011-v1'
EXP=ROOT/'.local/paper-reference'/EXPERIMENT
TASKS=['t01_main','t02_abstract','t03_subset_a','t04_missing','t05_duplicate',
       't06_wrong_id','t07_wrong_year','t08_wrong_doi','t09_subset_b','t10_incremental']


def prepare():
    if (EXP/'inputs.json').exists():return json.loads((EXP/'inputs.json').read_text())
    diag=rsi.checks.source_diagnostics(rsi.ORIGIN,'main.tex',None)
    allrows=[]
    for p in sorted(rsi.ORIGIN.rglob('*.bib')):
        allrows += [{**r,'file':str(p.relative_to(rsi.ORIGIN))} for r in bib_records(p.read_text())]
    active=[r for r in allrows if r['key'] in diag['cited_keys'] and re.search(r'\d{4}\.\d{4,5}',r['raw'])]
    unique={r['key']:r for r in active};keys=list(unique)
    if len(keys)<10:raise ValueError('expected real paper preprint scope missing')
    inputs={};definitions=[]
    for i,case in enumerate(TASKS):
        base=EXP/'cases'/case;source=base/'source';shutil.copytree(rsi.ORIGIN,source)
        main='extended_abstract.tex' if i==1 else 'main.tex'
        kind='original_active_manuscript' if i==0 else 'same_paper_abstract' if i==1 else 'same_paper_diagnostic_variant'
        mutation=[]
        if i in [2,3,4,5,6,7,8,9]:
            chosen=keys[-5:] if i==8 else keys[:5]
            if i==9:chosen=list(dict.fromkeys(chosen+keys[5:8]));kind='same_paper_incremental_scope'
            bibs=diag['active_bibliography_files'] if 'active_bibliography_files' in diag else list(dict.fromkeys(r['file'][:-4] for r in active))
            # Use the actual registered bibliography file, no model-selected paths.
            main='task.tex';text='\\documentclass{article}\n\\begin{document}\n\\cite{'+','.join(chosen)+'}\n\\bibliography{'+','.join(bibs)+'}\n\\end{document}\n'
            if i==3:text=text.replace('\\end{document}','\\cite{rsi_missing_diagnostic}\n\\end{document}');mutation.append('added_missing_citation_key')
            (source/main).write_text(text)
            if i in [4,5,6,7]:
                record=unique[chosen[0]];bib=source/record['file'];original=bib.read_text();raw=record['raw'];new=raw
                if i==4:bib.write_text(original+'\n'+raw+'\n');mutation.append('duplicate_active_bib_entry')
                else:
                    if i==5:
                        old=re.search(r'\d{4}\.\d{4,5}',raw).group();other=re.search(r'\d{4}\.\d{4,5}',unique[keys[-1]]['raw']).group()
                        new=raw.replace(old,other);mutation.append('arxiv_identifier_of_different_existing_bib_work')
                    elif i==6:
                        new=re.sub(r'(\byear\s*=\s*[{\"]?)\d{4}',r'\g<1>1990',raw,flags=re.I)
                        if new==raw:new=raw[:-1]+',year={1990}\n}'
                        mutation.append('deliberately_wrong_bibliography_year')
                    else:
                        # Known malformed diagnostic value, never asserted as a real DOI.
                        new=re.sub(r'\bdoi\s*=\s*\{[^}]*\}\s*,?','',raw,flags=re.I)
                        new=new[:-1]+',doi={10.0000/rsi-deliberately-invalid}\n}'
                        mutation.append('injected_invalid_doi_not_a_real_bibliographic_claim')
                    bib.write_text(original.replace(raw,new,1))
            if i in [2,8]:kind='same_paper_subset'
        inputs[case]={'root':str(base),'source_dir':'source','main':main}
        definitions.append({'case':case,'type':kind,'mutation':mutation,'main':main,
            'source_version':rsi.checks.PaperEvidence({case:inputs[case]},ROOT/'.local').version(case)})
        for p in base.rglob('*'):p.chmod(0o700 if p.is_dir() else 0o600)
    rsi.save(EXP/'inputs.json',inputs);rsi.save(EXP/'task-definitions.json',definitions)
    return inputs


def score(run):
    c=json.loads((run/'manifest.json').read_text());rows=steps(run)
    lines=run/'work/.local/flow-shadow.jsonl'
    predictions=[json.loads(s) for s in lines.read_text().split('\n') if s.strip()] if lines.exists() else []
    live=[p for p in predictions if p['kind'] in ['flow_shadow_prediction','flow_shadow_deferred']]
    if len(live)!=len(rows) or [p['request_ordinal'] for p in live]!=list(range(1,len(rows)+1)):
        raise ValueError('live before-request audit boundary missing; cannot count predictions')
    outcomes=[]
    for p,row in zip(live,rows):
        outcome='no_prediction'
        if p['kind']=='flow_shadow_prediction':
            actual=sorted([{'tool':t['name'],'arguments':t['arguments']} for t in row['calls']],key=lambda t:t['tool'])
            expected=sorted(p['expected_tools'],key=lambda t:t['tool'])
            if actual!=expected:outcome='different_next_operation'
            elif any(not t['ok'] or not isinstance(t['output'],dict) or
                     t['output'].get('version_sha256',t['output'].get('source_version'))!=c['input_version'] for t in row['calls']):outcome='result_failed_or_version_changed'
            elif p.get('snapshot_sha256') and any(t['output'].get('report_sha256')!=p['snapshot_sha256'] for t in row['calls']):outcome='artifact_changed'
            elif any(b.get('type')!='tool-call' and not(b.get('type')=='text' and not b.get('text','').strip()) for b in row['content']):outcome='local_tools_match_text_requires_review'
            else:outcome='strict_whole_request'
        outcomes.append({'request':row['ordinal'],'motif_id':p.get('motif_id'),'support':p.get('training_session_count'),
            'reason':p.get('reason'),'outcome':outcome,'actual_tools':[t['name'] for t in row['calls']]})
    result={'run':run.name,'library_digest':c['flow_shadow_library_digest'],'actual_requests':len(rows),
        'predictions':sum(p['kind']=='flow_shadow_prediction' for p in live),
        'strict_whole_requests':sum(o['outcome']=='strict_whole_request' for o in outcomes),
        'actual_model_skips':0,'outcomes':outcomes}
    result['strict_ratio']=result['strict_whole_requests']/len(rows)
    rsi.save(run/'flow-shadow-score.json',result);return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--phase',choices=['preview','prepare','baseline','compile','shadow','score'],default='preview')
    ap.add_argument('--case',choices=TASKS);ap.add_argument('--library',type=Path);ap.add_argument('--version',default='v01');ap.add_argument('--call-model',action='store_true');a=ap.parse_args()
    EXP.mkdir(parents=True,exist_ok=True,mode=0o700)
    budget=rsi.load_budget_record(EXP/'authorized-budget.json');_,prior,_=rsi.reference.budget.account(EXP)
    if a.phase=='preview':print(json.dumps({'cap_usd':budget['cap_usd'],'cumulative_estimated_usd':prior,'remaining_upper_usd':budget['cap_usd']-prior,'tasks':TASKS,'paid_enabled':False}));return
    inputs=prepare()
    if a.phase=='prepare':print(json.dumps({'prepared':len(inputs),'independent_papers':1}));return
    if a.phase=='compile':
        if not re.fullmatch(r'v\d{2}',a.version):raise ValueError('version required')
        target=EXP/'libraries'/a.version/'library.json'
        if target.exists():raise ValueError('preserve frozen library')
        runs=[EXP/'runs'/('baseline-'+c) for c in TASKS if (EXP/'runs'/('baseline-'+c)/'metrics.json').exists()]
        valid=[r for r in runs if json.loads((r/'metrics.json').read_text()).get('delivery_check_passed')]
        lib=compile_flow_shadow(valid);rsi.save(target,lib)
        print(json.dumps({'library':str(target.relative_to(ROOT)),'digest':lib['manifest_digest'],'motifs':len(lib['motifs']),'training_runs':len(valid)}));return
    if not a.case:raise ValueError('case required')
    if a.phase=='score':print(json.dumps(score(EXP/'runs'/('shadow-'+a.case))));return
    if ROOT!=Path('/root/autodl-tmp/jjy') or not a.call_model or not rsi.os.environ.get('DEEPSEEK_API_KEY'):raise ValueError('explicit real server run required')
    rsi.ARXIV_BATCH=rsi.BOUNDED_EVIDENCE=rsi.FLOW_DELIVERY=rsi.FORMAL_METADATA=True
    rsi.DELIVERY_CHECK='off' if a.phase=='baseline' else 'shadow'
    if a.phase=='shadow':
        if not a.library or not a.library.resolve().is_relative_to((EXP/'libraries').resolve()):raise ValueError('frozen private library required')
        rsi.FLOW_SHADOW_LIBRARY=a.library
    with exclusive_lock((ROOT/'.local/paper-motif/.budget.lock')) as lock:
        result=rsi.run(EXP,inputs,a.case,'baseline' if a.phase=='baseline' else 'shadow',budget,a.phase+'-'+a.case)
    if result['status']!='completed' or not result['delivery_check_passed']:raise ValueError('preserve failed run; diagnose before proceeding')
    if a.phase=='shadow':print(json.dumps(score(EXP/'runs'/('shadow-'+a.case))))


if __name__=='__main__':main()
