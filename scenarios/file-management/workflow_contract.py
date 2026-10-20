"""Versioned scope guards and independent byte acceptance for the first workflow batch."""
from __future__ import annotations
import json,zipfile
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
from common import ROOT,DATA,digest,sha,snapshot
from task_contract import relative
VERSION='sss-file-workflow-v1'

class WorkflowContract(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    version:Literal['sss-file-workflow-v1']
    workflow_id:Literal['FM01','FM05','FM13','FM17','FM21','FM38']
    source_paths:list[str]=Field(max_length=32)
    destination_prefixes:list[str]=Field(min_length=1,max_length=8)
    required_reads:list[str]=Field(default_factory=list,max_length=32)
    allowed_reads:list[str]=Field(default_factory=list,max_length=32)
    context_paths:list[str]=Field(default_factory=list,max_length=8)
    recovery_goal:Literal['complete','rollback']='complete'
    @model_validator(mode='after')
    def valid(self):
        for values in (self.source_paths,self.required_reads,self.allowed_reads,self.context_paths):
            if len(values)!=len(set(values)):raise ValueError('duplicate workflow path')
            for path in values:relative(path)
        for prefix in self.destination_prefixes:
            if not prefix.endswith('/'):raise ValueError('destination prefix needs trailing slash')
            relative(prefix[:-1])
        if not set(self.required_reads)<=set(self.allowed_reads):raise ValueError('required read outside allowed scope')
        return self

def contract(spec):
    c=WorkflowContract.model_validate(spec['workflow_contract'])
    if not set(c.source_paths+c.allowed_reads+c.context_paths)<=set(spec['initial_snapshot']):raise ValueError('workflow original absent')
    return c

def verify_workflow(spec,report,output,events=None):
    """Oracle is private, hash-bound, and never exposed through read_task or model tools."""
    c=contract(spec);output=Path(output);errors=[]
    oracle_path=Path(spec['workflow_oracle_file']).resolve()
    if not oracle_path.is_relative_to((ROOT/'.local').resolve()) or sha(oracle_path)!=spec['workflow_oracle_sha256']:raise ValueError('frozen workflow oracle changed')
    oracle=json.loads(oracle_path.read_text());actual=snapshot(spec['workspace'])
    expected=dict(oracle['expected_snapshot'])
    zip_path=oracle.get('zip_path')
    if zip_path:
        try:
            with zipfile.ZipFile(Path(spec['workspace'])/zip_path) as z:
                names=z.namelist()
                if len(names)!=len(set(names)) or set(names)!=set(oracle['zip_members']):errors.append('ZIP membership differs')
                if z.testzip() is not None:errors.append('ZIP CRC failed')
                import hashlib
                for name,h in oracle['zip_members'].items():
                    if name not in names or hashlib.sha256(z.read(name)).hexdigest()!=h:errors.append('ZIP bytes differ: '+name)
            if zip_path in actual:expected[zip_path]=actual[zip_path]
        except (OSError,ValueError,KeyError,zipfile.BadZipFile):errors.append('no valid actual ZIP')
    if actual!=expected:errors.append('workflow file postcondition differs')
    observations=[json.loads(p.read_text()) for p in (output/'reads').glob('*.json')]
    read_paths=set()
    for row in observations:
        name=row['path'];read_paths.add(name)
        if name not in c.allowed_reads:errors.append('read outside workflow scope: '+name)
        if row.get('sha256')!=spec['initial_snapshot'].get(name):errors.append('original read version differs: '+name)
        if row.get('source_version')!=digest({'path':name,'sha':row.get('sha256'),'parser':'fm-parser-v1'}):errors.append('read source version differs: '+name)
    if not set(c.required_reads)<=read_paths:errors.append('workflow required reads missing')
    if not report:errors.append('no actual workflow report')
    else:
        wanted={'file:local:'+digest({'path':name,'sha':h})[:24] for name,h in actual.items() if name!='.experiment-copy'}
        if set(report.get('file_ids',[]))!=wanted or len(report.get('file_ids',[]))!=len(wanted):errors.append('workflow report current identities differ')
        if report.get('input_sha256')!=digest(spec) or report.get('final_snapshot')!=actual:errors.append('workflow report input/snapshot differs')
        if report.get('workflow_contract_version')!=VERSION:errors.append('workflow report version differs')
        if c.workflow_id=='FM38':
            from recovery_tools import recovery_version
            if report.get('recovery_execution_version_sha256')!=recovery_version():errors.append('recovery execution version differs')
        else:
            from workflow_tools import workflow_version
            if report.get('workflow_execution_version_sha256')!=workflow_version():errors.append('workflow execution version differs')
        for marker in oracle.get('required_gap_markers',[]):
            if not any(marker in gap for gap in report.get('gaps',[])):errors.append('workflow gap omitted: '+marker)
    journals=[json.loads(p.read_text()) for p in (output/'journals').glob('*.json')]
    if oracle.get('require_effects') and not journals:errors.append('no actual operation journal')
    if oracle.get('require_restore') and not any(j.get('status')=='restored_verified' for j in journals):errors.append('no actual restored journal')
    # Backup recovery must actually read a produced backup, not recopy originals.
    if c.workflow_id=='FM17' and c.source_paths:
        restore_sources=[]
        for j in journals:
            before=j.get('before',{})
            ids={'file:local:'+digest({'path':n,'sha':h})[:24]:n for n,h in before.items()}
            for a in j.get('completed',[]):
                if a['destination'].startswith('recovery-drill/'):
                    restore_sources.extend(ids.get(fid,'') for fid in a['file_ids'])
        if set(restore_sources)!=set(oracle['backup_sources']):errors.append('recovery did not copy actual backup sources')
    manifest={'contract_version':VERSION,'workflow_id':c.workflow_id,'input_sha256':digest(spec),
              'snapshot_sha256':digest(actual),'actual_files':actual,'journal_ids':[j['plan_id'] for j in journals],
              'mapping':oracle.get('mapping',{}),'mapping_verified':actual==expected,
              'zip_members_verified':bool(zip_path and not errors),'derived_by':'fixed independent acceptance, not model-authored',
              'human_semantic_review':'not performed','errors':errors}
    return {'passed':not errors,'errors':errors,'contract_version':VERSION,'manifest':manifest,'human_blind_review':False}
