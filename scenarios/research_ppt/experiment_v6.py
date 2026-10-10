"""V6 单任务真实实验入口；复用公共 Harness，保留失败，禁止隐式重跑。"""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .cli import prepare, scenario_for
from .documents import file_hash
from .experiment_v5 import collect, digest, source_hashes, terminate_tree
from .service import ROOT, SCENE, private_path


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


async def actual_schema(job: Path) -> dict:
    from mcp import Client, StdioServerParameters
    spec = json.loads(scenario_for(job, False).read_text(encoding='utf-8'))
    params = StdioServerParameters(command=sys.executable, args=[str(SCENE/'server.py')],
        cwd=ROOT, env={'PYTHONPATH':str(ROOT), 'SSS_PPT_JOB':str(job)})
    async with Client(params, read_timeout_seconds=60) as client:
        tools = (await client.list_tools()).tools
        offered = {f'mcp__ppt__{t.name}':t.model_dump(mode='json', by_alias=True) for t in tools}
        ordered = [{'name':name, **offered[name]} for name in spec['allowed_tools']]
        # MCP 的原始 name 为短名，导出契约绑定需要完整 Harness 工具名。
        for row, name in zip(ordered, spec['allowed_tools']):
            row['name'] = name
        return {'tools':ordered, 'allowed_tool_order':spec['allowed_tools'],
                'mcp_advertised_order':[t.name for t in tools], 'schema_sha256':digest(ordered),
                'scope':'actual_mcp_not_provider_payload', 'provider_facing_schema_sha256':None}


def execute(*, area: Path, task_id: str, inputs: list[Path], instruction: str, slides: int,
            group: str, certificate: Path | None, manifest: Path | None,
            template='lab', stage='evaluation', call_model=False) -> dict:
    area = private_path(area)
    area.mkdir(parents=True, exist_ok=False)
    if group not in {'baseline','manual','generated','generated_motif'}:
        raise ValueError('未知实验组')
    if group != 'baseline' and certificate is None:
        raise ValueError('生成工具和人工脚本对照均需冻结证书与相同 MCP schema')
    if group == 'generated_motif' and manifest is None:
        raise ValueError('Motif 组需独立认证 manifest')
    job = prepare(inputs, instruction, slides, call_model, template=template,
        generated_tool_certificate=certificate if group != 'baseline' else None)
    data = json.loads(job.read_text(encoding='utf-8'))
    if group == 'manual':
        data['catalog_execution'] = 'manual'
    guard = ROOT/'.local/research-ppt/rsi/v2-20261010/active-guard.json'
    if group == 'generated_motif':
        data['rsi_dir'] = str(guard.parent)
    write(job, data)
    schema = asyncio.run(actual_schema(job))
    write(area/'tool-schema.json', schema)
    hashes = source_hashes()
    hashes.update({str(p.relative_to(ROOT)):file_hash(p) for p in SCENE.glob('*.py')})
    config = {'schema_version':1,'experiment_id':'research-ppt-v6-tool-rsi-20261011',
        'stage':stage,'task_id':task_id,'group':group,'job':str(job),
        'input_versions':[{k:r[k] for k in ('document_id','name','version_sha256')} for r in data['inputs']],
        'instruction':instruction,'slides':slides,'template':template,
        'source_hashes':hashes, 'tool_schema_sha256':schema['schema_sha256'],
        'allowed_tool_order':schema['allowed_tool_order'], 'provider':'deepseek-official',
        'model':'deepseek-flash','reasoning_effort':'off','compression_enabled':False,
        'execution':'steps','budget_cap_usd':1.0,'max_steps':40,'max_output':6000,
        'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'git_status':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),
        'python':sys.version,'node':subprocess.check_output(['node','--version'],text=True).strip(),
        'harness_npm':json.loads((ROOT/'node_modules/@deepseek-ai/dsh/package.json').read_text())['version'],
        'sdk':importlib.metadata.version('deepseek-harness-sdk'),
        'certificate_sha256':file_hash(certificate) if certificate and group!='baseline' else None,
        'manifest_sha256':file_hash(manifest) if manifest else None,
        'guard_sha256':file_hash(guard) if group=='generated_motif' else None,
        'embedding_model':'structural-only','semantic_matching':'disabled',
        'missing_configuration':['provider_facing_schema_hash_and_order','provider_internal_retry_policy',
            'invoice','human_blind_review','human_revision_minutes','development_cost'],
        'quality':'not_human_reviewed'}
    write(area/'config.json',config)
    mode = 'execute' if group=='generated_motif' else 'baseline'
    command = [sys.executable,'-u','-m','scenarios.research_ppt.cli','run','--job',str(job),
        '--mode',mode,'--execution','steps','--budget-usd','1','--max-steps','40']
    if manifest and mode=='execute':
        command += ['--manifest',str(manifest)]
    if call_model:
        command.append('--call-model')
    log = ROOT/'test-logs'/f'{area.name}.log'
    row = {'task_id':task_id,'group':group,'stage':stage,'job_path':str(job),
        'status':'running','model_call_enabled':call_model,'model_run_started':False,
        'quality':'quality_not_reviewed','delivery_completed':False,
        'started_utc':datetime.now(timezone.utc).isoformat(), 'command':command,
        'log_path':str(log),'config_sha256':file_hash(area/'config.json'),
        'accounted_for_cap_usd':1.0 if call_model else 0.0,'accounting_missing':call_model}
    write(area/'run.json',row)
    output_dir, process, started = None, None, time.monotonic()
    try:
        with log.open('x',encoding='utf-8') as stream:
            process = subprocess.Popen(command,cwd=ROOT,env=dict(os.environ,PYTHONUTF8='1'),
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',
                errors='replace',bufsize=1,start_new_session=True)
            row['model_run_started'] = call_model
            write(area/'run.json',row)
            for line in process.stdout:
                stream.write(line); stream.flush()
                try:
                    value = json.loads(line)
                    if isinstance(value,dict) and value.get('output_dir'):
                        output_dir = private_path(Path(value['output_dir']))
                        row['run_dir'] = str(output_dir); write(area/'run.json',row)
                except (ValueError,TypeError):
                    pass
            row['returncode'] = process.wait()
            row['status'] = 'preview' if not call_model and row['returncode']==0 else 'error'
    except BaseException as exc:
        terminate_tree(process)
        row.update(status='interrupted',error_type=type(exc).__name__)
        raise
    finally:
        row['elapsed_seconds'] = round(time.monotonic()-started,3)
        collect(row,job,output_dir)
        write(area/'run.json',row)
    if stage in {'motif_train','motif_heldout'} and row['delivery_completed']:
        subprocess.run([sys.executable,str(ROOT/'scripts/freeze-dsh-task-identity.py'),
            '--task-dir',str(output_dir),'--decision-id',task_id,
            '--events','agent-events.jsonl'],cwd=ROOT,check=True,capture_output=True)
    print(json.dumps({k:row.get(k) for k in ('task_id','group','status','run_dir','job_path',
        'delivery_completed','paid_model_requests','api_cost_usd','tokens',
        'verified_model_requests_skipped','elapsed_seconds')},ensure_ascii=False),flush=True)
    return row


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--area',type=Path,required=True)
    p.add_argument('--task-id',required=True)
    p.add_argument('--input',type=Path,nargs='+',required=True)
    p.add_argument('--instruction',required=True)
    p.add_argument('--slides',type=int,default=6)
    p.add_argument('--group',choices=['baseline','manual','generated','generated_motif'],default='baseline')
    p.add_argument('--stage',choices=['evaluation','motif_train','motif_heldout'],default='evaluation')
    p.add_argument('--certificate',type=Path)
    p.add_argument('--manifest',type=Path)
    p.add_argument('--call-model',action='store_true')
    p.add_argument('--api-env',type=Path)
    a=p.parse_args()
    if a.call_model and a.api_env:
        from .tool_learning import _load_key
        _load_key(a.api_env)
    row=execute(area=a.area,task_id=a.task_id,inputs=a.input,instruction=a.instruction,slides=a.slides,
        group=a.group,certificate=a.certificate,manifest=a.manifest,stage=a.stage,call_model=a.call_model)
    return 0 if row['delivery_completed'] or row['status']=='preview' else 1


if __name__=='__main__':
    raise SystemExit(main())
