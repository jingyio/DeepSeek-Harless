"""Learn finite, guarded MCP control flow from independent native decisions.

Tools declare observable control domains, never the next tool or a route. Edges,
parameter transfers, exits and loops all come from actual calls. Unknown cases
return to the model. No expressions, semantic constants or unbounded execution.
"""
from __future__ import annotations
from collections import defaultdict
from copy import deepcopy
from .experience_registry import digest
from .operation_graph import at, bindable, scalar, valid_output

FORMAT = 'sss-operation-flow-v3'
CERT = 'sss-operation-certification-v3'
MAX_STEPS = 64


def guard(out, contract):
    result = {}
    for path, domain in contract.get('control_fields', {}).items():
        # Presence must distinguish absent/malformed data from explicit EOF.
        value = out
        for key in path.split('.'):
            if not isinstance(value, dict) or key not in value:
                raise ValueError('missing declared control field')
            value = value[key]
        if domain == 'nullable_handle':
            if value is not None and not scalar(value):
                raise ValueError('malformed continuation handle')
            result[path] = 'null' if value is None else 'present'
        elif domain == 'boolean' and type(value) is bool:
            result[path] = value
        elif isinstance(domain, list) and type(value) in (str, bool, int) and value in domain:
            result[path] = value
        else:
            raise ValueError('unknown control domain/value')
    return result


def transfer(previous, row, tools):
    schema = tools[row['name']]['schema']
    required = set(schema.get('required', []))
    if not required or set(row['args']) != required:
        return None
    bindings = {}
    for key, value in row['args'].items():
        prop = schema.get('properties', {}).get(key, {})
        origins = [p for p in tools[previous['name']]['contract']['exports']
                   if '[]' not in p and bindable(at(previous['out'], p), prop) and at(previous['out'], p) == value]
        if not bindable(value, prop) or len(origins) != 1:
            return None
        bindings[key] = origins[0]
    return bindings


def safe_interleaving(row,tools,scope):
    tc=tools.get(row['name'])
    return bool(tc and tc['contract']['effect']=='read' and
                (tc['contract'].get('flow_interleaving') or tc['contract'].get('safe_interleaving'))
                and valid_output(row,tc,scope))


def inherited_edge(edge,parents):
    for p in parents:
        a=p['artifact']
        if p.get('format')==FORMAT and edge in a['edges']:return True
        if p.get('format') in ('sss-operation-graph-v1','sss-operation-graph-v2'):
            for i,n in enumerate(a['nodes'][1:],1):
                if (a['nodes'][i-1]['tool']==edge['from'] and n['tool']==edge['to']
                        and set(n['bindings'])==set(edge['bindings'])
                        and all(b=={'node':i-1,'path':edge['bindings'][key]} for key,b in n['bindings'].items())):
                    return True
    return False


def episodes(f):
    rows, tools, scope = f['rows'], f['tools'], f['scope']
    for start, root in enumerate(rows):
        tc = tools.get(root['name'])
        if (not tc or tc['contract']['auto_continue'] and not tc['contract'].get('control_fields') or not tc['contract']['exports']
                or root.get('generated') or root.get('message_seq') is None
                or not valid_output(root, tc, scope)):
            continue
        path = [root]; edges = []; previous = root
        for row in rows[start+1:start+MAX_STEPS*16]:
            target = tools.get(row['name'])
            if not target or not target['contract']['auto_continue'] or target['contract']['effect']=='semantic' or not valid_output(row, target, scope):
                if safe_interleaving(row,tools,scope):continue
                break
            binding = transfer(previous, row, tools)
            if binding is None:
                if safe_interleaving(row,tools,scope):continue
                break
            if len(path)>=MAX_STEPS:break
            try:
                edge = {'from': previous['name'], 'guard': guard(previous['out'], tools[previous['name']]['contract']),
                        'to': row['name'], 'bindings': binding}
            except ValueError:
                break
            if row.get('generated'):
                # Generated prefixes may only inherit an already certified edge.
                if not inherited_edge(edge,f.get('parents', [])):
                    break
            elif row.get('message_seq') is None:
                break
            edges.append(edge); path.append(row); previous = row
            if not target['contract']['exports']:
                try:
                    terminal = {'from': row['name'], 'guard': guard(row['out'], target['contract']),
                                'to': None, 'bindings': {}}
                except ValueError:
                    break
                if any(not r.get('generated') for r in path[1:]):
                    yield {'root': root['name'], 'edges': edges + [terminal], 'path': path}
                break


def discover_flows(frames):
    groups = defaultdict(list); rejected = []
    for f in frames:
        for ep in episodes(f):
            key = digest({'root': ep['root'], 'catalog': f['tools'], 'execution_version': f['scope']['execution_version']})
            groups[key].append((f, ep))
    candidates = []
    for key, pairs in groups.items():
        evidence = defaultdict(dict); routes = {}; values = defaultdict(lambda:defaultdict(set)); ambiguous = False
        for f, ep in pairs:
            for i, edge in enumerate(ep['edges']):
                case = digest({'from': edge['from'], 'guard': edge['guard']})
                if case in routes and routes[case] != edge:
                    ambiguous = True
                routes[case] = edge
                # An inherited edge cannot witness a new edge/branch decision.
                native = not ep['path'][i if i==len(ep['path'])-1 else i+1].get('generated')
                if native:
                    evidence[case][f['fingerprint']] = f
                    if edge['to'] is not None:
                        for param, path in edge['bindings'].items():
                            values[(case, param)][f['fingerprint']].add(digest(at(ep['path'][i]['out'], path)))
        if ambiguous or any(len(v) < 2 for v in evidence.values()) or len(evidence) != len(routes):
            rejected.append({'opportunity_key': key, 'reason': 'ambiguous route or fewer than two independent native witnesses per branch/exit'})
            continue
        if any(len({digest(sorted(xs)) for xs in v.values()}) < 2 for v in values.values()):
            rejected.append({'opportunity_key': key, 'reason': 'constant values cannot prove control-flow transfer'})
            continue
        edges = sorted(routes.values(), key=digest)
        tools = pairs[0][0]['tools']; root = pairs[0][1]['root']
        names = [root, *sorted({e['from'] for e in edges} - {root})]
        # Linear chains already use v2. V3 must add observed conditional routing
        # or a back-edge, not relabel a fixed sequence as control-flow learning.
        conditional = any(sum(e['from'] == n for e in edges) > 1 for n in names)
        if not conditional or len(names) > 16 or len(edges) > 64:
            continue
        unique = {f['fingerprint']: f for f, ep in pairs}
        compiled = {'kind': 'learned_mcp_control_flow', 'status': 'compiled_candidate',
                    'nodes': [{'tool': n} for n in names], 'root': root, 'edges': edges,
                    'tool_contracts': {n: tools[n] for n in names}, 'max_steps': MAX_STEPS,
                    'interleaving_contracts':{n:t for n,t in tools.items() if t['contract']['effect']=='read' and (t['contract'].get('flow_interleaving') or t['contract'].get('safe_interleaving'))},
                    'execution_version': pairs[0][0]['scope']['execution_version'],
                    'certification_contract': CERT, 'source_task_fingerprints': list(unique),
                    'branch_evidence': {c: sorted(v) for c, v in evidence.items()},
                    'witnesses': [{'trace_id': f['trace_id'], 'events_sha256': f['record']['events_sha256'],
                                   'calls': [r['call_id'] for r in ep['path']]} for f, ep in pairs]}
        candidates.append({'key': key, 'kind': 'operation_graph', 'compiled': compiled, 'frames': list(unique.values())})
    return candidates, rejected


def certify_flow(compiled, f):
    if f['fingerprint'] in compiled['source_task_fingerprints']:
        raise ValueError('native control-flow certification overlaps training')
    if f['scope']['execution_version'] != compiled['execution_version']:
        raise ValueError('control-flow execution version changed')
    eps = [ep for ep in episodes(f) if ep['root'] == compiled['root']]
    witnessed = {digest(e) for ep in eps for e in ep['edges']}
    if not witnessed or any(digest(e) not in witnessed for e in compiled['edges']):
        raise ValueError('new native control-flow witness does not cover every branch/exit')
    a = deepcopy(compiled)
    a.update(status='trace_validated_effectful' if any(t['contract']['effect'] == 'authorized_write'
             for t in a['tool_contracts'].values()) else 'trace_validated_read_only',
             validation_task_fingerprint=f['fingerprint'], validation_edges=sorted(witnessed))
    a['certified_digest'] = digest(a)
    p = {'schema_version': 1, 'format': FORMAT, 'execution_version_sha256': a['execution_version'], 'artifact': a}
    p['policy_digest'] = digest(p)
    return p


def verify_execution_path(policy, f, completion):
    """Recompute the complete dynamic path from actual native MCP call/results."""
    a=policy['artifact'];rows=f['rows']
    roots=[i for i,r in enumerate(rows) if r['call_id']==completion.get('root_call_id')]
    count=completion.get('nodes',0)
    if len(roots)!=1 or not 2<=count<=a['max_steps']:
        return False
    ids=completion.get('control_call_ids',[])
    if len(ids)!=count or len(set(ids))!=count or not ids or ids[0]!=completion['root_call_id']:return False
    positions={r['call_id']:i for i,r in enumerate(rows)}
    if any(cid not in positions for cid in ids) or [positions[cid] for cid in ids]!=sorted(positions[cid] for cid in ids):return False
    path=[rows[positions[cid]] for cid in ids]
    for row in rows[roots[0]:positions[ids[-1]]+1]:
        if row['call_id'] not in ids and not safe_interleaving(row,a.get('interleaving_contracts',{}),f['scope']):return False
    if len(path)!=count or path[0]['name']!=a['root'] or path[0].get('generated') or path[0].get('message_seq') is None:
        return False
    seen=set();visited=[]
    for i,row in enumerate(path):
        signature=digest({'tool':row['name'],'args':row['args']})
        if signature in seen or row['name'] not in a['tool_contracts'] or not valid_output(row,a['tool_contracts'][row['name']],f['scope']):return False
        seen.add(signature)
        try:g=guard(row['out'],a['tool_contracts'][row['name']]['contract'])
        except ValueError:return False
        edges=[e for e in a['edges'] if e['from']==row['name'] and e['guard']==g]
        if len(edges)!=1:return False
        edge=edges[0];visited.append(digest(edge))
        if i==len(path)-1:
            if edge['to'] is not None:return False
        else:
            following=path[i+1]
            if edge['to']!=following['name'] or edge['bindings']!=transfer(row,following,a['tool_contracts']):return False
    return completion.get('control_edges')==visited and completion.get('control_flow') is True
