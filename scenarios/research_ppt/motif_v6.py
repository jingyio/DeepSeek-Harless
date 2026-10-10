"""V6 场景离线学习：复用公共编译器，不预写 Motif 图或在线规则。

输入是正常 Harness 运行的冻结身份、事件及实际 MCP schema。新工具和旧工具
一同进入挖掘；是否得到新结构由真实参数证据决定。此模块不会调用云模型，
也不会因编译成功就声明科学质量合格、真实旁路或成本下降。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
SCENE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.adapters.task_identity import load_trace_identity, require_distinct_decisions
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.tool_schema_contracts import bind_mcp_descriptions
from src.motif_core.offline.library_builder import _digest as library_digest, library_from_certified


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private_path(path: Path, *, exists=False) -> Path:
    target = path.resolve(strict=exists)
    if not target.is_relative_to((ROOT / '.local').resolve()):
        raise ValueError('原始轨迹、编译产物和证据必须留在仓库 .local')
    return target


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_new(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2,
                                allow_nan=False) + '\n')
    path.chmod(0o600)


def schema_tools(payload: dict | list) -> dict:
    """接受实际 MCP list_tools，或场景实验保存的有序 schema 快照。"""
    if isinstance(payload, dict) and 'ordered_allowed_mcp_schemas' in payload:
        items = payload['ordered_allowed_mcp_schemas']
        if not isinstance(items, list):
            raise ValueError('有序 MCP schema 需要列表')
        rows = []
        for item in items:
            if (not isinstance(item, dict) or not isinstance(item.get('mcp_tool'), dict)
                    or not isinstance(item.get('harness_tool_name'), str)):
                raise ValueError('有序 MCP schema 缺少实际工具数据')
            rows.append({**item['mcp_tool'], 'name': item['harness_tool_name']})
        return {'tools': rows}
    if isinstance(payload, list):
        return {'tools': payload}
    if not isinstance(payload, dict) or not isinstance(payload.get('tools'), list):
        raise ValueError('实际 MCP schema 需要 tools 列表')
    return {'tools': payload['tools']}


def load_dataset(path: Path) -> tuple[dict, list[dict]]:
    data = read(private_path(path, exists=True))
    if (not isinstance(data, dict) or set(data) != {'train', 'heldout'}
            or not isinstance(data['train'], list) or len(data['train']) < 2
            or not isinstance(data['heldout'], list) or not data['heldout']):
        raise ValueError('dataset 需至少两个独立 train 和一个 heldout 的冻结运行目录')
    rows, identities, directories = {}, [], []
    for split in ('train', 'heldout'):
        rows[split] = []
        for value in data[split]:
            if not isinstance(value, str):
                raise ValueError('dataset 运行目录必须是路径字符串')
            directory = private_path(path.parent / value, exists=True)
            if not directory.is_dir() or directory in directories:
                raise ValueError('训练与认证必须使用不同运行目录')
            directories.append(directory)
            events = directory / 'agent-events.jsonl'
            identity_path = directory / 'task-identity.json'
            identity = load_trace_identity(identity_path, events, ROOT / '.local')
            identities.append(identity)
            rows[split].append({'trace_id': directory.name, 'events': str(events),
                                'identity': str(identity_path)})
    if len({row['trace_id'] for split in rows.values() for row in split}) != len(directories):
        raise ValueError('运行目录的 trace_id 重名，不能合并证据')
    require_distinct_decisions(identities)
    return rows, identities


def source_lock(paths: list[Path]) -> list[dict]:
    unique = dict.fromkeys(path.resolve(strict=True) for path in paths)
    return [{'path': str(path), 'sha256': file_hash(path)} for path in unique]


def structural_candidates(manifest: dict) -> list[dict]:
    """描述与现有在线子集相容的候选；不执行或提升其它结构。"""
    result = []
    for artifact in manifest['artifacts']:
        for tool in artifact['tools'][1:]:
            contract = manifest['contracts'][tool]
            edges = [edge for edge in artifact['transfer_evidence'] if edge['to_tool'] == tool]
            if (re.search(r'(?:^|__)read_pinned_[a-z0-9_]+$', tool)
                    and contract['required_params'] == ['source_id']
                    and not contract['default_params'] and not artifact.get('code_nodes')
                    and len(edges) == 1 and edges[0]['from_field'] == 'source_id'
                    and edges[0]['to_param'] == 'source_id'
                    and edges[0].get('version_relation', 'same_source') == 'same_source'
                    and manifest['version_fields'].get(tool)
                    and manifest['version_fields'].get(edges[0]['from_tool'])):
                result.append({'motif_id': artifact['motif_id'], 'tool': tool,
                               'from_tool': edges[0]['from_tool'],
                               'status': 'compatible_candidate_not_observed_bypass'})
    return result


def learn(dataset: Path, *, contracts_path: Path = SCENE / 'contracts.json',
          version_fields_path: Path = SCENE / 'version-fields.json',
          tool_schema_path: Path | None = None, out_dir: Path | None = None,
          generated_tool: str | None = None, guard_paths: tuple[Path, ...] = (),
          mining='sequence') -> Path:
    """从实际事件挖掘、独立认证、导出；没有新候选时如实保留结果。"""
    if mining not in {'sequence', 'witnessed_edges'}:
        raise ValueError('mining 只能为 sequence 或 witnessed_edges')
    dataset = private_path(dataset, exists=True)
    rows, identities = load_dataset(dataset)
    if mining == 'witnessed_edges' and len(rows['heldout']) != 1:
        raise ValueError('公共 witnessed compiler 入口需恰好一个独立 heldout')
    contracts_path = contracts_path.resolve(strict=True)
    version_fields_path = version_fields_path.resolve(strict=True)
    raw_contracts, versions = read(contracts_path), read(version_fields_path)
    contracts = parse_tool_contracts(raw_contracts)
    if not isinstance(versions, dict):
        raise ValueError('版本字段配置必须是字典')
    for name, field in versions.items():
        if name not in contracts or field not in contracts[name].output_fields:
            raise ValueError('版本字段必须来自已批准的实际工具输出')
    if generated_tool is not None and generated_tool not in contracts:
        raise ValueError('新工具必须出现在批准的契约中')
    schema = None
    if tool_schema_path is not None:
        tool_schema_path = tool_schema_path.resolve(strict=True)
        schema = schema_tools(read(tool_schema_path))
        bound = bind_mcp_descriptions(contracts, schema)
        raw_contracts = {name: {**raw_contracts[name], 'description': contract.description}
                         for name, contract in bound.items()}
    output = private_path(out_dir or ROOT / '.local/research-ppt/libraries-v6' / uuid4().hex)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {**rows, 'contracts': raw_contracts}
    if schema is not None:
        write_new(output / 'tool-schema.json', schema)
        manifest['tool_schema_file'] = str(output / 'tool-schema.json')
    write_new(output / 'contracts.json', raw_contracts)
    write_new(output / 'compile.json', manifest)
    paths = [dataset, contracts_path, version_fields_path, *guard_paths]
    paths += [ROOT / path for path in (
        'scripts/compile-dsh-motif-library.py', 'scripts/compile-witnessed-read-chains.py',
        'scripts/export-online-motif-manifest.py', 'src/adapters/dsh_trajectory.py',
        'src/adapters/task_identity.py', 'src/adapters/tool_contract_loader.py',
        'src/adapters/tool_schema_contracts.py', 'src/motif_core/offline/trace_compiler.py',
        'src/motif_core/offline/edge_compiler.py', 'src/motif_core/offline/chain_compiler.py',
        'src/motif_core/offline/library_builder.py', 'src/motif_core/offline/local_programs.py',
        'src/motif_core/read_executor.py', 'src/motif_core/online_skill_runtime.mjs')]
    if tool_schema_path is not None:
        paths.append(tool_schema_path)
    for split in rows.values():
        for row in split:
            events = Path(row['events'])
            paths += [events, Path(row['identity']), events.parent / 'manifest.json']
    lock = {'schema_version': 1, 'sources': source_lock(paths), 'mining': mining,
            'identity_assertion': 'decision_ids_are_agent_asserted_not_human_blind_review',
            'identities': identities}
    write_new(output / 'evidence-lock.json', lock)
    try:
        if mining == 'sequence':
            subprocess.run([sys.executable, str(ROOT / 'scripts/compile-dsh-motif-library.py'),
                            '--manifest', str(output / 'compile.json'), '--out', str(output / 'library.json')],
                           cwd=ROOT, check=True)
        else:
            command = [sys.executable, str(ROOT / 'scripts/compile-witnessed-read-chains.py'),
                       '--contracts', str(output / 'contracts.json'),
                       '--out', str(output / 'witnessed-edge-report.json')]
            for split in ('train', 'heldout'):
                for row in rows[split]:
                    command += ['--' + split, row['trace_id'], row['identity'], row['events']]
            subprocess.run(command, cwd=ROOT, check=True)
            edge_report = read(output / 'witnessed-edge-report.json')
            # 全部候选及拒绝由公共脚本给出。这里只封装它已认证的产物，
            # 不指定工具顺序、添加参数边或跳过失败/写入 barrier。
            learned = library_from_certified(edge_report['artifacts'])
            learned['rejected'] = edge_report['rejected']
            learned['task_identity_evidence'] = {
                row['trace_id']: identity for row, identity in zip(
                    rows['train'] + rows['heldout'], identities, strict=True)}
            learned['library_digest'] = library_digest({
                key: value for key, value in learned.items() if key != 'library_digest'})
            write_new(output / 'library.json', learned)
        library = read(output / 'library.json')
        used = {tool.rstrip('+') for item in library['artifacts'] for tool in item['tools']}
        effective_versions = {tool: field for tool, field in versions.items() if tool in used}
        write_new(output / 'version-fields.json', effective_versions)
        subprocess.run([sys.executable, str(ROOT / 'scripts/export-online-motif-manifest.py'),
                        '--library', str(output / 'library.json'),
                        '--contracts', str(output / 'contracts.json'),
                        '--version-fields', str(output / 'version-fields.json'),
                        '--output', str(output / 'online-manifest.json')], cwd=ROOT, check=True)
    except subprocess.CalledProcessError as exc:
        write_new(output / 'learning-failure.json', {
            'stage': Path(exc.cmd[1]).name, 'returncode': exc.returncode,
            'evidence_lock_sha256': file_hash(output / 'evidence-lock.json'),
            'status': 'not_promoted', 'reason': 'public_compiler_or_exporter_rejected'})
        raise
    online = read(output / 'online-manifest.json')
    derived = structural_candidates(online)
    report = {'schema_version': 1, 'status': 'independently_trace_certified_not_quality_certified',
              'mining': mining, 'product_registered': False, 'quality_cost_promoted': False,
              'library_digest': library['library_digest'], 'manifest_digest': online['manifest_digest'],
              'generated_tool': generated_tool,
              'new_tool_artifacts': [item['motif_id'] for item in online['artifacts']
                                     if generated_tool and generated_tool in item['tools']],
              'structural_candidates': derived,
              'new_tool_structural_candidates': [item for item in derived if item['tool'] == generated_tool],
              'rejected_candidates': library['rejected'],
              'source_lock_sha256': file_hash(output / 'evidence-lock.json'),
              'output_lock': source_lock([output / name for name in
                                         ('compile.json', 'contracts.json', 'version-fields.json',
                                          'library.json', 'online-manifest.json')]
                                        + ([output / 'tool-schema.json'] if schema is not None else [])
                                        + ([output / 'witnessed-edge-report.json']
                                           if mining == 'witnessed_edges' else [])),
              'quality': 'not_reviewed', 'real_bypass_observed': False,
              'scope': 'model-generated tool and learned Motif are separately certified'}
    write_new(output / 'learning-report.json', report)
    validate_compilation(output / 'online-manifest.json')
    return output / 'online-manifest.json'


def validate_compilation(manifest: Path) -> dict:
    """在线任务入口调用此检查后，仍须公共 Node verifier 和工具自身守卫。"""
    manifest = private_path(manifest, exists=True)
    report = read(manifest.parent / 'learning-report.json')
    lock_path = manifest.parent / 'evidence-lock.json'
    if (not isinstance(report, dict) or report.get('schema_version') != 1
            or file_hash(lock_path) != report.get('source_lock_sha256')):
        raise ValueError('学习证据锁发生变化，不能加载旧 Motif')
    lock = read(lock_path)
    for row in lock['sources'] + report['output_lock']:
        path = Path(row['path']).resolve(strict=True)
        if file_hash(path) != row['sha256']:
            raise ValueError('来源、工具代码/schema 或编译产物变化，须重新认证')
    if read(manifest)['manifest_digest'] != report.get('manifest_digest'):
        raise ValueError('Motif manifest 与认证记录不一致')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--contracts', type=Path, default=SCENE / 'contracts.json')
    parser.add_argument('--version-fields', type=Path, default=SCENE / 'version-fields.json')
    parser.add_argument('--tool-schema', type=Path)
    parser.add_argument('--generated-tool')
    parser.add_argument('--guard-path', type=Path, action='append', default=[])
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--mining', choices=['sequence', 'witnessed_edges'], default='sequence')
    args = parser.parse_args()
    print(learn(args.dataset, contracts_path=args.contracts,
                version_fields_path=args.version_fields, tool_schema_path=args.tool_schema,
                generated_tool=args.generated_tool, guard_paths=tuple(args.guard_path),
                out_dir=args.out_dir, mining=args.mining))


if __name__ == '__main__':
    main()
