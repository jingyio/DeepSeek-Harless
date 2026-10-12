# 科研报告 benchmark 与最新 main 的合并检查

## 范围与版本

2026-10-12，按用户要求将最新 `main` 合入 `feature/data-analysis-agent`，并提交指向 `main` 的 PR。本次验证代码兼容性，不重新运行付费模型实验，也不修改历史报告结论。

- 原数据分析分支：`92042f4ef67fef621bef4c33e1456b029ae23c72`。
- 本次合入的 main：`bc1ecd5ba17fa4f12b2d2eaa780d72b5076b79cc`。
- 共同基座：`2368235f274329be6227a8393b850633cb943da4`。
- 合并提交：`303a69b00823ed216bdca1836c1ae0ff2583430a`。
- 合并源码树：`a9db38dff2ba07e044f14ee1e4f7cf045a22c447`，与此前隔离测试使用的三方合并树完全一致。

两侧分别改动 34、111 个文件，没有重叠文件，Git 三方合并及正式 merge 均无冲突。相对最新 main，场景变更仍限于四个 benchmark 及其文档，不修改公共内核。随后补充本记录与场景交接，属于文档变动，不重复执行已通过且源码未变的检查。

## 接口核查

DSH 仍固定为 `0.1.5-rc.3`，锁文件变化仅为项目名称。benchmark 使用的 `create_harness`、轨迹投影、在线运行实现未改变。公共 `prepare_scenario` 增加两个返回字段，保留原字段；benchmark 从公共预算模块导入的 `response_usage` 未变，自有 `BudgetGate` 不依赖 main 新增的会话预算选择接口。

四目录的实际依赖为 `v3.1 → v3 → v2 → v1`，不能删除旧目录后声称 v3.1 可独立运行。新的 Web 入口尚未注册科研报告场景；合并源码不会自动使 Web 支持上传科研数据并生成报告。

## 已完成的本地检查

环境为 Windows 11、Python 3.13.5、Node 24.16.0。隔离快照的 307 个非 PDF 文件与合并树逐项核对哈希；22 份历史 PDF 在原仓库核验。检查后源码未变化，原始结果、失败和科学评审未修改。

| 检查 | 结果与范围 |
|---|---|
| benchmark Python | 112 / 112 通过，涵盖 v1 工具/runner、v2、v3、审计器和 v3.1 准备器 |
| benchmark Node 插件 | 66 / 66 通过，v1/v2/v3 分别 10/32/24 |
| 公共 `npm test` 的 Python 回归 | 145 通过、1 因 Windows 符号链接权限失败 |
| 公共 Node 七个测试文件 | 45 / 45 通过；因 Python 阶段中断而单独补跑 |
| `npm run smoke` | 18 题、83 对象通过；真实 Harness SDK 初始化，无付费模型请求 |
| v3.1 统计诊断 | 6 场景、18 次实际本地统计工具执行、9 次 fixture 续接通过 |
| 科研报告 MCP | 真实 stdio MCP 串行执行 14 个工具，从输入检查到交付生成 1 页诊断 PDF；数值、文件、版面与交付技术检查通过 |

公共 Python 唯一失败为 `tests/test_dsh_task_identity.py:119` 的 `test_manifest_symlink_cannot_define_task_identity`：创建符号链接遇到 `WinError 1314`，当前账户缺少权限，尚未进入功能断言。未修改或跳过测试，不能写成公共 `npm test` 全部通过。

报告 MCP 诊断使用测试夹具给出统计方案、图形方案和正文，不经过 LLM 决策或 Harness Agent 循环；它验证真实工具连接与计算，不能作为新的 Agent 质量或费用实验。首次诊断因临时脚本未向子进程传递 MCP 依赖路径而失败；只修正临时诊断脚本的环境传递，第二次 14 工具全部通过，仓库实现未改。统计续接诊断中的库也是 fixture，不是新增学习证据。

单元测试复现命令沿用各 benchmark README。审计器命令为 `python -m unittest discover -s benchmarks/research_report_agent_v3/review -p test_auditor.py -v`；公共 Node 七个文件以当前 `scripts/project.mjs` 的 `test` 分支为准。私有诊断日志和完整命令留在 `.local/merge-check-20261012/`，不进入 Git。

## 尚未完成与历史结果边界

用户 Linux 服务器在 SSH 握手阶段返回 `Error reading SSH protocol banner`，原生 SSH 也被关闭连接，因此本轮该服务器的合并后验收未完成。Windows 本地结果不等于 Linux 已通过；需恢复连接后补跑公共与 benchmark 检查。之前在原底座完成的 Linux 实验保持原版本记录。

本次 API 请求及模型费用为零。已发表的 143→62 次请求、0.72016560→0.61217400 元等结果仍属于 [v3.1 原实验](research-report-agent-v31-20261010.md)，不能追改为“最新 main 上重新完成的真实实验”。
