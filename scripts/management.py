"""One local entry for daily management, inventory and private recovery."""
import argparse,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    command=argv.pop(0) if argv and argv[0] in {'start','status','motifs','backup','verify-backup','restore','migrate'} else 'start'
    if command=='motifs':
        from src.adapters.management_inventory import inventory
        print(json.dumps(inventory(ROOT),ensure_ascii=False,indent=2));return 0
    if command=='status':
        from src.adapters.management_inventory import inventory
        profiles=inventory(ROOT);print(json.dumps({'branch_required':'feature/rsi-research-agent','entry':'npm run management',
          'profile':'daily-management-real-v3','credentials_configured':bool(os.environ.get('DEEPSEEK_API_KEY') or (ROOT/'.local/deepseek.env').is_file()),
          'management':next((p for p in profiles['profiles'] if p['profile']=='daily-management-real-v3'),None),
          'historical_entries':profiles['unique_historical_entries'],'cloud_requests':0},ensure_ascii=False,indent=2));return 0
    if command in {'backup','verify-backup','restore','migrate'}:
        from src.adapters.management_backup import cli
        return cli(ROOT,command,argv)
    ap=argparse.ArgumentParser(add_help=False);ap.add_argument('--mock',action='store_true');ap.add_argument('--real-model',action='store_true')
    flags,rest=ap.parse_known_args(argv)
    if flags.mock and flags.real_model:raise ValueError('choose real model or explicit mock diagnostic')
    if any(v==k or v.startswith(k+'=') for v in rest for k in ('--scenario','--frozen')):raise ValueError('management uses the native files scene; other scenes use npm run web')
    for option,limit,kind in [('--budget-usd',5,float),('--request-limit',96,int),('--max-output',4000,int),('--run-budget-usd',25,float),('--run-request-limit',4000,int)]:
        if option in rest and rest.index(option)==len(rest)-1:raise ValueError(option+' requires a value')
        values=[v.split('=',1)[1] if '=' in v else rest[i+1] for i,v in enumerate(rest) if v==option or v.startswith(option+'=')]
        if any(not 0<kind(v)<=limit for v in values):raise ValueError(option+' exceeds the original management limit')
    env=dict(os.environ)
    if not flags.mock and not env.get('DEEPSEEK_API_KEY'):
        # Existing trusted local configuration; never execute shell or print values.
        keyfile=ROOT/'.local/deepseek.env'
        if keyfile.is_file():
            for line in keyfile.read_text().splitlines():
                key,sep,value=line.removeprefix('export ').partition('=')
                if sep and key.strip()=='DEEPSEEK_API_KEY':env[key.strip()]=value.strip().strip('"\'')
        if not env.get('DEEPSEEK_API_KEY'):raise ValueError('configure DEEPSEEK_API_KEY in the environment, .env or existing .local/deepseek.env')
    args=[sys.executable,str(ROOT/'scripts/harness-geneloop.py'),'--scenario','files','--mode','execute','--budget-usd','5',
          '--request-limit','96','--run-budget-usd','25','--run-request-limit','4000','--max-output','4000',*rest]
    if not flags.mock:args.append('--real-model')
    return subprocess.run(args,cwd=ROOT,env=env).returncode

def run(argv=None):
    try:return main(argv)
    except Exception as e:
        from src.adapters.management_backup import journal
        args=sys.argv[1:] if argv is None else argv
        journal(ROOT,'command_failed',{'command':args[0] if args else 'start','error_type':type(e).__name__,'reason':str(e)})
        print(str(e),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(run())
