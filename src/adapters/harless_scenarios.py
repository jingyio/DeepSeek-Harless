"""Server-owned scene registry; session templates mount the same RSI Runtime."""
from __future__ import annotations
import importlib.util
import hashlib
import json
import os
import re
from pathlib import Path
from .scenario import prepare_scenario

IDENTITY = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')
WORKSPACE = '__HARLESS_SESSION_WORKSPACE__'


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
        if (not isinstance(row, dict) or set(row) - {'id', 'label', 'scenario', 'case', 'instructions', 'rsi', 'adapter', 'unavailable_reason', 'diagnostic'} or
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
        path = (root / row['scenario']).resolve(strict=True)
        prepared = (prepared_default if row['id'] == default_id else
                    prepare_scenario(path, case=row.get('case', ''), session_workspace=WORKSPACE if row.get('adapter') else None))
        scene.update(allowed_tools=prepared['allowed_tools'], config_sha256=prepared['config_sha256'],
                     scenario_version=1, scenario=row['scenario'], case=prepared['case'],
                     embedding_endpoint=embedding_endpoint, embedding_model=embedding_model)
        if row.get('adapter'):
            scene.update(adapter=row['adapter'], mcp_rows=prepared['mcp_rows'], environment_references=prepared['environment_references'])
        if row.get('adapter') in ('data-report','ppt') or row['id']=='paper-proofreading':
            for mcp in scene['mcp_rows']:
                if mcp['config']['serverName'] in ('research_report','paper_trace_rsi','ppt'):
                    mcp['config'].setdefault('env',{})['HARLESS_PRIVATE_ROOT']=str(output.resolve())
        if row.get('adapter') == 'literature':
            from .harless_pdf_deployment import configure_pdf_parser
            try: configure_pdf_parser(scene)
            except (OSError, ValueError): scene['unavailable_reason'] = 'literature_pdf_dependencies_missing'
        if row.get('adapter') == 'data-report' and any(importlib.util.find_spec(module) is None for module in ('numpy','pandas','scipy','matplotlib','statsmodels')):
            scene['unavailable_reason'] = 'data_report_python_dependencies_missing'
        if row.get('adapter') == 'ppt':
            from .harless_ppt_deployment import configure_ppt_rendering
            try:configure_ppt_rendering(scene)
            except (ValueError,OSError):scene['output_unavailable_reason']='ppt_rendering_dependencies_invalid'
            if not (root / 'scenarios/research_ppt/dist/mcp-adapter.js').is_file():
                scene['unavailable_reason'] = 'ppt_adapter_not_built'
            elif any(importlib.util.find_spec(module) is None for module in ('pypdf', 'fitz', 'pptx', 'reportlab', 'PIL')):
                scene['unavailable_reason'] = 'ppt_python_dependencies_missing'
        if row.get('instructions'):
            instructions = (root / row['instructions']).read_text(encoding='utf-8')
            if not instructions.strip() or len(instructions) > 100000: raise ValueError('invalid scene instructions')
            scene.update(instructions=instructions, instructions_sha256=hashlib.sha256(instructions.encode()).hexdigest())
        if row.get('rsi'):
            rsi = row['rsi']
            if isinstance(rsi, dict) and set(rsi) == {'runtime_bundle'}:
                from .harless_rsi_bundle import load_product_bundle
                bundle = (root / rsi['runtime_bundle']).resolve(strict=True)
                try: scene.update(load_product_bundle(root, bundle, row['id']))
                except (ValueError, OSError, KeyError): scene['rsi_unavailable_reason'] = 'existing_runtime_bundle_incompatible'
                rsi = None
            if isinstance(rsi, dict) and set(rsi)=={'bundle_from_env'}:
                if row['id'] not in ('ppt','paper-proofreading','research-data-analysis','literature') or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,100}',rsi['bundle_from_env']):raise ValueError('invalid trusted runtime bundle reference')
                value=os.environ.get(rsi['bundle_from_env'])
                if value:
                    from .harless_rsi_bundle import load_uploaded_bundle
                    try:scene.update(load_uploaded_bundle(root,Path(value),row['id']))
                    except (ValueError,OSError,KeyError):scene['rsi_unavailable_reason']='runtime_bundle_certification_invalid'
                else:scene['rsi_unavailable_reason']='runtime_bundle_not_deployed'
                rsi = None
            if rsi is None:
                pass
            else:
                _bind_legacy_rsi(root, rsi, scene, prepared)
        if row['id'] != default_id:
            preset = output / 'presets' / scene['preset']; preset.mkdir(parents=True, mode=0o700, exist_ok=True)
            rows = [{'id': 'sss-persona', 'name': '@deepseek-ai/dsh-persona', 'config': {
                'prefix': 'Complete the bounded task using only the permitted MCP evidence.',
                'suffix': 'Cite source IDs and versions. Do not invent evidence. Writes require tool-side preview and confirmation.'}},
                *([] if row.get('adapter') else prepared['mcp_rows'])]
            rendered = json.dumps(rows, ensure_ascii=False, indent=2)
            for token, expression in prepared['environment_references'].items(): rendered = rendered.replace(json.dumps(token), expression)
            (preset / 'agent.cordis.yml').write_text(rendered, encoding='utf-8'); (preset / 'agent.cordis.yml').chmod(0o600)
            (preset / 'preset.yml').write_text(json.dumps({'name': 'GeneLoop · ' + row['label']}, ensure_ascii=False), encoding='utf-8')
            (preset / 'preset.yml').chmod(0o600)
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
