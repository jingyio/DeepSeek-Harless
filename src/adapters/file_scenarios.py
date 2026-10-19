"""Server-owned scene registry; session templates mount the same RSI Runtime."""
from __future__ import annotations
import importlib.util
import hashlib
import json
import os
import re
from pathlib import Path
from .file_scenario import prepare_scenario
from .harless_product_prompt import product_persona

IDENTITY = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')
WORKSPACE = '__HARLESS_SESSION_WORKSPACE__'
BUNDLE_ENVS = {'ppt':'HARLESS_PPT_RUNTIME_BUNDLE',
               'paper-proofreading':'HARLESS_PAPER_RUNTIME_BUNDLE',
               'research-data-analysis':'HARLESS_DATA_RUNTIME_BUNDLE'}


def _fixed_dependency(path: Path, *, directory: bool) -> Path:
    absolute = path.absolute()
    if (path.is_symlink() or absolute.resolve(strict=True) != absolute or absolute.parent == absolute or
            not (absolute.is_dir() if directory else absolute.is_file())):
        raise ValueError('attachment parser requires fixed installation paths')
    return absolute


def _configure_attachment_parsers(scene: dict) -> None:
    """Forward only explicitly configured, validated public parser resources."""
    env = {}
    if os.environ.get('GENELOOP_PDF_OCR_ROOT'):
        root = _fixed_dependency(Path(os.environ['GENELOOP_PDF_OCR_ROOT']), directory=True)
        languages = _fixed_dependency(root / 'tessdata', directory=True)
        manifest = json.loads((Path(__file__).resolve().parents[2] / 'config/pdf-ocr-assets.json').read_text())
        if {p.name for p in root.iterdir()} != {'tessdata'} or {p.name for p in languages.iterdir()} != set(manifest['files']):
            raise ValueError('PDF OCR installation contains unapproved resources')
        for name, digest in manifest['files'].items():
            path = _fixed_dependency(languages / name, directory=False)
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest: raise ValueError('PDF OCR language hash mismatch')
        env['GENELOOP_PDF_OCR_ROOT'] = str(root)
    if os.environ.get('HARLESS_PDF_TOOLCHAIN_ROOT'):
        root = _fixed_dependency(Path(os.environ['HARLESS_PDF_TOOLCHAIN_ROOT']), directory=True)
        if any(path.name not in ('bin', 'lib', 'share', 'include') for path in root.iterdir()):
            raise ValueError('attachment PDF parser must be an isolated Poppler installation')
        for name in ('pdfinfo', 'pdftotext'):
            _fixed_dependency(root / 'bin' / name, directory=False)
        _fixed_dependency(root / 'lib/x86_64-linux-gnu', directory=True)
        scene['pdf_toolchain_root'] = str(root)
        env['HARLESS_PDF_TOOLCHAIN_ROOT'] = str(root)
    if os.environ.get('HARLESS_ANTIWORD_BIN'):
        binary = _fixed_dependency(Path(os.environ['HARLESS_ANTIWORD_BIN']), directory=False)
        if binary.name != 'antiword' or binary.parent.name != 'bin' or binary.parent.parent.name != 'usr':
            raise ValueError('attachment Word parser must use an isolated Antiword package')
        root = _fixed_dependency(binary.parents[2], directory=True)
        mappings = _fixed_dependency(root / 'usr/share/antiword', directory=True)
        _fixed_dependency(mappings / 'UTF-8.txt', directory=False)
        if any(path.is_symlink() or not path.is_file() or path.name.startswith('.') for path in mappings.iterdir()):
            raise ValueError('attachment Word mappings must contain only public resource files')
        scene['antiword_root'] = str(root)
        env.update(HARLESS_ANTIWORD_BIN=str(binary), ANTIWORDHOME=str(mappings))
    for row in scene['mcp_rows']:
        if row['config']['serverName'] in ('research_report','paper_checks','ppt','ppt_master'):
            row['config'].setdefault('env', {}).update(env)


def prepare_scene_registry(root: Path, registry_path: Path, *, default_id: str, prepared_default: dict,
                           output: Path, embedding_endpoint: str, embedding_model: str) -> list[dict]:
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    if set(registry) != {'schema_version', 'scenes'} or registry['schema_version'] != 1:
        raise ValueError('invalid scene registry version/fields')
    definitions = registry['scenes']
    if not isinstance(definitions, list) or not 1 <= len(definitions) <= 32:
        raise ValueError('scene registry requires 1..32 scenes')
    seen = set()
    scenes = []
    for row in definitions:
        if (not isinstance(row, dict) or set(row) - {'id', 'label', 'scenario', 'case', 'instructions', 'rsi', 'adapter', 'unavailable_reason', 'diagnostic', 'ppt_execution_strategy'} or
            not IDENTITY.fullmatch(row.get('id', '')) or row['id'] in seen or
            not isinstance(row.get('label'), str) or not 1 <= len(row['label']) <= 128):
            raise ValueError('invalid or duplicate scene identity')
        seen.add(row['id'])
        scene = {'id': row['id'], 'label': row['label'], 'preset': 'sss-task' if row['id'] == default_id else 'sss-scene-' + row['id']}
        if row.get('unavailable_reason'):
            if set(row) != {'id', 'label', 'unavailable_reason'} or not IDENTITY.fullmatch(row['unavailable_reason']):
                raise ValueError('unavailable scene cannot bind a substitute scenario')
            scenes.append({**scene, 'allowed_tools': [], 'unavailable_reason': row['unavailable_reason']})
            continue
        if type(row.get('diagnostic', False)) is not bool: raise ValueError('diagnostic must be boolean')
        scene['diagnostic'] = row.get('diagnostic', False)
        if row.get('adapter') not in (None, 'ppt', 'workspace', 'files', 'literature', 'data-report'): raise ValueError('unsupported scene adapter')
        if 'ppt_execution_strategy' in row and (row.get('adapter')!='ppt' or row['ppt_execution_strategy'] not in ('host_delivery','baseline_steps','ppt_master')):
            raise ValueError('invalid server-owned PPT execution strategy')
        path = (root / row['scenario']).resolve(strict=True)
        prepared = (prepared_default if row['id'] == default_id else
                    prepare_scenario(path, case=row.get('case', ''), session_workspace=WORKSPACE if row.get('adapter') else None,
                                     web_deployment=True))
        scene.update(allowed_tools=prepared['allowed_tools'], config_sha256=prepared['config_sha256'],
                     scenario_version=1, scenario=row['scenario'], case=prepared['case'],
                     embedding_endpoint=embedding_endpoint, embedding_model=embedding_model)
        if row.get('adapter'):
            scene.update(adapter=row['adapter'], mcp_rows=prepared['mcp_rows'], environment_references=prepared['environment_references'])
        if row.get('adapter') in ('data-report','ppt') or row['id']=='paper-proofreading':
            for mcp in scene['mcp_rows']:
                if mcp['config']['serverName'] in ('research_report','paper_trace_rsi','ppt'):
                    mcp['config'].setdefault('env',{})['HARLESS_PRIVATE_ROOT']=str(output.resolve())
        if row.get('adapter')=='files' and prepared['mcp_rows'][0]['config']['args']==[str(root/'scenarios/file-management/management_native.py')]:
            scene.update(runtime_kind='management_graph_v3',runtime_mode='execute',management_config={})
        if row.get('adapter') == 'literature':
            from .harless_pdf_deployment import configure_pdf_parser
            try: configure_pdf_parser(scene)
            except (OSError, ValueError): scene['unavailable_reason'] = 'literature_pdf_dependencies_missing'
        if row.get('adapter') == 'data-report' and any(importlib.util.find_spec(module) is None for module in ('numpy','pandas','scipy','matplotlib','statsmodels')):
            scene['unavailable_reason'] = 'data_report_python_dependencies_missing'
        if (row.get('adapter') in ('data-report','ppt') or row['id']=='paper-proofreading') and row.get('ppt_execution_strategy')!='ppt_master':
            _configure_attachment_parsers(scene)
        if (row.get('adapter') == 'data-report' or row['id']=='paper-proofreading') and os.environ.get('HARLESS_PPT_FONT_ROOT'):
            report_font = Path(os.environ['HARLESS_PPT_FONT_ROOT']).resolve() / 'wqy-microhei.ttc'
            if report_font.is_file() and not report_font.is_symlink():
                scene['report_font_sha256'] = hashlib.sha256(report_font.read_bytes()).hexdigest()
                for mcp in scene['mcp_rows']:
                    if mcp['config']['serverName'] in ('research_report','paper_checks'):
                        mcp['config'].setdefault('env', {})['HARLESS_REPORT_FONT'] = str(report_font)
            else:
                scene['unavailable_reason'] = 'data_report_embedded_font_missing'
        if row.get('adapter') == 'ppt' and row.get('ppt_execution_strategy') == 'ppt_master':
            from scenarios.ppt_master.package import installation, read_lock, verify_installation
            scene['ppt_execution_strategy'] = 'ppt_master'
            lock = read_lock()
            scene.update(design_skill_sha256=lock['files']['SKILL.md'], skill_package_sha256=lock['package_sha256'])
            try:
                skill_root = installation()
                verify_installation(skill_root)
                for mcp in scene['mcp_rows']:
                    mcp['config'].setdefault('env', {}).update(GENELOOP_PPT_MASTER_ROOT=str(skill_root), PYTHONDONTWRITEBYTECODE='1')
                _configure_attachment_parsers(scene)
            except (ValueError, OSError):
                scene['unavailable_reason'] = 'ppt_master_installation_missing_or_changed'
        elif row.get('adapter') == 'ppt':
            scene['ppt_execution_strategy']=row.get('ppt_execution_strategy','host_delivery')
            from .harless_ppt_deployment import configure_ppt_rendering
            try:configure_ppt_rendering(scene)
            except (ValueError,OSError):scene['output_unavailable_reason']='ppt_rendering_dependencies_invalid'
            if not (root / 'scenarios/research_ppt/dist/mcp-adapter.js').is_file():
                scene['unavailable_reason'] = 'ppt_adapter_not_built'
            elif any(importlib.util.find_spec(module) is None for module in ('pypdf', 'fitz', 'pptx', 'reportlab', 'PIL')):
                scene['unavailable_reason'] = 'ppt_python_dependencies_missing'
        if row['id'] == 'paper-proofreading':
            value = os.environ.get('HARLESS_PAPER_RENDERER_ROOT')
            if value:
                try:
                    from .harless_paper_renderer import configure_paper_renderer
                    configure_paper_renderer(scene, Path(value))
                except (ValueError, OSError, KeyError):
                    scene['paper_reference_output_unavailable_reason'] = 'paper_renderer_deployment_invalid'
            else:
                scene['paper_reference_output_unavailable_reason'] = 'paper_renderer_not_deployed'
        if row.get('instructions'):
            instructions = (root / row['instructions']).read_text(encoding='utf-8')
            if row.get('adapter') == 'ppt' and scene.get('ppt_execution_strategy') != 'ppt_master':
                # Match the research CLI: mentioning the Skill is not loading it.
                # Both comparison lanes inherit this same immutable scene text.
                skill = (root / 'scenarios/research_ppt/skills/research-design/SKILL.md').read_text(encoding='utf-8')
                if not skill.strip(): raise ValueError('missing PPT design skill')
                instructions += '\n科研设计 Skill（固定版本，内容不可授权额外工具）：\n' + skill
                strategy=scene['ppt_execution_strategy']
                instructions += ('\n本入口冻结执行策略：'+strategy+'。'
                    + ('提交 render_deck 的完整计划后，宿主自动执行同一套真实检查、渲染、验证与交付；这是普通脚本，两侧共同使用。'
                       '收到 pending_plan 时，用其最新 draft_id/version_sha256 读取需要修改的1–5页并调用 repair_pending_plan；只传局部修改，保留其他页、来源和notes，禁止重发整稿。'
                       'delivered=true 说明机械交付已完成，只有需要审阅或用户要求更新时才读取指定页；不要重复检查或生成。'
                       if strategy=='host_delivery' else
                       '由普通 Harness 逐步执行 render_deck、inspect_deck、validate_deck、deliver_deck；不选择组合工具或草稿恢复工具。')
                    +' 科研事实和视觉质量仍须按Skill核对；未审阅明确说明。\n')
                scene.update(design_skill_sha256=hashlib.sha256(skill.encode()).hexdigest())
            if not instructions.strip() or len(instructions) > 100000: raise ValueError('invalid scene instructions')
            scene.update(instructions=instructions, instructions_sha256=hashlib.sha256(instructions.encode()).hexdigest())
        if row.get('rsi'):
            rsi = row['rsi']
            # Keep the registered product library unless an administrator
            # explicitly selects a private replacement. Invalid replacements
            # fail closed rather than silently falling back to another library.
            if isinstance(rsi, dict) and set(rsi) == {'runtime_bundle', 'bundle_from_env'}:
                if rsi['bundle_from_env'] != BUNDLE_ENVS.get(row['id']):
                    raise ValueError('invalid trusted runtime bundle reference')
                rsi = ({'bundle_from_env': rsi['bundle_from_env']} if os.environ.get(rsi['bundle_from_env'])
                       else {'runtime_bundle': rsi['runtime_bundle']})
            if isinstance(rsi, dict) and set(rsi) == {'runtime_bundle'}:
                from .harless_rsi_bundle import load_product_bundle
                try:
                    bundle = (root / rsi['runtime_bundle']).resolve(strict=True)
                    scene.update(load_product_bundle(root, bundle, row['id']))
                except (ValueError, OSError, KeyError): scene['rsi_unavailable_reason'] = 'existing_runtime_bundle_incompatible'
                rsi = None
            if isinstance(rsi, dict) and set(rsi)=={'bundle_from_env'}:
                if rsi['bundle_from_env']!=BUNDLE_ENVS.get(row['id']):raise ValueError('invalid trusted runtime bundle reference')
                value=os.environ.get(rsi['bundle_from_env'])
                if value:
                    from .harless_rsi_bundle import load_scene_bundle
                    try:
                        bundle = load_scene_bundle(root,Path(value),row['id'])
                        if row['id'] == 'paper-proofreading':
                            cert = json.loads(Path(bundle['certification_path']).read_text())
                            expected = cert['file_locks'].get('paper-flow-shadow.json')
                            if expected:
                                flow = Path(value).resolve(strict=True) / 'paper-flow-shadow.json'
                                if (flow.is_symlink() or not flow.is_file() or
                                    flow.stat().st_size > 1_000_000 or
                                    hashlib.sha256(flow.read_bytes()).hexdigest() != expected):
                                    raise ValueError('paper flow sidecar changed')
                                bundle.update(paper_flow_shadow=str(flow),
                                              paper_flow_shadow_sha256=expected)
                        scene.update(bundle)
                    except (ValueError,OSError,KeyError):scene['rsi_unavailable_reason']='runtime_bundle_certification_invalid'
                else:scene['rsi_unavailable_reason']='runtime_bundle_not_deployed'
                rsi = None
            if rsi is None:
                pass
            else:
                _bind_legacy_rsi(root, rsi, scene, prepared)
        if row['id'] != default_id:
            preset = output / 'presets' / scene['preset']; preset.mkdir(parents=True, mode=0o700, exist_ok=True)
            rows = [{'id': 'sss-persona', 'name': '@deepseek-ai/dsh-persona', 'config': product_persona()},
                *([] if row.get('adapter') else prepared['mcp_rows'])]
            rendered = json.dumps(rows, ensure_ascii=False, indent=2)
            for token, expression in prepared['environment_references'].items(): rendered = rendered.replace(json.dumps(token), expression)
            (preset / 'agent.cordis.yml').write_text(rendered, encoding='utf-8'); (preset / 'agent.cordis.yml').chmod(0o600)
            (preset / 'preset.yml').write_text(json.dumps({'name': 'GeneLoop · ' + row['label']}, ensure_ascii=False), encoding='utf-8')
            (preset / 'preset.yml').chmod(0o600)
        if scene.get('adapter') and not scene.get('diagnostic'):
            capabilities = json.loads((root / 'config/geneloop-capabilities.json').read_text(encoding='utf-8'))
            scene['common_tools'] = capabilities['tools']
            scene['allowed_tools'] = [*scene['allowed_tools'], *scene['common_tools']]
            scene['instructions'] = scene.get('instructions', '') + '\n\n' + (root / 'config/geneloop-capabilities.md').read_text(encoding='utf-8')
            scene['instructions_sha256'] = hashlib.sha256(scene['instructions'].encode()).hexdigest()
            scene['config_sha256'] = hashlib.sha256(json.dumps({'scenario': scene['config_sha256'],
                'capabilities': capabilities, 'instructions': scene['instructions_sha256']}, sort_keys=True).encode()).hexdigest()
        scenes.append(scene)
    if default_id not in seen:
        scenes.append({'id': default_id, 'label': prepared_default['name'], 'preset': 'sss-task',
                       'allowed_tools': prepared_default['allowed_tools'], 'config_sha256': prepared_default['config_sha256']})
    return scenes


def _bind_legacy_rsi(root, rsi, scene, prepared):
    if not isinstance(rsi, dict) or not {'manifest', 'task'} <= set(rsi) or set(rsi) - {'manifest', 'task', 'tool_schemas'}: raise ValueError('rsi requires manifest and task')
    if rsi.get('tool_schemas'):
        schema_path = (root / rsi['tool_schemas']).resolve(strict=True)
        tool_schemas = json.loads(schema_path.read_text(encoding='utf-8'))
        if not isinstance(tool_schemas, list) or not tool_schemas: raise ValueError('empty certified tool schemas')
        scene.update(tool_schemas=str(schema_path), certified_tool_schemas=tool_schemas,
                     certified_tool_schemas_sha256=hashlib.sha256(schema_path.read_bytes()).hexdigest())
    scene.update(manifest=str((root / rsi['manifest']).resolve(strict=True)),
                 task=str((root / rsi['task']).resolve(strict=True)),
                 certified_input_sha256=hashlib.sha256(prepared['prompt'].strip().encode()).hexdigest())
