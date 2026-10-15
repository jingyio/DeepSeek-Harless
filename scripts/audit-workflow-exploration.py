"""Read-only cost/source/byte audit and scalar graph observation; certifies no Motif."""
from __future__ import annotations
import argparse,importlib.util,json,sys,shutil
from collections import defaultdict,Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'));sys.path.insert(0,str(ROOT))
from common import digest,sha,save,snapshot
from experiment import accounting
from src.adapters.file_job_budget import job_command
sp=importlib.util.spec_from_file_location('workflow_original_graph_observer',ROOT/'scenarios/file-management/learn.py');observer=importlib.util.module_from_spec(sp);sp.loader.exec_module(observer)

def frozen_verifier(exp,p):
    """Run the archived verifier/version functions; keep real private-data boundaries.

    This is an offline audit process only. It never constructs a scene, job or provider.
    """
    frozen=exp/'frozen-source';here=frozen/'scenarios/file-management';modules={}
    for name in ('common','file_tools','collection_tools','report_tools','task_contract','task_tools','plan_tools','workflow_contract','workflow_tools','recovery_tools'):
        s=importlib.util.spec_from_file_location(name,here/(name+'.py'));m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);modules[name]=m
        if name=='common':m.ROOT=ROOT;m.DATA=ROOT/'testpdf/file-management-experiment'
        # These modules' version functions hash ROOT-relative archived source.
        # Their scene constructors are not used by this audit.
        if name in ('plan_tools','recovery_tools'):m.ROOT=frozen
    assert modules['workflow_tools'].workflow_version()==p['versions']['workflow'],'archived workflow version differs'
    assert modules['recovery_tools'].recovery_version()==p['versions']['recovery'],'archived recovery version differs'
    return modules['workflow_contract'].verify_workflow

def audit(exp):
    p=json.loads((exp/'protocol.json').read_text());graphs=[];rows=[];tokens=Counter();missing_usage=0;candidate_tasks=defaultdict(set);candidate_workflows=defaultdict(set)
    for name,h in p['source_code'].items():assert sha(exp/'frozen-source'/name)==h,name
    verify=frozen_verifier(exp,p)
    for name,h in p['original_pdfs'].items():assert sha(ROOT/'testpdf'/name)==h,'original PDF changed'
    parent=json.loads((Path(p['parent'])/'protocol.json').read_text())
    for t in parent['tasks']:
        saved=p['parent_protected'][t['task_id']]
        assert digest(snapshot(t['pristine']))==saved['snapshot_sha256'],t['task_id']
        assert sha(Path(t['task_dir'])/'input-template.json')==saved['template_sha256'],t['task_id']
        assert sha(Path(t['task_dir'])/'oracle.json')==t['oracle_sha256'],t['task_id']
    for c in p['tasks']:
        td=Path(c['task_dir']);assert sha(td/'input-template.json')==c['input_template_sha256'];assert sha(td/'oracle.json')==c['oracle_sha256']
        assert digest(snapshot(c['pristine']))==c['snapshot_sha256']
        matches=list(td.glob('attempts/*/outcome.json'));assert len(matches)==1,(c['task_id'],len(matches))
        out=json.loads(matches[0].read_text());attempt=Path(out['attempt']);spec=json.loads((attempt/'input.json').read_text())
        assert digest(spec)==out['input_sha256'];assert out['source_sha256']==digest(p['source_code'])
        assert out['accounting_complete'] and out['normal_harness_only'] and not out['learning_performed']
        reportpath=attempt/'delivery/report.json';report=json.loads(reportpath.read_text()) if reportpath.exists() else None
        review=verify(spec,report if out['receipt_verified'] else None,attempt/'delivery')
        assert review['passed']==out['acceptance']['passed'],c['task_id']
        actual_requests=0;estimated=0;all_ledger=[];schema=json.loads((attempt/'tool-schemas.json').read_text())
        config=json.loads((attempt/'config.json').read_text());assert digest(schema)==config['schemas_sha256']
        assert config['mode']=='baseline' and not config['motif_enabled'] and config['budget_usd']==p['per_task_cap_usd']
        for r in out['runs']:
            run=Path(r['output_dir']);raw=json.loads((run/'metrics.json').read_text());assert raw['upstream_requests']==r['upstream_requests']
            assert all(raw.get(k,0)==0 for k in ('model_requests_skipped_verified','collection_model_requests_bypassed_verified','plan_model_requests_bypassed_verified','reentry_epoch_batches_verified'))
            ledger=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()];paid=[x for x in ledger if 'request_id' in x and 'response_status' in x]
            assert len(paid)==r['upstream_requests'],(c['task_id'],'HTTP count')
            cost=sum(x['observed_peak_usd'] if x.get('observed_peak_usd') is not None else x['reserved_upper_usd'] for x in paid)
            assert abs(cost-r['budget_accounted_usd'])<1e-6,(c['task_id'],'fee')
            actual_requests+=len(paid);estimated+=cost;all_ledger.extend(paid)
            for x in paid:
                usage=x.get('response_usage',{})
                if not set(('prompt_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens','completion_tokens','total_tokens'))<=set(usage):missing_usage+=1;continue
                for key in ('prompt_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens','completion_tokens','total_tokens'):tokens[key]+=usage.get(key,0)
            eventfile=run/'agent-events.jsonl';events=[json.loads(l) for l in eventfile.read_text().splitlines()]
            if r is out['runs'][-1]:assert sha(eventfile)==out['events_sha256']
            g=observer.graph(events,run.name,c['workflow_id']);g.update(task_id=c['task_id'],workflow_id=c['workflow_id'],schema_sha256=digest(schema),
                task_acceptance_passed=review['passed'],segment_status=r['status'],successful_normal_observation=bool(review['passed'] and r['status']=='done'),
                source_sha256=out['source_sha256'],execution_version_sha256=p['versions']['recovery' if c['workflow_id']=='FM38' else 'workflow'],
                role='explore',arm='H',events_sha256=sha(eventfile),certified=False)
            byid={n['call_id']:n for n in g['nodes']}
            for n in g['nodes']:
                n['runtime_generated']=n['call_id'].startswith('sss-');n['producer']='certified_runtime' if n['runtime_generated'] else 'normal_harness'
                if n['tool'].removeprefix('mcp__file_management__') in ('select_files','collect_reads','preview_actions','authorize_plan'):n['effectful']=False
            if g['successful_normal_observation']:
                for edge in g['edges']:
                    if edge['kind']!='observed_parameter':continue
                    a,b=byid[edge['from']],byid[edge['to']]
                    if a['runtime_generated'] or b['runtime_generated']:continue
                    key=(a['tool'],edge['field'],b['tool'],edge['argument']);candidate_tasks[key].add(out['input_sha256']);candidate_workflows[key].add(c['workflow_id'])
            graphs.append(g)
        assert actual_requests==out['run']['upstream_requests'];assert abs(estimated-out['run']['budget_accounted_usd'])<1e-6
        assert out['run']['budget_accounted_usd']<=p['per_task_cap_usd']
        if c['workflow_id']=='FM38':
            job=job_command(attempt/'job.json','state')['state'];assert job['requests']==actual_requests;assert abs(job['spent_units']/1e9-out['run']['budget_accounted_usd'])<1e-6
            assert job['repairs']<=p['max_repairs'] and job['checks']<=p['max_repairs']+1
            if len(out['runs'])>1:
                rec=json.loads((attempt/'cold-restart.json').read_text());assert rec['original_job_sha256']==job['task_sha256']
                assert job['requests']>=rec['requests_before'] and job['repairs']>=rec['repairs_before'] and job['spent_units']>=rec['spent_units_before']
        rows.append({'task_id':c['task_id'],'passed':review['passed'],'requests':actual_requests,'estimated_usd':out['run']['budget_accounted_usd'],
                     'segments':len(out['runs']),'tool_errors':out['tool_errors'],'human_semantic_review':False})
    candidates=[{'from_tool':a,'from_field':f,'to_tool':b,'to_param':arg,'independent_task_conditions':len(v),'workflows':sorted(candidate_workflows[(a,f,b,arg)]),
                 'status':'observed_candidate_only','execution_permission':False} for (a,f,b,arg),v in candidate_tasks.items() if len(v)>=2]
    result={'status':'passed','experiment_id':exp.name,'tasks':len(rows),'machine_passed':sum(r['passed'] for r in rows),'machine_failed':sum(not r['passed'] for r in rows),
            'requests':sum(r['requests'] for r in rows),'estimated_usd':sum(r['estimated_usd'] for r in rows),'tokens_from_http':dict(tokens),'http_usage_complete':missing_usage==0,'missing_usage_requests':missing_usage,'rows':rows,
            'graphs':len(graphs),'nodes':sum(len(g['nodes']) for g in graphs),'accepted_normal_segments':sum(g['successful_normal_observation'] for g in graphs),
            'runtime_nodes_excluded_from_learning':sum(n['runtime_generated'] for g in graphs for n in g['nodes']),'candidates':candidates,
            'new_certified_graphs':0,'holdout_runs':0,'all_parent_pristine_and_holdout_unchanged':True,'original_pdfs_unchanged':True,
            'accounting':accounting(),'analysis_source_sha256':sha(__file__),'acceptance_replayed_with_archived_source':True,
            'observer_limitations':'scalar output-to-argument evidence only; nested collections/capability branches require independent compiler witnesses','human_semantic_review':False}
    save(exp/'unified-observed-graphs.json',graphs);save(exp/'independent-audit.json',result)
    analysis=exp/'analysis-source';analysis.mkdir(exist_ok=True,mode=0o700)
    old=analysis/Path(__file__).name
    if old.exists():shutil.copyfile(old,analysis/('audit-workflow-exploration.'+sha(old)+'.py'))
    shutil.copyfile(__file__,old)
    shutil.copyfile(__file__,analysis/('audit-workflow-exploration.'+sha(__file__)+'.py'))
    return result

def pool(experiments):
    """Preserve failures in one observational dataset; separate executable versions.

    No provider call, compiler, certification, library or runtime activation occurs.
    """
    from uuid import uuid4
    destination=ROOT/'.local/file-management'/('workflow-observations-20261014-'+uuid4().hex[:8]);destination.mkdir(mode=0o700)
    audits=[];graphs=[];groups=defaultdict(list)
    for exp in experiments:
        result=audit(exp.resolve());audits.append(result)
        for g in json.loads((exp/'unified-observed-graphs.json').read_text()):
            g['experiment_id']=exp.name;graphs.append(g)
            if g['successful_normal_observation']:groups[(g['execution_version_sha256'],g['schema_sha256'])].append(g['trace_id'])
    save(destination/'graphs.json',graphs)
    result={'dataset':str(destination),'experiments':[e.name for e in experiments],'graphs':len(graphs),'nodes':sum(len(g['nodes']) for g in graphs),
            'accepted_normal_segments':sum(g['successful_normal_observation'] for g in graphs),'failed_segments_retained':sum(not g['task_acceptance_passed'] for g in graphs),
            'requests':sum(a['requests'] for a in audits),'estimated_usd':sum(a['estimated_usd'] for a in audits),
            'tokens_from_http':dict(sum((Counter(a['tokens_from_http']) for a in audits),Counter())),
            'http_usage_complete':all(a['http_usage_complete'] for a in audits),
            'compatible_training_groups':[{'execution_version_sha256':v,'schema_sha256':s,'trace_ids':ids} for (v,s),ids in groups.items()],
            'graphs_sha256':sha(destination/'graphs.json'),'audit_sha256':{e.name:sha(e/'independent-audit.json') for e in experiments},
            'free_mock_and_holdout_included':False,'runtime_generated_nodes':sum(n['runtime_generated'] for g in graphs for n in g['nodes']),
            'learning_performed':False,'new_certification':False,'human_semantic_review':False,'accounting':accounting(),'analysis_source_sha256':sha(__file__)}
    save(destination/'summary.json',result);shutil.copyfile(__file__,destination/'analysis-source.py')
    save(ROOT/'.local/file-management/workflow-observations-current.json',{'dataset':str(destination)})
    return result

if __name__=='__main__':
    a=argparse.ArgumentParser();choice=a.add_mutually_exclusive_group(required=True);choice.add_argument('--experiment',type=Path);choice.add_argument('--pool',nargs='+',type=Path);args=a.parse_args()
    r=pool(args.pool) if args.pool else audit(args.experiment.resolve())
    print(json.dumps({k:v for k,v in r.items() if k not in ('rows','candidates')},ensure_ascii=False))
