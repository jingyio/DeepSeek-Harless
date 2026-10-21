#!/usr/bin/env python3
"""Review unchanged Paper/PPT Motif IR against native capability integration.

Network-free --preview is the default. --write creates fresh immutable v26/v23
only after the source is frozen. Registry changes additionally require the
explicit --update-registry flag. Old releases, raw evidence, MCP schemas and
online programs are never rewritten. This performs no learning or model call.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.tool_schema_contracts import bind_mcp_descriptions

SPEC=importlib.util.spec_from_file_location('native_compat_exporter',ROOT/'scripts/export-online-motif-manifest.py')
exporter=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(exporter)

COMMON_REVIEWED={
    'config/geneloop-capabilities.json','config/geneloop-capabilities.md',
    'src/adapters/deepseek_cost_gate.py','src/adapters/dsh_web_tasks.ts',
    'src/adapters/geneloop_capabilities.ts','src/adapters/geneloop_shell.ts',
    'src/adapters/harless_comparison.ts','src/adapters/harless_comparison_artifacts.ts',
    'src/adapters/harless_task_progress.ts',
    'src/adapters/harless_reasoning.ts',
    'scripts/harless_gateway.mjs',
}
ADDITIONAL_LOCKS={
    'scripts/reexport-native-capabilities-compat.py','scripts/harness-web.py',
    'src/adapters/geneloop_context.ts','src/adapters/geneloop_delegation.ts',
    'src/adapters/geneloop_fs.ts','src/adapters/geneloop_fs_search.ts',
    'src/adapters/geneloop_interactions.ts','src/adapters/geneloop_native_work.ts',
    'src/adapters/geneloop_retry.ts','src/adapters/geneloop_plan.ts',
    'src/adapters/geneloop_goal.ts',
    'src/adapters/geneloop_web_search.ts','src/adapters/geneloop_native_host.mjs',
    'scripts/prepare-native-host.mjs',
    'src/adapters/geneloop_runtime_routes.ts','src/adapters/harless_file_scene.ts',
}
RELEASES=[
    ('paper-web-v24','paper-web-v26','paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json',COMMON_REVIEWED|{'scripts/harness-web.py','scripts/learn-web-paper-document-motif.py','src/adapters/geneloop_web_search.ts'}),
    ('ppt-master-v21','ppt-master-v23','ppt',
     'scenarios/ppt_master/contracts.json',COMMON_REVIEWED|{'scenarios/ppt_master/prompt.md'}),
]
# v25/v22 are preserved, superseded local candidates, never overwritten. The
# certified program/evidence still comes from v24/v21, not those candidates.
REGISTRY_SELECTED={'paper-web-v24':'paper-web-v25','ppt-master-v21':'ppt-master-v22'}
IMMUTABLE_ARTIFACTS=('library.json','online-manifest.json','task.json','tool-schemas.json','source-evidence.json')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):Path(path).write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())

def review():
    registry=(ROOT/'config/harless-scenes.json').read_text(encoding='utf-8')
    capabilities=read(ROOT/'config/geneloop-capabilities.json')
    native=capabilities['tools']
    if (not isinstance(native,list)
        or any(not isinstance(name,str) or not re.fullmatch(r'[a-z][a-z0-9_]*',name) or name.startswith('mcp__') for name in native)
        or len(native)!=len(set(native))):
        raise ValueError('Common tools must remain a distinct native vocabulary')
    candidates=[]
    for old_name,new_name,scene,contracts_path,allowed in RELEASES:
        old,new=(ROOT/'motif-libraries'/name for name in (old_name,new_name))
        if new.exists():raise ValueError('Fresh release path already exists; published/failed evidence must not be overwritten: '+new_name)
        entry,cert=read(old/'entry.json'),read(old/'certification.json')
        for name,expected in entry['files'].items():
            if Path(name).name!=name or (old/name).is_symlink() or sha(old/name)!=expected:
                raise ValueError('Previous published artifact changed: '+old_name+'/'+name)
        for name,expected in cert['file_locks'].items():
            if sha(old/name)!=expected:raise ValueError('Previous certification artifact changed: '+old_name+'/'+name)
        if sha(old/'source-evidence.json')!=cert['source_evidence_sha256'] or sha(old/'learning-report.json')!=cert['learning_report_sha256']:
            raise ValueError('Previous evidence/report binding changed: '+old_name)
        differences={name for name,expected in cert['code_locks'].items() if not (ROOT/name).is_file() or sha(ROOT/name)!=expected}
        if differences!=allowed:
            raise ValueError('Exact source review differs for '+old_name+': '+repr({'actual':sorted(differences),'expected':sorted(allowed)}))
        schemas=read(old/'tool-schemas.json')
        names={row['name'] for row in schemas}
        if any(not name.startswith('mcp__') for name in names) or names.intersection(native):
            raise ValueError('Public native tools entered certified MCP schemas: '+old_name)
        library,manifest=read(old/'library.json'),read(old/'online-manifest.json')
        learned_tools={name for row in library.get('artifacts',[]) for name in row.get('tools',[])}
        if learned_tools.intersection(native) or set(manifest.get('contracts',{})).intersection(native):
            raise ValueError('Public native tools entered the learned program: '+old_name)
        contracts=read(ROOT/contracts_path)
        bound=bind_mcp_descriptions(parse_tool_contracts(contracts),
            [{'name':row['name'],'description':row['description'],'inputSchema':row['parameters']} for row in schemas])
        contracts={name:{**contracts[name],'description':row.description} for name,row in bound.items()}
        if exporter.export_manifest(library,contracts,manifest['slot_rules'],manifest['version_fields'])!=manifest:
            raise ValueError('Re-export changed the certified online program: '+old_name)
        needle='motif-libraries/'+REGISTRY_SELECTED[old_name]
        if registry.count(needle)!=1:raise ValueError('Registry no longer selects the expected previous release: '+old_name)
        registry=registry.replace(needle,'motif-libraries/'+new_name)
        lock_names=set(cert['code_locks'])|ADDITIONAL_LOCKS
        locks={name:sha(ROOT/name) for name in sorted(lock_names)}
        candidates.append({'previous':old_name,'release':new_name,'scene':scene,'old':old,'new':new,
            'entry':entry,'cert':cert,'locks':locks,'native_tools':native,
            'reviewed_changes':sorted(differences),'additional_locks':sorted(lock_names-set(cert['code_locks'])),
            'locked_artifact_hashes':{name:sha(old/name) for name in IMMUTABLE_ARTIFACTS},
            'old_lock_differences':{name:{'previous':cert['code_locks'][name],'current':locks[name]} for name in sorted(differences)}})
    return candidates,registry

def compatibility_record(candidate,validation_record):
    return {'method':'reexport_certified_serialized_library','previous_release':candidate['previous'],
        'previous_certification_sha256':sha(candidate['old']/'certification.json'),
        'same_library_and_evidence':True,'same_online_program':True,'same_mcp_schema':True,
        'public_native_tools':candidate['native_tools'],'public_native_tools_in_certified_mcp_schema':False,
        'public_native_tools_learned_or_certified':False,
        'changed_code_locks':candidate['reviewed_changes'],'additional_code_locks':candidate['additional_locks'],
        'previous_code_lock_differences':candidate['old_lock_differences'],
        'unchanged_artifact_sha256':candidate['locked_artifact_hashes'],
        'repairs':['native_image_and_filesystem_channel_with_session_containment',
                   'native_search_in_existing_session_command_sandbox',
                   'skill_todo_present_and_question_surface_integration',
                   'same_task_metered_delegation','native_context_pressure_and_accounted_retry_boundaries'],
        'raw_traces_replayed':False,'new_training_tasks':0,'model_requests':0,
        'quality_cost_promoted':False,'net_cost_reduction_proven':False,
        'validation_record':validation_record,
        'training_flag_scope':'Existing entry/report new_training=true identifies the original independently trained library; this compatibility export adds zero training tasks.'}

def prepare(candidate,directory,validation_record):
    shutil.copytree(candidate['old'],directory,dirs_exist_ok=True)
    report=read(directory/'learning-report.json')
    report['native_capabilities_compatibility']=compatibility_record(candidate,validation_record)
    report['common_native_tools']=candidate['native_tools']
    report['common_native_tools_in_certified_mcp_schema']=False
    report['common_capabilities_compatibility_scope']='Public native tools are separately admitted by current code-locked policy; they are not mined, certified, replayed, or claimed as newly learned by this MCP-only compatibility re-export.'
    write(directory/'learning-report.json',report)
    (directory/'README.md').write_bytes((
        '# '+candidate['release']+'\n\n'
        '从 '+candidate['previous']+' 重导出的原生能力兼容版本。相同 IR、online manifest、task、完整 MCP schema 与来源证据逐字节保留；旧库保留。\n\n'
        '公共原生 read/read_image、文件搜索、skill/todo/present、提问和同任务受控子 Agent 是运行环境能力，未加入本库认证的 MCP 子集，也没有被本次学习。'
        'PPT 新增的 read_image 页面视觉检查属于两侧共同的真实图像通道，原来源固定与转换结构不变。'
        '上下文压力、重试计量与用户界面接线通过代码锁绑定，不是新的结构认证。\n\n'
        '本次零新训练任务、零原始轨迹重放、零模型调用；不声称合格净降本。entry/report 原有 new_training=true 描述原始训练来源，'
        '不是本次重导出发生训练。当前质量、费用和压力效果需独立真实实验；未测结果不能写为通过。\n\n'
        '验证记录：'+validation_record+'。\n').encode())
    cert=dict(candidate['cert'])
    cert.update(code_locks=candidate['locks'],learning_report_sha256=sha(directory/'learning-report.json'),
        file_locks={name:sha(directory/name) for name in cert['file_locks']})
    write(directory/'certification.json',cert)
    entry=dict(candidate['entry']);entry['files']={name:sha(directory/name) for name in entry['files']}
    write(directory/'entry.json',entry)
    for name,expected in candidate['locked_artifact_hashes'].items():
        if sha(directory/name)!=expected:raise ValueError('Compatibility export altered immutable artifact: '+name)
    from src.adapters.harless_rsi_bundle import load_product_bundle
    admitted=load_product_bundle(ROOT,directory,candidate['scene'])
    if admitted['runtime_kind']!=entry['runtime_kind']:raise ValueError('Runtime kind changed')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--preview',action='store_true');mode.add_argument('--write',action='store_true')
    parser.add_argument('--update-registry',action='store_true')
    parser.add_argument('--validation-record',default='docs/experiments/dsh-native-capabilities-20261021.md')
    args=parser.parse_args()
    if args.update_registry and not args.write:parser.error('--update-registry requires --write after final source freeze')
    candidates,registry=review()
    if not args.write:
        print(json.dumps({'written':False,'registry_updated':False,'model_requests':0,'new_training_tasks':0,
          'releases':[{key:row[key] for key in ('previous','release','scene','reviewed_changes','additional_locks','old_lock_differences','locked_artifact_hashes','native_tools')} for row in candidates]},ensure_ascii=False,indent=2))
        return
    # Prepare and verify both under fresh private staging names before any final release is published.
    staged=[]
    for candidate in candidates:
        stage=Path(tempfile.mkdtemp(prefix='.native-compat-'+candidate['release']+'-',dir=ROOT/'motif-libraries'))
        prepare(candidate,stage,args.validation_record);staged.append((candidate,stage))
    # A source edit during the export cannot silently produce mixed locks.
    for candidate,_ in staged:
        if any(sha(ROOT/name)!=expected for name,expected in candidate['locks'].items()):raise ValueError('Source changed during export; preserve staging evidence and re-review')
        if candidate['new'].exists():raise ValueError('Release appeared during export; refuse overwrite')
    for candidate,stage in staged:os.rename(stage,candidate['new'])
    if args.update_registry:(ROOT/'config/harless-scenes.json').write_bytes(registry.encode())
    print(json.dumps({'written':True,'registry_updated':args.update_registry,'model_requests':0,'new_training_tasks':0,
      'releases':[row['release'] for row in candidates],'same_mcp_schema':True,'same_online_program':True,'quality_cost_promoted':False}))

if __name__=='__main__':main()
