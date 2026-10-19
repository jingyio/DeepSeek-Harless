#!/usr/bin/env python3
"""为账户内 PPT 后台学习接线核验旧认证 IR，发布独立兼容版本。

保留原始证据和旧版；不重采集、不调用模型、不授予质量/费用晋级。
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.tool_schema_contracts import bind_mcp_descriptions
from src.adapters.harless_rsi_bundle import load_product_bundle
spec=importlib.util.spec_from_file_location('exporter',ROOT/'scripts/export-online-motif-manifest.py')
exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    shared={'src/adapters/dsh_web_tasks.ts','src/adapters/harless_rsi_bundle.py','src/adapters/dsh_online_motif.mjs'}
    releases=[('ppt-master-v8','ppt-master-v9','ppt','scenarios/ppt_master/contracts.json',
               shared|{'scripts/learn-ppt-master-motif.py','src/adapters/harless_settings.ts'}),
              ('paper-web-v13','paper-web-v14','paper-proofreading','scenarios/paper_proofreading/document-read-contracts.json',shared)]
    for previous,current,scene,contract_path,expected in releases:
        old=ROOT/'motif-libraries'/previous;new=ROOT/'motif-libraries'/current
        if new.exists():raise ValueError('Never overwrite a published compatibility release')
        entry=read(old/'entry.json');cert=read(old/'certification.json')
        for name,version in entry['files'].items():
            if sha(old/name)!=version:raise ValueError('original release changed: '+name)
        changed={name for name,version in cert['code_locks'].items() if sha(ROOT/name)!=version}
        if changed!=expected:raise ValueError('unreviewed compatibility changes: '+repr(changed))
        library=read(old/'library.json');manifest=read(old/'online-manifest.json');contracts=read(ROOT/contract_path)
        schemas=[{'name':r['name'],'description':r['description'],'inputSchema':r['parameters']} for r in read(old/'tool-schemas.json')]
        bound=bind_mcp_descriptions(parse_tool_contracts(contracts),schemas)
        contracts={name:{**contracts[name],'description':row.description} for name,row in bound.items()}
        if exporter.export_manifest(library,contracts,manifest['slot_rules'],manifest['version_fields'])!=manifest:
            raise ValueError('online program changed')
        shutil.copytree(old,new)
        report=read(old/'learning-report.json')
        report['ppt_learning_compatibility']={'method':'reexport_certified_serialized_library','previous_release':previous,
            'previous_certification_sha256':sha(old/'certification.json'),'same_library_and_evidence':True,'same_online_program':True,
            'changed_code_locks':sorted(changed),'raw_traces_replayed':False,'new_training_tasks':0,'model_requests':0,
            'quality_cost_promoted':False,'validation_record':'docs/experiments/ppt-user-learning-20261019.md'}
        write(new/'learning-report.json',report)
        locks=set(cert['code_locks'])|{'src/adapters/harless_ppt_learning.ts','scripts/learn-web-ppt-tasks.py','scripts/reexport-ppt-learning-compat.py'}
        cert.update(code_locks={name:sha(ROOT/name) for name in sorted(locks)},
            learning_report_sha256=sha(new/'learning-report.json'),file_locks={name:sha(new/name) for name in cert['file_locks']})
        write(new/'certification.json',cert);entry['files']={name:sha(new/name) for name in entry['files']};write(new/'entry.json',entry)
        if load_product_bundle(ROOT,new,scene)['runtime_kind']!=entry['runtime_kind']:raise ValueError('release not loadable')
        print(json.dumps({'release':current,'same_online_program':True,'model_requests':0}))
    registry=ROOT/'config/harless-scenes.json';text=registry.read_text(encoding='utf-8')
    for previous,current,*_ in releases:
        if text.count('motif-libraries/'+previous)!=1:raise ValueError('unexpected scene registry')
        text=text.replace('motif-libraries/'+previous,'motif-libraries/'+current)
    registry.write_text(text,encoding='utf-8')


if __name__=='__main__':main()
