"""运行依赖快照；记录实际解释器、字体和可选兼容证据，不绑定实验轮次。"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

from .accounting import version
from .documents import file_hash

ROOT = Path(__file__).resolve().parents[2]


def runtime_file(path: str | Path | None) -> dict:
    """记录被选择的文件和实际落点，不保存文件内容或环境变量。"""
    if path is None:
        return {'path': None, 'exists': False, 'sha256': None}
    target = Path(path).absolute()
    sha256 = None
    if target.is_file():
        if target.stat().st_size > 512 * 1024 * 1024:
            raise ValueError('运行依赖文件超出快照限额')
        hashed = hashlib.sha256()
        with target.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                hashed.update(block)
        sha256 = hashed.hexdigest()
    return {'path': str(target), 'resolved_path': str(target.resolve()),
            'exists': target.is_file(), 'sha256': sha256}


def node_runtime_snapshot() -> dict:
    """PATH wrapper 和 Node 实际 execPath 分开冻结；不保存 NODE_OPTIONS。"""
    selected = runtime_file(shutil.which('node'))
    value = {'selected_command': 'node', 'path_selected': selected,
             'process_executable': None, 'process_version': None, 'probe_status': 'not_found'}
    if not selected['exists']:
        return value
    script = 'process.stdout.write(JSON.stringify({execPath:process.execPath,version:process.version}))'
    try:
        result = subprocess.run(['node', '-e', script], text=True, encoding='utf-8',
                                capture_output=True, timeout=15, cwd=ROOT)
        if result.returncode != 0:
            return dict(value, probe_status='failed', probe_returncode=result.returncode)
        observed = json.loads(result.stdout)
        if not isinstance(observed, dict) or not isinstance(observed.get('execPath'), str) or not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', observed.get('version', '')):
            return dict(value, probe_status='invalid_output')
        actual = runtime_file(observed['execPath'])
        return dict(value, process_executable=actual, process_version=observed['version'],
                    selection_differs_from_process=os.path.normcase(selected['resolved_path']) != os.path.normcase(actual['resolved_path']),
                    probe_status='ok')
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError) as error:
        return dict(value, probe_status='error', probe_error_type=type(error).__name__)


def node_compat_provenance(evidence_path: str | Path | None = None) -> dict:
    """只读取调用者显式选择的项目私有证据；默认不臆测历史 wrapper。"""
    value = {'evidence_path': None, 'evidence_sha256': None, 'status': 'not_configured', 'files': {}}
    if evidence_path is None:
        return value
    selected = Path(evidence_path)
    evidence = (selected if selected.is_absolute() else ROOT / selected).resolve()
    if not evidence.is_relative_to((ROOT / '.local').resolve()):
        raise ValueError('兼容运行证据必须位于项目 .local')
    relative = evidence.relative_to(ROOT.resolve()).as_posix()
    value.update(evidence_path=relative, evidence_sha256=file_hash(evidence) if evidence.is_file() else None,
                 status='absent')
    if not evidence.is_file():
        return value
    try:
        if evidence.stat().st_size > 32768:
            return dict(value, status='invalid_metadata')
        row = json.loads(evidence.read_text(encoding='utf-8'))
        if not isinstance(row, dict) or row.get('scope') != 'project-private-node-wrapper':
            return dict(value, status='invalid_metadata')
        recipe = {key: row[key] for key in ('scope', 'node', 'reason', 'changes', 'not_changed') if key in row}
        for name, path in [('wrapper', '.local/node-compat/bin/node'), ('preload', '.local/node-compat/warm-report.cjs')]:
            observed = runtime_file(ROOT / path)
            expected = row.get(name + '_sha256')
            expected = expected if isinstance(expected, str) and re.fullmatch(r'[a-f0-9]{64}', expected) else None
            value['files'][name] = dict(observed, project_relative_path=path,
                                       declared_sha256=expected,
                                       matches_declared_sha256=expected is not None and observed['sha256'] == expected)
        return dict(value, status='recorded', recipe=recipe,
                    usage_verification='node_execPath_probe_and_path_selection;preload_activation_not_independently_proven')
    except (OSError, ValueError, TypeError) as error:
        return dict(value, status='error', error_type=type(error).__name__)


def font_configuration_snapshot() -> dict:
    """冻结字体配置和实际候选文件；宿主探针不冒充 PDF 绘制验收。"""
    configured = {name: os.environ[name] for name in ('FONTCONFIG_FILE', 'FONTCONFIG_PATH') if os.environ.get(name)}
    config = runtime_file(configured.get('FONTCONFIG_FILE'))
    probes = {}
    candidates = [shutil.which('fc-match')]
    if os.name == 'posix' and Path('/usr/bin/fc-match').is_file():
        candidates.append('/usr/bin/fc-match')
    for command in dict.fromkeys(path for path in candidates if path):
        try:
            result = subprocess.run([command, '-f', '%{file}\n', 'Noto Sans CJK SC'],
                capture_output=True, text=True, encoding='utf-8', timeout=15)
            paths = result.stdout.strip().splitlines()
            probes[command] = {'returncode': result.returncode,
                'candidate_file': runtime_file(paths[0]) if result.returncode == 0 and len(paths) == 1 else None}
        except (OSError, subprocess.TimeoutExpired, ValueError) as error:
            probes[command] = {'error_type': type(error).__name__}
    return {'configured_env': configured, 'config_file': config, 'host_probes': probes,
        'scope': 'host_configuration_and_candidates;actual_visible_glyphs_checked_in_delivery',
        'stdio_forwarding': 'explicit_fontconfig_only_at_both_mcp_boundaries'}


def versions(*, compat_evidence: str | Path | None = None) -> dict:
    packages = {}
    for name in ['deepseek-harness-sdk', 'PyMuPDF', 'mcp', 'jsonschema']:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = 'not_installed'
    npm_packages = {}
    for name in ['@deepseek-ai/dsh', '@deepseek-ai/dsh-llm']:
        path = ROOT / 'node_modules' / name / 'package.json'
        npm_packages[name] = json.loads(path.read_text(encoding='utf-8'))['version'] if path.is_file() else 'not_installed'
    return {'os': platform.platform(), 'python': platform.python_version(),
            'node': version(['node', '--version']), 'node_execution': node_runtime_snapshot(),
            'node_compat_provenance': node_compat_provenance(compat_evidence),
            'render_font_configuration': font_configuration_snapshot(),
            'libreoffice': version(['soffice', '--headless', '--version']),
            'python_packages': packages, 'npm_packages': npm_packages}
