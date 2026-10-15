"""Stable server-owned file profiles; mock and real evidence never share a library."""
from pathlib import Path
import os
from .continuous_rsi import ROOT,DATA,STATE_HOME,load_config,initialize,writer_lock
from src.motif_core.offline.experience_registry import durable,read
def default_config(real):
    name='daily-files-real-v2' if real else 'daily-files-mock-v2';file=STATE_HOME/(name+'.json')
    with writer_lock(STATE_HOME,'daily-profile'):
        if not file.exists():
            workspace=DATA/name;workspace.mkdir(parents=True,exist_ok=True,mode=0o700)
            durable(file,{'schema_version':1,'format':'sss-continuous-rsi-v1','adapter':'file_operations_v2',
               'state_root':str(STATE_HOME/name),'workspace_roots':[str(workspace)],'mode':'learn' if real else 'observe',
               'provider_mode':'real' if real else 'mock','series_cap_usd':1000,'learning_cap_usd':25,
               'auto_worker':real,'allow_material_copy':real,'limits':{'budget_usd':5,'max_steps':96,'max_output':4000,'max_repairs':2}},exclusive=True)
    initialize(load_config(file));return file
def status(config):
    cfg=load_config(config);root=Path(cfg['state_root']);initialize(cfg);p=read(root/'registry/current.json');library=read(root/'registry'/p['file'])
    jobs=[]
    for j in (root/'learning').glob('*'):
        if not j.is_dir():continue
        stage='active' if (j/'activation.json').exists() else 'rejected' if (j/'failure.json').exists() else 'certifying'
        jobs.append({'id':j.name,'status':stage})
    pool=read(root/'pool.json')['runs'];enabled=cfg['mode']=='learn' and cfg['auto_worker'] and cfg['provider_mode']=='real'
    worker=read(root/'worker.lock') if (root/'worker.lock').exists() else None
    alive=False
    if worker:
        from .process_state import process_exists
        alive=process_exists(worker['pid'])
    return {'persistent':True,'provider_mode':cfg['provider_mode'],'learning_enabled':enabled,'library_generation':library['generation'],
      'active_motifs':sum(e['state']=='active' for e in library['entries']),'disabled_motifs':sum(e['state']=='disabled' for e in library['entries']),
      'certification':jobs,'worker_running':alive,'recorded_tasks':len(pool),'estimated_cost_usd':sum(v.get('cost_usd',0) for v in pool.values()),
      'reserved_upper_usd':sum(v['cap_usd'] for v in pool.values() if v['status']=='reserved'),'learning_cap_usd':cfg['learning_cap_usd'],
      'series_cap_usd':cfg['series_cap_usd'],'actual_paid_usd':0 if cfg['provider_mode']=='mock' else None,'cost_basis':'proxy_estimate_not_provider_bill'}
