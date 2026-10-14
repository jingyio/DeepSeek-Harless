"""长期资料/组件登记；保留字节与证据，不执行代码、不继承任务授权。

tenant_id 必须来自可信后端身份。此模块的逻辑隔离不是操作系统沙箱或登录系统。
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from uuid import uuid4

from . import document_cache, documents

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORE = ROOT / '.local/research-ppt/library'
MAX_DOCUMENT_BYTES = documents.MAX_BYTES
MAX_RECORD_BYTES = 128 * 1024
LOCK_WAIT_SECONDS = 5.0
LOCK_POLL_SECONDS = 0.03
FIXED_SCRIPTS = {
    'render_delivery': ('scenarios/research_ppt/ts/delivery-adapter.ts',
                        'scenarios/research_ppt/ts/render.ts',
                        'scenarios/research_ppt/ts/execution-policy.ts'),
    'direct_edit': ('scenarios/research_ppt/direct_edit.py',
                    'scenarios/research_ppt/ts/direct-edit-cli.ts'),
    'document_parse': ('scenarios/research_ppt/document_cache.py',
                       'scenarios/research_ppt/documents.py'),
}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value):
        raise ValueError(f'{name} 必须为 1–80 位受限标识符')
    return value


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('需要 SHA-256 版本')
    return value


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) <= set(required) | set(optional):
        raise ValueError('资料库字段不符合受限协议')


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('资料库 JSON 字段重复')
        result[key] = value
    return result


def _read(path):
    if path.stat().st_size > MAX_RECORD_BYTES:
        raise ValueError('资料库记录过大')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('非法 JSON 数值')))


def _safe(path, root, *, exists=False):
    """Reject symlinks at every existing segment, including paths not yet created."""
    path, root = Path(path).absolute(), Path(root).absolute()
    if not path.is_relative_to(root):
        raise ValueError('资料库路径越界')
    for current in (path, *path.parents):
        if current.is_symlink():
            raise ValueError('资料库不接受符号链接')
    resolved = path.resolve(strict=exists)
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('资料库路径越界')
    return resolved


def _write(path, value, *, exclusive=False):
    encoded = _canonical(value)
    if len(encoded) > MAX_RECORD_BYTES:
        raise ValueError('资料库记录过大')
    if exclusive:
        with path.open('xb') as stream:
            if os.name != 'nt':
                os.chmod(path, 0o600)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.library-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _consent(visibility, value):
    if visibility not in {'private', 'public'}:
        raise ValueError('visibility 只能是 private/public')
    if visibility == 'private':
        if value is not None:
            raise ValueError('私有记录不能附带公开授权')
        return None
    _keys(value, ('confirmed', 'source_url', 'license', 'consent_reference'))
    if value['confirmed'] is not True:
        raise PermissionError('公开复用需要明确授权')
    if (not isinstance(value['source_url'], str) or len(value['source_url']) > 1000 or
            not value['source_url'].startswith('https://')):
        raise ValueError('公开复用需要 https 来源定位')
    for key in ('license', 'consent_reference'):
        if not isinstance(value[key], str) or not 1 <= len(value[key].strip()) <= 500:
            raise ValueError('公开复用需要许可/授权依据')
    return json.loads(_canonical(value))


def required_job_components(job: dict) -> tuple[str, ...]:
    """由宿主任务权限确定固定组件集合；不根据模型建议加载代码。"""
    if not isinstance(job, dict) or type(job.get('allow_output')) is not bool:
        raise ValueError('组件绑定需要明确 allow_output 布尔值')
    names = ('document_parse', 'render_delivery')
    return names + (('direct_edit',) if job['allow_output'] else ())


def validate_job_components(job: dict, *, library=None) -> dict[str, dict]:
    """核验冻结的job组件，只返回descriptor，不执行或重新登记。

    两字段都缺省的历史任务保持原入口；一旦存在任何绑定字段，协议不完整
    就拒绝，不能在版本失效时悄悄改走历史模式。实际租户仍由可信宿主绑定。
    """
    if not isinstance(job, dict):
        raise ValueError('组件校验需要 job 对象')
    schema_key, bindings_key = 'library_component_schema_version', 'library_components'
    present = {key for key in (schema_key, bindings_key) if key in job}
    if not present:
        return {}  # 明确历史兼容；不能宣称该任务已使用组件库。
    if (len(present) != 2 or type(job[schema_key]) is not int or job[schema_key] != 1 or
            job.get('persistent_library') is not True or
            type(job.get('library_schema_version')) is not int or job['library_schema_version'] != 1):
        raise ValueError('job 组件绑定协议不完整或无长期库；不能绕过校验')
    tenant = _id(job.get('library_tenant'), 'library_tenant')
    job_id = _id(job.get('job_id'), 'job_id')
    bindings = job[bindings_key]
    expected = required_job_components(job)
    if not isinstance(bindings, dict) or set(bindings) != set(expected):
        raise ValueError('job 固定组件集合不完整或包含未授权组件')
    for script_id in expected:
        binding = bindings[script_id]
        _keys(binding, ('resource_id', 'version_sha256'))
        resource_id = binding['resource_id']
        if not isinstance(resource_id, str) or not re.fullmatch('component-[0-9a-f]{40}', resource_id):
            raise ValueError('job 组件资源标识无效')
        _sha(binding['version_sha256'])
    store = PersistentLibrary() if library is None else library
    if not isinstance(store, PersistentLibrary):
        raise ValueError('组件宿主需要 PersistentLibrary')
    descriptors = {}
    for script_id in expected:
        binding = bindings[script_id]
        resolved = store.resolve_component(binding['resource_id'], tenant_id=tenant, job_id=job_id,
                                           expected_sha256=binding['version_sha256'], expected_script_id=script_id)
        descriptor = resolved['descriptor']
        if (descriptor.get('kind') != 'fixed_script' or descriptor.get('script_id') != script_id or
                descriptor.get('execution') != 'descriptor_only_existing_host_required'):
            raise ValueError('job 组件种类或固定脚本绑定不一致')
        descriptors[script_id] = descriptor
    return descriptors


class PersistentLibrary:
    """Persistence across jobs/restarts; all writes are serialized and audited.

    No job cleanup calls this store. A revoke keeps historical bytes but rejects future
    access. Previously delivered/extracted copies cannot be remotely retracted.
    """

    def __init__(self, root: Path | str | None = None):
        self.root = _safe(Path(DEFAULT_STORE if root is None else root), ROOT / '.local')
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt':
            os.chmod(self.root, 0o700)
        for name in ('records', 'objects', 'events', 'caches'):
            self._path(name).mkdir(exist_ok=True)

    def _path(self, *parts, exists=False):
        return _safe(self.root.joinpath(*parts), self.root, exists=exists)

    @contextmanager
    def _lock(self):
        lock = self._path('.write-lock')
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        token = uuid4().hex
        while True:
            try:
                with lock.open('x', encoding='utf-8') as stream:
                    stream.write(json.dumps({'pid': os.getpid(), 'created_at': _now(), 'token': token}))
                break
            except FileExistsError as error:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('资料库写入等待超时；残留锁需确认无写入者后处理') from error
                time.sleep(min(LOCK_POLL_SECONDS, remaining))
        try:
            yield
        finally:
            # Never remove a replaced lock owned by another writer.
            if lock.exists() and _read(lock).get('token') == token:
                lock.unlink()

    def _event(self, action, tenant_id, job_id, *, resource_id=None, details=None):
        event = {'schema_version': 1, 'event_id': uuid4().hex, 'created_at': _now(),
                 'action': action, 'tenant_id': tenant_id, 'job_id': job_id,
                 'resource_id': resource_id, 'details': details or {}}
        event['event_sha256'] = _digest(event)
        _write(self._path('events', event['event_id'] + '.json'), event, exclusive=True)
        return event['event_id']

    def _record(self, resource_id):
        if not isinstance(resource_id, str) or not re.fullmatch(r'(doc|component)-[0-9a-f]{40}', resource_id):
            raise ValueError('无效 resource_id')
        record = _read(self._path('records', resource_id + '.json', exists=True))
        _keys(record, ('schema_version', 'resource_id', 'kind', 'owner', 'visibility', 'public_consent',
                       'status', 'created_at', 'title', 'version_sha256', 'payload', 'record_sha256'))
        if (type(record['schema_version']) is not int or record['schema_version'] != 1 or
                record['resource_id'] != resource_id or
                record['record_sha256'] != _digest({k: v for k, v in record.items() if k != 'record_sha256'})):
            raise ValueError('资料库记录版本或完整性无效')
        _id(record['owner'], 'owner')
        _sha(record['version_sha256'])
        _consent(record['visibility'], record['public_consent'])
        if record['status'] not in {'active', 'revoked'} or record['kind'] not in {'document', 'component'}:
            raise ValueError('资料库状态无效')
        return record

    def _save(self, record, *, exclusive=False):
        record = dict(record)
        record['record_sha256'] = _digest({k: v for k, v in record.items() if k != 'record_sha256'})
        _write(self._path('records', record['resource_id'] + '.json'), record, exclusive=exclusive)

    def _allowed(self, record, tenant_id):
        if (record['status'] != 'active' or
                (record['owner'] != tenant_id and record['visibility'] != 'public')):
            raise PermissionError('资料不存在或当前身份无复用权限')

    @staticmethod
    def _summary(record):
        return {k: record[k] for k in ('resource_id', 'kind', 'visibility', 'status', 'title',
                                      'version_sha256', 'created_at')}

    def register_document(self, path: Path | str, *, tenant_id: str, job_id: str,
                          expected_sha256: str | None = None, title: str = '',
                          visibility: str = 'private', public_consent: dict | None = None) -> dict:
        """Copy to persistent content storage. Upload/read permission is checked by caller."""
        _id(tenant_id, 'tenant_id'); _id(job_id, 'job_id')
        consent = _consent(visibility, public_consent)
        if not isinstance(title, str) or len(title) > 500:
            raise ValueError('title 最多 500 字符')
        source = Path(path).resolve(strict=True)
        file_format = source.suffix.lower().lstrip('.')
        if file_format not in {'pdf', 'pptx'} or not source.is_file():
            raise ValueError('资料库仅接受 PDF/PPTX')
        if not 1 <= source.stat().st_size <= MAX_DOCUMENT_BYTES:
            raise ValueError('资料文件大小需为 1–100 MiB')
        source_sha = documents.file_hash(source)
        if expected_sha256 is not None and source_sha != _sha(expected_sha256):
            raise ValueError('输入版本已变化')
        resource_id = 'doc-' + _digest({'owner': tenant_id, 'sha256': source_sha, 'format': file_format})[:40]
        with self._lock():
            record_path = self._path('records', resource_id + '.json')
            if record_path.exists():
                record = self._record(resource_id)
                self._allowed(record, tenant_id)
                # Registration never silently changes a prior sharing decision.
                if record['visibility'] != visibility or record['public_consent'] != consent:
                    raise ValueError('已有记录可见性不同；请显式修改共享授权')
                self._document_path(record)
                action = 'document_reused'
            else:
                relative = f'objects/{resource_id}.{file_format}'
                target = self._path(relative)
                if target.exists():
                    if documents.file_hash(target) != source_sha:
                        raise ValueError('保留副本完整性无效')
                else:
                    # An interrupted copy cannot become a registered resource.
                    temporary = self._path('objects', '.' + uuid4().hex + '.tmp')
                    try:
                        with source.open('rb') as src, temporary.open('xb') as dst:
                            if os.name != 'nt':
                                os.chmod(temporary, 0o600)
                            copied = 0
                            while chunk := src.read(1024 * 1024):
                                copied += len(chunk)
                                if copied > MAX_DOCUMENT_BYTES:
                                    raise ValueError('输入文件在复制中超出大小限制')
                                dst.write(chunk)
                            dst.flush(); os.fsync(dst.fileno())
                        if documents.file_hash(temporary) != source_sha or documents.file_hash(source) != source_sha:
                            raise ValueError('输入版本在复制中变化')
                        os.replace(temporary, target)
                    finally:
                        if temporary.exists():
                            temporary.unlink()
                record = {'schema_version': 1, 'resource_id': resource_id, 'kind': 'document',
                          'owner': tenant_id, 'visibility': visibility, 'public_consent': consent,
                          'status': 'active', 'created_at': _now(), 'title': title or 'Document',
                          'version_sha256': source_sha, 'payload': {'format': file_format, 'object': relative}}
                self._save(record, exclusive=True)
                action = 'document_registered'
            if documents.file_hash(source) != source_sha:
                raise ValueError('输入版本已变化')
            event = self._event(action, tenant_id, job_id, resource_id=resource_id,
                                details={'source_sha256': source_sha, 'visibility': visibility})
            return {**self._summary(record), 'source_sha256': source_sha, 'format': file_format,
                    'audit_event_id': event}

    def _document_path(self, record):
        if record['kind'] != 'document':
            raise ValueError('资料不是文档')
        _keys(record['payload'], ('format', 'object'))
        fmt = record['payload']['format']
        if fmt not in {'pdf', 'pptx'} or record['payload']['object'] != f"objects/{record['resource_id']}.{fmt}":
            raise ValueError('资料副本定位无效')
        path = self._path(record['payload']['object'], exists=True)
        if not path.is_file() or documents.file_hash(path) != record['version_sha256']:
            raise ValueError('资料副本版本已变化')
        return path

    def resolve_document(self, resource_id: str, *, tenant_id: str, job_id: str,
                         expected_sha256: str | None = None) -> dict:
        _id(tenant_id, 'tenant_id'); _id(job_id, 'job_id')
        with self._lock():
            record = self._record(resource_id)
            self._allowed(record, tenant_id)
            if expected_sha256 is not None and record['version_sha256'] != _sha(expected_sha256):
                raise ValueError('资料版本不一致')
            path = self._document_path(record)
            event = self._event('document_resolved', tenant_id, job_id, resource_id=resource_id,
                                details={'source_sha256': record['version_sha256']})
            return {**self._summary(record), 'path': str(path), 'format': record['payload']['format'],
                    'source_sha256': record['version_sha256'], 'audit_event_id': event}

    def cache_directory(self, resource_id: str, *, tenant_id: str, job_id: str) -> Path:
        """Authorize before returning a persistent parse cache directory; not a read capability."""
        self.resolve_document(resource_id, tenant_id=tenant_id, job_id=job_id)
        directory = self._path('caches', resource_id)
        directory.mkdir(exist_ok=True)
        return directory

    def parse_document(self, resource_id: str, *, tenant_id: str, job_id: str,
                       expected_sha256: str | None = None, use_cache: bool = True, audit=None) -> dict:
        if type(use_cache) is not bool:
            raise ValueError('use_cache 必须为明确布尔值')
        resolved = self.resolve_document(resource_id, tenant_id=tenant_id, job_id=job_id,
                                         expected_sha256=expected_sha256)
        directory = self._path('caches', resource_id)
        events = []
        if use_cache:
            payload = document_cache.cached_parse_document(Path(resolved['path']), directory,
                        expected_sha256=resolved['source_sha256'], audit=events.append)
        else:
            payload = documents.parse_document(Path(resolved['path']))
        # Revocation during parsing/cache generation rejects returning the payload.
        self.resolve_document(resource_id, tenant_id=tenant_id, job_id=job_id,
                              expected_sha256=resolved['source_sha256'])
        with self._lock():
            self._allowed(self._record(resource_id), tenant_id)
            event = self._event('document_parsed', tenant_id, job_id, resource_id=resource_id,
                                details={'source_sha256': resolved['source_sha256'],
                                         'cache_enabled': use_cache, 'cache_events': events})
        if audit is not None:
            for row in events:
                audit({**row, 'library_resource_id': resource_id, 'library_event_id': event})
        return payload

    def set_document_sharing(self, resource_id: str, *, tenant_id: str, job_id: str,
                             visibility: str, public_consent: dict | None = None) -> dict:
        return self._change(resource_id, tenant_id, job_id, visibility=visibility,
                            public_consent=public_consent, document_only=True)

    def revoke_document(self, resource_id: str, *, tenant_id: str, job_id: str) -> dict:
        return self._change(resource_id, tenant_id, job_id, status='revoked', document_only=True)

    def revoke_component(self, resource_id: str, *, tenant_id: str, job_id: str) -> dict:
        return self._change(resource_id, tenant_id, job_id, status='revoked', component_only=True)

    def _change(self, resource_id, tenant_id, job_id, *, visibility=None, public_consent=None,
                status=None, document_only=False, component_only=False):
        _id(tenant_id, 'tenant_id'); _id(job_id, 'job_id')
        consent = _consent(visibility, public_consent) if visibility is not None else None
        with self._lock():
            record = self._record(resource_id)
            if record['owner'] != tenant_id:
                raise PermissionError('只有资料所有者可撤回或修改共享授权')
            if ((document_only and record['kind'] != 'document') or
                    (component_only and record['kind'] != 'component')):
                raise ValueError('资料类型不一致')
            previous = {'visibility': record['visibility'], 'status': record['status']}
            if visibility is not None:
                record.update(visibility=visibility, public_consent=consent)
            if status is not None:
                record['status'] = status
            self._save(record)
            event = self._event('access_changed', tenant_id, job_id, resource_id=resource_id,
                                details={'previous': previous, 'visibility': record['visibility'],
                                         'status': record['status'], 'bytes_retained': True})
            return {**self._summary(record), 'audit_event_id': event, 'bytes_retained': True}

    def _component(self, descriptor, *, public=False):
        if not isinstance(descriptor, dict):
            raise ValueError('组件必须是受限 descriptor')
        if descriptor.get('kind') == 'fixed_script':
            _keys(descriptor, ('kind', 'script_id'))
            script_id = descriptor['script_id']
            if not isinstance(script_id, str) or script_id not in FIXED_SCRIPTS:
                raise ValueError('未知固定脚本；不允许任意路径、代码或命令')
            versions = {path: documents.file_hash(_safe(ROOT / path, ROOT, exists=True))
                        for path in FIXED_SCRIPTS[script_id]}
            return {**descriptor, 'implementation_sha256': _digest(versions), 'files': versions,
                    'execution': 'descriptor_only_existing_host_required'}
        if descriptor.get('kind') == 'certified_generated_tool':
            _keys(descriptor, ('kind', 'certificate_path', 'certificate_sha256'))
            if public:
                raise PermissionError('认证工具当前携私有轨迹依赖；未脱敏打包前不可跨租户公开')
            certificate_path = descriptor['certificate_path']
            if not isinstance(certificate_path, str) or not 1 <= len(certificate_path) <= 4096:
                raise ValueError('组件认证路径无效')
            path = _safe(Path(certificate_path), ROOT / '.local', exists=True)
            if documents.file_hash(path) != _sha(descriptor['certificate_sha256']):
                raise ValueError('组件认证版本不一致')
            from .generated_tools import load_certified_tool
            checked = load_certified_tool(path)
            return {'kind': 'certified_generated_tool', 'certificate_path': str(path),
                    'certificate_sha256': checked['certificate_sha256'], 'code_sha256': checked['code_sha256'],
                    'input_schema_sha256': checked['input_schema_sha256'],
                    'execution': 'descriptor_only_existing_certified_host_required'}
        if descriptor.get('kind') == 'certified_motif':
            _keys(descriptor, ('kind', 'manifest_path', 'manifest_sha256'))
            if public:
                raise PermissionError('Motif 认证依赖私有轨迹；未脱敏打包前不可跨租户公开')
            manifest_path = descriptor['manifest_path']
            if not isinstance(manifest_path, str) or not 1 <= len(manifest_path) <= 4096:
                raise ValueError('Motif manifest 路径无效')
            path = _safe(Path(manifest_path), ROOT / '.local', exists=True)
            if documents.file_hash(path) != _sha(descriptor['manifest_sha256']):
                raise ValueError('Motif manifest 版本不一致')
            from .motif_v6 import validate_compilation
            checked = validate_compilation(path)
            if checked.get('status') != 'independently_trace_certified_not_quality_certified':
                raise ValueError('Motif 缺少独立轨迹编译记录')
            evidence = _safe(path.parent / 'evidence-lock.json', ROOT / '.local', exists=True)
            report = _safe(path.parent / 'learning-report.json', ROOT / '.local', exists=True)
            return {'kind': 'certified_motif', 'manifest_path': str(path),
                    'manifest_sha256': documents.file_hash(path), 'manifest_digest': checked['manifest_digest'],
                    'evidence_lock_sha256': documents.file_hash(evidence),
                    'learning_report_sha256': documents.file_hash(report),
                    'execution': 'descriptor_only_existing_motif_host_required',
                    'certification_scope': 'independent_trace_not_quality_cost_promotion'}
        raise ValueError('不支持的组件类型；不能登记任意可执行代码')

    def register_component(self, descriptor: dict, *, tenant_id: str, job_id: str,
                           title: str = '', visibility: str = 'private',
                           public_consent: dict | None = None) -> dict:
        _id(tenant_id, 'tenant_id'); _id(job_id, 'job_id')
        consent = _consent(visibility, public_consent)
        if not isinstance(title, str) or len(title) > 500:
            raise ValueError('title 最多 500 字符')
        bounded = self._component(descriptor, public=visibility == 'public')
        version = _digest(bounded)
        resource_id = 'component-' + _digest({'owner': tenant_id, 'descriptor': bounded})[:40]
        with self._lock():
            record_path = self._path('records', resource_id + '.json')
            if record_path.exists():
                record = self._record(resource_id)
                self._allowed(record, tenant_id)
                if record['visibility'] != visibility or record['public_consent'] != consent:
                    raise ValueError('已有组件共享范围不同')
                action = 'component_reused'
            else:
                record = {'schema_version': 1, 'resource_id': resource_id, 'kind': 'component',
                          'owner': tenant_id, 'visibility': visibility, 'public_consent': consent,
                          'status': 'active', 'created_at': _now(), 'title': title or 'Component',
                          'version_sha256': version, 'payload': bounded}
                self._save(record, exclusive=True)
                action = 'component_registered'
            event = self._event(action, tenant_id, job_id, resource_id=resource_id,
                                details={'version_sha256': version, 'descriptor_kind': descriptor['kind']})
            return {**self._summary(record), 'audit_event_id': event}

    def resolve_component(self, resource_id: str, *, tenant_id: str, job_id: str,
                          expected_sha256: str | None = None, expected_script_id: str | None = None) -> dict:
        _id(tenant_id, 'tenant_id'); _id(job_id, 'job_id')
        if expected_script_id is not None and (not isinstance(expected_script_id, str) or
                                              expected_script_id not in FIXED_SCRIPTS):
            raise ValueError('未知固定组件绑定')
        with self._lock():
            record = self._record(resource_id)
            self._allowed(record, tenant_id)
            if record['kind'] != 'component':
                raise ValueError('资料不是组件')
            stored = record['payload']
            if expected_script_id is not None and (stored.get('kind') != 'fixed_script' or
                                                   stored.get('script_id') != expected_script_id):
                raise ValueError('job 组件种类或固定脚本绑定不一致')
            if stored.get('kind') == 'fixed_script':
                request = {k: stored[k] for k in ('kind', 'script_id')}
            elif stored.get('kind') == 'certified_motif':
                request = {k: stored[k] for k in ('kind', 'manifest_path', 'manifest_sha256')}
            else:
                request = {k: stored[k] for k in ('kind', 'certificate_path', 'certificate_sha256')}
            bounded = self._component(request, public=record['visibility'] == 'public')
            if bounded != stored or _digest(bounded) != record['version_sha256']:
                raise ValueError('组件实现或认证依赖已变化；需重新登记')
            if expected_sha256 is not None and record['version_sha256'] != _sha(expected_sha256):
                raise ValueError('组件版本不一致')
            event = self._event('component_resolved', tenant_id, job_id, resource_id=resource_id,
                                details={'version_sha256': record['version_sha256']})
            return {**self._summary(record), 'descriptor': bounded, 'audit_event_id': event}

    def list_resources(self, *, tenant_id: str, kind: str | None = None) -> list[dict]:
        """Do not expose private existence, owner IDs, object paths or certification paths."""
        _id(tenant_id, 'tenant_id')
        if kind is not None and kind not in {'document', 'component'}:
            raise ValueError('无效资源类型')
        with self._lock():
            rows = []
            for path in sorted(self._path('records').glob('*.json')):
                record = self._record(path.stem)
                if (record['status'] == 'active' and (record['owner'] == tenant_id or record['visibility'] == 'public')
                        and (kind is None or record['kind'] == kind)):
                    rows.append(self._summary(record))
            return rows
