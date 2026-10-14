"""Mine source-bound read-only batches from completed normal tool trajectories.

This is a shadow hypothesis library, not an execution certificate. Engineering
defines the permitted capabilities; the preceding tool sets and argument edges
are discovered from traces. Semantic text and writes never become reusable code.
"""
from collections import defaultdict
import json
from pathlib import Path
from .native_motif_compiler import digest, root_events
from .paper_shadow_compiler import file_hash, arguments, artifact_path

P = 'mcp__paper_checks__'
READS = {P+'read_pinned_paper_citations': 'source_id',
         P+'read_pinned_citation_records':'citation_id',
         P+'fetch_pinned_cited_preprint_metadata':'citation_id',
         P+'fetch_pinned_formal_reference_metadata':'citation_id',
         P+'recover_pinned_formal_reference_queries':'citation_id'}
SAFE = set(READS) | {P+'pin_paper_citations','check_paper_triage','read_current_triage'}


def steps(run):
    current=None; calls={}; rows=[]
    for e in root_events(Path(run)):
        d=e.get('data',{})
        if e['type']=='assistant/message':
            current={'ordinal':len(rows)+1,'content':d['message']['content'],'calls':[]};rows.append(current)
        elif e['type']=='tool/call':
            row={**d,'arguments':arguments(d['arguments']),'ok':False,'output':None}
            calls[d['callId']]=row;current['calls'].append(row)
        elif e['type']=='tool/result':
            for b in d.get('message',{}).get('content',[]):
                r=calls.get(b.get('toolCallId'))
                if not r:continue
                r['ok']=not d.get('error') and not b.get('isError')
                try:r['output']=json.loads(b['content'][0]['text'])
                except (ValueError,KeyError,TypeError):pass
    return rows


def recipe(previous, current, config, work):
    targets=current['calls']
    if not targets or len({t['name'] for t in targets})!=len(targets):return None
    # Initial case binding is a task goal, not a remembered identifier.
    if previous is None:
        if len(targets)!=1 or targets[0]['name']!=P+'pin_paper_citations' or targets[0]['arguments']!={'case_id':config['case']}:return None
        return {'anchor':[],'anchor_result':'task_start','nodes':[{'tool':targets[0]['name'],'bindings':{'case_id':{'task_field':'case_id'}}}]}
    anchors=previous['calls']
    if not anchors:return None
    names=sorted(a['name'] for a in anchors)
    if len(set(names))!=len(names):return None
    if len(anchors)==1 and anchors[0]['name']=='check_paper_triage':
        old=anchors[0].get('output');target=targets[0] if len(targets)==1 else None
        if (anchors[0]['ok'] and isinstance(old,dict) and old.get('status')=='needs_repair' and
                old.get('source_version')==config['input_version'] and old.get('report_sha256') and target and
                target['name']=='read_current_triage' and target['arguments']=={} and target['ok'] and
                isinstance(target.get('output'),dict) and target['output'].get('source_version')==config['input_version'] and
                target['output'].get('report_sha256')==old['report_sha256']):
            return {'anchor':names,'anchor_result':'needs_repair','artifact':'triage.json',
                    'nodes':[{'tool':'read_current_triage','bindings':{}}]}
        return None
    if len(anchors)==1 and anchors[0]['name'] in {'write','edit'}:
        a=anchors[0]
        if not artifact_path(a['arguments'].get('file_path'),work):return None
        expected='check_paper_triage' if a['ok'] else 'read_current_triage'
        if (len(targets)!=1 or targets[0]['name']!=expected or targets[0]['arguments']!={} or
                not targets[0]['ok'] or not isinstance(targets[0]['output'],dict) or
                targets[0]['output'].get('source_version')!=config['input_version']):return None
        if expected=='check_paper_triage' and targets[0]['output'].get('check')!='paper_citation_triage_structure':return None
        return {'anchor':names,'anchor_result':'success' if a['ok'] else 'failed',
                'artifact':'triage.json','nodes':[{'tool':expected,'bindings':{}}]}
    if any(not a['ok'] or a['name'] not in SAFE or not isinstance(a['output'],dict) or
           a['output'].get('version_sha256')!=config['input_version'] for a in anchors):return None
    nodes=[]
    for t in sorted(targets,key=lambda r:r['name']):
        param=READS.get(t['name'])
        if (not param or set(t['arguments'])!={param} or not t['ok'] or not isinstance(t['output'],dict)
                or t['output'].get('version_sha256')!=config['input_version']):return None
        sources=sorted([(a['name'],param) for a in anchors if a['output'].get(param)==t['arguments'][param]])
        if not sources:return None
        # Multiple equal-current handles are co-constraints, not semantic ranking.
        nodes.append({'tool':t['name'],'bindings':{param:{'source_fields':[{'tool':n,'field':f} for n,f in sources]}}})
    return {'anchor':names,'anchor_result':'success','nodes':nodes}


def compile_flow_shadow(runs):
    groups=defaultdict(list);graphs={};sources={};schemas=None;order=None;epoch=None;sessions=set()
    for value in runs:
        run=Path(value);c=json.loads((run/'manifest.json').read_text());m=json.loads((run/'metrics.json').read_text())
        if c['mode']!='baseline' or not c.get('flow_delivery') or c['delivery_check_mode']!='off' or m['status']!='completed' or not all(m[k] for k in ['source_unchanged','output_coverage_valid','delivery_check_passed']):
            raise ValueError('completed normal flow baseline with valid provenance required')
        if c['session_id'] in sessions:raise ValueError('duplicate training session')
        sessions.add(c['session_id'])
        schema_rows=[]
        for p in sorted((run/'requests').glob('*.json')):
            tools=json.loads(p.read_text())['tools'];new={t['function']['name']:digest(t['function']['parameters']) for t in tools};names=[t['function']['name'] for t in tools]
            if schemas is not None and (new!=schemas or names!=order):raise ValueError('tool contract/order drift')
            schemas,order=new,names;schema_rows.append(p)
        if epoch is not None and epoch!=c['code_sha256']:raise ValueError('compiler input code epoch drift')
        epoch=c['code_sha256'];rows=steps(run)
        if len(rows)!=m['actual_requests'] or len(schema_rows)!=len(rows):raise ValueError('request boundary mismatch')
        check=json.loads((run/'delivery-check-config.json').read_text())
        sources[run.name]={'session_id':c['session_id'],'input_version':c['input_version'],'events_sha256':file_hash(run/'session-events.jsonl'),
            'manifest_sha256':file_hash(run/'manifest.json'),'requests':{p.name:file_hash(p) for p in schema_rows}}
        for i,row in enumerate(rows):
            g=recipe(rows[i-1] if i else None,row,c,check['work'])
            if not g:continue
            key=digest(g);graphs[key]=g
            groups[key].append({'run_id':run.name,'session_id':c['session_id'],'target_request':row['ordinal'],
                'contains_text':any(b.get('type')=='text' and b.get('text','').strip() for b in row['content'])})
    if not sources:raise ValueError('no training sources')
    # Only the offline miner and non-executing observer can migrate here. This
    # cannot silently certify altered baseline tools, prompts, or source logic.
    expected=dict(epoch);migrations=[];root=Path(__file__).resolve().parents[2]
    for path,old in epoch.items():
        current=file_hash(root/path)
        if current==old:continue
        if path not in {'src/adapters/paper_flow_shadow_compiler.py','src/adapters/dsh_paper_flow_shadow.ts'}:
            raise ValueError('baseline behavior changed; a new training epoch is required')
        expected[path]=current;migrations.append({'path':path,'training_sha256':old,'runtime_sha256':current,
            'reason':'offline mining/shadow-only observer; absent from baseline execution'})
    library={'schema_version':1,'scope':'source_bound_readonly_batch_shadow','execution_policy':'shadow_only',
        'tool_schema_sha256':schemas,'tool_order':order,'code_sha256':expected,'training_code_sha256':epoch,
        'shadow_only_migrations':migrations,'source_traces':sources,
        'motifs':[{'motif_id':'paper-flow-'+key[:12],'graph':graphs[key],'training_witnesses':w,
                   'training_session_count':len({x['session_id'] for x in w})} for key,w in sorted(groups.items())],
        'limitations':['same-paper variants, not independent papers','semantic report content remains model-owned',
                       'prediction is not an execution certificate','all nonempty response text excluded from strict whole-request counts']}
    library['manifest_digest']=digest(library);return library
