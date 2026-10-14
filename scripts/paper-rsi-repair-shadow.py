"""Frozen read-after-failed-check extension, no new baseline/execute loop."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('repair_recovery',ROOT/'scripts/paper-rsi-recovery.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
TRAIN=m.EXP
m.EXP=ROOT/'.local/paper-reference/paper-rsi-overnight-20261011-v3';m.n.EXP=m.EXP


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--phase',choices=['preview','compile','shadow'],default='preview')
    ap.add_argument('--case',choices=m.n.TASKS);ap.add_argument('--call-model',action='store_true');a=ap.parse_args()
    if a.phase=='preview':
        _,prior,_=m.r.reference.budget.account(m.EXP);print(json.dumps({'cap_usd':8,'cumulative_estimated_usd':prior,'paid_enabled':False}));return
    m.setup();path=m.EXP/'libraries/v01/library.json'
    if a.phase=='compile':
        if path.exists():raise ValueError('preserve frozen repair library')
        lib=m.n.compile_flow_shadow([TRAIN/'runs'/('baseline-'+c) for c in m.n.TASKS[:3]])
        m.r.save(path,lib);print(json.dumps({'motifs':len(lib['motifs']),'digest':lib['manifest_digest'],
            'shadow_only_migrations':lib['shadow_only_migrations']}));return
    if not a.call_model or not a.case:raise ValueError('explicit real shadow case required')
    print(json.dumps(m.run(a.case,'shadow',path)))


if __name__=='__main__':main()
