# 仓库修改与非侵入式发布审计

审计日期：2026-10-10。目标分支为 `feature/data-analysis-agent`，原基座为 `2368235f274329be6227a8393b850633cb943da4`。用户授权提交 benchmark、实验综合报告及各次运行 PDF。

## 修改范围

发布前既有跟踪文件的 `git diff HEAD` 为空。本次提交仅新增以下内容：

| 路径 | 内容与必要性 |
|---|---|
| `benchmarks/research_report_agent_v1/` | 统计、绘图、预算代理、初版报告、轨迹编译与测试；含历史汇总 |
| `benchmarks/research_report_agent_v2/` | 可变报告大纲、页面布局、检查与共享工具 |
| `benchmarks/research_report_agent_v3/` | 三处 LLM 语义关口、14 个工具、局部插件、审计器及对照运行器 |
| `benchmarks/research_report_agent_v31/` | 统计续接公开授权、准备/运行/诊断入口、发布审计与本轮结果 |
| `docs/experiments/research-report-agent-v31-20261010.md` | 匿名化实验配置、结果、费用、失败及证据限制 |
| `docs/handoffs/research-report-agent.md` | 本场景交接与复现入口 |

四个 benchmark 的运行依赖是 **v3.1 → v3 → v2 → v1**，v3 也直接复用 v1 预算代理和生成器。只提交 v3.1 会缺少实现。未改动 `src/`、`scripts/`、`config/`、已有 `tests/`、原有 benchmark、`package.json` 或任何依赖锁；没有复制或修改上游 DSH 核心。

## 如何接入且不修改内核

`v3/runner.py` 使用已有 `create_harness` 启动真实 DSH，在公开 profile 中插入本 benchmark 的插件，并配置 stdio MCP。`v3/motif_plugin.ts` / `.mjs` 只注册 `agent/created`、`tools/result`、`llm/stream` 事件。

DSH 即将向模型请求下一步时，插件依据已认证边、实际工具凭证、当前文件/工具版本和显式授权决定是否提供工具命令；DSH 随后仍使用原有工具派发机制执行 MCP。条件不成立时调用原模型路径。LLM 仍负责统计方案、依据结果选图与组织报告、撰写正文。这是新增 benchmark 内的窄范围插件，不是给通用 Motif 核心原生增加任意写操作，也不是强制全流程 DAG。

两组通过相同配置关闭模型重试、压缩与工具结果裁剪；对照称为“相同配置的 DSH 基线”。非侵入指未修改核心源码，不表示没有配置插件或没有改变本次实验的请求调度。

## 原实验快照与发布文档

逐项比较原运行冻结的 22 个文件与 104 个共享依赖哈希：运行源码、工具契约、配置与插件字节保持一致；只有以下公开文档发生发布整理，原实验证据未追改：

- v1 `RESULTS.json`：去除 25 处私有仓库绝对路径前缀，补充说明；运行 ID、数值、失败记录、产物哈希保持原样。原文件保存在忽略的 `.local/`。
- v3.1 `README.md`：替换私人服务器激活命令，补充通用环境要求和报告索引。

完整文件哈希及例外见 [publication-source-audit.json](publication-source-audit.json)。文档例外不伪称与旧冻结文件字节相同；真实模型结果也没有重新运行或被替换。v1/v2/v3 的 TypeScript 源与对应 `.mjs` 文件分别完全相同。

冻结源码中 9 个文件保留了历史 CRLF 或混合换行。各 benchmark 内新增局部 `.gitattributes`，只对这些文件禁用自动换行转换，并将 v3.1 PDF 标记为二进制；否则 Git 的通用 LF 规范化会使已记录的实验源码哈希失效。未改动这些源码或仓库根属性。发布前同时核验暂存区文件字节，不能只检验工作区。4 个历史源码的文件末尾空行按原样保留；差异检查以 `git -c core.whitespace=-blank-at-eof,cr-at-eol diff --cached --check` 保留这项历史空白并正确识别 CRLF。

## 报告、隐私与体积

[公开结果](results/20261010/README.md)包含 22 份 PDF：19 个本轮原件（16 正式、2 训练、1 认证）和 3 个汇总报告。19 个原件共 47 页；汇总报告分别为 20、4、10 页，全部原样复制。每份 PDF 的 SHA-256、页数和评审状态都记录在 [清单](results/20261010/artifact-manifest.json)。不合格结果保留，不截断四页报告。

仅发布用户要求的报告及脱敏摘要；原始 HTTP/SSE、模型和工具日志、凭据、完整私有环境、缓存、依赖目录及大 ZIP 均不进入 Git。公开 PDF 文本/元数据和源文件经过凭据及私有路径扫描。结果目录约 15.28 MiB，无单个文件接近 GitHub 100 MiB 限制。

## 本次验证

本机 Windows，Python 3.13.5、Node 24.16.0。`npm ci --no-audit --no-fund` 使用原锁文件安装忽略目录中的依赖，不改锁。初次插件测试因缺依赖失败，安装后解除，无代码修复。

| 检查 | 结果 |
|---|---|
| v1 Python 工具/报告测试 + runner 测试 | 16 + 6 通过 |
| v2 Python 测试 | 48 通过 |
| v3 Python 测试 + 审计器测试 | 32 + 7 通过 |
| v3.1 Python 准备器测试 | 3 通过 |
| v1 / v2 / v3 Node 插件测试 | 10 / 32 / 24 通过 |
| v3.1 统计诊断 | 6 个场景、18 次真实本地统计工具执行、9 次 fixture 续接通过 |
| 矩阵预览、源码和 JSON 解析 | 通过，无 API 调用 |
| 公共 `npm run setup` | 成功，依赖仅写入忽略的 `.venv-sss` |
| 公共 `npm test` 的 Python 回归 | 135 通过、1 因 Windows 符号链接权限失败 |
| 单独执行公共入口的同四个 Node 测试文件 | 29 / 29 通过 |

benchmark 合计 **112 项 Python、66 项 Node 测试通过**。诊断中的库是测试 fixture，未经过真实 MCP 传输、未调用 LLM、没有生成 learned library，不计入论文效果。诊断命令：

```sh
python benchmarks/research_report_agent_v31/diagnose_statistics_chain.py --output .local/v31-publish-diagnostic
```

公共 `npm test` 未全绿：原有 `tests/test_dsh_task_identity.py` 的 `test_manifest_symlink_cannot_define_task_identity` 在创建符号链接时遇到 `WinError 1314`（当前 Windows 账户没有该特权），未进入功能断言。未修改或跳过该测试；入口中断后单独补跑其四个 Node 测试文件。这个环境限制与新增 benchmark 的 112/66 通过分别报告。

各版本单元测试命令在对应 README；审计器用 `python -m unittest discover -s benchmarks/research_report_agent_v3/review -p test_auditor.py -v`。原 Linux 真实 LLM/DSH/MCP 的 19 次运行与本次 Windows 离线复核分开记账。本次没有新增付费 API 调用，Windows 数值包版本与 Linux 冻结环境存在差别，不能宣称精确重现实验输出。

科学文字合格率为 7/8 与 6/8，公开发布不表示这些报告已获得科研正确性认证。完整限制见 [实验记录](../../docs/experiments/research-report-agent-v31-20261010.md)。
