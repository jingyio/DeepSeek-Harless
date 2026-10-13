"""科研 PPT 工具后端的同 job、版本绑定 JSON 状态恢复。

公共移植使用 schema 2；旧私有 schema 1 不隐式迁移或重新签署。

仅恢复同一 job 的权限与来源，校验失败拒绝启动。预览文件损坏只撤销
对应 validation，保留 deck 和完整计划，须再次真实验收才能交付。
checkpoint 的摘要用于损坏检测，不是抵御有本机写权限者的签名。
"""
from __future__ import annotations

import base64
import copy
from datetime import datetime, timezone
from functools import wraps
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
from contextlib import contextmanager
from typing import Any

from scenarios.research_ppt.documents import file_hash, inspect_pptx
from scenarios.research_ppt.service import PPTService, ROOT, SCENE, private_path

FORMAT = "research-ppt-service-checkpoint"
SCHEMA_VERSION = 2
MAX_CHECKPOINT_BYTES = 128 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_DECK = re.compile(r"[0-9a-f]{32}\Z")
_SOURCE = re.compile(r"source-[0-9a-f]{32}\Z")


class CheckpointRejected(ValueError):
    """明确拒绝恢复/写入；不会悄悄创建无历史的新会话。"""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _raw_hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _json_value(value: Any, depth=0, count=None):
    count = [0] if count is None else count
    count[0] += 1
    if depth > 40 or count[0] > 1000000:
        raise CheckpointRejected("checkpoint JSON 深度或节点数量超限")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item, depth + 1, count)
        return
    if type(value) is dict:
        for key, item in value.items():
            if not isinstance(key, str) or key in {"__proto__", "constructor", "prototype"}:
                raise CheckpointRejected("checkpoint JSON 属性名不安全")
            _json_value(item, depth + 1, count)
        return
    raise CheckpointRejected("checkpoint 只接受有限纯 JSON，不接受可执行对象")


def _object(value, keys, message):
    if type(value) is not dict or set(value) != set(keys):
        raise CheckpointRejected(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CheckpointRejected("checkpoint JSON 出现重复属性")
        result[key] = value
    return result


def _read_json(path: Path):
    if not path.is_file() or path.stat().st_size > MAX_CHECKPOINT_BYTES:
        raise CheckpointRejected("checkpoint 文件不存在或超过安全大小")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               CheckpointRejected("checkpoint 非有限 JSON 数值")))
        _json_value(value)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise CheckpointRejected("checkpoint 破损，拒绝加载历史状态") from error


class CheckpointPPTService(PPTService):
    def __init__(self, job_path: Path, checkpoint_path: Path | None = None):
        super().__init__(job_path)
        self._lock = threading.RLock()
        self._transaction_depth = 0
        self._save_pending = False
        self._checkpoint_blocked = False
        self.claim_evidence: dict = {}
        self.checkpoint_path = self._checkpoint_path(
            checkpoint_path or self.job_path.parent / "service-checkpoint.json")
        self._disk_checkpoint_sha256: str | None = None
        self._job_sha256 = file_hash(self.job_path)
        self._version_snapshot = self.checkpoint_versions()
        self.restore_status = {"restored": False, "discarded_validations": [],
                               "checkpoint_schema_version": SCHEMA_VERSION}
        try:
            self._guard_current_dependencies()
        except Exception as error:
            self._checkpoint_blocked = True
            self.record("checkpoint_initialization_rejected", {"error_type": type(error).__name__,
                        "reason": str(error)[:800], "schema_version": SCHEMA_VERSION})
            raise CheckpointRejected("当前job/来源/证书依赖已失效，拒绝初始化历史状态") from error
        # lexists distinguishes a missing checkpoint from a broken symlink.
        if os.path.lexists(self.checkpoint_path):
            self._load_checkpoint()

    def _checkpoint_path(self, path: Path) -> Path:
        result = private_path(Path(path))
        if result.parent != self.job_path.parent.resolve():
            raise CheckpointRejected("checkpoint 必须位于当前 job 同目录")
        if result in {self.job_path, self.job_path.parent / "feedback.jsonl"}:
            raise CheckpointRejected("checkpoint 不能覆盖任务或反馈文件")
        return result

    def checkpoint_versions(self) -> dict:
        """新增子类可追加自己的宿主文件，不能删掉父类版本守卫。"""
        names = ("service.py", "server.py", "delivery_server.py", "scenario.json", "documents.py", "revision.py", "validation.py",
                 "restyle.py", "generated_tools.py", "figure_catalog.py", "document_cache.py",
                 "layout_learning.py", "contracts.json", "version-fields.json",
                 "package-lock.json", "ts/render.ts", "ts/layout-policy.ts",
                 "dist/render.js", "dist/layout-policy-cli.js")
        version = {"scene/" + name: _raw_hash(SCENE / name) for name in names}
        version["scene/recovery.py"] = _raw_hash(Path(__file__).resolve())
        # The actual subclass module is part of the online state protocol.
        import inspect
        extension = Path(inspect.getfile(type(self))).resolve()
        if extension != Path(__file__).resolve():
            version["scene/subclass.py"] = _raw_hash(extension)
        return version

    def _guard_current_dependencies(self):
        if file_hash(self.job_path) != self._job_sha256 or self.checkpoint_versions() != self._version_snapshot:
            raise CheckpointRejected("job 或服务/修订/渲染/schema 代码版本变化，拒绝旧状态")
        for row in self.job.get("inputs", []):
            self.current(row)
        for key, value in self.job.items():
            if key.endswith("_certificate") and value:
                path = private_path(Path(value))
                expected = self.job.get(key + "_sha256")
                if not isinstance(expected, str) or file_hash(path) != expected:
                    raise CheckpointRejected("任务证书缺少冻结摘要或版本已变化")
        if self.job.get("generated_tool_certificate"):
            self.pinned_figure_tool()  # checks compiler, code, training and heldout evidence.
        if self.job.get("layout_policy_certificate"):
            from scenarios.research_ppt.layout_learning import validate_certificate
            cert = validate_certificate(Path(self.job["layout_policy_certificate"]))
            if cert["policy_digest"] != self.job.get("layout_policy_digest"):
                raise CheckpointRejected("布局证书摘要不一致")

    def _bindings(self) -> dict:
        return {"job_id": self.job["job_id"], "job_sha256": self._job_sha256,
                "input_version": self.input_version, "versions": self._version_snapshot,
                "permission_sha256": _digest({"allow_output": self.job["allow_output"],
                    "allow_rsi": self.job.get("allow_rsi", False),
                    "inputs": self.job["inputs"], "output": str(self.output.resolve()),
                    "rsi": str(self.rsi.resolve())})}

    def _image_hashes(self, handles: dict) -> dict:
        hashes = {}
        for handle, item in handles.items():
            images = item["parsed"].get("images")
            if not isinstance(images, list) or len(images) > 250:
                raise CheckpointRejected("来源图件列表数量无效")
            entries = {}
            for image in images:
                if not isinstance(image, dict) or not isinstance(image.get("image_id"), str):
                    raise CheckpointRejected("来源图件记录无效")
                identifier = image["image_id"]
                if identifier in entries:
                    raise CheckpointRejected("来源图件 ID 重复")
                data = image.get("data")
                if not isinstance(data, str) or not data.startswith("image/png;base64,"):
                    raise CheckpointRejected("恢复图件只接受包内 PNG data")
                try:
                    raw = base64.b64decode(data.partition(",")[2], validate=True)
                    if not 1 <= len(raw) <= MAX_IMAGE_BYTES:
                        raise ValueError("图件大小超限")
                    from PIL import Image
                    with Image.open(io.BytesIO(raw)) as opened:
                        if opened.format != "PNG" or list(opened.size) != [image.get("width"), image.get("height")]:
                            raise ValueError("图件尺寸不匹配")
                        opened.verify()
                except (ValueError, OSError) as error:
                    raise CheckpointRejected("恢复图件内容或尺寸无效") from error
                if type(image.get("page")) is not int or not 1 <= image["page"] <= item["parsed"]["page_count"]:
                    raise CheckpointRejected("恢复图件页码无效")
                entries[identifier] = {"data_sha256": hashlib.sha256(raw).hexdigest(),
                                       "record_sha256": _digest(image)}
            hashes[handle] = entries
        return hashes

    def _extra_state(self) -> dict:
        return {"claim_evidence": copy.deepcopy(self.claim_evidence)}

    def _restore_extra_state(self, value: dict):
        _object(value, {"claim_evidence"}, "checkpoint 额外状态格式未知")
        if type(value["claim_evidence"]) is not dict:
            raise CheckpointRejected("claim_evidence 状态必须是对象")
        self.claim_evidence = copy.deepcopy(value["claim_evidence"])

    def checkpoint_validate_extra_handle(self, handle: str, item: dict) -> bool:
        """子类为额外scope重核真实证书、来源、anchor和句柄公式；默认拒绝。"""
        return False

    def _state(self) -> dict:
        handles = {key: {"document_id": item["row"]["document_id"],
                         "parsed": item["parsed"], "read": item["read"]}
                   for key, item in self.handles.items()}
        state = {"handles": handles, "decks": {key: str(value) for key, value in self.decks.items()},
                 "deck_records": self.deck_records, "validations": self.validations,
                 "catalogs": self.catalogs, "extra": self._extra_state(),
                 "image_hashes": self._image_hashes(handles)}
        _json_value(state)
        return state

    def _deck_path(self, identifier: str, value: str) -> Path:
        if not isinstance(identifier, str) or not _DECK.fullmatch(identifier) or not isinstance(value, str):
            raise CheckpointRejected("checkpoint deck ID 或路径无效")
        expected = private_path(self.output / identifier / "presentation.pptx")
        actual = private_path(Path(value))
        if actual != expected or not actual.is_relative_to(self.output.resolve()):
            raise CheckpointRejected("checkpoint deck 路径不在当前 job 输出范围")
        return actual

    def _validate_request_plan(self, plan: dict):
        from scenarios.research_ppt.revision import merge_slide_updates
        if not isinstance(plan, dict) or not isinstance(plan.get("slides"), list) or not plan["slides"]:
            raise CheckpointRejected("checkpoint 缺少完整请求计划")
        if len(plan["slides"]) != self.job["slides"]:
            raise CheckpointRejected("checkpoint 计划页数不符合 job")
        merge_slide_updates(plan, [{"page": 1, "changes": {"title": plan["slides"][0]["title"]}}])
        for slide in plan["slides"]:
            for citation in slide["sources"]:
                if not isinstance(citation, dict) or set(citation) != {"source_id", "page"}:
                    raise CheckpointRejected("恢复计划来源不使用受限句柄")
                item = self.source(citation["source_id"])
                if not item["read"] or type(citation["page"]) is not int or not 1 <= citation["page"] <= item["parsed"]["page_count"]:
                    raise CheckpointRejected("恢复计划来源未读取或页码无效")
            if slide.get("image") is not None:
                image = slide["image"]
                if not isinstance(image, dict) or set(image) != {"source_id", "image_id"}:
                    raise CheckpointRejected("恢复请求计划不能以路径代替图件句柄")
                item = self.source(image["source_id"])
                if not item["read"] or sum(row["image_id"] == image["image_id"] for row in item["parsed"]["images"]) != 1:
                    raise CheckpointRejected("恢复计划引用图件不存在")

    def _validation_check(self, identifier: str, report: dict):
        if (not isinstance(identifier, str) or not isinstance(report, dict) or
                identifier != report.get("validation_id") or report.get("deck_id") not in self.decks or
                type(report.get("passed")) is not bool or report.get("input_version") != self.input_version or
                report.get("file_sha256") != self.deck_records[report["deck_id"]]["sha256"]):
            raise CheckpointRejected("checkpoint 核验绑定格式或版本无效")
        report_path = report.get("report_path")
        if not isinstance(report_path, str):
            raise CheckpointRejected("checkpoint 核验缺少真实 report_path")
        path = private_path(Path(report_path))
        # New deliveries persist inside their own job, including member mounts.
        # Keep the historical CLI directory readable, never another job's root.
        validation_roots = {(self.job_path.parent / "validation").resolve(),
                            (ROOT / ".local/research-ppt/validation").resolve()}
        if path.name != "report.json" or path.parent.parent not in validation_roots:
            raise CheckpointRejected("checkpoint 核验报告路径越界")
        if report.get("pptx_path") != str(self.decks[report["deck_id"]]):
            raise CheckpointRejected("checkpoint 核验PPT路径与当前deck不一致")
        artifacts = report.get("artifacts")
        if not isinstance(artifacts, list) or (report["passed"] and not artifacts):
            raise CheckpointRejected("checkpoint 缺少真实预览清单")
        for artifact in artifacts:
            if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str) or not isinstance(artifact.get("sha256"), str) or not _SHA.fullmatch(artifact["sha256"]):
                raise CheckpointRejected("checkpoint 预览清单格式无效")
            artifact_path = private_path(Path(artifact["path"]))
            if artifact_path.parent != path.parent or artifact.get("kind") not in {"pdf", "preview"}:
                raise CheckpointRejected("checkpoint 预览路径或类型越界")
        if report["passed"]:
            pdfs = [row for row in artifacts if row.get("kind") == "pdf"]
            previews = [row for row in artifacts if row.get("kind") == "preview"]
            if len(pdfs) != 1 or sorted(row.get("page", -1) for row in previews) != list(range(1, self.job["slides"] + 1)):
                raise CheckpointRejected("checkpoint 已通过核验缺少每页PNG或唯一PDF")
        # Missing/replaced previews revoke validation; they do not invalidate the deck.
        try:
            actual_report = _read_json(path)
            expected_report = copy.deepcopy(report)
            for key in ("deck_id", "input_version", "file_sha256"):
                expected_report.pop(key, None)
            expected_report["validation_id"] = path.parent.name
            if actual_report != expected_report:
                return "validation_report_missing_or_changed"
            self.checked_validation_artifacts(report)
        except (ValueError, OSError):
            return "preview_artifact_missing_or_changed"
        return None

    def _install_state(self, state: dict, *, discard_changed_previews: bool):
        _object(state, {"handles", "decks", "deck_records", "validations", "catalogs", "extra", "image_hashes"},
                "checkpoint 状态格式未知")
        if any(type(state[name]) is not dict for name in state):
            raise CheckpointRejected("checkpoint 状态字段必须为对象")
        rows = {row["document_id"]: row for row in self.job["inputs"]}
        self._restore_extra_state(state["extra"])
        self.handles = {}
        per_document = {}
        for handle, value in state["handles"].items():
            _object(value, {"document_id", "parsed", "read"}, "checkpoint 来源句柄格式未知")
            if not _SOURCE.fullmatch(handle) or value["document_id"] not in rows or type(value["read"]) is not bool:
                raise CheckpointRejected("checkpoint 来源句柄未获当前job授权")
            parsed = value["parsed"]
            _object(parsed, {"format", "page_count", "text_chars", "pages", "images", "warnings"}, "checkpoint 来源解析格式未知")
            if parsed["format"] not in {"pdf", "pptx"} or type(parsed["page_count"]) is not int or not 1 <= parsed["page_count"] <= 200:
                raise CheckpointRejected("checkpoint 来源格式或页数无效")
            if (not isinstance(parsed["pages"], list) or len(parsed["pages"]) != parsed["page_count"] or
                    type(parsed["text_chars"]) is not int or parsed["text_chars"] < 0 or
                    not isinstance(parsed["warnings"], list) or any(not isinstance(row, str) for row in parsed["warnings"])):
                raise CheckpointRejected("checkpoint 来源正文格式无效")
            for number, page in enumerate(parsed["pages"], 1):
                _object(page, {"page", "text", "truncated"}, "checkpoint 来源页结构未知")
                if page["page"] != number or not isinstance(page["text"], str) or len(page["text"]) > 30000 or type(page["truncated"]) is not bool:
                    raise CheckpointRejected("checkpoint 来源页码或正文容量无效")
            if value["document_id"] in per_document:
                item = per_document[value["document_id"]]
                if item["parsed"] != parsed or item["read"] != value["read"]:
                    raise CheckpointRejected("checkpoint 同一来源的别名状态不一致")
            else:
                item = {"row": rows[value["document_id"]], "parsed": copy.deepcopy(parsed), "read": value["read"]}
                per_document[value["document_id"]] = item
            self.handles[handle] = item
        if self._image_hashes(state["handles"]) != state["image_hashes"]:
            raise CheckpointRejected("checkpoint 图件数据摘要变化")
        self.catalogs = copy.deepcopy(state["catalogs"])
        for handle, bound in self.catalogs.items():
            _object(bound, {"document_id", "source_id", "version_sha256", "tool_code_sha256"}, "checkpoint 图件目录格式未知")
            if (handle not in self.handles or bound["source_id"] not in self.handles or
                    bound["document_id"] not in rows or bound["version_sha256"] != rows[bound["document_id"]]["version_sha256"] or
                    self.handles[handle] is not self.handles[bound["source_id"]]):
                raise CheckpointRejected("checkpoint 目录参数绑定或来源版本不一致")
            tool = self.pinned_figure_tool()
            if bound["tool_code_sha256"] != tool["code_sha256"]:
                raise CheckpointRejected("checkpoint 目录工具代码版本变化")
        for handle, item in self.handles.items():
            row = item["row"]
            expected = "source-" + hashlib.sha256((row["document_id"] + row["version_sha256"]).encode()).hexdigest()[:32]
            if handle != expected and handle not in self.catalogs:
                if self.checkpoint_validate_extra_handle(handle, item) is not True:
                    raise CheckpointRejected("checkpoint 句柄不符合来源或认证目录公式")
            if handle in self.catalogs:
                expected = "source-" + hashlib.sha256(("figure-catalog:" + row["document_id"] + row["version_sha256"] + self.catalogs[handle]["tool_code_sha256"]).encode()).hexdigest()[:32]
                if handle != expected:
                    raise CheckpointRejected("checkpoint 图件目录句柄公式不一致")
        if set(state["decks"]) != set(state["deck_records"]):
            raise CheckpointRejected("checkpoint deck 与完整记录未成对保存")
        self.decks = {identifier: self._deck_path(identifier, value) for identifier, value in state["decks"].items()}
        self.deck_records = copy.deepcopy(state["deck_records"])
        for identifier, record in self.deck_records.items():
            if (not isinstance(record, dict) or not {"sha256", "sources", "input_version"} <= set(record) or
                    set(record) - {"sha256", "sources", "input_version", "plan", "request_plan"} or
                    record["input_version"] != self.input_version or not _SHA.fullmatch(record["sha256"])):
                raise CheckpointRejected("checkpoint deck记录格式或输入版本变化")
            path = self.checked_deck(identifier)
            inspected = inspect_pptx(path)
            if inspected["slide_count"] != self.job["slides"] or not inspected["each_slide_has_editable_text"]:
                raise CheckpointRejected("checkpoint deck未保持页数和可编辑文字")
            if "plan" in record or "request_plan" in record:
                if not {"plan", "request_plan"} <= set(record):
                    raise CheckpointRejected("checkpoint 生成稿缺少完整request_plan")
                self._validate_request_plan(record["request_plan"])
                plan_path = private_path(path.parent / "plan.json")
                if _read_json(plan_path) != record["plan"]:
                    raise CheckpointRejected("checkpoint 完整渲染计划与产物目录不一致")
        self.validations = {}
        discarded = []
        for identifier, report in state["validations"].items():
            reason = self._validation_check(identifier, report)
            if reason:
                if not discard_changed_previews:
                    raise CheckpointRejected("旧预览已变化，先显式撤销核验并重新真实验收")
                discarded.append({"validation_id": identifier, "deck_id": report["deck_id"], "reason": reason})
            else:
                self.validations[identifier] = copy.deepcopy(report)
        return discarded

    def _load_checkpoint(self):
        try:
            value = _read_json(self.checkpoint_path)
            _object(value, {"format", "schema_version", "bindings", "state", "payload_sha256", "saved_at", "reason"},
                    "checkpoint envelope格式未知")
            if value["format"] != FORMAT or value["schema_version"] != SCHEMA_VERSION:
                raise CheckpointRejected("checkpoint 格式或schema版本未知")
            if value["payload_sha256"] != _digest({"bindings": value["bindings"], "state": value["state"]}):
                raise CheckpointRejected("checkpoint 内容摘要变化或破损")
            if value["bindings"] != self._bindings():
                raise CheckpointRejected("checkpoint 的job/来源/权限/代码版本已失效")
            discarded = self._install_state(value["state"], discard_changed_previews=True)
            self._guard_current_dependencies()
            self._disk_checkpoint_sha256 = _raw_hash(self.checkpoint_path)
            self.restore_status.update(restored=True, discarded_validations=discarded)
            self.record("checkpoint_restored", {"deck_count": len(self.decks),
                        "discarded_validations": discarded, "schema_version": SCHEMA_VERSION})
            if discarded:
                self.save_checkpoint("restore_discarded_changed_previews")
        except Exception as error:
            self._checkpoint_blocked = True
            try:
                self.record("checkpoint_restore_rejected", {"error_type": type(error).__name__,
                            "reason": str(error)[:800], "schema_version": SCHEMA_VERSION})
            except Exception:
                pass
            if isinstance(error, CheckpointRejected):
                raise
            raise CheckpointRejected("checkpoint 恢复守卫失败，拒绝加载历史状态") from error

    @contextmanager
    def _writer_lock(self):
        """同job多进程保存互斥；生产实验仅验证Linux。"""
        path = private_path(self.job_path.parent / ".service-checkpoint.write.lock")
        if path.parent != self.job_path.parent.resolve():
            raise CheckpointRejected("checkpoint lock路径越界")
        with path.open("a+b") as stream:
            if os.name == "nt":
                import msvcrt
                if stream.tell() == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as error:
                    raise CheckpointRejected("另一会话正在写checkpoint，拒绝覆盖") from error
                try:
                    yield
                finally:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    raise CheckpointRejected("另一会话正在写checkpoint，拒绝覆盖") from error
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def save_checkpoint(self, reason="explicit") -> dict:
        with self._lock:
            if self._transaction_depth:
                self._save_pending = True
                return {"saved": False, "pending_outer_transaction": True}
            with self._writer_lock():
                return self._save_checkpoint_locked(reason)

    def _save_checkpoint_locked(self, reason="explicit") -> dict:
        with self._lock:
            if self._checkpoint_blocked:
                raise CheckpointRejected("checkpoint 已拒绝写入，需重新核对当前job和文件版本")
            if self._transaction_depth:
                self._save_pending = True
                return {"saved": False, "pending_outer_transaction": True}
            try:
                self._guard_current_dependencies()
                state = self._state()
                # Reuse the same strict checker before persisting. It preserves shared aliases.
                self._install_state(state, discard_changed_previews=False)
                current = _raw_hash(self.checkpoint_path) if self.checkpoint_path.exists() else None
                if current != self._disk_checkpoint_sha256:
                    raise CheckpointRejected("checkpoint 已被另一会话更新，拒绝过期实例覆盖")
                payload = {"bindings": self._bindings(), "state": state}
                value = {"format": FORMAT, "schema_version": SCHEMA_VERSION, **payload,
                         "payload_sha256": _digest(payload),
                         "saved_at": datetime.now(timezone.utc).isoformat(), "reason": str(reason)[:150]}
                raw = (_canonical(value) + "\n").encode("utf-8")
                if len(raw) > MAX_CHECKPOINT_BYTES:
                    raise CheckpointRejected("checkpoint 超过安全大小，未覆盖旧状态")
                self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temporary = tempfile.mkstemp(prefix=".checkpoint-", suffix=".tmp", dir=self.checkpoint_path.parent)
                temporary_path = Path(temporary)
                try:
                    os.chmod(temporary_path, 0o600)
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                    self._guard_current_dependencies()
                    # Prevent stale overwrite after snapshot work; single-process MCP also uses RLock.
                    final_current = _raw_hash(self.checkpoint_path) if self.checkpoint_path.exists() else None
                    if final_current != self._disk_checkpoint_sha256:
                        raise CheckpointRejected("checkpoint 写入期间被另一会话更新，拒绝覆盖")
                    os.replace(temporary_path, self.checkpoint_path)
                    if os.name != "nt":
                        directory = os.open(self.checkpoint_path.parent, os.O_RDONLY | os.O_DIRECTORY)
                        try:
                            os.fsync(directory)
                        finally:
                            os.close(directory)
                finally:
                    if temporary_path.exists():
                        temporary_path.unlink()
                self._disk_checkpoint_sha256 = _raw_hash(self.checkpoint_path)
                self._save_pending = False
                return {"saved": True, "checkpoint_sha256": self._disk_checkpoint_sha256,
                        "schema_version": SCHEMA_VERSION, "deck_count": len(self.decks)}
            except Exception as error:
                self._checkpoint_blocked = True
                try:
                    self.record("checkpoint_save_rejected", {"reason": str(error)[:800],
                                "error_type": type(error).__name__, "operation": str(reason)[:150]})
                except Exception:
                    pass
                if isinstance(error, CheckpointRejected):
                    raise
                raise CheckpointRejected("checkpoint 一致性检查或原子写入失败，旧文件保留") from error

    def list_restorable_decks(self) -> dict:
        self._guard_current_dependencies()
        decks = []
        for identifier, record in self.deck_records.items():
            self.checked_deck(identifier)
            reports = [row for row in self.validations.values() if row["deck_id"] == identifier and row["passed"]]
            for report in reports:
                self.checked_validation_artifacts(report)
            decks.append({"deck_id": identifier, "file_sha256": record["sha256"],
                          "input_version": self.input_version, "slides": self.job["slides"],
                          "title": record.get("request_plan", {}).get("title"),
                          "has_request_plan": "request_plan" in record,
                          "validation_id": reports[-1]["validation_id"] if reports else None,
                          "validated": bool(reports), "scientific_quality": "not_reviewed"})
        return {"decks": decks, "restore": copy.deepcopy(self.restore_status),
                "scope": "same_job_version_bound_restore_only; scientific_quality_not_certified"}


def _persisted_operation(name):
    method = getattr(PPTService, name)

    @wraps(method)
    def execute(self: CheckpointPPTService, *args, **kwargs):
        with self._lock:
            if self._checkpoint_blocked:
                raise CheckpointRejected("checkpoint 已拒绝写入，停止旧实例操作")
            self._guard_current_dependencies()
            self._transaction_depth += 1
            error = None
            try:
                result = method(self, *args, **kwargs)
                self._save_pending = True
                return result
            except Exception as failure:
                error = failure
                try:
                    self.record("checkpoint_operation_failed", {"operation": name,
                                "error_type": type(failure).__name__, "reason": str(failure)[:800]})
                except Exception:
                    pass
                raise
            finally:
                self._transaction_depth -= 1
                if self._transaction_depth == 0:
                    # Failed nested revise cleans candidate deck state first. Keep files and
                    # feedback as negative evidence; save only the consistent resulting state.
                    try:
                        self.save_checkpoint(name + (":failed_consistent_state" if error else ":success"))
                    except Exception:
                        if error is None:
                            raise
    return execute


for _name in ("pin_source", "read_source", "read_page", "extract_figure", "pin_figure_catalog",
              "read_generated_catalog", "render_deck", "revise_deck", "validate_deck",
              "restyle_deck", "build_delivery", "propose_guard", "propose_layout_policy"):
    setattr(CheckpointPPTService, _name, _persisted_operation(_name))
