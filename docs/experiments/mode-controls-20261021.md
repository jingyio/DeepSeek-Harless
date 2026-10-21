# Plan / Compact / Goal 功能复测（2026-10-21）

## 范围与配置

应用户要求，验证规划审批、上下文压缩和有限目标续行。这是合成任务功能验收，不是业务质量、Motif 降本或全系统长期稳定性实验。判失败条件包括提前写入、压缩后所需事实丢失、原日志被删、越过明确轮次或取消后继续自动执行。

- 正式源码 `7e167ed0c1a1846d6927fcc6fd6590e28cba9519`；沿私有 `GENELOOP_SERVICE_HOME` / `GENELOOP_SERVICE_CONFIG`，无应用代码、配置或库变更，无服务重启。本次仅增加记录。
- 模型 `deepseek-official` / `deepseek-flash`，推理 `off`；费用/请求/应用输出额度均为 `null`，wire `max_tokens=393216`，保留原累计账本。
- 复用已有五个诊断账号，在新对话中执行八项真实案例；四个客户端线程，经正式账号网关 loopback 入口并保留原 public Origin。另在真实公网网页的一个新诊断会话中操作 Plan → Compact → 回忆 → Goal。没有改普通用户任务、权限或原文件。
- 输入为合成标记、文本附件、计数和本会话文件。Goal 的受控 sleep 只用于捕获本人新任务的暂停/取消窗口。明确轮数是用户授权范围，不是重新加入平台额度。
- 私有证据 `.local/mode-controls-20261021/`；结果 `mode-controls-retest-20261021-a/` 中保存 `results.json`、`summary.json`、原 Task/journal、`ui-before-approval.json`、`ui-audit-v3.json`；网页截图在主目录。服务器同名证据已同步本地，凭证和原日志不提交。
- Task、模型、工具顺序、权限/预算路由、Goal revision/cap、压缩来源和逐请求 usage 均留在证据。安装版本沿正式锁文件，本轮没有单独导出 Node/Python/DSH 版本清单，不声称完整环境快照。

私有 `acceptance.py` 只有指定 `--execute-real --results <新的私有绝对路径>` 才调用模型；不覆盖旧结果、不自动重试未知写操作。

## 结果

确定性诊断命令：

```sh
node --test tests/test_geneloop_plan.mjs tests/test_geneloop_goal.mjs tests/test_geneloop_interactions.mjs tests/test_geneloop_context.mjs tests/test_geneloop_context_native.mjs
```

**33 通过、0 失败、0 跳过**。这些是无模型诊断，不替代真实验收；纯记录变更不重跑全量或额外付费实验。

| 真实案例 | 已验证 | 模型请求 | 代理估费 USD |
|---|---|---:|---:|
| Plan 批准 | 批准前未写入，批准后沿原 Task 写入、读取核验 | 5 | 0.001927320 |
| Plan 修改反馈 | 首次只反馈；重新审批后才执行修改版，原文件未创建 | 7 | 0.002909510 |
| Plan 关闭 | 开关不建模型任务；后续普通请求无遗留审批 | 4 | 0.000807570 |
| Compact | 原生摘要、执行侧替换、旧日志/Task 字节保留；不重传也准确回忆附件标记及数字 | 5 | 0.005367150 |
| Goal 完成 | 真实原生自动续轮，get_goal/update_goal，同 Task/计量完成 | 5 | 0.001266260 |
| Goal 停止生成 | 已确认原生执行窗口后取消，边界闭合，无新自动轮 | 2 | 0.000523750 |
| Goal 上限 | 拒绝缺轮数、零、小数且不建任务；明确两轮后恰好达上限，clear 生效 | 3 | 0.000527830 |
| Goal 暂停/恢复 | 当前轮完成后不再续轮；resume 保留目标/已用轮数/上限，最终完成并 clear | 13 | 0.002983150 |
| **八项合计** | **8/8 通过** | **44** | **0.016312540** |

另外三个真实网页流程均通过，独立计 **10 请求 / USD0.003537370**：

1. `/` 菜单可见三命令。Plan 显示审批卡片；批准前独立后台采样只有 exit_plan_mode，没有文件。点击批准且不填额外文字后，write/read、最终精确标记与退出规划模式均正确。
2. `/compact` 显示压缩九条历史、约 2583 tokens。后台有 `llmStreamCall=true` 摘要和来源对应的 surface replace，旧事件仍在。随后要求不读文件、不调用工具，准确答出原标记，实际工具数为零。
3. `/goal --rounds 1 ...` 首次只答准备就绪，随后真实自动续行、get_goal/update_goal，目标 complete、roundsStarted=1、maxGoalRounds=1，最终标记正确；没有客户端追加提示冒充续行。

总计 **54 个唯一真实请求 / USD0.019849910** 代理估费；输入 496328 tokens（命中 459520、未命中 36808），输出 5042 tokens。包括两次压缩维护调用。Task 和维护路由均对齐原收据，pending/unknown 为零；按 `(task_id, request_id, request_utc_epoch)` 去重。原累计账本前缀 SHA 不变，**服务商实付账单未知**。

测试后统一 `service status/check` 仍为原 owner/gateway PID、认证正常、登录 200；健康检查零模型请求。人工诊断、网页点击和轨迹审阅未计时；Plan 页面耗时含人为等待审批，不当作模型延迟。

## 问题与限制

- **界面待完善：** 中文网页的 Plan 审批标题、选项及说明仍为英文；功能可用，本轮未修改文案。
- **瞬时重连：** 网页测试中观察一次自动重连并自行恢复，没有重复发送，三个流程均完成。原因未调查，不称该问题已修复或公网长期稳定。
- 审计 v1 将原生 `surfaceOp` 对象误当字符串；v2 又计入后续独立系统消息替换，两份失败保留。v3 按真实对象、compact 插件和 compactionId 精确核验通过；未改应用、放宽来源或重跑模型。
- `/goal pause` 阻止后续自动轮，当前轮可完成；立即取消使用“停止生成”。`--rounds N` 是人类初始轮后的自动续轮数，不是 N 次 API 调用。
- Plan 是协作模式，题面中遵循审批不代表新增强制只读权限边界。Compact 是摘要，样本准确不保证所有长文事实无损。
- 本轮网页使用主聊天原生执行器；未另测 Paper/PPT/Data 业务交付、File 独立 SDK、进程重启恢复或长期断网。不把本轮 8/8 外推为所有场景无异常。

下一步最小工作是本地化审批卡片，并在再次重连时按原请求身份收集网络与服务端证据；现有观察不足以归因或要求重启服务。
