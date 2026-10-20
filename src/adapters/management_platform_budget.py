"""Route account-local certification through the existing platform budget API."""
import hashlib,json,os,urllib.request
from uuid import uuid4
from pathlib import Path
from urllib.parse import urlsplit


class PlatformBudget:
    def __init__(self,policy,session,model,cap,out,resuming):
        endpoint=policy['control_endpoint'];url=urlsplit(endpoint)
        if url.scheme!='http' or url.hostname!='127.0.0.1':raise ValueError('original local platform meter required')
        prefix=policy.get('budget_task_prefix','')
        identity=hashlib.sha256((session+':'+uuid4().hex).encode()).hexdigest()
        self.task=prefix+identity[len(prefix):32];self.session='turn-'+self.task
        self.endpoint=endpoint;self.token=policy['control_token'];self.upstream=policy['endpoint'].rstrip('/').removesuffix('/v1')
        self.out=Path(out)
        platform_cap=policy.get('budget_usd')
        cap=platform_cap if cap is None else cap if platform_cap is None else min(cap,platform_cap)
        self.call('/tasks/register',{'task_id':self.task,'session_id':self.session,'model':model,'budget_usd':cap})
        self.call('/tasks/activate',{'session_id':self.session})
    def call(self,path,value):
        request=urllib.request.Request(self.endpoint+path,data=json.dumps(value).encode(),method='POST',
            headers={'Content-Type':'application/json','X-SSS-Control-Token':self.token})
        with urllib.request.urlopen(request,timeout=15) as response:return json.load(response)
    def headers(self,value):
        result={k:v for k,v in value.items() if k.lower()!='x-deepseek-harness-session-id'}
        result['X-DeepSeek-Harness-Session-Id']=self.session;return result
    def close(self,interrupted=False):
        value=self.call('/tasks/cancel',{'session_id':self.session})
        path=self.out/'platform-accounting.json'
        if path.exists():path=self.out/('platform-accounting-'+hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()+'.json')
        if not path.exists():
            with path.open('x') as stream:json.dump(value,stream)
            path.chmod(0o600)


def enroll_platform(session,model,cap,out,resuming=False):
    path=os.environ.get('SSS_WEB_POLICY')
    if not os.environ.get('HARLESS_MANAGEMENT_PRIVATE_ROOT') or not path:return None
    policy=json.loads(Path(path).read_text())
    if policy.get('provider_mode')!='real':return None
    return PlatformBudget(policy,session,model,cap,out,resuming)
