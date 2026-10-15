"""Reuse the conservative price gate, with all persistent task mutations owned by TypeScript."""
from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path
from src.adapters.deepseek_cost_gate import reservation,observed_peak_cost
ROOT=Path(__file__).resolve().parents[2]

def job_command(path,command,payload=None):
    result=subprocess.run(['node',str(ROOT/'src/adapters/file_workflow_job.ts'),str(path),command],
                          input=json.dumps(payload or {},ensure_ascii=False),text=True,capture_output=True,timeout=30)
    value=json.loads(result.stdout)
    if result.returncode:raise ValueError(value.get('error','durable job command failed'))
    return value

class FileJobBudget:
    def __init__(self,path,record):
        self.path=Path(path);self.record=Path(record);self._state=job_command(path,'state')['state']
        self.output_cap=self._state['limits']['max_output'];self.cap_usd=self._state['limits']['budget_usd']
    @property
    def request_count(self):return job_command(self.path,'state')['state']['requests']
    @property
    def reserved_usd(self):return job_command(self.path,'state')['state']['spent_units']/1e9
    def book(self,body):
        model,cost,ceiling=reservation(body,max_output=self.output_cap)
        value=job_command(self.path,'reserve',{'model':model,'upper_usd':cost,'request_sha256':hashlib.sha256(body).hexdigest()})
        return (value['request_id'],model,cost,ceiling) if value['admitted'] else None
    def settle(self,request_id,model,status,usage):
        try:observed=observed_peak_cost(model,usage) if status==200 else None
        except ValueError:observed=None
        value=job_command(self.path,'settle',{'request_id':request_id,'model':model,'observed_usd':observed})
        return value['observed_usd'],value['released_usd']
    def log(self,row):
        job_command(self.path,'log',row)
        self.record.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.record.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        self.record.chmod(0o600)
