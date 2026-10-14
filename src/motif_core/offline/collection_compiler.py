"""Certify witnessed source-array foreach and complete-gather dependencies."""
from __future__ import annotations
import json
from dataclasses import asdict
from .entry_compiler import digest
from .trace_compiler import artifact_signature

def contract_signature(tools,contracts):
    if any(not contracts[t].read_only for t in tools):raise ValueError('collection graph requires read-only contracts')
    expected=(('file_ids',),('file_id',),('source_id',),('collection_id','source_ids'))
    if any(tuple(contracts[t].required_params)!=params or contracts[t].default_params for t,params in zip(tools,expected)):
        raise ValueError('collection contract shape changed')
    return digest({'guard':'model_selected_collection_versions_v1','contracts':{t:asdict(contracts[t]) for t in tools}})

def collection_witness(events,task,tools,*,trace_id,task_fingerprint):
    source,pin,read,gather=tools;calls={};results={};models={}
    for event in events:
        if event.get('ptc_analysis_source'):raise ValueError('projected events cannot train collection graph')
        if event.get('type')=='tool/call':
            cid=event['data']['callId']
            if cid in calls or cid.startswith('sss-'):raise ValueError('duplicate/runtime-produced training call')
            calls[cid]=event
        if event.get('type')=='tool/result':
            for block in event['data']['message'].get('content',[]):
                if block.get('type')=='tool-result':results.setdefault(block['toolCallId'],[]).append((event,block))
        if event.get('type')=='assistant/message':
            data=event['data'];message=data.get('message',{})
            for block in message.get('content',[]):
                if block.get('type')=='tool-call':
                    if message.get('source',{}).get('kind')!='model' or not data.get('usage'):
                        raise ValueError('original provider decision required')
                    if block['id'] in models:raise ValueError('duplicate model call')
                    models[block['id']]=(event,block)
    def original(cid):
        if cid not in models or len(results.get(cid,[]))!=1:raise ValueError('ambiguous call/result evidence')
        message,block=models[cid];call=calls[cid];result,out=results[cid][0]
        args=json.loads(call['data']['arguments']);content=out.get('content',[])
        if (call['data']['name']!=block['name'] or json.loads(block['arguments'])!=args
                or not message['seq']<call['seq']<result['seq'] or out.get('isError')
                or len(content)!=1 or content[0].get('type')!='text'):
            raise ValueError('failed or changed model call/result')
        observation=json.loads(content[0]['text'])
        return args,observation,{'call_id':cid,'tool':call['data']['name'],'message_seq':message['seq'],
                               'call_seq':call['seq'],'result_seq':result['seq'],'observation_sha256':digest(observation)}
    source_ids=[cid for cid,e in calls.items() if e['data']['name']==source and len(results.get(cid,[]))==1 and not results[cid][0][1].get('isError')]
    if len(source_ids)!=1:raise ValueError('one unambiguous successful selected collection required')
    args,packet,ref=original(source_ids[0]);members=packet.get('files');scope={r['file_id']:r for r in task['inventory']}
    if (set(args)!= {'file_ids'} or not isinstance(members,list) or not 1<=len(members)<=32
            or len({r['file_id'] for r in members})!=len(members)
            or [r['file_id'] for r in members]!=args['file_ids'] or any(scope.get(r['file_id'])!=r for r in members)
            or packet.get('selection')!='actual_model_selected_members' or packet.get('count')!=len(members)
            or packet.get('input_sha256')!=task['input_version'] or packet.get('snapshot_sha256')!=task['snapshot_sha256']
            or packet.get('execution_version_sha256')!=task['execution_version_sha256']
            or packet.get('collection_sha256')!=digest({k:v for k,v in packet.items() if k!='collection_sha256'})):
        raise ValueError('source array differs from actual selected current scope')
    refs=[{**ref,'role':'source'}];pins={};reads={};gathered=None;end_seq=None
    for cid,event in sorted(calls.items(),key=lambda item:item[1]['seq']):
        if event['seq']<=ref['result_seq']:continue
        if event['data']['name'] not in (pin,read,gather):continue
        args,out,row=original(cid);name=event['data']['name']
        if name==pin:
            fid=args.get('file_id');member=next((r for r in members if r['file_id']==fid),None)
            if set(args)!= {'file_id'} or member is None or fid in pins or out.get('file_id')!=fid or out.get('source_version')!=member['source_version']:
                raise ValueError('pin not bound to unique source-array member')
            pins[fid]=(out,row);refs.append({**row,'role':'pin','source_array_index':members.index(member),'file_id':fid,'source_call_id':ref['call_id']})
        elif name==read:
            matches=[fid for fid,(p,_) in pins.items() if p.get('source_id')==args.get('source_id')]
            if set(args)!= {'source_id'} or len(matches)!=1:raise ValueError('read lacks unique actual pin handle')
            fid=matches[0];p,prior=pins[fid];member=scope[fid]
            if (fid in reads or row['call_seq']<=prior['result_seq'] or row['message_seq']<=prior['result_seq']
                    or out.get('file_id')!=fid or out.get('source_id')!=p['source_id']
                    or out.get('source_version')!=member['source_version'] or out.get('path')!=member['path']
                    or out.get('sha256')!=member['sha256'] or out.get('status') not in ('readable','unreadable','metadata_only','unsupported')):
                raise ValueError('read observation differs from corresponding member/version')
            reads[fid]=out;refs.append({**row,'role':'read','file_id':fid,'pin_call_id':prior['call_id'],'status':out['status']})
        else:
            if len(reads)!=len(members):raise ValueError('gather before complete actual reads')
            selected=[reads[r['file_id']]['source_id'] for r in members]
            expected=[{'file_id':r['file_id'],'path':r['path'],'source_id':reads[r['file_id']]['source_id'],
                       'source_version':r['source_version'],'status':reads[r['file_id']]['status'],
                       'read_sha256':digest(reads[r['file_id']])} for r in members]
            if (set(args)!= {'collection_id','source_ids'} or args['collection_id']!=packet['collection_id']
                    or len(args['source_ids'])!=len(selected) or set(args['source_ids'])!=set(selected)
                    or row['message_seq']<=max(r['result_seq'] for r in refs)
                    or out.get('status')!='collection_complete' or out.get('files')!=expected
                    or out.get('collection_id')!=packet['collection_id'] or out.get('count')!=len(expected)
                    or out.get('collection_sha256')!=packet['collection_sha256'] or out.get('coverage_sha256')!=digest(expected)
                    or out.get('input_sha256')!=task['input_version'] or out.get('execution_version_sha256')!=task['execution_version_sha256']
                    or out.get('snapshot_sha256')!=task['snapshot_sha256'] or out.get('semantic_judgment_certified') is not False):
                raise ValueError('gather is not bound to complete actual reads and collection')
            refs.append({**row,'role':'gather'});gathered=out;end_seq=row['result_seq'];break
    if gathered is None:raise ValueError('no complete gather witness')
    if any(e['data']['name'] not in tools for e in calls.values() if ref['result_seq']<e['seq']<end_seq):
        raise ValueError('other operation interrupts collection graph')
    return {'kind':'model_selected_collection_witness','trace_id':trace_id,'task_fingerprint':task_fingerprint,
            'target_count':len(members),'input_version':task['input_version'],'selected_ids_sha256':digest([r['file_id'] for r in members]),
            'references':refs,'selection_sha256':digest(packet),'coverage_sha256':gathered['coverage_sha256'],
            'execution_version_sha256':task['execution_version_sha256'],'tools':list(tools)}

def compile_collection_motif(training,contracts,schemas):
    if (len(training)<2 or len({r['trace_id'] for r in training})!=len(training)
            or len({r['task_fingerprint'] for r in training})!=len(training)
            or len({r['target_count'] for r in training})<2 or len({digest(r['tools']) for r in training})!=1
            or len({r['execution_version_sha256'] for r in training})!=1):
        raise ValueError('independent varying-size collection witnesses required')
    tools=training[0]['tools'];source,pin,read,gather=tools
    signature=contract_signature(tools,contracts)
    edges=[{'from_tool':source,'from_field':'files[].file_id','to_tool':pin,'to_param':'file_id','mapping':'foreach_all_selected'},
           {'from_tool':pin,'from_field':'source_id','to_tool':read,'to_param':'source_id','mapping':'same_iteration'},
           {'from_tool':read,'from_field':'source_id','to_tool':gather,'to_param':'source_ids','mapping':'gather_complete'},
           {'from_tool':source,'from_field':'collection_id','to_tool':gather,'to_param':'collection_id','mapping':'same_collection'}]
    return {'schema_version':1,'kind':'selected_collection_read_graph','status':'compiled_candidate',
            'motif_id':'collection_'+digest(tools)[:16],'tools':tools,'transfer_evidence':edges,
            'source_trace_ids':[r['trace_id'] for r in training],'source_task_fingerprints':[r['task_fingerprint'] for r in training],
            'contract_signature':signature,'tool_schema_sha256':{t:digest(schemas[t]) for t in tools},
            'graph':{'source_tool':source,'pin_tool':pin,'read_tool':read,'gather_tool':gather,'selection':'actual_model_selected_members',
                     'array_field':'files','identity_field':'file_id','pin_param':'file_id','read_param':'source_id','gather_param':'source_ids',
                     'max_targets':32,'max_batch':8,'stop':'semantic_handoff_after_complete_gather'},'training_witnesses':training}

def certify_collection_motif(compiled,heldout,contracts):
    if (compiled.get('status')!='compiled_candidate' or heldout['trace_id'] in compiled['source_trace_ids']
            or heldout['task_fingerprint'] in compiled['source_task_fingerprints']
            or heldout['tools']!=compiled['tools'] or contract_signature(compiled['tools'],contracts)!=compiled['contract_signature']
            or heldout['execution_version_sha256']!=compiled['training_witnesses'][0]['execution_version_sha256']):
        raise ValueError('new task with unchanged collection contracts and execution required')
    result={**compiled,'status':'trace_validated_read_only','validation_trace_id':heldout['trace_id'],
            'validation_task_fingerprint':heldout['task_fingerprint'],'validation_witness':heldout}
    result['certified_digest']=artifact_signature(result);return result

def export_collection_policy(artifact,execution_version):
    if artifact.get('status')!='trace_validated_read_only' or artifact_signature(artifact)!=artifact['certified_digest']:
        raise ValueError('certified collection artifact required')
    body={'schema_version':1,'format':'sss-collection-read-v1','artifact':artifact,
          'source_library_digest':digest({'artifacts':[artifact]}),'execution_version_sha256':execution_version}
    body['policy_digest']=digest(body);return body
