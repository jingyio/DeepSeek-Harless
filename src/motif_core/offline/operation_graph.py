"""Name-independent, bounded parameter DAGs from native MCP decisions.

Operators declare authority and exportable fields; they do not declare a route.
Actual calls discover the route. Existing generated nodes can prove an inherited
prefix, never supply evidence for a newly learned parameter relation.
"""
from __future__ import annotations
import copy
from collections import defaultdict
from .experience_registry import digest

FORMAT='sss-operation-graph-v2'
CONTRACT='sss-mcp-learning-v1'

def at(value,path):
    parts=path.split('.')
    for i,part in enumerate(parts):
        wildcard=part.endswith('[]');key=part[:-2] if wildcard else part
        if not isinstance(value,dict) or key not in value:return None
        value=value[key]
        if wildcard:
            if not isinstance(value,list) or not 1<=len(value)<=40:return None
            suffix='.'.join(parts[i+1:])
            return [at(v,suffix) if suffix else v for v in value]
    return value

def scalar(value):
    return isinstance(value,str) and 0<len(value)<=512 and not any(ord(c)<32 for c in value)

def bindable(value,schema):
    if scalar(value):return schema.get('type','string')=='string'
    return (isinstance(value,list) and 1<=len(value)<=40 and all(scalar(v) for v in value)
        and len(set(value))==len(value) and schema.get('type')=='array'
        and schema.get('items',{}).get('type')=='string' and 1<=schema.get('maxItems',0)<=40
        and schema.get('minItems',1)<=len(value)<=schema['maxItems'])

def catalog(schemas):
    result={}
    for tool in schemas:
        meta=tool.get('_meta',tool.get('meta',{})) or {};c=meta.get('sss_learning')
        if not c:continue
        if c.get('format')!=CONTRACT or c.get('effect') not in ('read','stage','authorized_write','semantic'):
            raise ValueError('invalid declared MCP learning contract')
        if type(c.get('auto_continue')) is not bool or not isinstance(c.get('exports'),list):
            raise ValueError('invalid MCP transfer contract')
        schema=tool.get('inputSchema',tool.get('input_schema'))
        if not isinstance(schema,dict):raise ValueError('missing actual input schema')
        name=tool['name'];name=name if name.startswith('mcp__') else 'mcp__'+tool['server_name']+'__'+name
        result[name]={'contract':c,'schema':schema,'schema_sha256':digest(schema)}
    return result

def valid_output(row,contract,scope):
    out=row.get('out');c=contract['contract']
    if not isinstance(out,dict) or out.get('_sss_scope')!=scope:return False
    if c.get('statuses') and out.get('status') not in c['statuses']:return False
    if any(scope.get(k)!=v for k,v in c.get('scope_requirements',{}).items()):return False
    if c['effect']=='authorized_write' and out.get('_sss_authorized') is not True:return False
    return True

def request_lane(row,tools,scope):
    import re
    out=row.get('out') or {};c=tools.get(row['name'],{}).get('contract',{});v=out.get('_sss_request_lane',{})
    if (c.get('request_lane')!='sss-prepared-request-v1' or out.get('_sss_scope')!=scope
        or v.get('format')!='sss-prepared-request-v1'
        or not (v.get('isolated_outputs') is True or c.get('effect')=='stage' and v.get('stage_only') is True)
        or not re.fullmatch(r'tool-request-[a-f0-9]{32}',v.get('request_id',''))
        or not re.fullmatch(r'[a-f0-9]{64}',v.get('request_sha256','')) or out.get('request_id')!=v['request_id']):return None
    args=row['args']
    if c['effect']=='stage':
        if out.get('status') not in ('prepared','prepared_certifiable') or out.get('request_sha256')!=v['request_sha256']:return None
    else:
        if out.get('status')!='completed':return None
        receipt=v['request_id'].replace('tool-request-','tool-result-')
        if out.get('receipt_id')!=receipt:return None
        actual=args.get('request_id') if c['effect']=='authorized_write' else args.get('receipt_id')
        if actual!=(v['request_id'] if c['effect']=='authorized_write' else receipt):return None
    return v

def witnesses(rows,tools,scope,parent_policies=()):
    """Extend real model roots by exported arguments, allowing declared safe reads."""
    found=[]
    for start,root in enumerate(rows):
        if root.get('message_seq') is None or root.get('generated') or root['name'] not in tools:continue
        if not valid_output(root,tools[root['name']],scope):continue
        nodes=[{'tool':root['name'],'bindings':{}}];used=[root];inherited=None
        root_lane=request_lane(root,tools,scope)
        for row in rows[start+1:start+64]:
            tc=tools.get(row['name']);bindings={}
            peer=request_lane(row,tools,scope) if root_lane else None
            if peer and peer['request_id']!=root_lane['request_id']:continue
            if tc and tc['contract'].get('safe_interleaving') and tc['contract']['effect']=='read' and valid_output(row,tc,scope):continue
            if not tc or not tc['contract']['auto_continue'] or not valid_output(row,tc,scope):break
            schema=tc['schema'];required=set(schema.get('required',[]));args=row['args']
            # No learned semantic constants, hidden defaults or arbitrary code.
            if set(args)!=required or not required:break
            for param,value in args.items():
                parameter=schema.get('properties',{}).get(param,{})
                if not bindable(value,parameter):break
                origins=[]
                for i,previous in enumerate(used):
                    for path in tools[previous['name']]['contract']['exports']:
                        v=at(previous['out'],path)
                        if bindable(v,parameter) and v==value:origins.append({'node':i,'path':path})
                if len(origins)!=1:break
                bindings[param]=origins[0]
            if set(bindings)!=required:break
            node={'tool':row['name'],'bindings':bindings}
            if row.get('generated'):
                matching=[p for p in parent_policies if p['artifact']['nodes'][:len(nodes)+1]==nodes+[node]]
                if not matching:break
                inherited=max(matching,key=lambda p:len(p['artifact']['nodes']))['policy_digest']
            elif row.get('message_seq') is None:break
            nodes.append(node);used.append(row)
            if len(nodes)==8:break
        if len(nodes)<2:continue
        native_new=[i for i,r in enumerate(used[1:],1) if not r.get('generated')]
        if not native_new:continue
        values={str(i)+':'+param:at(used[b['node']]['out'],b['path'])
                for i,n in enumerate(nodes[1:],1) for param,b in n['bindings'].items() if i in native_new}
        found.append({'nodes':nodes,'values':values,'calls':[r['call_id'] for r in used],
                      'native_new_nodes':native_new,'inherited_policy':inherited})
    return found

def discover_graphs(frames):
    groups=defaultdict(list)
    for f in frames:
        for w in witnesses(f['rows'],f['tools'],f['scope'],f.get('parents',())):
            key=digest({'nodes':w['nodes'],'catalog':f['tools'],'execution_version':f['scope']['execution_version']})
            groups[key].append((f,w))
    candidates=[];excluded=[]
    for key,pairs in groups.items():
        unique={}
        for f,w in pairs:unique.setdefault(f['fingerprint'],(f,w))
        pairs=list(unique.values())
        if len(pairs)<2:
            excluded.append({'opportunity_key':key,'reason':'two independent native decisions required'});continue
        fields=set(pairs[0][1]['values'])
        if not fields or any(len({digest(w['values'].get(k)) for f,w in pairs})<2 for k in fields):
            excluded.append({'opportunity_key':key,'reason':'constant/unchanged values cannot prove transfer'});continue
        f,w=pairs[0];artifact={'kind':'learned_mcp_operation_dag','status':'compiled_candidate','nodes':w['nodes'],
          'tool_contracts':{n['tool']:f['tools'][n['tool']] for n in w['nodes']},'max_nodes':8,
          'interleaving_contracts':{n:t for n,t in f['tools'].items() if t['contract'].get('safe_interleaving') and t['contract']['effect']=='read'},
          'request_lane_contracts':{n:t for n,t in f['tools'].items() if t['contract'].get('request_lane')=='sss-prepared-request-v1'} if request_lane(f['rows'][next(i for i,r in enumerate(f['rows']) if r['call_id']==w['calls'][0])],f['tools'],f['scope']) else {},
          'execution_version':f['scope']['execution_version'],'certification_contract':'sss-operation-certification-v2',
          'source_task_fingerprints':[f['fingerprint'] for f,w in pairs],
          'witnesses':[{'session_id':f['trace_id'],'calls':w['calls'],'native_new_nodes':w['native_new_nodes'],
                       'inherited_policy':w['inherited_policy'],'events_sha256':f['record']['events_sha256']} for f,w in pairs]}
        candidates.append({'key':key,'kind':'operation_graph','compiled':artifact,'frames':[f for f,w in pairs]})
    # Retain independently observed shorter routes: a longer route can fail
    # certification without disproving a shorter one. Never invent prefixes;
    # each candidate above still needs its own two native witnesses and values.
    candidates.sort(key=lambda c: -len(c['compiled']['nodes']))
    return candidates,excluded

def certify_graph(compiled,f):
    if f['fingerprint'] in compiled['source_task_fingerprints']:raise ValueError('native certification overlaps training')
    matches=[w for w in witnesses(f['rows'],f['tools'],f['scope'],f.get('parents',())) if w['nodes']==compiled['nodes']]
    if not matches:raise ValueError('new native graph witness unavailable')
    # A native decision must introduce every node beyond any inherited prefix.
    if f['scope']['execution_version']!=compiled['execution_version']:raise ValueError('operator version changed')
    a=copy.deepcopy(compiled);a.update(status='trace_validated_effectful' if any(t['contract']['effect']=='authorized_write' for t in a['tool_contracts'].values()) else 'trace_validated_read_only',
        validation_task_fingerprint=f['fingerprint'],validation_witness=matches[0])
    a['certified_digest']=digest(a)
    p={'schema_version':1,'format':FORMAT,'execution_version_sha256':compiled['execution_version'],'artifact':a}
    p['policy_digest']=digest(p);return p
