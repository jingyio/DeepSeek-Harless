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
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.script_motif_compiler import observe,sha

def collect(task):
    effective=json.loads((task/'effective-config.json').read_text())
    state=json.loads((task/'task-state.json').read_text())
    if state.get('status')!='completed' or effective.get('provider_mode')!='real' or effective.get('mode')!='baseline':
        raise ValueError('completed_real_baseline_required')
    calls={};found=[];rejected=[];previous=None
    request=json.loads((task/'task.json').read_text())
    goal='\n'.join(p['text'] for p in request['content'] if p['type']=='text')
    events=[json.loads(line) for line in (task/'events.jsonl').read_text().splitlines() if line]
    for event in events[effective.get('trace_start_index',0):]:
        data=event.get('data',{})
        if event.get('type')=='tool/call':
            args=data['arguments'];args=json.loads(args) if isinstance(args,str) else args
            calls[data['callId']]={'name':data['name'],'args':args}
        if event.get('type')!='tool/result':continue
        for block in data.get('message',{}).get('content',[]):
            if block.get('type')!='tool-result' or block.get('isError') or block.get('toolCallId') not in calls:continue
            observed=calls.pop(block['toolCallId']);call=observed['args'];prefix=previous
            previous={'tool':observed['name'],'intent':call.get('description',observed['name'])}
            if observed['name']!='bash':continue
            try:
                stdout=''.join(c.get('text','') for c in block.get('content',[]) if c.get('type')=='text')
                row=observe(call['command'],call.get('description',''),effective['workspace'],stdout,task.name,block['toolCallId'])
                row.update(source_goal=goal,predecessor=prefix,intent=call.get('description',''))
                row['witness']['events_sha256']=sha((task/'events.jsonl').read_bytes());found.append(row)
            except (ValueError,SyntaxError,KeyError,TypeError,OSError,UnicodeError) as error:
                rejected.append({'call_id':block['toolCallId'],'reason':str(error)[:160]})
    return {'task_id':task.name,'workspace':effective['workspace'],'candidates':found,'rejected':rejected}

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
