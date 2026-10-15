"""Scene-owned material/acceptance adapters; discovery is independent of tool names.

New MCP scenes register a trusted adapter here. Task/model content cannot load
Python modules or change authority. The compiler consumes standard tool _meta.
"""
from __future__ import annotations
from pathlib import Path
from typing import Protocol
from .continuous_rsi import ROOT
from src.motif_core.offline.experience_registry import digest

class LearningAdapter(Protocol):
    def validate(self,spec,prepared): ...
    def scope(self,spec): ...
    def runtime_sources(self): ...
    def verify_record(self,spec,record,origin,rows,events): ...
    def copy_material(self,spec,pristine,workspace,nonce): ...

class FileOperations:
    def validate(self,spec,prepared):
        if spec.get('workflow_contract') or spec.get('task_contract') or not spec.get('operation_contract'):
            raise ValueError('file operation adapter requires its independent business acceptance')
        if not set(spec['allowed_operations'])<= {'copy','move','convert','archive','quarantine'}:
            raise ValueError('operation outside original experiment grant')
        rows=prepared['mcp_rows']
        if len(rows)!=1 or rows[0]['config']['args']!=[str(ROOT/'scenarios/file-management/operation_tools.py')]:
            raise ValueError('registered file adapter service changed')
        if spec['report_contract']['kind']!='task_result':raise ValueError('effect task needs task_result acceptance')
    def scope(self,spec):
        import sys
        sys.path.insert(0,str(ROOT/'scenarios/file-management'))
        from operation_tools import operation_version
        return {'input_sha256':digest(spec),'execution_version':operation_version(),
                'permission_sha256':digest({'operations':spec['allowed_operations'],'rules':spec['rules']}),
                'initial_snapshot_sha256':digest(spec['initial_snapshot']),'result_read_allowed':spec['operation_contract']['require_result_read']}
    def runtime_sources(self):
        return ['src/adapters/dsh_operation_motif.ts','src/motif_core/operation_graph_policy.ts',
                'src/motif_core/online_skill_runtime.mjs','scenarios/file-management/operation_tools.py',
                'scenarios/file-management/operation_contract.py','scenarios/file-management/report_tools.py',
                'scenarios/file-management/collection_tools.py','scenarios/file-management/file_tools.py','scenarios/file-management/common.py']
    def verify_record(self,spec,record,origin,rows,events):
        import sys
        from .continuous_rsi import read,sha
        sys.path.insert(0,str(ROOT/'scenarios/file-management'))
        from operation_contract import verify_operations
        from file_tools import FileScene
        scope=self.scope(spec)
        task=next((r['out'] for r in rows if r['name'].endswith('__read_task')),None)
        if not task or task.get('learning_scope')!=scope:raise ValueError('actual MCP authority/scope differs')
        delivery=Path(record['delivery']);review=verify_operations(spec,read(delivery/'report.json'),delivery,events)
        if not review['passed']:raise ValueError('operation delivery rejected: '+str(review['errors']))
        parser=FileScene.__new__(FileScene)
        for p in (delivery/'reads').glob('*.json'):
            rb=read(p);src=origin/'pristine'/rb['path']
            if not src.exists() or sha(src)!=rb['sha256']:src=origin/'final-workspace'/rb['path']
            if sha(src)!=rb['sha256']:raise ValueError('operation read version differs')
            try:status,text,meta=parser.parse(src)
            except Exception:
                if rb['status']!='unreadable':raise
            else:
                if (status,text[:6000],meta)!=(rb['status'],rb.get('text',''),rb.get('metadata',{})):raise ValueError('operation read replay differs')
    def copy_material(self,spec,pristine,workspace,nonce):
        import shutil,json
        shutil.copytree(pristine,workspace);changed=0
        for p in workspace.rglob('*'):
            if p.is_file() and p.suffix.lower() in ('.txt','.md') and p.stat().st_size:
                try:json.loads(p.read_text());continue
                except (ValueError,UnicodeError):pass
                p.write_text(p.read_text()+'\nIndependent material '+nonce+'\n');changed+=1
        if not changed:raise ValueError('independent material adapter requires new source bytes')

class FileOperationsV2(FileOperations):
    durable=True
    def validate(self,spec,prepared):
        from copy import deepcopy
        replacement=deepcopy(prepared)
        if len(replacement['mcp_rows'])!=1 or replacement['mcp_rows'][0]['config']['args']!=[str(ROOT/'scenarios/file-management/operation_tools_v2.py')]:raise ValueError('registered v2 service changed')
        replacement['mcp_rows'][0]['config']['args']=[str(ROOT/'scenarios/file-management/operation_tools.py')]
        super().validate(spec,replacement)
        if spec['operation_contract'].get('validation_version')!='sss-file-operation-quality-v2':raise ValueError('new independent quality contract required')
    def scope(self,spec):
        import sys
        sys.path.insert(0,str(ROOT/'scenarios/file-management'))
        from operation_tools_v2 import operation_version
        return {**super().scope(spec),'execution_version':operation_version()}
    def runtime_sources(self):
        return [*super().runtime_sources(),'src/motif_core/operation_graph_policy_v1.ts',
          'scenarios/file-management/operation_tools_v2.py','scenarios/file-management/operation_contract_v2.py','src/adapters/operation_job.ts','src/adapters/file_workflow_job.ts']
    def verify_record(self,spec,record,origin,rows,events):
        super().verify_record(spec,record,origin,rows,events)
        from operation_contract_v2 import verify_operations_v2
        from .continuous_rsi import read
        r=verify_operations_v2(spec,read(Path(record['delivery'])/'report.json'),record['delivery'],events)
        if not r['passed']:raise ValueError('v2 independent quality rejected: '+str(r['errors']))

REGISTRY={'file_operations_v1':FileOperations,'file_operations_v2':FileOperationsV2}
def adapter(identity):
    if identity not in REGISTRY:raise ValueError('no registered material/quality adapter for this MCP scene')
    return REGISTRY[identity]()
