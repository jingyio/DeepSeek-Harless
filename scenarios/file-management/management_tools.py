"""Autonomous copy-workspace operations; risky effects need host-issued approval."""
from __future__ import annotations
import copy,json,os,shutil,errno
from pathlib import Path,PurePosixPath
from typing import Annotated,Literal
from uuid import uuid4
from pydantic import BaseModel,ConfigDict,Field
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from mcp.server.mcpserver.exceptions import ToolError
from common import ROOT,HERE,digest,sha
from plan_tools import atomic
from operation_tools_v2 import OperationSceneV2,TOOLS as BASE_TOOLS,operator_contract as inherited_contract
from management_reading import DocumentReading,TOOLS as READING_TOOLS,contract as reading_contract
from src.adapters.general_tools import GeneralTools,NAMES as GENERAL_TOOLS
TOOLS=[*BASE_TOOLS,*READING_TOOLS,*GENERAL_TOOLS]

VERSION='sss-management-v3'
LOW_OPS={'copy','move','rename','mkdir','quarantine'}
RESERVED={'.experiment-copy','.management-copy'}
class ManagementAction(BaseModel):
    model_config=ConfigDict(extra='forbid')
    op:Literal['copy','move','rename','mkdir','overwrite','delete','quarantine','read']
    file_ids:list[str]=Field(default_factory=list,max_length=1,description='At most one actual file_id from list_files. When nonempty, omit source or set source=null; never provide both identities.')
    source:str|None=Field(default=None,max_length=180,description='Alternative relative source path. Use only when file_ids is empty. Omit for mkdir.')
    source_root:str='workspace'
    destination:str|None=Field(default=None,max_length=180)
    destination_root:str='workspace'

def tree(root,ignored=()):
    files={};directories=[]
    for p in sorted(Path(root).rglob('*')):
        if p.is_symlink():raise ValueError('symlink outside management authority')
        n=p.relative_to(root).as_posix()
        if n in ignored:continue
        if p.is_file():files[n]=sha(p)
        elif p.is_dir():directories.append(n)
        else:raise ValueError('unsupported workspace object')
    return {'files':files,'directories':directories}

def execution_version():
    paths=[HERE/n for n in ('management_tools.py','management_native.py','management_reading.py','management_contract.py','management_goals.py','management_temporal.py','management_provenance.py','file_tools.py','report_tools.py','collection_tools.py','common.py')]
    paths += [ROOT/n for n in ('src/adapters/general_tools.py','src/adapters/general_tool_replay.py','scenarios/file-management/general-tools.json','scenarios/general/runtime.py','scenarios/general/runtime_code.ts')]
    return digest({str(p.relative_to(ROOT)):sha(p) for p in paths})

def operator_contract(name):
    if name in READING_TOOLS:return reading_contract(name)
    if name in GENERAL_TOOLS:
        from src.adapters.general_tool_replay import operator_contract as general_contract
        return general_contract(name)
    c=inherited_contract(name)
    if name in ('pin_file','read_file'):c={**c,'flow_interleaving':True}
    if name=='preview_actions':c={**c,'statuses':['validated_management_plan','confirmation_required']}
    if name=='select_files':c={**c,'exports':['collection_id','files[].file_id']}
    if name=='collect_reads':c={**c,'effect':'read','auto_continue':True,'statuses':['collection_complete']}
    if name=='restore_plan':c={'format':'sss-mcp-learning-v1','effect':'semantic','auto_continue':False,'exports':[]}
    return c

class ManagementScene(DocumentReading,GeneralTools,OperationSceneV2):
    fields=(*OperationSceneV2.fields,'documents','visual_reads')
    def __init__(self,spec,output):
        self.spec=copy.deepcopy(spec);self.input_digest=digest(spec)
        self.output=Path(output).resolve();self.root=Path(spec['workspace']).resolve()
        if not self.output.is_relative_to((ROOT/'.local').resolve()) or self.output==self.root or self.output.is_relative_to(self.root):raise ValueError('separate private journal root required')
        self.roots={'workspace':self.root}
        for key,row in spec.get('external_roots',{}).items():
            if not key.startswith('external-') or row['owner']!=spec['owner']:raise ValueError('external root ownership differs')
            p=Path(row['path']).resolve()
            if p==self.root or p.is_relative_to(self.root) or self.root.is_relative_to(p):raise ValueError('overlapping management roots')
            self.roots[key]=p
        from src.adapters.continuous_rsi import STATE_HOME
        for key,p in self.roots.items():
            if p.is_relative_to(STATE_HOME.resolve()) or STATE_HOME.resolve().is_relative_to(p):raise ValueError('management roots cannot expose account control state')
            if not p.is_dir() or any(q.is_symlink() for q in (Path(spec['workspace']) if key=='workspace' else Path(spec['external_roots'][key]['path']),*p.parents)):raise ValueError('invalid registered copy root')
            if self.output.is_relative_to(p) or p.is_relative_to(self.output) or p.is_relative_to((ROOT/'.local/rsi').resolve()) or (ROOT/'.local/rsi').resolve().is_relative_to(p):raise ValueError('management roots cannot expose private control state')
        marker=self.root/'.experiment-copy'
        if not marker.is_file() or sha(marker)!=spec['workspace_marker_sha256']:raise ValueError('server-issued copy marker changed')
        self.output.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.state_file=self.output/'management-state.json'
        self.learning_scope={'input_sha256':self.input_digest,'execution_version':execution_version(),
          'permission_sha256':digest({'owner':spec['owner'],'workspace_id':spec['workspace_id'],'external_roots':spec.get('external_roots',{}),'low_operations':sorted(LOW_OPS),'read_only':spec.get('rules',{}).get('read_only',False),'high_risk':'one_plan_native_confirmation'}),
          'initial_snapshot_sha256':digest(spec['initial_tree']),'result_read_allowed':True}
        self.execution_version=execution_version();self.report_contract={'version':'sss-file-report-v3','kind':'task_result'}
        self.task_read=False;self.search_receipts={};self.collections={};self.collection_results={};self.documents={};self.visual_reads={}
        self.plans={};self.receipts={};self.result_handles={};self.handles={};self.reads={};self.index={};self.journals={};self.external_read_grants=[];self.local_staging={}
        self.expected_tree=copy.deepcopy(spec['initial_tree']);self.sync_files()
        if self.state_file.exists():
            s=json.loads(self.state_file.read_text())
            if s['state_sha256']!=digest({k:v for k,v in s.items() if k!='state_sha256'}) or s['input_sha256']!=self.input_digest or s['execution_version']!=execution_version():raise ValueError('original management task/version/state changed')
            self.expected_tree=s['expected_tree']
            for k in (*self.fields,'journals','external_read_grants','local_staging'):setattr(self,k,s[k])
            actual=self.actual_tree();allowed=[self.expected_tree]
            for j in self.journals.values():
                if j['status'] in ('executing','restoring') and j.get('flight'):allowed += [j['flight']['before'],j['flight']['after']]
            if actual not in allowed:raise ValueError('unrecorded workspace change; recovery refused')
            self.expected_tree=actual;self.sync_files()
        elif self.actual_tree()!=self.expected_tree:raise ValueError('initial management material changed')
        self.persist()
    def actual_tree(self):return {key:tree(p,[v['path'] for v in self.local_staging.values() if v['root']==key]) for key,p in self.roots.items()}
    def sync_files(self):self.expected={key+'/'+name:h for key,t in self.expected_tree.items() for name,h in t['files'].items()}
    def persist(self):
        body={'input_sha256':self.input_digest,'execution_version':execution_version(),'expected_tree':self.expected_tree,
          'journals':self.journals,'external_read_grants':self.external_read_grants,'local_staging':self.local_staging,**{k:getattr(self,k) for k in self.fields}}
        body['state_sha256']=digest(body);atomic(self.state_file,body)
        for pid,j in self.journals.items():atomic(self.output/'journals'/f'{pid}.json',j)
    def guard(self):
        actual=self.actual_tree()
        if actual!=self.expected_tree:raise ToolError('workspace changed outside recorded operation boundaries')
    def active(self):
        self.guard()
        if not self.task_read:raise ToolError('read_task first')
        if os.environ.get('FM_JOB_FILE'):
            from src.adapters.operation_budget import command
            s=command(os.environ['FM_JOB_FILE'],'state')['state']
            if s['task_sha256']!=sha(Path(os.environ['FM_TASK_FILE'])) or s['execution_version_sha256']!=execution_version() or s['status']!='running':raise ToolError('original task permission/version/budget inactive')
            if s.get('owner_pid'):
                from src.adapters.process_state import process_exists
                if not process_exists(s['owner_pid']):raise ToolError('original task owner exited; recover the original job first')
    def resolve_path(self,key,name):
        if key not in self.roots or not isinstance(name,str) or not 1<=len(name)<=180 or '\\' in name or any(ord(c)<32 for c in name):raise ToolError('invalid registered relative path')
        p=PurePosixPath(name)
        if p.is_absolute() or any(c in ('..','.') for c in name.split('/')) or p.parts[0] in RESERVED or any(c.startswith('.sss-management-') for c in p.parts):raise ToolError('path outside copy grant')
        result=self.roots[key]/p
        if not result.resolve().is_relative_to(self.roots[key]) or any(q.is_symlink() for q in (result,*result.parents) if q.is_relative_to(self.roots[key])):raise ToolError('path escapes registered copy')
        return result
    def path(self,name):
        key,relative=name.split('/',1);return self.resolve_path(key,relative)
    def files(self):return {self.file_id(n):n for n in self.expected if n.split('/',1)[1] not in RESERVED and (n.startswith('workspace/') or n in self.external_read_grants)}
    def read_task(self):
        self.guard();self.task_read=True
        self.gateway()  # Snapshot approved inputs before any move/rename.
        frozen_goal=self.spec.get('quality',{}).get('goal',{})
        public_goal={k:v for k,v in frozen_goal.items() if k not in ('expected_tree','expected_roots','expected_origins','intermediate_sources')}
        return self.stamp({'task_id':self.spec['task_id'],'objective':self.spec['objective'],'copy_only':True,'default_operations':[] if self.spec.get('rules',{}).get('read_only') else sorted(LOW_OPS),
          'approved_inputs':self.spec.get('approved_inputs',[]),
          'high_risk_operations':['overwrite','delete','external_root_access'],'external_root_ids':list(self.spec.get('external_roots',{})),
          'learning_scope':self.learning_scope,'goal_acceptance':public_goal,'goal_contract_sha256':digest(frozen_goal),
          'default_type_directories':{'PDF/Word':'documents','Excel/CSV':'tables','images':'images','text':'notes','other':'others'},
          'recovery_state':[{'plan_id':p,'status':j['status']} for p,j in self.journals.items()],
          'instruction':'Choose actions from the user goal and actual file identities. No fixed source/destination list. High-risk plans need one native human confirmation; do not invent approval tokens.'})
    def list_files(self):
        self.active()
        return self.stamp({'files':[{'file_id':fid,'path':name.split('/',1)[1],'root_id':name.split('/',1)[0],'sha256':self.expected[name],'bytes':self.path(name).stat().st_size} for fid,name in self.files().items()],
          'directories':self.expected_tree['workspace']['directories'],'snapshot_sha256':digest(self.expected_tree)})
    def inventory_rows(self):
        return [{**r,'source_version':digest({'path':r['root_id']+'/'+r['path'],'sha':r['sha256'],'parser':'fm-parser-v1'})} for r in self.list_files()['files']]
    def parse(self,path):
        if path.suffix.lower()=='.pdf':
            from management_reading import page_count,extract_page
            count=page_count(path);text,_=extract_page(path,1,'text',self.output/'preview-cache')
            return 'readable',text,{'scope':'page 1 preview','page_count':count,'preview_only':True,'coverage_established':False,
                'full_read_tool':'open_document → read_document_chunk → document_coverage'}
        if path.suffix.lower()=='.json':return 'readable',path.read_text(encoding='utf-8'),{}
        return super().parse(path)
    def compare_snapshot(self):
        """Compare user files and directories with this original task's frozen tree."""
        self.active()
        old={k+'/'+n:h for k,t in self.spec['initial_tree'].items() for n,h in t['files'].items() if n not in RESERVED}
        now={n:h for n,h in self.expected.items() if n.split('/',1)[1] not in RESERVED}
        before={k+'/'+n for k,t in self.spec['initial_tree'].items() for n in t['directories']}
        after={k+'/'+n for k,t in self.expected_tree.items() for n in t['directories']}
        return self.stamp({'added':sorted(set(now)-set(old)),'modified':sorted(n for n in now.keys()&old.keys() if now[n]!=old[n]),
          'deleted':sorted(set(old)-set(now)),'unchanged':sorted(n for n in now.keys()&old.keys() if now[n]==old[n]),
          'added_directories':sorted(after-before),'deleted_directories':sorted(before-after),'file_ids':list(self.files())})
    def select_files(self,file_ids:Annotated[list[str],Field(min_length=0,max_length=32)]):
        """Declare a reading collection using actual file_ids. Pin and read its members, then collect_reads verifies coverage."""
        v=super().select_files(file_ids);self.persist();return self.stamp(v)
    def collect_reads(self,collection_id:str,source_ids:Annotated[list[str],Field(min_length=0,max_length=32)]):
        """After actual member reads, verify one declared collection with its actual collection_id and source_ids."""
        v=super().collect_reads(collection_id,source_ids);self.persist();return self.stamp(v)
    def pin_file(self,file_id:Annotated[str,Field(description='Actual file_id from list_files or inspect_plan_result; pinning returns a different source_id for reading.')]):
        """Resolve one current file identity into an actual readable source handle."""
        return super().pin_file(file_id)
    def read_file(self,source_id:Annotated[str,Field(description='Use the exact source_id returned by a completed pin_file or pin_files call. A file_id is not a source_id.')]):
        """Read one already pinned source. Wait for pinning before using its handle."""
        self.active()
        if any(j['status'] in ('executing','restoring') for j in self.journals.values()):raise ToolError('recover the original unfinished plan before reading file contents')
        super().read_file(source_id)
        result=self.reads[source_id]
        if result.get('metadata',{}).get('preview_only'):
            result['truncated']=True
            result['metadata']['coverage_established']=False
        from management_provenance import read_provenance
        try:proof=read_provenance(self.spec,json.loads(self.state_file.read_text()),result)
        except ValueError as error:raise ToolError(str(error)) from error
        result={**result,'provenance':proof};self.reads[source_id]=result
        atomic(self.output/'reads'/f'{source_id}.json',result);self.persist()
        return self.stamp(copy.deepcopy(result))
    def pin_files(self,file_ids:Annotated[list[str],Field(min_length=1,max_length=40,description='Unique actual file_ids from list_files or inspect_plan_result.files. Returns source_ids for later reading.')]):
        """Pin a bounded set of current files; preserve the returned source_ids."""
        return super().pin_files(file_ids)
    def read_files(self,source_ids:Annotated[list[str],Field(min_length=1,max_length=40,description='Unique actual source_ids returned by a completed pin_files or pin_file call. Do not substitute file_ids or guess handles.')]):
        """Read already pinned sources after pinning completes; pinning and reading are dependent calls."""
        return super().read_files(source_ids)
    def preview_actions(self,actions:list[ManagementAction]):
        self.active()
        if any(j['status'] in ('executing','restoring') for j in self.journals.values()):raise ToolError('recover the original unfinished plan before creating another plan')
        if not 1<=len(actions)<=40:raise ToolError('bounded 1-40 management actions required')
        actual=[];risks=[];destinations=set();sources=set()
        for raw in actions:
            a=raw if isinstance(raw,ManagementAction) else ManagementAction(**raw);row=a.model_dump()
            if a.op not in self.spec.get('allowed_operations',LOW_OPS|{'overwrite','delete','read'}):raise ToolError('operation outside original task permission')
            if self.spec.get('rules',{}).get('read_only') and a.op!='read':raise ToolError('this task explicitly selected read-only mode')
            if a.file_ids:
                _,name=self.file(a.file_ids[0]);row['source_root'],row['source']=name.split('/',1)
                if a.source is not None:raise ToolError('choose file_id or source path, never both')
            if a.op!='mkdir':
                if row['source'] is None:raise ToolError('actual source required')
                src=self.resolve_path(row['source_root'],row['source'])
                if not src.is_file():raise ToolError('file source missing')
                if (row['source_root'],row['source']) in sources:raise ToolError('one source per plan; use a new plan for repeated actions')
                sources.add((row['source_root'],row['source']));row['source_sha256']=sha(src)
            if a.op not in ('delete','read'):
                if not a.destination:raise ToolError('actual destination required')
                dest=self.resolve_path(a.destination_root,a.destination)
                if (a.destination_root,a.destination) in destinations:raise ToolError('duplicate destination')
                destinations.add((a.destination_root,a.destination))
                if a.op=='overwrite':
                    if not dest.is_file():raise ToolError('overwrite requires an existing file')
                    row['overwritten_sha256']=sha(dest)
                elif dest.exists() and not (a.op=='mkdir' and dest.is_dir()):raise ToolError('existing destination requires explicit overwrite plan')
                if any(p.exists() and not p.is_dir() for p in dest.parents if p.is_relative_to(self.roots[a.destination_root])):raise ToolError('destination parent conflict')
                if a.op!='mkdir' and (row['source_root'],row['source'])==(a.destination_root,a.destination):raise ToolError('source equals destination')
            risk=a.op in ('overwrite','delete') or row['source_root']!='workspace' or a.destination_root!='workspace'
            if risk:risks.append({'op':a.op,'source':row['source'],'source_root':row['source_root'],'destination':a.destination,'destination_root':a.destination_root,'irreversible':a.op=='delete'})
            from management_provenance import check_goal_action
            try:check_goal_action(self.spec,json.loads(self.state_file.read_text()),row)
            except ValueError as error:raise ToolError(str(error)) from error
            actual.append(row)
        pid='management-plan-'+uuid4().hex
        plan={'plan_id':pid,'task_sha256':self.input_digest,'execution_version':execution_version(),'before':copy.deepcopy(self.expected_tree),'actions':actual,'risks':risks}
        plan['plan_sha256']=digest(plan);self.plans[pid]=plan;self.persist()
        return self.stamp({'plan_id':pid,'plan_sha256':plan['plan_sha256'],'actions':actual,'risks':risks,'status':'confirmation_required' if risks else 'validated_management_plan'})
    def approve(self,plan_id,plan_sha256,proof):
        self.guard();p=self.plans.get(plan_id)
        if not p or p['plan_sha256']!=plan_sha256 or p['before']!=self.expected_tree:raise ToolError('approval plan/source state changed')
        if proof.get('outcome')!='allowed-once' or proof.get('task_sha256')!=self.input_digest or not proof.get('approval_event_id') or not proof.get('session_id'):raise ToolError('actual native one-plan confirmation required')
        atomic(self.output/'approvals'/f'{plan_id}.json',{'plan_id':plan_id,'plan_sha256':plan_sha256,'proof':proof})
    def effects(self,plan,j):
        effects=[]
        for a in plan['actions']:
            if a['op']=='read':continue
            if a['op']=='delete':effects.append({'kind':'unlink','root':a['source_root'],'path':a['source']});continue
            target=self.resolve_path(a['destination_root'],a['destination'])
            parents=[p for p in reversed((target if a['op']=='mkdir' else target.parent).parents) if p.is_relative_to(self.roots[a['destination_root']]) and p!=self.roots[a['destination_root']]]
            parents+=[target if a['op']=='mkdir' else target.parent]
            for p in parents:
                n=p.relative_to(self.roots[a['destination_root']]).as_posix()
                if n!='.' and n not in self.expected_tree[a['destination_root']]['directories'] and not any(e['kind']=='mkdir' and (e['root'],e['path'])==(a['destination_root'],n) for e in effects):effects.append({'kind':'mkdir','root':a['destination_root'],'path':n})
            if a['op']=='mkdir':continue
            staged=self.output/'staging'/plan['plan_id']/str(len(effects));staged.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(self.resolve_path(a['source_root'],a['source']),staged)
            if sha(staged)!=a['source_sha256']:raise ToolError('source changed after preview')
            with staged.open('r+b') as f:os.fsync(f.fileno())
            effects.append({'kind':'replace' if a['op']=='overwrite' else 'publish','root':a['destination_root'],'path':a['destination'],'staged':str(staged),'sha256':sha(staged)})
            if a['op'] in ('move','rename','quarantine'):effects.append({'kind':'unlink','root':a['source_root'],'path':a['source']})
        return effects
    def execute_plan(self,plan_id:str):
        self.active();p=self.plans.get(plan_id)
        if not p:raise ToolError('unknown current plan')
        j=self.journals.get(plan_id)
        if j and j['status']=='restored_verified':raise ToolError('restored plan cannot execute again')
        if plan_id in self.receipts:
            if self.receipts[plan_id]['snapshot_sha256']!=digest(self.expected_tree):raise ToolError('prior receipt is stale')
            return self.receipt(plan_id)
        if not j:
            if p['before']!=self.expected_tree:raise ToolError('stale management plan')
            if p['risks']:
                approval=self.output/'approvals'/f'{plan_id}.json'
                if not approval.is_file() or json.loads(approval.read_text())['plan_sha256']!=p['plan_sha256']:raise ToolError('native high-risk confirmation required')
            backups={}
            for a in p['actions']:
                names=[] if a['op'] in ('delete','mkdir','read') else [(a['source_root'],a['source'])]
                if a['op']=='overwrite':names.append((a['destination_root'],a['destination']))
                for key,n in names:
                    dst=self.output/'backups'/plan_id/key/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(self.resolve_path(key,n),dst);backups[key+'/'+n]=sha(dst)
            j={'plan_id':plan_id,'before':copy.deepcopy(self.expected_tree),'completed':[],'status':'executing','backups':backups,'irreversible':any(a['op']=='delete' for a in p['actions']),'effects':[],'boundaries':[]}
            j['effects']=self.effects(p,j);self.journals[plan_id]=j;self.persist()
        if j['status']!='executing':raise ToolError('prior plan is inactive')
        for e in j['effects'][len(j['completed']):]:
            self.active();flight=j.get('flight')
            if not flight:
                before=copy.deepcopy(self.expected_tree);after=copy.deepcopy(before);t=after[e['root']]
                if e['kind']=='mkdir':t['directories']=sorted(set(t['directories'])|{e['path']})
                elif e['kind']=='unlink':t['files'].pop(e['path'])
                else:t['files'][e['path']]=e['sha256']
                flight={'before':before,'after':after};j['flight']=flight;self.persist()
            path=self.resolve_path(e['root'],e['path'])
            if self.expected_tree==flight['before']:
                if e['kind']=='mkdir':path.mkdir()
                elif e['kind']=='unlink':path.unlink()
                else:
                    if sha(Path(e['staged']))!=e['sha256']:raise ToolError('staged bytes changed')
                    self.publish_bytes(e['staged'],path,e['kind']=='replace')
                if getattr(self,'crash_after_effect',None)==len(j['completed']):raise SystemExit('recorded management effect boundary')
            self.expected_tree=self.actual_tree();self.sync_files()
            if self.expected_tree!=flight['after']:raise ToolError('effect footprint changed')
            j['boundaries'].append(flight);j['completed'].append(e);j.pop('flight',None);self.persist()
        for a in p['actions']:
            if a['op']=='read':self.external_read_grants.append(a['source_root']+'/'+a['source'])
        self.clean_local_staging()
        j.update(status='executed_verified',after=copy.deepcopy(self.expected_tree));self.persist()
        self.receipts[plan_id]={'plan_id':plan_id,'status':'executed_verified','operation_count':len(p['actions']),'snapshot_sha256':digest(self.expected_tree),'journal_sha256':digest(j)}
        self.persist();return self.receipt(plan_id)
    def inspect_plan_result(self,receipt_id:str):
        self.active();pid=self.result_handles.get(receipt_id)
        if not pid or pid not in self.receipts or self.journals[pid].get('after')!=self.expected_tree:raise ToolError('unknown or stale result receipt')
        files=[];directories=[]
        for a in self.plans[pid]['actions']:
            if a['op']=='mkdir':directories.append({'root_id':a['destination_root'],'path':a['destination']})
            elif a['op'] not in ('delete','read'):
                n=a['destination_root']+'/'+a['destination'];files.append({'file_id':self.file_id(n),'path':a['destination'],'root_id':a['destination_root'],'sha256':self.expected[n]})
                if a['destination_root']!='workspace':self.external_read_grants.append(n)
        self.persist();v={'status':'verified_plan_results','receipt_id':receipt_id,'files':files,'directories':directories,'primary_file_id':files[0]['file_id'] if len(files)==1 else None};atomic(self.output/'result-inspections'/f'{receipt_id}.json',v);return self.stamp(v)
    def publish_bytes(self,source,target,replace=False):
        source=Path(source);target=Path(target)
        try:
            (os.replace if replace else os.link)(source,target);return
        except OSError as error:
            if error.errno!=errno.EXDEV and getattr(error,'winerror',None)!=17:raise
        # Only a specifically journaled private temporary file is ignored by
        # the user-tree guard. Unknown similarly named files remain visible.
        key=digest({'source':str(source),'target':str(target),'replace':replace})
        root=next(k for k,p in self.roots.items() if target.is_relative_to(p))
        name=target.parent/('.sss-management-'+key[:32]+'.tmp')
        descriptor={'root':root,'path':name.relative_to(self.roots[root]).as_posix()}
        if self.local_staging.get(key) not in (None,descriptor):raise ToolError('original local staging changed')
        if key not in self.local_staging:
            if name.exists() or name.is_symlink():raise ToolError('local staging collision')
            self.local_staging[key]=descriptor;self.persist()
        if name.is_symlink():raise ToolError('local staging symlink refused')
        if name.exists():name.unlink()
        with source.open('rb') as src,name.open('xb') as dst:
            shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
        if sha(name)!=sha(source):raise ToolError('local staging bytes changed')
        (os.replace if replace else os.link)(name,target)
        if name.exists():name.unlink()
        self.local_staging.pop(key);self.persist()
    def clean_local_staging(self):
        for key,v in list(self.local_staging.items()):
            p=self.roots[v['root']]/v['path']
            if p.is_symlink():raise ToolError('local staging symlink refused')
            if p.exists():p.unlink()
            self.local_staging.pop(key);self.persist()
    def restore_sha(self,plan_id):
        j=self.journals[plan_id]
        return digest({'plan_sha256':self.plans[plan_id]['plan_sha256'],'direction':'restore','before':j.get('restore_before',self.expected_tree)})
    def approve_restore(self,plan_id,plan_sha256,proof):
        self.guard()
        if plan_sha256!=self.restore_sha(plan_id) or proof.get('outcome')!='allowed-once' or proof.get('task_sha256')!=self.input_digest or not proof.get('approval_event_id') or not proof.get('session_id'):raise ToolError('actual one-plan restoration confirmation required')
        atomic(self.output/'restore-approvals'/f'{plan_id}.json',{'plan_id':plan_id,'plan_sha256':plan_sha256,'proof':proof})
    def restore_plan(self,plan_id:str):
        self.active();j=self.journals.get(plan_id)
        if not j or j['status'] not in ('executed_verified','executing','restoring','restored_verified'):raise ToolError('unknown restoration journal')
        if j['irreversible']:raise ToolError('permanent deletion cannot be restored by this service')
        if j['status']=='restored_verified':return self.stamp({'plan_id':plan_id,'status':'restored_verified'})
        if j['status']=='executed_verified' and self.expected_tree!=j.get('after',self.expected_tree):raise ToolError('later changes prohibit restoration')
        if self.plans[plan_id]['risks']:
            f=self.output/'restore-approvals'/f'{plan_id}.json'
            if not f.exists() or json.loads(f.read_text())['plan_sha256']!=self.restore_sha(plan_id):raise ToolError('actual one-plan restoration confirmation required')
        if j['status']=='executing' and j.get('flight'):
            flight=j['flight']
            if self.expected_tree==flight['after']:
                j['completed'].append(j['effects'][len(j['completed'])]);j['boundaries'].append(flight)
            elif self.expected_tree!=flight['before']:raise ToolError('unfinished operation boundary differs')
            j.pop('flight');self.persist()
        j.setdefault('restore_before',copy.deepcopy(self.expected_tree));j.setdefault('restore_boundaries',[])
        # Each reverse boundary is persisted before touching the corresponding path.
        todo=list(reversed(list(zip(j['completed'],j['boundaries']))))
        j.update(status='restoring',restored_count=j.get('restored_count',0));self.persist()
        # Abandoned target-volume copies must be removed before undoing their
        # parent directories. They never became user-visible file effects.
        self.clean_local_staging()
        for e,b in todo[j['restored_count']:]:
            self.active()
            current=self.actual_tree()
            if current not in (b['after'],b['before']):raise ToolError('restoration boundary changed')
            j['flight']={'before':b['after'],'after':b['before']};self.persist()
            if current==b['after']:
                path=self.resolve_path(e['root'],e['path'])
                if e['kind']=='mkdir':path.rmdir()
                elif e['kind']=='publish':path.unlink()
                else:
                    saved=self.output/'backups'/plan_id/e['root']/e['path']
                    if sha(saved)!=j['backups'][e['root']+'/'+e['path']]:raise ToolError('restoration backup changed')
                    temp=self.output/'restore-staging'/uuid4().hex;temp.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(saved,temp)
                    self.publish_bytes(temp,path,e['kind']=='replace')
            self.expected_tree=self.actual_tree()
            if self.expected_tree!=b['before']:raise ToolError('restoration effect footprint changed')
            j['restore_boundaries'].append(j['flight']);self.sync_files();j['restored_count']+=1;j.pop('flight',None);self.persist()
        if self.expected_tree!=j['before']:raise ToolError('restoration postcondition differs')
        self.clean_local_staging()
        j.update(status='restored_verified',after=self.expected_tree);self.persist();return self.stamp({'plan_id':plan_id,'status':'restored_verified'})
    def submit_report(self,summary:str,file_ids:list[str],gaps:list[str]):
        self.active()
        if len(file_ids)!=len(set(file_ids)) or set(file_ids)!=set(self.files()):raise ToolError('report must include all actual current file identities')
        from management_contract import verify_management
        report={'task_id':self.spec['task_id'],'input_sha256':self.input_digest,'final_tree':self.expected_tree,'file_ids':file_ids,'summary':summary,'gaps':gaps}
        r=verify_management(self.spec,report,self.output)
        if not r['passed']:raise ToolError('actual management delivery rejected: '+str(r['errors']))
        atomic(self.output/'report.json',report);atomic(self.output/'acceptance.json',r);self.persist();return self.stamp({'status':'delivered_with_gaps' if gaps else 'delivered','artifact':str(self.output/'report.json'),'artifact_sha256':digest(report),'input_sha256':self.input_digest,'file_count':len(file_ids),'semantic_quality_verified':r['semantic_quality_verified']})

def serve():
    scene=ManagementScene(json.loads(Path(os.environ['FM_TASK_FILE']).read_text()),os.environ['FM_OUTPUT']);server=MCPServer('file_management')
    for n in TOOLS:server.tool(name=n,meta={'sss_learning':operator_contract(n)},annotations=ToolAnnotations(readOnlyHint=n not in ('execute_plan','restore_plan','submit_report','build_index','execute_tool_call'),destructiveHint=False,openWorldHint=False))(getattr(scene,n))
    server.run()
if __name__=='__main__':serve()
