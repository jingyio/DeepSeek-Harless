"""Drain or inspect the ordinary Agent's persistent offline Motif queue."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.continuous_rsi import load_config,initialize,records
from src.adapters.continuous_motif_learning import drain

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--drain',action='store_true');args=p.parse_args()
    cfg=load_config(args.config);root=initialize(cfg)
    if not args.drain:print(json.dumps({'state_root':str(root),'records':len(records(root)),'paid':False}));return
    try:result=drain(args.config)
    except RuntimeError as error:
        if 'writer is active' not in str(error):raise
        result={'status':'worker_already_active','new_requests':0}
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
