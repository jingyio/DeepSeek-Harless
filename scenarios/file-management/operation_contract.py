"""Frozen business acceptance, separate from discovery of operation DAGs."""
from __future__ import annotations
import json,zipfile
from pathlib import Path
from common import digest,sha,snapshot
from report_study import receipt_errors

VERSION='sss-file-operation-contract-v1'

def verify_operations(spec,report,output,events):
    output=Path(output);errors=receipt_errors(spec,report,output)
    review={'errors':errors,'human_blind_review':False,'report_contract_checked':True}
    current=snapshot(spec['workspace'])
    ids={'file:local:'+digest({'path':n,'sha':h})[:24] for n,h in current.items() if n!='.experiment-copy'}
    if not report or (report.get('task_id'),report.get('input_sha256'),report.get('final_snapshot'))!=(spec['task_id'],digest(spec),current):errors.append('actual report task/source/snapshot differs')
    if report and (len(report.get('file_ids',[]))!=len(ids) or set(report['file_ids'])!=ids):errors.append('current report identities differ')
    c=spec['operation_contract']
    if c['version']!=VERSION:errors.append('unknown operation acceptance version')
    expected=dict(spec['initial_snapshot']);root=Path(spec['workspace']);observed=[]
    for p in (output/'journals').glob('*.json'):
        j=json.loads(p.read_text())
        if j['status']=='executed_verified':observed+=j['completed']
        else:errors.append('unfinished execution journal')
    actual=[{'op':a['op'],'source':next((n for n,h in spec['initial_snapshot'].items()
                if a['file_ids']==['file:local:'+digest({'path':n,'sha':h})[:24]]),None),
             'destination':a['destination'],'format':a['format']} for a in observed]
    if sorted(actual,key=lambda a:a['destination'])!=sorted(c['actions'],key=lambda a:a['destination']):errors.append('executed operations differ from original goal')
    for a in c['actions']:
        dest=root/a['destination'];source=a['source']
        if not dest.is_file():errors.append('missing produced file '+a['destination']);continue
        if a['op'] in ('copy','move','quarantine'):
            if sha(dest)!=spec['initial_snapshot'][source]:errors.append('produced bytes differ '+a['destination'])
        elif a['op']=='archive':
            try:
                with zipfile.ZipFile(dest) as z:
                    import hashlib
                    if z.namelist()!=[source] or hashlib.sha256(z.read(source)).hexdigest()!=spec['initial_snapshot'][source]:errors.append('archive content differs')
            except (OSError,zipfile.BadZipFile):errors.append('invalid actual archive')
        elif a['op']=='convert':
            from file_tools import FileScene
            parser=FileScene.__new__(FileScene);status,text,meta=parser.parse(root/source)
            if a['format']=='csv' and status=='readable':
                import csv,io
                expected_csv=io.StringIO(newline='');csv.writer(expected_csv).writerows(meta['rows'])
                if dest.read_bytes()!=expected_csv.getvalue().encode():errors.append('converted CSV differs from actual rows')
            elif a['format']!='text' or status!='readable' or dest.read_text()!=text:errors.append('converted text differs from actual source')
        expected[a['destination']]=sha(dest)
        if a['op'] in ('move','quarantine'):expected.pop(source)
    if snapshot(root)!=expected:errors.append('unrequested or missing filesystem changes')
    if c['require_result_read']:
        inspected={row['path'] for p in (output/'result-inspections').glob('*.json') for row in json.loads(p.read_text())['files']}
        read_paths={json.loads(p.read_text())['path'] for p in (output/'reads').glob('*.json')}
        required={a['destination'] for a in c['actions']}
        if not required<=inspected:errors.append('actual execution receipt not inspected')
        if not required<=read_paths:errors.append('produced results not actually read')
    review['passed']=not errors;review['operation_contract_version']=VERSION;return review
