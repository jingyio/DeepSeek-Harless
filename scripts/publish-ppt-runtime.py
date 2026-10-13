#!/usr/bin/env python3
"""Recompile independent historical traces, then emit only guarded runtime assets.

No cloud calls, no rewritten old certificates, no quality or savings promotion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scenarios.research_ppt.motif_v6 import learn

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--dataset',type=Path,required=True);a.add_argument('--schemas',type=Path,required=True)
    a.add_argument('--output',type=Path,required=True);args=a.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to((ROOT/'.local').resolve()):raise ValueError('private output required')
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    raw=json.loads(args.schemas.read_text());schemas=raw.get('tools',[]) if isinstance(raw,dict) else raw
    if not isinstance(schemas,list) or len(schemas)!=19 or any(not s['name'].startswith('mcp__ppt__') for s in schemas):
        raise ValueError('actual full 19-tool Harness schema snapshot required')
    if schemas!=sorted(schemas,key=lambda s:s['name']):raise ValueError('actual Harness tool order required')
    mcp=[{'name':s['name'],'description':s['description'],'inputSchema':s['parameters']} for s in schemas]
    schema_path=out/'actual-mcp-schema.json';write(schema_path,{'tools':mcp})
    manifest=learn(args.dataset,tool_schema_path=schema_path,out_dir=out/'compilation',mining='witnessed_edges')
    data=json.loads(manifest.read_text())
    if not data['artifacts'] or set(data['contracts'])!={'mcp__ppt__pin_source','mcp__ppt__read_source'}:
        raise ValueError('no compatible certified PPT read-only continuation')
    bundle=out/'runtime';bundle.mkdir(mode=0o700)
    for name in ('online-manifest.json','library.json'):
        shutil.copyfile(manifest.parent/name,bundle/name);(bundle/name).chmod(0o600)
    write(bundle/'tool-schemas.json',schemas)
    write(bundle/'task.json',{'schema_version':1,'task_id':'ppt-runtime-admission','session_id':'ppt-runtime-admission',
        'intent':'Read only sources approved for the current PPT task.','input_version':'0'*64,'bindings':{},
        'source_versions':{name:'0'*64 for name in data['version_fields']}})
    code=['src/adapters/dsh_online_motif.mjs','src/motif_core/online_skill_runtime.mjs',
          'src/adapters/harless_rsi_binding.ts','src/adapters/harless_rsi_bundle.py']
    for p in (ROOT/'scenarios/research_ppt').rglob('*'):
        if p.is_file() and not {'node_modules','tests','__pycache__'} & set(p.parts) and p.suffix in ('.py','.ts','.js'):
            code.append(str(p.relative_to(ROOT)))
    write(bundle/'certification.json',{'schema_version':1,'scene':'ppt','certification_scope':'independent_trace_structure',
        'binding_policy':'ppt_uploaded_sources_v1','matching_policy':'structural_only','quality_cost_promoted':False,
        'source_evidence_sha256':sha(manifest.parent/'evidence-lock.json'),
        'learning_report_sha256':sha(manifest.parent/'learning-report.json'),
        'manifest_digest':data['manifest_digest'],
        'file_locks':{p.name:sha(p) for p in bundle.iterdir() if p.is_file()},
        'code_locks':{name:sha(ROOT/name) for name in sorted(set(code))}})
    print(json.dumps({'runtime_bundle':str(bundle),'artifacts':len(data['artifacts']),
                      'model_requests':0,'quality_cost_promoted':False}))

if __name__=='__main__':main()
