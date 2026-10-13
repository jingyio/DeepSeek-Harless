"""Server-owned scene registry; each preset mounts its own MCP composition."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from .scenario import prepare_scenario

IDENTITY = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')

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
        if (not isinstance(row, dict) or set(row) - {'id', 'label', 'scenario', 'case', 'instructions', 'rsi'} or
            not IDENTITY.fullmatch(row.get('id', '')) or row['id'] in seen or
            not isinstance(row.get('label'), str) or not 1 <= len(row['label']) <= 128):
            raise ValueError('invalid or duplicate scene identity')
        seen.add(row['id'])
        path = (root / row['scenario']).resolve(strict=True)
        prepared = prepared_default if row['id'] == default_id else prepare_scenario(path, case=row.get('case', ''))
        scene = {'id': row['id'], 'label': row['label'], 'preset': 'sss-task' if row['id'] == default_id else 'sss-scene-' + row['id'],
                 'allowed_tools': prepared['allowed_tools'], 'config_sha256': prepared['config_sha256'],
                 'case': prepared['case'], 'embedding_endpoint': embedding_endpoint, 'embedding_model': embedding_model}
        if row.get('instructions'):
            instructions = (root / row['instructions']).read_text(encoding='utf-8')
            if not instructions.strip() or len(instructions) > 100000: raise ValueError('invalid scene instructions')
            scene.update(instructions=instructions, instructions_sha256=hashlib.sha256(instructions.encode()).hexdigest())
        if row.get('rsi'):
            rsi = row['rsi']
            if not isinstance(rsi, dict) or set(rsi) != {'manifest', 'task'}: raise ValueError('rsi requires manifest and task')
            scene.update(manifest=str((root / rsi['manifest']).resolve(strict=True)),
                         task=str((root / rsi['task']).resolve(strict=True)),
                         certified_input_sha256=hashlib.sha256(prepared['prompt'].strip().encode()).hexdigest())
        if row['id'] != default_id:
            preset = output / 'presets' / scene['preset']; preset.mkdir(parents=True, mode=0o700)
            rows = [{'id': 'sss-persona', 'name': '@deepseek-ai/dsh-persona', 'config': {
                'prefix': 'Complete the bounded task using only the permitted MCP evidence.',
                'suffix': 'Cite source IDs and versions. Do not invent evidence. Writes require tool-side preview and confirmation.'}}, *prepared['mcp_rows']]
            rendered = json.dumps(rows, ensure_ascii=False, indent=2)
            for token, expression in prepared['environment_references'].items(): rendered = rendered.replace(json.dumps(token), expression)
            (preset / 'agent.cordis.yml').write_text(rendered, encoding='utf-8'); (preset / 'agent.cordis.yml').chmod(0o600)
            (preset / 'preset.yml').write_text(json.dumps({'name': row['label']}, ensure_ascii=False), encoding='utf-8')
            (preset / 'preset.yml').chmod(0o600)
        scenes.append(scene)
    if default_id not in seen:
        # A private single-scene configuration still has a selectable entry.
        scenes.append({'id': default_id, 'label': prepared_default['name'], 'preset': 'sss-task',
                       'allowed_tools': prepared_default['allowed_tools'], 'config_sha256': prepared_default['config_sha256']})
    return scenes
