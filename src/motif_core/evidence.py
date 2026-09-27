"""绑定证据为权威索引；普通工具名仅保留给现有上下文消费者。"""
import json
from copy import deepcopy
from .observation import is_error_observation


class BoundEvidence(dict):
    def __init__(self):
        super().__init__()
        self.records = {}

    @staticmethod
    def key(tool, binding):
        return tool + "::" + json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def record(self, tool, binding, value, *, version=None):
        if is_error_observation(value):
            return False
        key = self.key(tool, binding)
        self.records[key] = {"type": tool, "binding": deepcopy(binding),
                             "value": value, "version": version}
        dict.__setitem__(self, tool, value)
        dict.__setitem__(self, key, value)
        return True

    def lookup(self, tool, binding, *, version=None):
        row = self.records.get(self.key(tool, binding))
        if row is not None and version is not None and row.get("version") != version:
            return None
        return row

    def __setitem__(self, key, value):
        # MotifExecutor 已写入 tool::{canonical arguments}；只接受显式绑定键。
        if "::" in key:
            tool, raw = key.split("::", 1)
            try:
                binding = json.loads(raw)
            except ValueError:
                binding = None
            if isinstance(binding, dict):
                self.record(tool, binding, value)
                return
        dict.__setitem__(self, key, value)

    def update(self, other=(), **kwargs):
        for key, value in dict(other, **kwargs).items():
            self[key] = value
