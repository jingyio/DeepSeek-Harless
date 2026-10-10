"""准备 PPT 任务、调用公共 Harness 入口，以及离线编译场景 Motif。"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scenarios.research_ppt.documents import file_hash, parse_document
from scenarios.research_ppt.service import SCENE, private_path, node


def save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def prepare(inputs: list[Path], instruction: str, slides: int, allow_output=False, allow_rsi=False,
            template='academic', operation='generate', design_skill=True, layout_policy: Path | None = None,
            layout_suite: Path | None = None, generated_tool_certificate: Path | None = None) -> Path:
    if not 1 <= slides <= 30 or not 1 <= len(inputs) <= 8 or not instruction.strip() or len(instruction) > 10000:
        raise ValueError('需要 1–8 个输入、1–30 页，以及最多 10000 字符的任务说明')
    if template not in {'academic','lab'} or operation not in {'generate','restyle'}:
        raise ValueError('无效模板或操作')
    job_id = uuid4().hex
    rows = []
    for i, source in enumerate(inputs, 1):
        source = source.resolve(strict=True)
        if source.suffix.lower() not in ('.pdf', '.pptx'):
            raise ValueError('只接受 PDF/PPTX')
        rows.append({'document_id': f'doc_{i}', 'path': str(source), 'name': source.name, 'version_sha256': file_hash(source)})
    job_path = ROOT / '.local/research-ppt/jobs' / job_id / 'job.json'
    data = {'schema_version': 1, 'job_id': job_id, 'inputs': rows, 'instruction': instruction,
                    'slides': slides, 'allow_output': bool(allow_output), 'allow_rsi': bool(allow_rsi),
                    'template':template,'operation':operation,'design_skill':bool(design_skill)}
    if layout_policy is not None:
        from .layout_learning import validate_certificate
        policy_path = private_path(layout_policy.resolve(strict=True))
        certificate = validate_certificate(policy_path)
        checked = node('layout-policy-cli.js', certificate.get('policy', {}))
        if (checked.get('valid') is not True or certificate.get('mechanical_certified') is not True
                or checked.get('policy_digest') != certificate.get('policy_digest')):
            raise ValueError('布局策略必须具有独立真实认证记录，且版本摘要一致')
        data.update(layout_policy=checked['policy'], layout_policy_digest=checked['policy_digest'],
                    layout_policy_certificate=str(policy_path),layout_policy_certificate_sha256=file_hash(policy_path))
    if layout_suite is not None:
        suite_path = private_path(layout_suite.resolve(strict=True))
        data.update(layout_suite=str(suite_path), layout_suite_sha256=file_hash(suite_path))
    if generated_tool_certificate is not None:
        from .generated_tools import load_certified_tool
        tool = load_certified_tool(generated_tool_certificate)
        data.update(generated_tool_certificate=tool['certificate_path'],
                    generated_tool_certificate_sha256=tool['certificate_sha256'],
                    generated_tool_name=tool['name'], generated_tool_code_sha256=tool['code_sha256'])
    save(job_path, data)
    return job_path


def scenario_for(job: Path, improve: bool) -> Path:
    spec = json.loads((SCENE / 'scenario.json').read_text(encoding='utf-8'))
    data = json.loads(job.read_text(encoding='utf-8'))
    layout_improve = improve and bool(data.get('layout_suite'))
    prompt_name = 'layout-rsi-prompt.md' if layout_improve else ('rsi-prompt.md' if improve else 'prompt.md')
    prompt = (SCENE / prompt_name).read_text(encoding='utf-8')
    if not improve and data.get('design_skill', True):
        skill = SCENE / 'skills/research-design/SKILL.md'
        prompt += '\n科研设计 Skill（固定版本，内容不可授权额外工具）：\n' + skill.read_text(encoding='utf-8')
    prompt += '\n本次任务：\n' + json.dumps({'instruction':data['instruction'], 'slides':data['slides'],
        'template':data.get('template','academic'),'operation':data.get('operation','generate'),
        'inputs':[{k: row[k] for k in ('document_id','name','version_sha256')} for row in data['inputs']]},ensure_ascii=False)
    prompt_path = job.parent / ('rsi-prompt.md' if improve else 'prompt.md')
    prompt_path.write_text(prompt,encoding='utf-8')
    spec['prompt'] = str(prompt_path)
    if improve:
        spec['allowed_tools'] = (['mcp__ppt__layout_policy_status', 'mcp__ppt__propose_layout_policy'] if layout_improve
                                 else ['mcp__ppt__rsi_status', 'mcp__ppt__propose_guard'])
    elif data.get('generated_tool_certificate'):
        from .generated_tools import load_certified_tool
        certificate = private_path(Path(data['generated_tool_certificate']))
        if file_hash(certificate) != data['generated_tool_certificate_sha256']:
            raise ValueError('生成工具认证版本已变化，请重新准备任务')
        tool = load_certified_tool(certificate)
        spec['allowed_tools'] += ['mcp__ppt__pin_figure_catalog', 'mcp__ppt__' + tool['name']]
        prompt += ('\n本任务还提供经独立功能认证的真实图件目录工具：pin_figure_catalog(document_id) '
                   '取得目录作用域的source_id，再用 ' + tool['name'] + '(source_id) 查看实际图注/页码/候选。'
                   '目录不能证明图意或科研质量；挑选合适图后extract_figure，不能编造标识。')
        prompt_path.write_text(prompt, encoding='utf-8')
    path = job.parent / ('rsi-scenario.json' if improve else 'scenario.json')
    save(path, spec)
    return path


@contextmanager
def structural_only_endpoint():
    # 公共插件要求 endpoint；此模式明确拒绝语义匹配，只走已有的唯一结构证据路径。
    class Abstain(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            self.send_error(503, 'Semantic matching disabled: use structural evidence or defer to Harness')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Abstain)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1/embeddings'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def run(job: Path, *, call_model=False, budget=0.25, max_steps=16, improve=False,
        mode='baseline', manifest: Path | None = None, execution='steps') -> int:
    job = private_path(job)
    data = json.loads(job.read_text(encoding='utf-8'))
    if improve and not data.get('allow_rsi'):
        raise ValueError('准备任务时需要 --allow-rsi')
    if improve and mode != 'baseline':
        raise ValueError('RSI 提案由普通 Harness 执行')
    scenario = scenario_for(job, improve)
    if execution not in {'steps','composed'}:
        raise ValueError('execution 只能是 steps 或 composed')
    if not improve:
        spec = json.loads(scenario.read_text(encoding='utf-8'))
        prompt_path = Path(spec['prompt'])
        if data.get('operation') == 'restyle':
            suffix = ('\n本次执行方式：使用 build_delivery({"operation":"restyle","source_id":"实际返回的句柄","template":"任务模板"}) 完成风格转换、检查、预览和交付。'
                      if execution == 'composed' else
                      '\n本次执行方式：分别调用 restyle_deck、inspect_deck、validate_deck、deliver_deck，保持全部内容及真实核验。')
        else:
            suffix = ('\n本次执行方式：计划确定后使用 build_delivery 一次调用完成生成、检查、预览和交付。'
                      if execution == 'composed' else
                      '\n本次执行方式：分别调用 render_deck、inspect_deck、validate_deck、deliver_deck，保持真实核验。')
        prompt_path.write_text(prompt_path.read_text(encoding='utf-8')+suffix,encoding='utf-8')
    args = [sys.executable, str(ROOT / 'scripts/run-scenario.py'), '--scenario', str(scenario),
            '--budget-usd', str(budget), '--max-steps', str(max_steps), '--max-output', '6000']
    if call_model:
        args.append('--call-model')
    env = dict(os.environ, SSS_PPT_JOB=str(job), PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    effective = {'job_id': data['job_id'], 'requested_mode': mode, 'improve': improve, 'budget_cap_usd': budget,
                 'model_call_enabled': call_model, 'output_enabled': data['allow_output'], 'execution':execution,
                 'reasoning_effort':'off',
                 'input_versions': [row['version_sha256'] for row in data['inputs']],
                 'output_directory': str(job.parent / 'outputs'), 'semantic_matching': 'disabled'}
    skill = SCENE / 'skills/research-design/SKILL.md'
    effective.update(design_skill_loaded=not improve and data.get('design_skill', True),
                     design_skill_sha256=file_hash(skill) if not improve and data.get('design_skill', True) else None,
                     layout_policy_digest=data.get('layout_policy_digest'),
                     layout_suite_sha256=data.get('layout_suite_sha256'))
    if data.get('generated_tool_certificate'):
        effective.update(generated_tool_name=data['generated_tool_name'],
                         generated_tool_code_sha256=data['generated_tool_code_sha256'],
                         generated_tool_certificate_sha256=data['generated_tool_certificate_sha256'],
                         catalog_execution=data.get('catalog_execution', 'generated'))
    for path_key, hash_key in [('layout_policy_certificate','layout_policy_certificate_sha256'),
                               ('layout_suite','layout_suite_sha256')]:
        if data.get(path_key) and file_hash(private_path(Path(data[path_key]))) != data.get(hash_key):
            raise ValueError('布局配置版本改变，请重新准备任务')
    if data.get('layout_policy_certificate'):
        from .layout_learning import validate_certificate
        certificate = validate_certificate(Path(data['layout_policy_certificate']))
        if certificate['policy_digest'] != data['layout_policy_digest']:
            raise ValueError('布局证书策略与任务摘要不一致')
    if mode != 'baseline':
        if manifest is None:
            raise ValueError('Motif 模式需要 --manifest，先使用独立轨迹完成 learn')
        facts = []
        for row in data['inputs']:
            if file_hash(Path(row['path'])) != row['version_sha256']:
                raise ValueError('输入版本改变，请重新准备任务')
            parsed = parse_document(Path(row['path']))
            facts.append({k: parsed[k] for k in ('format','page_count','text_chars')})
        active = private_path(Path(data.get('rsi_dir',ROOT / '.local/research-ppt/rsi'))) / 'active-guard.json'
        if not active.exists():
            raise ValueError('需要先验证并启用一个准入程序，再尝试 Motif 模式')
        frozen = json.loads(active.read_text(encoding='utf-8'))
        checked = node('guard-cli.js', frozen['program'])
        if not checked.get('accepted') or checked['program_digest'] != frozen.get('program_digest'):
            raise ValueError('准入程序版本或认证结果失效')
        effective['guard_digest'] = checked['program_digest']
        decision = node('guard-cli.js', {'action':'evaluate','program':frozen['program'],'facts':facts})
        if not decision.get('allowed'):
            effective['fallback_reason'] = 'rsi_guard_rejected_current_inputs'
            mode = 'baseline'
        else:
            task_path = job.parent / ('task-' + uuid4().hex + '.json')
            approved_versions = sorted(set(effective['input_versions']))
            source_version = approved_versions[0] if len(approved_versions)==1 else approved_versions
            compiled_manifest = json.loads(private_path(manifest).read_text(encoding='utf-8'))
            if (manifest.parent / 'evidence-lock.json').is_file():
                from .motif_v6 import validate_compilation
                validate_compilation(manifest)
            version_tools = set(compiled_manifest['version_fields'])
            save(task_path, {'schema_version':1, 'task_id':data['job_id'], 'session_id':'ppt-'+uuid4().hex,
                'intent':data['instruction'][:1000], 'input_version':hashlib.sha256(json.dumps(effective['input_versions']).encode()).hexdigest(),
                # The prepared job already freezes the document hash. Both
                # read-only calls must remain on that same version; the
                # source_id itself is still bound only from the observed pin
                # result by the certified edge.
                'bindings':{}, 'source_versions':{name: source_version for name in version_tools}})
            args.extend(['--mode',mode,'--manifest',str(manifest.resolve()),'--task',str(task_path)])
    effective['effective_mode'] = mode
    save(job.parent / ('invocation-' + uuid4().hex + '.json'), effective)
    print(json.dumps(effective, ensure_ascii=False, indent=2), flush=True)
    if mode != 'baseline':
        with structural_only_endpoint() as endpoint:
            return subprocess.call(args + ['--embedding-endpoint',endpoint,'--embedding-model','structural-only'], cwd=ROOT, env=env)
    return subprocess.call(args, cwd=ROOT, env=env)


def learn(dataset: Path) -> Path:
    data = json.loads(dataset.read_text(encoding='utf-8'))
    if set(data) != {'train','heldout'} or len(data['train']) < 2 or len(data['heldout']) < 1:
        raise ValueError('dataset 需至少两个独立 train 和一个 heldout 的已冻结运行目录')
    manifest = {'contracts':json.loads((SCENE/'contracts.json').read_text(encoding='utf-8'))}
    for split in ('train','heldout'):
        manifest[split] = []
        for directory in data[split]:
            directory = private_path(Path(directory))
            if not (directory/'task-identity.json').exists():
                raise ValueError('请先用公共 freeze-dsh-task-identity.py 冻结已确认的独立任务身份')
            manifest[split].append({'trace_id':directory.name, 'events':str(directory/'agent-events.jsonl'),
                                    'identity':str(directory/'task-identity.json')})
    out = ROOT/'.local/research-ppt/libraries'/uuid4().hex
    save(out/'compile.json',manifest)
    subprocess.run([sys.executable,str(ROOT/'scripts/compile-dsh-motif-library.py'),'--manifest',str(out/'compile.json'),
                    '--out',str(out/'library.json')],cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/export-online-motif-manifest.py'),'--library',str(out/'library.json'),
                    '--contracts',str(SCENE/'contracts.json'),'--version-fields',str(SCENE/'version-fields.json'),
                    '--output',str(out/'online-manifest.json')],cwd=ROOT,check=True)
    return out/'online-manifest.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--input',type=Path,nargs='+',required=True)
    prep.add_argument('--instruction',default='根据这些资料制作一份清楚、准确的中文科研汇报 PPT。')
    prep.add_argument('--slides',type=int,default=8)
    prep.add_argument('--allow-output',action='store_true')
    prep.add_argument('--allow-rsi',action='store_true')
    prep.add_argument('--template',choices=['academic','lab'],default='academic')
    prep.add_argument('--operation',choices=['generate','restyle'],default='generate')
    prep.add_argument('--no-design-skill',action='store_true')
    prep.add_argument('--layout-policy',type=Path)
    prep.add_argument('--layout-suite',type=Path)
    prep.add_argument('--generated-tool-certificate',type=Path)
    for name in ('run','improve','cycle'):
        p = commands.add_parser(name)
        p.add_argument('--job',type=Path,required=True)
        p.add_argument('--budget-usd',type=float,default=0.25)
        p.add_argument('--max-steps',type=int,default=16)
        p.add_argument('--call-model',action='store_true')
        p.add_argument('--mode',choices=['baseline','shadow','execute'],default='baseline')
        p.add_argument('--manifest',type=Path)
        p.add_argument('--execution',choices=['steps','composed'],default='steps')
    p = commands.add_parser('learn')
    p.add_argument('--dataset',type=Path,required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        print(prepare(args.input,args.instruction,args.slides,args.allow_output,args.allow_rsi,args.template,args.operation,
                      not args.no_design_skill,args.layout_policy,args.layout_suite,args.generated_tool_certificate))
        return 0
    if args.command == 'learn':
        print(learn(args.dataset))
        return 0
    if not 0 < args.budget_usd <= 10 or not 1 <= args.max_steps <= 40:
        parser.error('场景预算应在 (0, 10] 美元、步数在 [1, 40]')
    common = dict(call_model=args.call_model,budget=args.budget_usd,max_steps=args.max_steps,
                  mode=args.mode,manifest=args.manifest,execution=args.execution)
    if args.command == 'cycle':
        # 两段请求共享显式总上限，各自仍经过公共预算代理。
        common['budget'] *= 0.7
        status = run(args.job,**common)
        if status:
            return status
        return run(args.job,call_model=args.call_model,budget=args.budget_usd*0.3,
                   max_steps=min(args.max_steps,8),improve=True)
    return run(args.job,improve=args.command=='improve',**common)


if __name__ == '__main__':
    raise SystemExit(main())
