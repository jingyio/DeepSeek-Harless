"""Original FileJob budget, with durable retries, crash reconciliation and raw fees."""
import json,subprocess
from pathlib import Path
from .file_job_budget import FileJobBudget,job_command,ROOT
def command(path,name,value=None):
    r=subprocess.run(['node',str(ROOT/'src/adapters/operation_job.ts'),str(path),name],input=json.dumps(value or {}),capture_output=True,text=True,timeout=30)
    v=json.loads(r.stdout)
    if r.returncode:raise ValueError(v.get('error','operation task command failed'))
    return v
class OperationBudget(FileJobBudget):
    def claim_provider_retry(self):return command(self.path,'provider-retry')['admitted']
    def recover(self,version,owner_pid):
        value=command(self.path,'recover',{'execution_version_sha256':version,'owner_pid':owner_pid})
        logged={r.get('request_id') for r in (json.loads(l) for l in self.record.read_text().splitlines())} if self.record.exists() else set()
        for row in value['recovered']:
            if row['request_id'] not in logged:self.log({**row,'response_status':0,'observed_peak_usd':None,'response_usage':{},'kind':'interrupted_request','original_reservation_retained':True})
        # A crash after settlement can precede the JSONL append; the immutable job
        # events still carry the charged amount. Reconstruct the missing row once.
        reserved={};settled={}
        for p in sorted(Path(str(self.path)+'.events').glob('*.json')):
            e=json.loads(p.read_text())
            if e['kind']=='request_reserved':
                i=e['detail']['id'];pending=e['state']['pending'][str(i)];reserved[i]={'request_id':i,'model':pending['model'],'reserved_upper_usd':pending['amount']/1e9}
            if e['kind']=='request_settled':settled[e['detail']['request_id']]=e['detail']['observed']
        logged={r.get('request_id') for r in (json.loads(l) for l in self.record.read_text().splitlines())} if self.record.exists() else set()
        for i,row in reserved.items():
            if i not in logged:
                amount=settled.get(i);self.log({**row,'response_status':0,'observed_peak_usd':None if amount is None else amount/1e9,
                    'response_usage':{},'kind':'recovered_accounting','recovered_usage_unknown':True})
        return value
