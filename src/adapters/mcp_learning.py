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
        return ['src/adapters/dsh_operation_motif.ts','src/motif_core/operation_graph_policy.ts','src/motif_core/control_flow_policy.ts',
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
        parser=FileScene.__new__(FileScene);parser.spec=spec
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

class ManagementOperations(FileOperationsV2):
    def validate(self,spec,prepared):
        from management_contract import VERSION as QUALITY_VERSION
        if spec.get('management_contract')!='sss-management-v3' or spec.get('quality',{}).get('version')!=QUALITY_VERSION:raise ValueError('independent management contract required')
        rows=prepared['mcp_rows']
        if len(rows)!=1 or rows[0]['config']['args']!=[str(ROOT/'scenarios/file-management/management_tools.py')]:raise ValueError('registered management service changed')
    def scope(self,spec):
        import sys
        sys.path.insert(0,str(ROOT/'scenarios/file-management'))
        from management_tools import execution_version,LOW_OPS
        return {'input_sha256':digest(spec),'execution_version':execution_version(),
          'permission_sha256':digest({'owner':spec['owner'],'workspace_id':spec['workspace_id'],'external_roots':spec.get('external_roots',{}),'low_operations':sorted(LOW_OPS),'read_only':spec.get('rules',{}).get('read_only',False),'high_risk':'one_plan_native_confirmation'}),
          'initial_snapshot_sha256':digest(spec['initial_tree']),'result_read_allowed':True}
    def runtime_sources(self):
        return [*super().runtime_sources(),'scenarios/file-management/management_tools.py','scenarios/file-management/management_native.py','scenarios/file-management/management_reading.py','scenarios/file-management/management_contract.py','scenarios/file-management/management_goals.py','scenarios/file-management/management_provenance.py','src/adapters/management_program.ts','src/adapters/general_tool_replay.py','src/adapters/general_tools.py','src/adapters/geneloop_pdf.py','scenarios/file-management/general-tools.json','scenarios/general/runtime.py','scenarios/file-management/management_temporal.py','src/adapters/management_temporal.ts','src/adapters/management_seed.py','src/adapters/management_seed.ts','src/adapters/management_model_gate.py','src/adapters/management_model_gate.ts','src/adapters/management_platform_budget.py','src/adapters/file_event_projection.ts','src/adapters/file_task_scope.ts','src/adapters/harless_file_scene.ts','src/adapters/file_approval_bridge.ts','scenarios/file-management/file_scene_worker.py','src/adapters/file_scenario.py','src/adapters/file_cost_gate.py','src/adapters/file_acceptance_guard.ts']
    def verify_record(self,spec,record,origin,rows,events):
        import sys,json
        sys.path.insert(0,str(ROOT/'scenarios/file-management'))
        from management_contract import verify_management
        from file_tools import FileScene
        from .continuous_rsi import read,sha
        task=next((r['out'] for r in rows if r['name'].endswith('__read_task')),None)
        if not task or task.get('learning_scope')!=self.scope(spec):raise ValueError('actual management MCP scope differs')
        delivery=Path(record['delivery']);review=verify_management(spec,read(delivery/'report.json'),delivery,root_paths={'workspace':origin/'final-workspace',**{k:v['path'] for k,v in spec.get('external_roots',{}).items()}},events=events)
        if not review['passed']:raise ValueError('management quality rejected: '+str(review['errors']))
        if not review['temporal']['verified']:raise ValueError('temporal goal not independently verified')
        state=read(delivery/'management-state.json')
        if any(p['risks'] for p in state['plans'].values()):raise ValueError('high-risk human decisions retained but not automatically recertified or reused as grants')
        # Semantic planning remains at the real model root. Certification covers
        # the guarded parameter graph and immutable effect-integrity standard;
        # exact goal predicates, when supplied before a task, remain mandatory.
        from management_tools import ManagementScene
        parser=ManagementScene.__new__(ManagementScene);parser.spec=spec;parser.output=delivery
        from management_provenance import resolve_read_source,ReadReplayPath
        observed=[]
        for row in rows:
            if not row.get('out'):continue
            if row['name'].endswith('__read_file'):observed.append(row['out'])
            elif row['name'].endswith('__read_files'):observed.extend(row['out'].get('reads',[]))
        for p in (delivery/'reads').glob('*.json'):
            v=read(p);key,name=v['path'].split('/',1)
            if key!='workspace':raise ValueError('external read cannot silently enter automatic certification')
            if not any({k:x for k,x in rb.items() if k not in ('_sss_scope','_sss_authorized')}==v for rb in observed):raise ValueError('read provenance lacks its actual original MCP result')
            src=resolve_read_source(spec,v,state,origin/'pristine')
            import zipfile,subprocess,xml.etree.ElementTree as ET
            try:status,text,meta=parser.parse(ReadReplayPath(src,v['path']))
            except (ValueError,OSError,KeyError,zipfile.BadZipFile,ET.ParseError,subprocess.SubprocessError) as error:
                if v['status']!='unreadable' or v.get('diagnostic')!=type(error).__name__:raise ValueError('management unreadable observation differs') from error
                continue
            if (status,text[:6000],meta)!=(v['status'],v.get('text',''),v.get('metadata',{})):raise ValueError('management read replay differs')
        from management_reading import verify_documents,verify_visual_reads
        document_errors=verify_documents(spec,state,delivery,pristine=origin/'pristine')
        document_errors+=verify_visual_reads(spec,state,delivery,pristine=origin/'pristine')
        if document_errors:raise ValueError(str(document_errors))
        from src.adapters.general_tool_replay import verify_general_tools
        verify_general_tools(spec,record,origin,rows)
        chunks=[{k:v for k,v in r['out'].items() if k not in ('_sss_scope','_sss_authorized')} for r in rows
                if r.get('out') and r['name'].endswith('__read_document_chunk')]
        opens=[r['out'] for r in rows if r.get('out') and r['name'].endswith('__open_document')]
        for d in state.get('documents',{}).values():
            if not any(r.get('document_id')==d['document_id'] and r.get('source_id')==d['anchor']['source_id'] for r in opens):raise ValueError('document lacks actual native opening')
            if any(c not in chunks for c in d['chunks'].values()):raise ValueError('document coverage lacks actual native chunk results')
        views=[{k:v for k,v in r['out'].items() if k not in ('_sss_scope','_sss_authorized')} for r in rows
               if r.get('out') and r.get('image_attachments') and r['name'].endswith('__view_document_page')]
        if any(v not in views for v in state.get('visual_reads',{}).values()):raise ValueError('visual input lacks actual native tool result')
    def copy_material(self,spec,pristine,workspace,nonce):
        import shutil,json
        shutil.copytree(pristine,workspace);changed=0
        fixed=spec.get('certification_fixed_sources',[])
        if any(n not in spec['initial_snapshot'] for n in fixed):raise ValueError('fixed semantic source outside original input')
        for p in workspace.rglob('*'):
            if not p.is_file() or p.name=='.experiment-copy':continue
            if p.relative_to(workspace).as_posix() in fixed:continue
            ext=p.suffix.lower();before=p.read_bytes()
            if ext in ('.txt','.md') and before:p.write_text(p.read_text()+'\nIndependent material '+nonce+'\n')
            elif ext=='.docx':
                from zipfile import ZipFile
                import xml.etree.ElementTree as ET
                with ZipFile(p) as z:parts={n:z.read(n) for n in z.namelist()}
                ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
                d=ET.fromstring(parts['word/document.xml']);para=ET.SubElement(d.find(ns+'body'),ns+'p');run=ET.SubElement(para,ns+'r');ET.SubElement(run,ns+'t').text='Independent material '+nonce
                parts['word/document.xml']=ET.tostring(d,encoding='utf-8',xml_declaration=True)
                with ZipFile(p,'w') as z:
                    for n,b in parts.items():z.writestr(n,b)
            elif ext=='.xlsx':
                from openpyxl import load_workbook
                d=load_workbook(p);d.active.append(['Independent material',nonce]);d.save(p)
            elif ext=='.pdf':
                from pypdf import PdfReader,PdfWriter
                d=PdfWriter();d.append(PdfReader(p));d.add_metadata({'/IndependentMaterial':nonce})
                with p.open('wb') as f:d.write(f)
            elif ext in ('.png','.jpg','.jpeg'):
                from PIL import Image
                with Image.open(p) as im:
                    im=im.convert('RGB');color=im.getpixel((0,0));im.putpixel((0,0),((color[0]+1)%256,color[1],color[2]));im.save(p)
            elif ext in ('.csv','.tsv') and before:p.write_text(p.read_text()+'\nIndependent material,'+nonce+'\n')
            elif ext=='.json':
                value=json.loads(p.read_text())
                if not isinstance(value,dict):raise ValueError('no independent material generator for this JSON structure')
                value['independent_material']=nonce;p.write_text(json.dumps(value))
            elif not before:continue
            else:raise ValueError('no registered independent material generator for '+ext)
            changed+=p.read_bytes()!=before
        if not changed:raise ValueError('independent management material needs fresh source bytes')

REGISTRY={'file_operations_v1':FileOperations,'file_operations_v2':FileOperationsV2,'management_v3':ManagementOperations}
def adapter(identity):
    if identity not in REGISTRY:raise ValueError('no registered material/quality adapter for this MCP scene')
    return REGISTRY[identity]()
