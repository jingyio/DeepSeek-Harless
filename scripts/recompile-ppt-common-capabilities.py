#!/usr/bin/env python3
"""Recompile existing private PPT evidence after the additive common-tool change.

No model calls or new training samples. Previous release bytes remain untouched.
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scenarios.research_ppt.motif_v6 import learn,validate_compilation

sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    old=ROOT/'motif-libraries/ppt-web-v2-r6';new=ROOT/'motif-libraries/ppt-web-v2-r7'
    out=args.out.resolve()
    if not out.is_relative_to(ROOT/'.local') or out.exists() or new.exists():raise ValueError('new private compilation and release paths required')
    out.mkdir(parents=True)
    evidence=read(old/'source-evidence.json')
    for split,folders in [('train',['train-1','train-2']),('heldout',['heldout-1'])]:
        for item,folder in zip(evidence[split],folders,strict=True):
            source=args.evidence/folder;identity=read(source/'task-identity.json')
            assert sha(source/'agent-events.jsonl')==identity['events_sha256']==item['events_sha256']
            assert identity['research_decision_id']==item['research_decision_id']
            shutil.copytree(source,out/folder)
    write(out/'dataset.json',{'train':['train-1','train-2'],'heldout':['heldout-1']})
    schemas=read(old/'tool-schemas.json')
    write(out/'schema.json',{'tools':[{'name':s['name'],'description':s['description'],'inputSchema':s['parameters']} for s in schemas]})
    guards=[ROOT/'src/adapters'/name for name in ('harless_task_scope.ts','harless_ppt_recovery.ts','dsh_web_tasks.ts',
        'harless_scenarios.py','harless_rsi_binding.ts','harless_rsi_bundle.py','geneloop_capabilities.ts','geneloop_shell.ts','geneloop_web_search.ts',
        'geneloop_command_broker.ts','geneloop_command_client.mjs')]
    manifest=learn(out/'dataset.json',contracts_path=ROOT/'scenarios/research_ppt/web-read-contracts.json',
        version_fields_path=ROOT/'scenarios/research_ppt/web-read-version-fields.json',tool_schema_path=out/'schema.json',
        out_dir=out/'compiled',guard_paths=tuple(guards),mining='witnessed_edges')
    validate_compilation(manifest)
    assert read(manifest)['artifacts']==read(old/'online-manifest.json')['artifacts']
    assert {k:v for k,v in read(manifest).items() if k not in ('manifest_digest','source_library_digest')}=={
        k:v for k,v in read(old/'online-manifest.json').items() if k not in ('manifest_digest','source_library_digest')}
    new.mkdir()
    for name in ('online-manifest.json','library.json'):shutil.copyfile(manifest.parent/name,new/name)
    for name in ('task.json','tool-schemas.json','tool-schema-variants.json','source-evidence.json'):shutil.copyfile(old/name,new/name)
    report=read(old/'learning-report.json');report.update(library_digest=read(manifest.parent/'library.json')['library_digest'],
        manifest_digest=read(manifest)['manifest_digest'],recompilation_of_manifest_digest=read(old/'online-manifest.json')['manifest_digest'],
        previous_manifest_file_sha256=sha(old/'online-manifest.json'),new_collection_tasks_for_recompilation=0,
        compatibility_scope='Same independently collected train/heldout events, unchanged witnessed read artifacts and complete 21-tool MCP contracts. Additive native web/command/job tools are separately allowlisted and excluded only from the certified MCP schema comparison. Current source guards are recompiled. No new collection or quality/cost promotion; validation is recorded separately.')
    write(new/'learning-report.json',report)
    cert=read(old/'certification.json')
    locks=set(cert['code_locks'])|{str(p.relative_to(ROOT)) for p in guards}|{'config/geneloop-capabilities.json','config/geneloop-capabilities.md'}
    cert.update(source_evidence_sha256=sha(new/'source-evidence.json'),learning_report_sha256=sha(new/'learning-report.json'),
        file_locks={p.name:sha(p) for p in new.iterdir()},code_locks={name:sha(ROOT/name) for name in sorted(locks)})
    write(new/'certification.json',cert)
    entry=read(old/'entry.json');entry['files']={p.name:sha(p) for p in new.iterdir()};write(new/'entry.json',entry)
    legacy=ROOT/'motif-libraries/ppt';binding=read(legacy/'runtime-bindings.json')
    binding['code_locks']={name:sha(ROOT/name) for name in binding['code_locks']}
    binding['validation']['common_capabilities']='Additive native tools; original certified MCP contracts and original certificate unchanged.'
    write(legacy/'runtime-bindings.json',binding)
    entry=read(legacy/'entry.json');entry['files']['runtime-bindings.json']=sha(legacy/'runtime-bindings.json');write(legacy/'entry.json',entry)
    print(json.dumps({'release':'ppt-web-v2-r7','same_witnessed_artifacts':True,'model_requests':0}))

if __name__=='__main__':main()
