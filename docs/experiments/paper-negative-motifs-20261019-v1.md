# Negative Motif：先提示、后局部早停（2026-10-19）

独立分支 `codex/paper-negative-motifs`，基于 `44a1d36`。用户要求将正确模式与错误模式同时纳入编译，先通过 prompt 引导，再阻止无效重试。原始证据和配置位于私有 `.local/script-negative-20261019-v1/`；未推送、未 PR、未部署，旧实验和生产库不改。

## 假设与范围

失败轨迹可以编译为有条件的负面经验。历史模式用于提示；当前任务已复现失败、模型实际收到提示、参数与权威状态未变时，才允许局部早停。若历史失败直接封禁新任务、提示没有进入实际请求、或变更后仍错误阻止执行，则本实现不通过。

这是第一版最小负面编译与在线门控。它不修复报告数据、不判断科研事实、不替代模型的最终语义答复；停止失败工具也不等于取消其已经消耗的模型请求。原任务的合格质量要求仍保留。

## 实现及学习证据

- `script_negative_compiler.py` 与 `learn-negative-motifs.py` 从已结束的真实 MCP 轨迹抽取结构化 validation_error，自动学习工具/失败码及参数与结果之间共同的版本回显。规则不保存历史论文正文、参数值或输出。至少两条不同执行证据；重复同一 call-id 不算新证据。
- 有当前 schema 的非失败对照和共同版本槽位时，编译为 `warn_then_exact_version_block`；其他候选仅提示。沿用已有 `motif_core.offline.failure_evolution` 的“失败是候选、需对照、当前绑定需核验”边界，但未将旧的 active_guard 注册表冒称接入新路径。
- `script_negative_runtime.ts` 经已有 `observation` 解析真实 MCP canonical value，先记录当前失败，再通过原 system prompt 提示；只有 notice 出现在实际不可变模型请求中才启用门控。当前唯一状态文件哈希、源文件、用户目标与工具 schema 变化释放门控。工具主体通过原生 tools.guard 拦截；其他工具继续可用，没有另造 Agent 循环。
- 正面 Script Motif 与负面库可以同时装载，工具数量仍为 30；未换模型、裁剪上下文或调整 embedding。当前负面编译仍需显式调用，没有接成生产自动学习服务。

学习来源是上一轮 RMSNorm 失败任务 `88ab59dbde12403e93d9ef15201bbf8a / 2b6a86b825fb4720987b007ce9e287ac`，另用 `6c1ea66685ed4964a8f971b7e69b1fde / 293a4e541e204974a45dc35e4fb89535`、`5e0c1e9ae2cf4b03a687f3f5b1a72c46 / 516c1ec39eea4abd90f047b542b37eef` 的结构化定稿成功作对照。它们的模型费用已在此前账本，不重复计。结构成功不等于报告事实合格。

生成 5 类模式：`renderer_input_duplicate_source_ids`、`renderer_input_invalid_status_priority`、`paper_audit_confirmed_without_source`、`paper_audit_duplicate_keys`、`paper_audit_batch_limit`；最后一种没有共同版本回显，仅提示。代码没有为这些名称编写专用 if 分支。4 类具有版本槽位和非失败对照。负面失败仍主要来自同一篇论文/同一任务，未证明跨任务失败因果或泛化。

对原失败轨迹重数：这些模式共 35 次显式失败，但仅 **3 次为同工具、同完整参数的原样重试**（32 个不同绑定）。这是历史机会，不是实际跳过。多数失败发生在草稿已改变之后；完整文件哈希门控不能阻止“改无关 notes 后继续失败”。因此不能声称这版负面早停能消除此前的 181 次报告请求差额。

## 配置、诊断与真实运行

本地真实模型 `deepseek-flash / reasoning_effort=off`、原 30 工具及顺序、单次输出上限 8,192；费用和请求无硬上限，沿用累计账本。局部恢复每项 180 秒看门狗，超时走取消而不伪造成功。三臂使用同一份真实失败草稿、同一 RMSNorm 源包，只在私有新任务副本中替换任务身份，来源哈希须完全一致。不修改原稿、旧草稿或认证库。

这些是**训练状态的局部恢复诊断**，不是新论文、独立留出、完整任务或净降本对照。目标是检查提示/门控接线及失败恢复，不以强制模型重复错误制造收益；真实提示明确要求避免无变化重试。

启动首次缺少 code scratch 目录，三组在模型提交前退出：run `eb5a640a89434b06b4fcd7a00107fdb7`、`bd91da78602743b194ebcff2609a3851`、`e3b830ff11b544169fc416a1442cfd70`，无 ledger 请求。修复自有目录初始化后重试，原日志保留。

重试三臂 Baseline/Prompt/Enforce 分别为 run `ff4716904fdf40bba11379f982a351c4` / `d14eb32e9a144d21986797194f819e93` / `faa531311c604add9bc6c7a64ef30e61`；各在 3/3/4 个请求后 HTTP 502 失败，尚未触发目标负面模式，不能比较费用效果。

随后单项协议探针显式先尝试定稿，以核对已有失败的接线。首次 run 的模型确实得到 duplicate_source_ids，但新模块漏解析 canonical MCP 包装，0 提示/拦截。模型不重复定稿，却继续多次读取/其他取证，最终导出阻塞说明；不能算结构化审计交付成功，也不能将其行为归为负面 Motif 效果。修复为复用 observation，并补真实包装回归；原 18 请求失败接线结果保留。

## 最终协议结果与费用

修复后的协议探针 run `30660c1bf49a43e5879b72836bdc0365 / 7ba18332b8a34b3595af8f28e4070593`：实际 finalize 返回 duplicate_source_ids，Runtime 成功记录当前失败、唯一草稿哈希绑定，并在下一次原生模型请求中确认 notice 存在（各 1 次）。模型没有原样重复定稿，因此 **真实早停 0 次**；随后仍做读取和源码检查，第 14 次请求流失败，没有合格恢复交付。不能从“不重试”推断提示的因果效果，修复前模型也没有重试。

| 局部诊断 | 请求 | 输入 / KV 命中 / 未命中 | 输出 | 保守估费 USD | 状态 |
|---|---:|---:|---:|---:|---|
| Baseline | 3 | 21,601 / 20,352 / 1,249 | 172 | 0.025304712 | HTTP 502，1 usage 未知 |
| Prompt | 3 | 21,603 / 20,352 / 1,251 | 183 | 0.025330812 | HTTP 502，1 usage 未知 |
| Enforce | 4 | 32,980 / 31,488 / 1,492 | 366 | 0.026428728 | HTTP 502，1 usage 未知 |
| 协议探针 v1（包装解析错误） | 18 | 237,074 / 231,936 / 5,138 | 4,669 | 0.008535816 | 原生完成，但仅导出阻塞说明，负面机制未生效 |
| 协议探针 v2（修复后） | 14 | 211,683 / 202,624 / 9,059 | 1,468 | 0.041175444 | 提示进入请求；流失败，1 usage 未知 |

五项任务时长分别为 109.619 / 109.641 / 248.820 / 81.492 / 185.618 秒。180 秒诊断取消计时从 submit 返回开始，并非端到端硬时限；同步提交等待和收尾可能更长。这里不做延迟优劣结论。三臂的原恢复题面 hash `12e133e0f8cc2e05004a90bc83de61e20a08a9868ab702ee91daf5c51ecbdcaf`；协议探针题面 hash `5de260c69a22d1975ab20d903d19f3b01ade18c0593b868bb6440a41b656036c`。全部原始 checkpoint hash 为 `41742b571e13c6f4e6783787473b53208540b581e19f828534d92ddfd2cbdf50`，当前任务身份重绑使恢复文件哈希各异，规则不包含这些具体值。

本轮累计 **42 请求 / 保守代理估费 $0.126775512**；usage 可见估费 $0.016726812，保留 **4 个未知 usage、pending=0**，不把未知费用算零。连同前轮本地累计 **2,835 请求 / $4.714453692**，此前 1 个未结算预留继续保留，远程 V100 未核清。以上均非提供商账单。离线负面编译没有新增模型请求；正面重新认证有 CPU/HTTP 成本，安装、开发、人工成本未完整计量，不算零。

## 验证、最终版本与复现

完整测试 906 Python 通过/199 跳过、881 Node 通过/5 跳过；接入阶段无模型 smoke 通过。最后又收紧失败资格：从失败与非失败对照自动识别真正的 false outcome 标志，排除双方共有的 semantic_quality_accepted=false。返回成功但带相似错误元数据不能触发早停。此安全收紧在真实探针后完成，针对性 25 Python / 33 Node 通过；未再次付费跑完整任务，费用表不冒称最终版本效果。

原生 ToolRuntime 诊断：首次失败后只生成提示不阻断；确认 notice 进入请求后，两次同状态重试均在工具主体前拒绝，修复工具仍执行。缺失/歧义文件、参数/输入/目标/schema 变化、不透明错误或新反证均放行/失效。这是真实注册器上的确定性检查，不是模型请求节省。

最终负面库 `.local/script-negative-20261019-v1/library-005/library.json`：5 类，digest `4b2c4796ca1713b8267e55a38ccc17e12e70d7453e033765143b5b13befe273f`。真实探针使用前一版 `library-004`（`9fca4f08d58d81e61ea3bb1c73919c4fda1bcbee58b6b41cdd50e3a861212ccc`），中间错误版和所有失败保留；真实探针版三个关键文件的源码在私有 source-versions/library-004 中按原库锁逐字节哈希核对保存。正面库用原四个历史任务重新执行认证，不直接更新旧锁；最终正面 7 算子库 digest `692b36f562a93597db334d5eacaea93344786e3911180cd4c98e46146bbf96b8`；与负面库共同装载的私有配置为 combined-final-config.json，已通过两库加载检查。当前编译显式验证的服务实现范围为 server.py、paper_renderer.py、session_report.py、session_files.py；不是自动证明全部第三方依赖的闭包。

最短入口（需已有真实轨迹、配置与私有环境）：

```sh
node scripts/project.mjs python scripts/learn-negative-motifs.py \
  --task /private/settled-failure-task --task /private/success-contrast-task \
  --implementation-file scenarios/paper_proofreading/server.py \
  --implementation-file src/adapters/paper_renderer.py \
  --implementation-file src/adapters/session_report.py \
  --implementation-file src/adapters/session_files.py --output .local/new-negative-library
```

公共协议见 [接口](../interfaces.md#negative-motif-实验接口)。实际配置、逐决策事件、source-snapshot、库锁与全账在各 run-id 目录及私有 aggregate/final-state 中；原论文题面未改，局部探针另有独立题面，不混用分母。

## 结论与下一步

已经实现“正面复用结构 + 负面提示和局部重试门控”两种编译产物。真实模型路径确认了当前失败识别与提示接线，确定性原生注册器确认了早停；**尚未验证真实模型重复命中后的早停收益，更未证明完整任务净降本**。三臂失败、无效接线费用与额外诊断全部保留，不能挑 v1 的低费用作效果。

下一步优先把工具失败返回变为可读、可修复的可信结构状态，并学习错误相关字段的依赖范围，处理“无关改动导致新全文件版本”这一覆盖缺口；保持新版本/新证据能恢复执行。随后在公平的完整验收路径上测试 Prompt 与 Enforce，报告合格交付、失败率及净成本。负面 Motif 不能代替修复坏接口，也不能为了省钱提前宣布任务完成。
