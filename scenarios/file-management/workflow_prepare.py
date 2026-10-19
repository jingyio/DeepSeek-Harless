"""Freeze fresh probe/explore/certify/holdout copies and private oracles; no model calls."""
from __future__ import annotations
import argparse,json,shutil,sys
from pathlib import Path
from uuid import uuid4
from common import ROOT,HERE,DATA,PREFIX,digest,sha,save,snapshot
sys.path.insert(0,str(ROOT))
from workflow_tools import TOOLS,workflow_version
from recovery_tools import recovery_version

IDS=('FM01','FM05','FM13','FM17','FM21','FM38')
def put(root,name,text):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8');return name
def cp(root,name,source):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,p);return name

def fixture(root,wid,condition,tag,assets,pdf):
    put(root,'.experiment-copy',tag);put(root,'outside-scope/sentinel.txt','UNSELECTED '+tag)
    source=[];reads=[];contexts=[];mapping={};gaps=[];extra={};ops=[];prefixes=[]
    def five(prefix):
        names=[cp(root,prefix+'reference.docx',assets/'brief.docx'),cp(root,prefix+'table.xlsx',assets/'ledger.xlsx'),
               cp(root,prefix+'image.png',assets/'poster.png'),cp(root,prefix+'paper.pdf',pdf),put(root,prefix+'memo.txt','PROJECT_A '+tag)]
        return names
    if wid=='FM01':
        source=five('inbox/')+[put(root,'inbox/second.txt','PROJECT_B '+tag),put(root,'inbox/empty.txt','  \n')]
        if condition=='E':source += [put(root,'inbox/left/same.txt','PROJECT_A '+tag+' left'),put(root,'inbox/right/same.txt','PROJECT_B '+tag+' right'),put(root,'inbox/ambiguous.txt','PROJECT_A PROJECT_B '+tag),put(root,'inbox/broken.docx','not a ZIP '+tag)]
        contexts=[put(root,'rules/project-routes.txt','Only delivered text containing exactly one of PROJECT_A / PROJECT_B may move. Others, empty and unreadable remain pending. Sort ALL inbox source paths globally; use organized/project-a or project-b/item_<global index, width 2><lowercase suffix>.')]
        for i,n in enumerate(sorted(source),1):
            text=(root/n).read_text() if n.endswith('.txt') else ''
            if ('PROJECT_A' in text)^('PROJECT_B' in text):mapping[n]=f'organized/project-{"a" if "PROJECT_A" in text else "b"}/item_{i:02d}{Path(n).suffix.lower()}'
            else:gaps.append(n)
        ops=['move'];prefixes=['organized/project-a/','organized/project-b/'];reads=contexts+source
    elif wid=='FM05':
        source=five('source-a/')+[put(root,'source-b/memo.txt','DIFFERENT '+tag),cp(root,'source-b/reference.docx',assets/'brief.docx')]
        if condition=='E':source += [put(root,'source-a/nested/same.txt',tag+' left'),put(root,'source-b/nested/same.txt',tag+' right'),cp(root,'source-b/renamed.png',assets/'poster.png')]
        representatives={}
        for n in sorted(source):representatives.setdefault(sha(root/n),n)
        mapping={n:'merged/'+representatives[sha(root/n)] for n in source};ops=['copy'];prefixes=['merged/']
        contexts=[put(root,'rules/merge.txt','Group exact SHA duplicates; output each group once at merged/<lexicographically first FULL source path>. Keep all sources. Different bytes at same relative name must both survive.')];reads=contexts
    elif wid=='FM13':
        source=[put(root,'versions/final.txt','Unreleased draft '+tag),put(root,'versions/v2.txt','Published revision '+tag),put(root,'versions/final-final.txt','Unconfirmed branch '+tag)]
        release={'published_versions':[] if condition=='E' else ['versions/v2.txt'],'basis':'review approval '+tag,'ambiguous':condition=='E'}
        contexts=[put(root,'context/release.txt',json.dumps(release))];reads=contexts+source
        if condition=='E':gaps=['context/release.txt']
        else:mapping={'versions/v2.txt':'selected/v2.txt'}
        ops=['copy'];prefixes=['selected/']
    elif wid=='FM17':
        source=five('source/')
        if condition=='E':source.append(put(root,'source/nested/empty.txt',''))
        mapping={n:'backup-set/'+n[len('source/'):] for n in source};extra['backup_sources']=list(mapping.values())
        ops=['copy'];prefixes=['backup-set/','recovery-drill/']
    elif wid=='FM21':
        source=five('materials/package/')+[put(root,'materials/internal/notes.txt','EXCLUDED '+tag)]
        if condition=='E':source += [put(root,'materials/package/sub/memo.txt','PROJECT_A '+tag+' extra'),put(root,'materials/broken.docx','broken '+tag)];gaps=['materials/package/approval.txt','materials/broken.docx']
        else:source.append(put(root,'materials/package/approval.txt','Approved '+tag))
        contexts=[put(root,'rules/delivery-scope.txt','Deliver materials/package/ only. Preserve original member paths in ZIP. Exclude materials/internal/. Required approval path is materials/package/approval.txt; report this exact path if missing. Report unreadable out-of-package candidates. Independent manifest stays outside ZIP.')];reads=contexts+source
        members=[n for n in source if n.startswith('materials/package/')];extra={'zip_path':'delivery/materials.zip','zip_members':{n:sha(root/n) for n in members}}
        ops=['archive'];prefixes=['delivery/']
    else:
        source=[put(root,f'inbox/{name}.txt',tag+' '+name) for name in ('alpha','beta','gamma')]
        mapping={n:f'normalized/txt/item_{i:02d}.txt' for i,n in enumerate(sorted(source),1)}
        ops=['move'];prefixes=['normalized/txt/']
        extra['recovery_goal']='rollback' if condition=='E' else 'complete'
    initial=snapshot(root);expected=dict(initial)
    if wid in ('FM01','FM38'):
        if wid!='FM38' or condition!='E':
            for n,d in mapping.items():expected[d]=expected.pop(n)
    elif wid in ('FM05','FM13'):
        for n,d in mapping.items():expected[d]=initial[n]
    elif wid=='FM17':
        for n,d in mapping.items():expected[d]=initial[n];expected['recovery-drill/'+n[len('source/'):]]=initial[n]
    oracle={'expected_snapshot':expected,'mapping':mapping,'required_gap_markers':gaps,'require_effects':bool(mapping or wid in ('FM17','FM21')),
            'require_restore':wid=='FM38' and condition=='E',**extra}
    c={'version':'sss-file-workflow-v1','workflow_id':wid,'source_paths':source,'destination_prefixes':prefixes,
       'required_reads':reads,'allowed_reads':reads,'context_paths':contexts,'recovery_goal':extra.get('recovery_goal','complete')}
    if wid=='FM05':c['allowed_reads']=contexts+source
    return c,oracle,ops,initial

def prepare(assets):
    for n in ('brief.docx','ledger.xlsx','poster.png'):
        if not (assets/n).is_file():raise ValueError('missing valid container template: '+n)
    pdfs=sorted((ROOT/'testpdf').glob('*.pdf'))
    if len(pdfs)!=3:raise ValueError('expected three protected original PDFs')
    eid='fm-workflow-free-20261013-'+uuid4().hex[:8];exp=ROOT/'.local/file-management'/eid;data=DATA/eid
    exp.mkdir(parents=True,mode=0o700,exist_ok=False);tasks=[]
    for role,conditions in [('probe','NEV'),('explore','NE'),('certify','N'),('holdout','NEV')]:
        for wid in IDS:
            for condition in conditions:
                tid=f'{role}-{wid}-{condition}';td=exp/'tasks'/tid;pristine=data/'pristine'/tid
                pristine.mkdir(parents=True,exist_ok=False);tag=tid+' '+uuid4().hex[:12]
                c,oracle,ops,initial=fixture(pristine,wid,condition,tag,assets,pdfs[IDS.index(wid)%3])
                save(td/'oracle.json',oracle)
                objective={
                    'FM01':'Read rules and all inbox candidates. Apply only unambiguous PROJECT_A/B text classification and global names; preserve every pending material and explain its exact path.',
                    'FM05':'Merge source-a and source-b according to rules/merge.txt: group equal SHA, copy representative once to merged/<full source path>; preserve all sources.',
                    'FM13':'First read context/release.txt, then select/read version files. Copy the confirmed version to selected/<basename>; ambiguous publication stays pending with its evidence path.',
                    'FM17':'Copy all source files to backup-set/<relative path>. Refresh inventory; recover FROM actual backup files into recovery-drill/<relative path>. Verify bytes; preserve originals.',
                    'FM21':'Read delivery scope and candidates; create delivery/materials.zip with exactly materials/package/ files and real paths. Report gaps; fixed acceptance derives a separate manifest.',
                    'FM38':'Global rename inbox to normalized/txt/item_NN.txt under the existing task grant. '+('Frozen crash drill: restart and restore the same authorized plan to original bytes.' if condition=='E' else 'Restart/repeat the executed plan idempotently and deliver final current identities.')
                }[wid]
                spec={'schema_version':1,'task_id':tid,'role':role,'family':'rename' if wid=='FM38' else 'workflow','variant':condition,
                      'objective':objective,'rules':{'experimental_copy_only':True,'no_overwrite':True,'semantic_review':'not performed'},
                      'allowed_operations':ops,'workspace':str(pristine),'initial_snapshot':initial,
                      'report_contract':{'version':'sss-file-report-v3','kind':'task_result'},'workflow_contract':c,
                      'workflow_oracle_file':str(td/'oracle.json'),'workflow_oracle_sha256':sha(td/'oracle.json')}
                if wid=='FM38':
                    spec.update(task_contract={'version':'sss-file-task-v1','kind':'rename'},
                                write_grant={'schema_version':1,'allowed_ops':['move'],'source_paths':c['source_paths'],'destination_prefixes':c['destination_prefixes'],'max_actions':3,'allow_restore':True})
                    if condition=='E':spec['recovery_crash_after_publish']=True
                save(td/'input-template.json',spec)
                (td/'prompt.md').write_text('Use only the approved MCP tools and actual evidence. No source changes outside the experiment. '+objective,encoding='utf-8')
                names=(*TOOLS[:11],'authorize_plan',*TOOLS[11:]) if wid=='FM38' else TOOLS
                env={n:{'from_env':n} for n in ('FM_TASK_FILE','FM_OUTPUT',*(('FM_JOB_FILE',) if wid=='FM38' else ()))}
                config={'schema_version':1,'name':'file_management','prompt':str(td/'prompt.md'),'servers':[{'server_name':'file_management','transport':'stdio','command':'${PYTHON}',
                         'args':['${PROJECT_ROOT}/scenarios/file-management/'+('recovery_tools.py' if wid=='FM38' else 'workflow_tools.py')],'cwd':'${PROJECT_ROOT}','env':env}],
                        'allowed_tools':[PREFIX+n for n in names],'acceptance_guard':{'kind':'file_management','max_repairs':2,**({'durable_job':True} if wid=='FM38' else {})}}
                save(td/'scenario.json',config)
                tasks.append({'task_id':tid,'workflow_id':wid,'condition':condition,'role':role,'task_dir':str(td),'pristine':str(pristine),
                              'input_template_sha256':sha(td/'input-template.json'),'oracle_sha256':sha(td/'oracle.json'),'snapshot_sha256':digest(initial)})
    frozen=[*HERE.glob('*.py'),*HERE.glob('*.md')]+[ROOT/n for n in (
        'src/adapters/file_workflow_job.ts','src/adapters/file_job_budget.py','src/adapters/file_acceptance_guard.ts',
        'src/adapters/file_scenario.py','src/adapters/file_cost_gate.py','src/adapters/harness_runtime.py',
        'scripts/run-file-scenario.py','scripts/validate-file-delivery.py','scripts/check-file-workflows.py','scripts/check-file-workflow-sdk.py',
        'config/semantic-sdk.patch.yml','package.json','package-lock.json','requirements.txt')]
    for p in frozen:
        dest=exp/'frozen-source'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest);dest.chmod(0o600)
    protocol={'experiment_id':eid,'type':'free MCP preparation, not model training','real_api_requests':0,'estimated_model_cost_usd':0,
              'series_cap_usd':1000,'prior_series_estimated_usd':3.836167800,'tasks':tasks,'data_directory':str(data),'model':'deepseek-flash',
              'reasoning_effort':'off','compression_enabled':False,'limits':{'budget_usd':5,'max_requests':96,'max_steps':96,'max_output':4000,'max_repairs':2},
              'versions':{'workflow':workflow_version(),'recovery':recovery_version()},'source_code':{str(p.relative_to(ROOT)):sha(p) for p in frozen},
              'original_pdfs':{p.name:sha(p) for p in pdfs},'templates':{n:sha(assets/n) for n in ('brief.docx','ledger.xlsx','poster.png')},
              'limitations':['Office/image containers reused unchanged; new text, paths and business conditions','real PDF copies repeat known sources; no corpus generalization claim','probe trajectories excluded from Motif learning','holdout remains untouched','macOS local validation only']}
    save(exp/'protocol.json',protocol);save(ROOT/'.local/file-management/workflow-current.json',{'experiment':str(exp)})
    print(json.dumps({'experiment':str(exp),'templates':len(tasks),'roles':{r:sum(t['role']==r for t in tasks) for r in ('probe','explore','certify','holdout')},'real_api_requests':0}));return exp

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,default=ROOT/'.local/file-management-author/assets/a');a=p.parse_args();prepare(a.assets)
