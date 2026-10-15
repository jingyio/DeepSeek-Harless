"""Copy original certified policies into a public reference package, without private proofs."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.motif_core.offline.experience_registry import read,durable,sha,check_motif_certificate

def privacy(value):
    if isinstance(value,dict):
        for k,v in value.items():
            if k.lower() in ('api_key','authorization','password','access_token','secret'):raise ValueError('credential field')
            privacy(v)
    elif isinstance(value,list):
        for v in value:privacy(v)
    elif isinstance(value,str):
        if any(p in value for p in ('/Users/','/home/','Bearer ','file://')) or len(value)>512:raise ValueError('unreviewed private string')

def export(state,destination):
    state=Path(state).resolve();destination=Path(destination).resolve()
    if not state.is_relative_to(ROOT/'.local') or not destination.is_relative_to(ROOT/'examples/motif-library'):raise ValueError('invalid publication boundary')
    if destination.exists():raise ValueError('publication exists; preserve old bytes')
    registry=state/'registry';pointer=read(registry/'current.json');view=read(registry/pointer['file']);entries=[]
    for e in view['entries']:
        if e['kind']!='operation_graph' or e['state']!='active':continue
        path=registry/e['payload'];policy=read(path);privacy(policy)
        certificate=registry/e['certificate']['file'];c=check_motif_certificate(policy,certificate,sha(path))
        row={'entry_id':e['entry_id'],'path':'policies/'+e['entry_id']+'.json','sha256':sha(path),'policy_digest':policy['policy_digest'],
             'original_certificate_sha256':sha(certificate),'original_status':c['status'],'certification_contract':c.get('certification_contract'),
             'runtime_source':e['runtime_source'],'nodes':[n['tool'] for n in policy['artifact']['nodes']],
             'holdout_used':c['holdout_used'],'quality_and_permission_required':c['quality_and_permission_required'],
             'reviews':[{k:r[k] for k in ('role','task_fingerprint','record_sha256','completion_count','audit_sha256') if k in r} for r in [c['native_review'],*c['reviews']]]}
        entries.append(row);target=destination/row['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
    catalog={'schema_version':1,'format':'sss-public-operation-library-v2','original_generation':view['generation'],
       'original_registry_sha256':sha(registry/pointer['file']),'default_activation':False,'includes_private_runtime_admission_proofs':False,
       'artifact_bytes':'exact original learned policy bytes; no re-signing','entries':entries,'private_evidence_required_for_original_activation':True}
    privacy(catalog);durable(destination/'catalog.json',catalog)
    lock={str(p.relative_to(destination)):sha(p) for p in destination.rglob('*') if p.is_file()};durable(destination/'files.lock.json',{'schema_version':1,'sha256':lock})
    print(json.dumps({'policies':len(entries),'generation':view['generation'],'path':str(destination.relative_to(ROOT)),'cloud_requests':0}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True);p.add_argument('--destination',type=Path,required=True);a=p.parse_args();export(a.state,a.destination)
