"""Explicit local mock for native batch and recovery integration; never training."""
import json,time
from http.server import BaseHTTPRequestHandler
PREFIX='mcp__file_management__'
class Provider(BaseHTTPRequestHandler):
    calls=[];embedding_calls=0;failures=0;response_delay=0
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.requests.append(body)
        time.sleep(self.response_delay);values=[]
        for m in body['messages']:
            if m['role']=='tool':
                try:values.append(json.loads(m['content']))
                except (ValueError,TypeError):pass
        find=lambda p:next((v for v in reversed(values) if isinstance(v,dict) and p(v)),None)
        task=find(lambda v:'operation_request' in v);inv=find(lambda v:'files' in v and 'status' not in v and 'snapshot_sha256' in v)
        receipt=find(lambda v:v.get('status')=='executed_verified');plan=find(lambda v:v.get('status')=='validated_copy_plan')
        ins=find(lambda v:v.get('status')=='verified_plan_results');report=find(lambda v:v.get('status') in ('delivered','delivered_with_gaps'))
        prior=next((r for r in (task or {}).get('recovery_state',[]) if r['status'] in ('executing','executed_verified')),None)
        if prior:
            plan=plan or prior
            if prior.get('receipt_id'):receipt=receipt or prior
        read_paths={r['path'] for v in values if isinstance(v,dict) and v.get('status')=='read_batch_complete' for r in v['reads']}
        read_paths|={r['path'] for r in (task or {}).get('reading_state',[])}
        def read_action(ids):
            pin=find(lambda v:v.get('status')=='pinned_batch' and v.get('file_ids')==ids)
            return ('read_files',{'source_ids':pin['source_ids']}) if pin else ('pin_files',{'file_ids':ids})
        if not task:action=('read_task',{})
        elif not inv:action=('list_files',{})
        elif task.get('require_source_read') and not {r['source'] for r in task['operation_request']}<=read_paths:
            action=read_action([next(f['file_id'] for f in inv['files'] if f['path']==r['source']) for r in task['operation_request']])
        elif not plan:
            action=('preview_actions',{'actions':[{'op':r['op'],'file_ids':[next(f['file_id'] for f in inv['files'] if f['path']==r['source'])],
                'destination':r['destination'],'format':r['format']} for r in task['operation_request']]})
        elif not receipt:action=('execute_plan',{'plan_id':plan['plan_id']})
        elif task['require_result_read'] and not ins:action=('inspect_plan_result',{'receipt_id':receipt['receipt_id']})
        elif task['require_result_read'] and not {r['destination'] for r in task['operation_request']}<=read_paths:
            action=read_action([r['file_id'] for r in ins['files']])
        elif not {r['destination'] for r in task['operation_request']}<={r['path'] for r in inv['files']}:action=('list_files',{})
        elif not report:action=('submit_report',{'summary':'Explicit mock of actual batch effects, recovery and complete source/output reads',
              'file_ids':[r['file_id'] for r in inv['files']],'gaps':[],'report_kind':'task_result'})
        else:action=None
        i=len(self.server.requests);delta={'role':'assistant','tool_calls':[{'index':0,'id':'mock-v2-'+str(i),'type':'function',
               'function':{'name':PREFIX+action[0],'arguments':json.dumps(action[1])}}]} if action else {'role':'assistant','content':'Mock complete.'}
        base={'id':'mock-v2','created':1,'model':body['model'],'object':'chat.completion.chunk'}
        chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},{**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if action else 'stop'}]},
          {**base,'choices':[],'usage':{'prompt_tokens':100,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100,'completion_tokens':20,'total_tokens':120}}]
        data=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode();self.send_response(200)
        self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
