"""Mine bounded native read continuations from repeated runs of ONE paper.

This is a separate diagnostic certification scope, never independent-task
certification. Unknown shell/programs and all writes remain model-controlled.
"""
from __future__ import annotations
from collections import defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shlex
from .trace_paths import relative_trace_path

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def normal(value, work):
    roots = [str(work), work.as_posix()]
    if isinstance(value,str):
        for root in dict.fromkeys(roots):
            value=value.replace(root,'${WORK}')
        return value
    if isinstance(value,list):return [normal(x,work) for x in value]
    if isinstance(value,dict):
        result={}
        for k,v in value.items():
            if k=='description':continue
            if k in {'file_path','workdir'} and isinstance(v,str):
                relative=relative_trace_path(v,roots)
                result[k]=('${WORK}' if relative=='.' else '${WORK}/'+relative) if relative is not None else v
            else:result[k]=normal(v,work)
        return result
    return value

def local_path(value,cwd='.'):
    if value.startswith('${WORK}'):cwd='.'
    value=value.replace('${WORK}/','').replace('${WORK}','.')
    if PureWindowsPath(value).anchor or '\\' in value or value.startswith('/') or '..' in PurePosixPath(value).parts or any(c in value for c in '*?[]$`\n\x00'):
        raise ValueError('unbounded or external native path')
    return str(PurePosixPath(cwd)/value)

def compile_read(call, files):
    name,args=call['name'],call['arguments']
    if name=='read':
        if set(args)-{'file_path','offset','limit'}:raise ValueError('unknown read argument')
        path=local_path(args['file_path'])
        if path not in files:raise ValueError('read file version missing')
        return {'tool':name,'arguments':args,'dependencies':{path:files[path]},'protocol':'native-file-read-v1'}
    if name!='bash' or set(args)-{'command','timeoutMs','description','workdir','run_in_background'} or args.get('run_in_background') is True:
        raise ValueError('only bounded native reads are executable')
    text=args['command']
    if any(c in text.replace('${WORK}','WORK') for c in '\n$`><*?[]\x00'):
        raise ValueError('shell expansion, redirect or program rejected')
    lexer=shlex.shlex(text,posix=True,punctuation_chars=';&|');lexer.whitespace_split=True
    tokens=list(lexer);cwd=local_path(args.get('workdir','.'))
    if tokens[:1]==['cd']:
        if len(tokens)<4 or tokens[2]!='&&':raise ValueError('unsupported directory change')
        cwd=local_path(tokens[1],cwd);tokens=tokens[3:]
    if not tokens:raise ValueError('empty native program')
    stages=[];part=[]
    for token in tokens+[';']:
        if token in {';','&&','|'}:
            if not part:raise ValueError('empty pipeline stage')
            stages.append({'argv':part,'separator':token});part=[]
        elif token in {'&','||',';;','|&'}:raise ValueError('unsupported shell operator')
        else:part.append(token)
    dependencies={}
    options={'cat':{'-n','-b','-s','-v','-E','-T','-A','--'},
             'head':{'-n','-c','--'},'tail':{'-n','-c','--'},
             'grep':{'-n','-i','-E','-F','-c','-o','-H','-h','-v','-s','-e','--'},
             'wc':{'-l','-w','-c','-m','-L','--'},'sha256sum':{'-b','-t','--'},
             'file':{'-b','-i','--'},'sort':{'-n','-r','-u','-h','-f','-b','--'},
             'uniq':{'-c','-d','-u','-i','--'},'pdfinfo':set(),'pdffonts':set(),'pwd':set(),'echo':set()}
    for stage in stages:
        argv=stage['argv'];program=argv[0]
        if program not in {'pwd','echo','cat','head','tail','grep','wc','sha256sum','file','pdfinfo','pdffonts','sort','uniq'}:
            raise ValueError('unapproved executable')
        for option in argv[1:]:
            if option.startswith('-') and program!='echo' and option not in options[program] and not (
                    program in {'head','tail'} and re.fullmatch(r'-(?:n|c)?[0-9]{1,7}',option)):
                raise ValueError('unapproved native read option')
        if program in {'sort','uniq'} and any(a in {'-o','--output'} or a.startswith('--output=') for a in argv[1:]):
            raise ValueError('output file option')
        if program=='file' and any(a.startswith(('-f','--files-from','-C','--compile')) for a in argv[1:]):
            raise ValueError('external file list or magic compilation')
        if program in {'pdfinfo','pdffonts'} and len(argv)!=2:raise ValueError('PDF tool needs one local file')
        # Every file-like operand must have a captured, in-root byte version.
        # Regex/format flags are literals; they cannot introduce shell code.
        for item in argv[1:]:
            if item.startswith('-') or program in {'echo','pwd'}:continue
            try:path=local_path(item,cwd)
            except ValueError:
                if program=='grep' and item==argv[1]:continue
                raise
            if path in files:dependencies[path]=files[path]
            elif '${WORK}' in item or '/' in item or re.search(r'\.(tex|bib|log|bbl|pdf|txt|md|zip)$',item):
                raise ValueError('uncaptured file operand')
    if not dependencies:raise ValueError('no witnessed local file dependency')
    return {'tool':'bash','arguments':args,'dependencies':dependencies,
            'protocol':'native-read-argv-v1','program':{'cwd':cwd,'stages':stages}}

def jsonl(path):
    # Literal Unicode paragraph separators are legal within JSON strings.
    # splitlines() would split one real tool result into invalid fake records.
    return [json.loads(x) for x in path.read_text().split('\n') if x.strip()]

def root_events(run):
    scoped=run/'session-events.jsonl'
    if scoped.exists():
        root=json.loads((run/'manifest.json').read_text())['session_id']
        rows=jsonl(scoped)
        if any(not r.get('session_id') for r in rows):
            raise ValueError('event session identity missing')
        return [r['event'] for r in rows if r['session_id']==root]
    events=jsonl(run/'agent-events.jsonl')
    if any(e['type']=='tool/call' and e['data']['name']=='subagent' for e in events):
        raise ValueError('legacy multi-agent trace lacks event session identity')
    return events

def trace_steps(run):
    work=run/'work';events=root_events(run)
    root=json.loads((run/'manifest.json').read_text())['session_id'] if (run/'session-events.jsonl').exists() else None
    versions={r['call_id']:r['snapshot'] for r in jsonl(run/'file-versions.jsonl')
              if root is None or r.get('session_id')==root}
    calls={};groups=defaultdict(list)
    for event in events:
        if event['type']=='tool/call':
            d=event['data'];args=d['arguments']
            if isinstance(args,str):args=json.loads(args)
            calls[d['callId']]={'name':d['name'],'arguments':normal(args,work),'step':d.get('step')}
        if event['type']!='tool/result':continue
        for block in event['data'].get('message',{}).get('content',[]):
            if block.get('type')!='tool-result':continue
            call=calls.get(block['toolCallId']);snap=versions.get(block['toolCallId'])
            if not call:continue
            output=normal(block.get('content',[]),work)
            groups[call['step']].append({'call':{k:v for k,v in call.items() if k!='step'},
                'ok':not block.get('isError',False),'output_sha256':digest(output),'snapshot':snap})
    return [groups[k] for k in sorted(k for k in groups if isinstance(k,int))]

def witnessed_job_reads(run):
    """Use the native background acknowledgement, never stdout-made-up IDs."""
    events=root_events(run)
    calls={};owned=set();rows=[]
    for event in events:
        if event['type']=='tool/call':
            d=event['data'];args=d['arguments']
            calls[d['callId']]={'name':d['name'],'arguments':json.loads(args) if isinstance(args,str) else args}
        if event['type']!='tool/result':continue
        for block in event['data'].get('message',{}).get('content',[]):
            call=calls.get(block.get('toolCallId'))
            if not call or block.get('isError'):continue
            args=call['arguments'];content=block.get('content',[])
            if call['name']=='bash' and args.get('run_in_background') is True and len(content)==1:
                match=re.fullmatch(r'started background job ([^\s]+)',content[0].get('text',''))
                if match:owned.add(match.group(1))
            if call['name']=='job_output' and args.get('job_id') in owned:
                extra={k:v for k,v in args.items() if k!='job_id'}
                if set(extra)-{'wait','timeout_ms'}:continue
                if 'wait' in extra and type(extra['wait']) is not bool:continue
                if 'timeout_ms' in extra and (type(extra['timeout_ms']) not in {int,float} or not 1<=extra['timeout_ms']<=600000):continue
                rows.append({'body':{'source_tool':'bash','source_field':'jobId','target_tool':'job_output',
                                     'target_param':'job_id','extra_arguments':extra,'only_when_terminal':True},
                             'source_job_id':args['job_id']})
    return rows

def compile_native_runs(exp, prompt_sha, input_sha):
    runs=[exp/'runs'/f'baseline-{i:02d}' for i in range(1,6)]
    schemas={};identities=[];occurrences=defaultdict(list);jobs=defaultdict(list);rejected=defaultdict(int);settings=None;tool_order=None
    for index,run in enumerate(runs):
        cfg=json.loads((run/'manifest.json').read_text())
        metrics=json.loads((run/'metrics.json').read_text())
        if cfg['prompt_sha256']!=prompt_sha or cfg['input_sha256']!=input_sha or metrics['status']!='completed':
            raise ValueError('five completed frozen-prompt native traces required')
        current={k:cfg[k] for k in ('model','provider','reasoning_effort','output_cap','compression','sandbox','approval')}
        if settings is not None and current!=settings:raise ValueError('baseline effective settings drift')
        settings=current
        identities.append({'run_id':run.name,'session_id':cfg['session_id'],
                           'events_sha256':hashlib.sha256((run/'agent-events.jsonl').read_bytes()).hexdigest(),
                           'report_produced':bool(metrics['reports']),'quality_review':'not_reviewed'})
        for row in witnessed_job_reads(run):
            jobs[digest(row['body'])].append({**row,'run_id':run.name,'index':index})
        for request in sorted((run/'requests').glob('*.json')):
            tools=json.loads(request.read_text()).get('tools',[])
            order=[tool['function']['name'] for tool in tools]
            if tool_order is not None and order!=tool_order:raise ValueError('native tool order drift')
            tool_order=order
            for tool in tools:
                f=tool['function'];h=digest(f['parameters']);name=f['name']
                if name in schemas and schemas[name]!=h:raise ValueError('native tool schema drift')
                schemas[name]=h
        steps=trace_steps(run)
        for anchor,target in zip(steps,steps[1:]):
            if not anchor or not target or len(target)>8 or not all(r['ok'] for r in anchor+target):continue
            try:
                nodes=[]
                for row in target:
                    if not row['snapshot'] or not row['snapshot']['complete']:raise ValueError('version snapshot incomplete')
                    nodes.append({**compile_read(row['call'],row['snapshot']['files']),
                                  'expected_output_sha256':row['output_sha256']})
                prefix=[{'call':r['call'],'output_sha256':r['output_sha256']} for r in anchor]
                body={'anchor':prefix,'nodes':nodes}
                occurrences[digest(body)].append({'run_id':run.name,'index':index,'body':body})
            except (ValueError,KeyError) as exc:rejected[str(exc)]+=1
    motifs=[]
    for key,rows in occurrences.items():
        training={r['run_id'] for r in rows if r['index']<3}
        heldout={r['run_id'] for r in rows if r['index']>=3}
        if len(training)<2 or not heldout:continue
        motifs.append({'motif_id':'native-read-'+key[:12],**rows[0]['body'],
                       'training_runs':sorted(training),'validation_runs':sorted(heldout),
                       'status':'same_task_trace_validated_read_only'})
    job_motifs=[]
    for key,rows in jobs.items():
        train={r['run_id'] for r in rows if r['index']<3};heldout={r['run_id'] for r in rows if r['index']>=3}
        # Native job IDs are session-local (e.g. bash-1). Distinct owned job
        # instances are identified by run + ID, not a globally unique string.
        if len(train)>=2 and heldout and len({(r['run_id'],r['source_job_id']) for r in rows})>=3:
            job_motifs.append({'motif_id':'native-job-'+key[:12],**rows[0]['body'],
                               'training_runs':sorted(train),'validation_runs':sorted(heldout),
                               'observed_job_instances':sorted({r['run_id']+':'+r['source_job_id'] for r in rows}),
                               'status':'same_task_witnessed_job_read'})
    result={'schema_version':1,'certification_scope':'same_task_repeated_runs',
            'prompt_sha256':prompt_sha,'input_sha256':input_sha,'tool_schema_hashes':schemas,'tool_order':tool_order,
            'trace_evidence':identities,'effective_settings':settings,'motifs':motifs,'job_motifs':job_motifs,'candidate_count':len(occurrences),
            'rejected':dict(rejected),'quality_review':'not_reviewed',
            'limitations':['no cross-task certification','no automatic writes, network fetch or arbitrary script evaluation']}
    result['manifest_digest']=digest(result);return result
