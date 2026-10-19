"""Host-configured MCP discovery and dispatch, independent of Motif availability.

The model chooses provider/tool/arguments. It cannot register host commands,
credentials or permissions. Existing native task/model budgets remain in force.
"""
from __future__ import annotations
import asyncio,copy,hashlib,json,os,re,sys,time
from contextlib import AsyncExitStack
from pathlib import Path
from uuid import uuid4
from mcp import Client,StdioServerParameters
from mcp.server.mcpserver.exceptions import ToolError
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[2]
FORMAT='sss-general-tools-v1'
NAMES=['discover_tools','describe_tool','prepare_tool_call','execute_tool_call','inspect_tool_result']
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_name(path.name+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temp.chmod(0o600);os.replace(temp,path)

class ProviderConnection:
    """Own a live MCP session in one long-lived task, across native tool turns."""
    def __init__(self,row,bound):
        self.row=row;self.bound=bound;self.queue=asyncio.Queue();self.ready=asyncio.get_running_loop().create_future()
        self.task=asyncio.create_task(self.worker())
    async def worker(self):
        try:
            async with AsyncExitStack() as stack:
                row=self.row
                if row['transport']=='stdio':
                    env={'PATH':os.environ.get('PATH','/usr/bin:/bin:/opt/homebrew/bin'),'LANG':'en_US.UTF-8',
                         'PYTHONPATH':str(ROOT),'PYTHONUNBUFFERED':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8',
                         **{k:os.environ[k] for k in ('SystemRoot','ComSpec','WINDIR','TEMP','TMP') if k in os.environ},**{k:self.bound(v) for k,v in row.get('env',{}).items()}}
                    connection=StdioServerParameters(command=self.bound(row['command']),args=[self.bound(v) for v in row.get('args',[])],
                        cwd=self.bound(row.get('cwd','${PROJECT_ROOT}')),env=env)
                else:
                    from mcp.client.streamable_http import streamable_http_client
                    from httpx2 import AsyncClient
                    http=await stack.enter_async_context(AsyncClient(headers={k:self.bound(v) for k,v in row.get('headers',{}).items()}))
                    connection=streamable_http_client(self.bound(row['url']),http_client=http)
                client=await stack.enter_async_context(Client(connection,read_timeout_seconds=row.get('timeout_seconds',120)))
                self.ready.set_result(True)
                while True:
                    item=await self.queue.get()
                    if item is None:break
                    method,args,future=item
                    if future.cancelled():continue
                    try:value=await getattr(client,method)(*args)
                    except Exception as e:
                        if not future.done():future.set_exception(e)
                    else:
                        if not future.done():future.set_result(value)
        except BaseException as e:
            if not self.ready.done():self.ready.set_exception(e)
            while not self.queue.empty():
                item=self.queue.get_nowait()
                if item and not item[2].done():item[2].set_exception(RuntimeError('provider process exited'))
    async def invoke(self,method,*args):
        await self.ready
        if self.task.done():raise ToolError('provider process exited; prepare against a new connection')
        future=asyncio.get_running_loop().create_future();await self.queue.put((method,args,future));return await future
    async def list_tools(self):return await self.invoke('list_tools')
    async def call_tool(self,*args):return await self.invoke('call_tool',*args)
    async def close(self):
        if not self.task.done():await self.queue.put(None)
        await self.task

class Gateway:
    def __init__(self,workspace,scope,*,config=None,guard=None):
        self.workspace=Path(workspace).resolve();self.scope=copy.deepcopy(scope);self.guard=guard or (lambda:None)
        if not self.workspace.is_relative_to(ROOT/'.local') or self.workspace.is_symlink():raise ValueError('private task tool workspace required')
        self.home=self.workspace/'tool-access';self.home.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.config=Path(config or os.environ.get('SSS_TOOL_PROVIDERS',Path(os.environ.get('HARLESS_MANAGEMENT_PRIVATE_ROOT', ROOT/'.local'))/'general-tools/providers.json'))
        self.clients={};self.locks={};self.generation=uuid4().hex

    def providers(self):
        public=json.loads((ROOT/'scenarios/file-management/general-tools.json').read_text(encoding='utf-8'))
        custom=json.loads(self.config.read_text(encoding='utf-8')) if self.config.exists() else {'format':FORMAT,'providers':[]}
        if custom.get('format')!=FORMAT:raise ToolError('unsupported host tool registry version')
        entries={}
        for raw in [*public['providers'],*custom['providers']]:
            row=copy.deepcopy(raw);pid=row['id']
            if not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}',pid) or pid in entries:raise ToolError('duplicate/invalid host provider')
            if row.get('policy') not in ('read_only','provider_guarded'):raise ToolError('provider permission policy missing')
            # Never infer permission from untrusted MCP annotations alone.
            if row.get('cost')!='local_no_model':raise ToolError('metered tool provider needs a budget adapter before execution')
            if row.get('transport') not in ('stdio','streamable-http'):raise ToolError('unsupported provider transport')
            entries[pid]=row
        return entries

    def bound(self,value):
        if isinstance(value,dict) and set(value)=={'from_env'}:
            name=value['from_env']
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name) or name not in os.environ:raise ToolError('provider credential is not configured')
            return os.environ[name]
        if not isinstance(value,str):raise ToolError('invalid provider value')
        for k,v in {'PROJECT_ROOT':str(ROOT),'PYTHON':sys.executable,'SESSION_WORKSPACE':str(self.workspace)}.items():value=value.replace('${'+k+'}',v)
        if '${' in value:raise ToolError('unsupported host provider placeholder')
        return value

    async def connect(self,row):
        key=digest({'provider':row,'scope':self.scope})
        if key in self.clients:return self.clients[key]
        client=ProviderConnection(row,self.bound);self.clients[key]=client
        await client.ready;return client

    async def catalog(self,pid):
        self.guard();row=self.providers().get(pid)
        if not row:raise ToolError('provider is not in the host registry; model cannot register commands')
        client=await self.connect(row);result=await client.list_tools()
        tools=[t.model_dump(mode='json',by_alias=True,exclude_none=True) for t in result.tools]
        return row,client,tools,digest({'provider':row,'tools':tools,'scope':self.scope})

    async def discover_tools(self,query:str=''):
        """Discover connected tools by goal. Missing credentials/connections are explicit.
        Other tools work through ordinary Harness without a Motif or RSI certificate.
        """
        self.guard();found=[]
        for pid,row in self.providers().items():
            try:
                _,_,tools,version=await self.catalog(pid)
                selected=[{'name':t['name'],'description':t.get('description','')} for t in tools
                          if not query or query.casefold() in json.dumps(t,ensure_ascii=False).casefold()]
                if selected:found.append({'provider_id':pid,'description':row.get('description',''),'available':True,
                    'catalog_sha256':version,'tools':selected,'policy':row['policy'],'motif_required':False})
            except Exception as e:
                found.append({'provider_id':pid,'available':False,'reason':type(e).__name__,
                    'description':row.get('description',''),'motif_required':False})
        return {'format':FORMAT,'providers':found,'registry_file':str(self.config),
            'registration':'Host config supports stdio and streamable-http MCP; tools are not a hard-coded scene limit.'}

    async def describe_tool(self,provider_id:str,tool_name:str):
        """Return the actual provider's complete tool schema before choosing arguments."""
        row,_,tools,version=await self.catalog(provider_id)
        tool=next((t for t in tools if t['name']==tool_name),None)
        if not tool:raise ToolError('tool not present in actual provider catalog')
        return {'provider_id':provider_id,'tool':tool,'catalog_sha256':version,'policy':row['policy'],'motif_required':False}

    async def prepare_tool_call(self,provider_id:str,tool_name:str,arguments:dict):
        """Validate a model-selected tool and arguments without executing it.
        Preserve returned request_id; execute that exact request once.
        """
        row,_,tools,version=await self.catalog(provider_id)
        for p in (self.home/'requests').glob('*.json'):
            prior=json.loads(p.read_text(encoding='utf-8'))
            if (prior.get('scope')==self.scope and prior.get('provider_id')==provider_id and prior.get('tool_name')==tool_name
                    and prior.get('arguments')==arguments and prior.get('status') in ('executing','transport_error')):
                raise ToolError('matching earlier call has unknown effects; inspect original request '+prior['request_id']+' before any retry')
        tool=next((t for t in tools if t['name']==tool_name),None)
        if not tool:raise ToolError('tool absent from actual provider')
        schema=tool.get('inputSchema',tool.get('input_schema'))
        errors=list(Draft202012Validator(schema).iter_errors(arguments))
        if errors:raise ToolError('arguments do not match actual MCP schema: '+errors[0].message)
        annotations=tool.get('annotations',{})
        if (row['policy']=='read_only' or self.scope.get('read_only')) and not annotations.get('readOnlyHint',annotations.get('read_only_hint',False)):
            raise ToolError('host registered this provider read-only; tool needs a provider-enforced permission adapter')
        q={'format':FORMAT,'request_id':'tool-request-'+uuid4().hex,'provider_id':provider_id,'tool_name':tool_name,
            'arguments':copy.deepcopy(arguments),'catalog_sha256':version,'scope':self.scope,'generation':self.generation,
            'provider_contract':copy.deepcopy(row),'tool_schema':copy.deepcopy(schema),'catalog_tools':copy.deepcopy(tools),
            'status':'prepared','created_at':time.time()}
        q['request_sha256']=digest({k:v for k,v in q.items() if k not in ('status','created_at')})
        save(self.home/'requests'/f"{q['request_id']}.json",q)
        return {'request_id':q['request_id'],'request_sha256':q['request_sha256'],'status':'prepared',
                'provider_id':provider_id,'tool_name':tool_name,'motif_required':False}

    def request(self,qid):
        if not re.fullmatch(r'tool-request-[a-f0-9]{32}',qid):raise ToolError('invalid request_id')
        p=self.home/'requests'/f'{qid}.json'
        if not p.exists():raise ToolError('unknown request_id')
        q=json.loads(p.read_text(encoding='utf-8'))
        if q['scope']!=self.scope:raise ToolError('original task/permission/version changed')
        expected=digest({k:v for k,v in q.items() if k not in ('status','created_at','request_sha256','receipt_id')})
        if q['request_sha256']!=expected:raise ToolError('prepared request changed')
        return q,p

    async def execute_tool_call(self,request_id:str):
        """Execute an exact prepared call, checking catalog and original permission.
        Repeating this ID returns its receipt. Interrupted unknown effects never rerun.
        """
        self.guard()
        lock=self.locks.setdefault(request_id,asyncio.Lock())
        async with lock:
            q,p=self.request(request_id)
            if q['status'] in ('completed','tool_error','transport_error'):return self.receipt_summary(q)
            if q['status']=='executing':raise ToolError('interrupted tool outcome unknown; inspect retained request, do not replay effects')
            if q['generation']!=self.generation:raise ToolError('provider process restarted; prepare a fresh call against current handles')
            _,client,_,version=await self.catalog(q['provider_id'])
            if q['catalog_sha256']!=version:raise ToolError('provider schema/permissions changed; choose tool again')
            q['status']='executing';save(p,q)
            try:
                result=await client.call_tool(q['tool_name'],q['arguments'])
                raw=result.model_dump(mode='json',by_alias=True,exclude_none=True)
                q['status']='tool_error' if raw.get('isError',raw.get('is_error',False)) else 'completed'
            except Exception as e:
                raw={'isError':True,'content':[{'type':'text','text':'Provider transport failed; outcome may be unknown: '+type(e).__name__}]}
                q['status']='transport_error'
            rid='tool-result-'+request_id.removeprefix('tool-request-')
            receipt={'receipt_id':rid,'request_id':request_id,'request_sha256':q['request_sha256'],'scope':self.scope,
                     'provider_id':q['provider_id'],'tool_name':q['tool_name'],'status':q['status'],
                     'actual_mcp_result':raw,'cost':{'kind':'local_no_model','model_requests':0},'finished_at':time.time()}
            receipt['receipt_sha256']=digest(receipt);save(self.home/'results'/f'{rid}.json',receipt)
            q['receipt_id']=rid;save(p,q)
            return self.receipt_summary(q)

    def receipt_summary(self,q):return {'request_id':q['request_id'],'receipt_id':q['receipt_id'],'status':q['status'],
        'next_step':'inspect_tool_result with the actual receipt_id'}

    def inspect_tool_result(self,receipt_id:str):
        """Read the retained actual provider result, including errors and artifacts."""
        self.guard()
        if not re.fullmatch(r'tool-result-[a-f0-9]{32}',receipt_id):raise ToolError('invalid receipt_id')
        p=self.home/'results'/f'{receipt_id}.json'
        if not p.exists():raise ToolError('unknown receipt_id')
        r=json.loads(p.read_text(encoding='utf-8'))
        if r['scope']!=self.scope or r['receipt_sha256']!=digest({k:v for k,v in r.items() if k!='receipt_sha256'}):raise ToolError('tool receipt changed')
        return r

    async def close(self):
        for client in self.clients.values():await client.close()

class GeneralTools:
    """Same generic gateway in SDK and native management; no second Agent loop."""
    def gateway(self):
        self.active()
        if not hasattr(self,'_gateway'):
            import shutil
            work=self.output/'general'/'work';inputs=work/'inputs';inputs.mkdir(parents=True,exist_ok=True)
            approved={}
            for name,h in self.spec['initial_tree']['workspace']['files'].items():
                if name in ('.experiment-copy','.management-copy'):continue
                # Keep relative paths, and use only the original task snapshot.
                p=inputs/name;p.parent.mkdir(parents=True,exist_ok=True)
                source=self.root/name
                if not p.exists():
                    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=h:raise ToolError('initialize tools before moving original inputs')
                    shutil.copyfile(source,p)
                if hashlib.sha256(p.read_bytes()).hexdigest()!=h:raise ToolError('general tool source version changed')
                approved[name]=h
            save(work/'approved-inputs.json',{'files':approved})
            report=work/'report';report.mkdir(exist_ok=True);(report/'request.txt').write_text(self.spec['objective'],encoding='utf-8')
            ppt_inputs=[
                {'document_id':'doc_'+str(i),'name':n,'path':str(inputs/n),'version_sha256':h}
                for i,(n,h) in enumerate(approved.items()) if Path(n).suffix.lower() in ('.pdf','.pptx')]
            writable=not self.spec.get('rules',{}).get('read_only',False)
            save(work/'general-task.json',{'task_id':self.spec['task_id'],'objective':self.spec['objective'],'allow_output':writable})
            save(work/'job.json',{'schema_version':1,'job_id':self.spec['task_id'],'inputs':ppt_inputs,
                'instruction':self.spec['objective'],'slides':6,'template':'academic','operation':'generate',
                'allow_output':writable and bool(ppt_inputs),'allow_rsi':False,
                'document_cache':False,'rsi_dir':str(work/'rsi')})
            self._gateway=Gateway(work,{**self.learning_scope,'read_only':self.spec.get('rules',{}).get('read_only',False)},guard=self.active)
        return self._gateway
    async def discover_tools(self,query:str=''):
        """Discover general tools beyond file organization, without requiring a Motif."""
        return self.stamp(await self.gateway().discover_tools(query))
    async def describe_tool(self,provider_id:str,tool_name:str):
        """Read the actual tool schema of a host-connected MCP provider."""
        return self.stamp(await self.gateway().describe_tool(provider_id,tool_name))
    async def prepare_tool_call(self,provider_id:str,tool_name:str,arguments:dict):
        """Choose any registered provider tool using its actual schema; no effects yet."""
        from src.adapters.general_tool_replay import eligible,lane
        g=self.gateway();out=await g.prepare_tool_call(provider_id,tool_name,arguments)
        q=g.request(out['request_id'])[0]
        if eligible(q):out={**out,'status':'prepared_certifiable'}
        out={**out,'_sss_request_lane':lane(q,preparing=True)}
        return self.stamp(out)
    async def execute_tool_call(self,request_id:str):
        """Execute the prepared general tool call once under the original task scope."""
        from src.adapters.general_tool_replay import eligible,lane
        g=self.gateway();out=await g.execute_tool_call(request_id)
        q=g.request(request_id)[0]
        if lane(q):out={**out,'_sss_request_lane':lane(q)}
        return self.stamp(out,authorized=eligible(q) and out['status']=='completed')
    def inspect_tool_result(self,receipt_id:str):
        """Inspect the actual general-tool receipt, errors and output artifacts."""
        from src.adapters.general_tool_replay import lane
        g=self.gateway();out=g.inspect_tool_result(receipt_id);q=g.request(out['request_id'])[0]
        if lane(q):out={**out,'_sss_request_lane':lane(q)}
        return self.stamp(out)
