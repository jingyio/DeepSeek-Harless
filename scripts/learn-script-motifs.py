#!/usr/bin/env python3
"""Mine native successful scripts; certify and publish only via the sandbox checker.

Explicit private experiment entry point. The first task is held out before source
selection. No paid compilation calls; rejected observations remain in the report.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import re
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.script_motif_compiler import observe,sha,digest,extract
from src.adapters.script_dataflow_compiler import observe_slices

def collect(task):
    effective=json.loads((task/'effective-config.json').read_text())
    state=json.loads((task/'task-state.json').read_text())
    if state.get('status')!='completed' or effective.get('provider_mode')!='real' or effective.get('mode')!='baseline':
        raise ValueError('completed_real_baseline_required')
    calls={};found=[];rejected=[];previous=None;argument_witnesses=[]
    request=json.loads((task/'task.json').read_text())
    goal='\n'.join(p['text'] for p in request['content'] if p['type']=='text')
    events=[json.loads(line) for line in (task/'events.jsonl').read_text().splitlines() if line]
    boundaries={r['call_id']:r for r in map(json.loads,(task/'reuse-boundaries.jsonl').read_text().splitlines())} if (task/'reuse-boundaries.jsonl').exists() else None
    def evidence(row,command,arguments):
        if boundaries is None:
            row['witness']['input_evidence_scope']='legacy_final_workspace_replay_not_boundary_snapshot';return row
        boundary=boundaries.get(row['witness']['call_id'])
        if not boundary or boundary['is_error']:raise ValueError('successful_boundary_evidence_required')
        if boundary['arguments_sha256']!=digest(arguments):raise ValueError('native_boundary_arguments_changed')
        before=boundary['before']['files']
        if any(before.get(w['relative'],{}).get('sha256')!=w['sha256'] for w in row['witness']['files'].values()):
            raise ValueError('input_changed_since_native_boundary')
        extracted=extract(command,effective['workspace'])
        if len(extracted)>2 and not re.search(r'\bcat\s*>',command) and not any(w['sha256']==extracted[3] for w in before.values()):
            raise ValueError('saved_program_changed_since_native_boundary')
        row['witness']['input_evidence_scope']='matching_native_pre_execution_snapshot'
        row['witness']['boundary_sha256']=sha(json.dumps(boundary,sort_keys=True))
        return row
    for event in events[effective.get('trace_start_index',0):]:
        data=event.get('data',{})
        if event.get('type')=='tool/call':
            try:
                args=data['arguments'];args=json.loads(args) if isinstance(args,str) else args
            except (KeyError,ValueError):
                rejected.append({'call_id':data.get('callId'),'reason':'invalid_native_arguments'});previous=None;continue
            calls[data['callId']]={'name':data['name'],'args':args}
        if event.get('type')!='tool/result':continue
        for block in data.get('message',{}).get('content',[]):
            if block.get('type')!='tool-result' or block.get('isError') or block.get('toolCallId') not in calls:continue
            observed=calls.pop(block['toolCallId']);call=observed['args'];prefix=previous
            previous={'tool':observed['name'],'intent':call.get('description',observed['name'])}
            if observed['name']!='bash':continue
            stdout=''.join(c.get('text','') for c in block.get('content',[]) if c.get('type')=='text')
            if re.search(r'\[exit code:\s*[1-9][0-9]*\]',stdout):
                rejected.append({'call_id':block['toolCallId'],'reason':'native_shell_nonzero_exit'});previous=None;continue
            if str(block['toolCallId']).startswith(('sss-reuse-', 'sss-script-')):
                previous=None;continue
            # A head-filtered invocation is not promoted as a whole operator.
            # Its actual arguments may independently validate a saved program.
            stripped=re.sub(r'\s+(?:2>&1\s*)?\|\s*head\s+-(?:n\s*)?\d+\s*$','',call.get('command',''))
            if stripped!=call.get('command'):
                try:
                    invocation=extract(stripped,effective['workspace'])
                    if len(invocation)>2:argument_witnesses.append({'source_sha256':invocation[3],'argv':invocation[2],'call_id':block['toolCallId'],'stdout':''.join(c.get('text','') for c in block.get('content',[]) if c.get('type')=='text'),'output_filter':'head'})
                except (ValueError,OSError,SyntaxError):pass
            try:
                stdout=''.join(c.get('text','') for c in block.get('content',[]) if c.get('type')=='text')
                row=observe(call['command'],call.get('description',''),effective['workspace'],stdout,task.name,block['toolCallId'])
                row.update(source_goal=goal,predecessor=prefix,intent=call.get('description',''))
                row['witness']['events_sha256']=sha((task/'events.jsonl').read_bytes());found.append(evidence(row,call['command'],call))
                previous['program_id']=row['id']
            except (ValueError,SyntaxError,KeyError,TypeError,OSError,UnicodeError) as error:
                rejected.append({'call_id':block['toolCallId'],'reason':str(error)[:160]})
            try:
                # Mining inside a Python invocation is independent of whether
                # its outer write/report program was admitted as one operator.
                for row in observe_slices(call.get('command',''),call.get('description',''),effective['workspace'],stdout,task.name,block['toolCallId']):
                    row.update(source_goal=goal,predecessor=None,intent=call.get('description',''))
                    row['witness']['events_sha256']=sha((task/'events.jsonl').read_bytes());found.append(evidence(row,call['command'],call))
            except (ValueError,SyntaxError,KeyError,TypeError,OSError,UnicodeError):pass
    return {'task_id':task.name,'workspace':effective['workspace'],'candidates':found,'rejected':rejected,'argument_witnesses':argument_witnesses}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',action='append',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if len(args.task)<2:parser.error('at least two completed real tasks, first held out, are required')
    args.output.mkdir(parents=True,exist_ok=False)
    rows=[collect(task.resolve()) for task in args.task]
    source=args.output/'observations.json';source.write_text(json.dumps(rows,ensure_ascii=False,indent=2));source.chmod(0o600)
    result=subprocess.run(['node',str(ROOT/'scripts/certify-script-motifs.mjs'),str(source),str(args.output)],cwd=ROOT)
    raise SystemExit(result.returncode)

if __name__=='__main__':main()
