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
        self.route=self.session;self.broker=None;self.bound=False
        if prefix:
            # Members enter the scoped gateway, which authorizes a native route
            # before the existing broker translates it to this task's budget.
            self.broker=policy['budget_broker_endpoint'];broker=urlsplit(self.broker)
            if (broker.scheme!='http' or broker.hostname!='127.0.0.1' or broker.path not in ('','/') or
                    broker.username or broker.password or broker.query or broker.fragment):
                raise ValueError('original local platform broker required')
            self.route='session-'+str(uuid4())
        self.out=Path(out)
        platform_cap=policy.get('budget_usd')
        cap=platform_cap if cap is None else cap if platform_cap is None else min(cap,platform_cap)
        self.call('/tasks/register',{'task_id':self.task,'session_id':self.session,'model':model,'budget_usd':cap})
        binding_attempted=False
        pair={'session_id':self.route,'budget_session_id':self.session}
        try:
            self.call('/tasks/activate',{'session_id':self.session})
            if self.broker:
                binding_attempted=True
                self.call('/bind',pair,endpoint=self.broker)
                self.bound=True
        except Exception as primary:
            failures=[]
            if binding_attempted:
                # The bind may have committed before its reply was lost. Only
                # the same immutable pair is eligible for best-effort cleanup.
                try:self.call('/unbind',pair,endpoint=self.broker)
                except Exception as error:failures.append(error)
            try:self.call('/tasks/cancel',{'session_id':self.session})
            except Exception as error:failures.append(error)
            if failures:primary.platform_cleanup_failures=tuple(failures)
            raise
    def call(self,path,value,*,endpoint=None):
        request=urllib.request.Request((endpoint or self.endpoint)+path,data=json.dumps(value).encode(),method='POST',
            headers={'Content-Type':'application/json','X-SSS-Control-Token':self.token})
        with urllib.request.urlopen(request,timeout=15) as response:return json.load(response)
    def headers(self,value):
        result={k:v for k,v in value.items() if k.lower()!='x-deepseek-harness-session-id'}
        result['X-DeepSeek-Harness-Session-Id']=self.route;return result
    def close(self,interrupted=False):
        try:
            if self.bound:
                self.call('/unbind',{'session_id':self.route,'budget_session_id':self.session},endpoint=self.broker)
                self.bound=False
        finally:
            # A failed route cleanup must still revoke this task's own budget.
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
