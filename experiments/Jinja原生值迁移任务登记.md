# Jinja2 原生值兼容性修复：任务登记

> 2026-09-24。在该任务的补丁模型调用前固定范围和验收；属于开发阶段任务，不作为未见仓库的统计样本。

- 来源：公开 `pallets/jinja` 标签 `2.10.1`，提交 `c4c4088945a2c12535f539be7f5453b9ca94666c`。先在被忽略的复制仓库中应用已核验的 `collections.abc` 修复；随后处理 Python 3.12 下 `NativeEnvironment` 的行为差异。
- 允许修改：仅 `jinja2/nativetypes.py`，不修改测试文件或原仓库；模型最多提议 2 个精确文本替换，结构层核对原文哈希、唯一匹配、语法后在新复制仓库跑测试。
- 症状：`tests/test_nativetypes.py::TestNativeEnvironment::test_undefined_native_return` 期望得到 `Undefined` 对象，现有 `native_concat` 进入 `literal_eval` 后抛 `UndefinedError`。另一个 traceback 格式测试 `test_runtime_error` 是独立的旧版 Python 3.12 兼容问题，不纳入本次修复。
- 主验收：`/Users/apple/Desktop/SSS/.local/venvs/jinja-heldout/bin/python -m pytest -q tests -k 'not test_runtime_error' --tb=short -p no:warnings` 在新复制仓库退出 0；原版基线预计留下上述原生值失败。还要检查补丁差异只触及允许文件，且原始公开仓库 Git 状态干净。
- 记录：模型调用数、输入/缓存/输出 token、失败与重试、测试数量、复制仓库和人类审查。若模型答复无法通过边界或测试则标记失败，不因为目标已知而手工改正后算成功。

## 实施前修订

检查到本机没有 Docker/Podman，可用的目录复制不是执行不受信任模型补丁的安全沙箱。因此本次先用**可静态证明位置与绑定的候选修复规则**实现上述目标：运行时检查 `native_concat` 的单值分支及 `literal_eval(out)` 形态，只在形态精确匹配时插入“单个非文本值直接返回”的有界规则；若不匹配则停止在语义缺口，不让模型生成任意代码后自动运行测试。模型请求数预计为 0，此改动在模型调用前登记。后续通用补丁生成必须先有可信执行隔离和独立评测。

## 运行结果

- 记录：`.local/native-value-runs/20260924T134055Z-baf8d3/`，使用 `.venv312` Python 3.12.14 和专用 `jinja-heldout` 测试环境；源码输入是先前已完成 ABC 迁移的 Jinja2 复制仓库。
- 旧行为：**1 failed、534 passed、3 skipped、1 deselected**；唯一未通过项是登记的 `test_undefined_native_return`。
- 结构改动：仅 `jinja2/nativetypes.py` 的 `literal_eval(out)` 前新增三行，在单值且结果不是 `text_type` 时返回原对象。AST 形态、导入、哈希和语法均由结构节点核验；原输入源码未改。
- 改动后：**535 passed、3 skipped、1 deselected**，退出码 0；被排除的 `test_runtime_error` 仍是独立的旧 traceback 预期问题，不能宣称旧版全套通过。
- 模型请求、输入/输出 token 均为 **0**。这表明此具体重复规则无需模型；还没有证明图比普通确定性脚本有额外成本优势，也不能外推到任意代码重构。

复核运行 `.local/native-value-runs/20260924T134403Z-e5440b/` 保存了两个复制仓库的路径与前后测试。再对修复后的复制仓库运行**未排除项目的完整旧测试**，得到 **1 failed、535 passed、3 skipped**；唯一剩余失败是登记时已知的 traceback 正则预期，原始输出在同一运行目录的 `full-suite-result.json`。因此主验收通过，但旧版全套仍不通过。
