# 持久化经验库、批量 Motif 与恢复（2026-10-15）

用户授权的三项本地集成已完成。付费验证、失败与边界见 [实验记录](../experiments/persistent-rsi-20261015.md)。本次未提交或推送；早期公开库仍保留原认证，不重新签名。

## 日常入口与前端

`npm run web -- --scenario file-management --real-model --mode execute` 默认固定使用 `.local/rsi/daily-files-real-v2.json` 和同名状态目录；模拟使用独立 `daily-files-mock-v2`，禁止进入真实学习。首次建库，以后读取已有库、版本、任务索引和费用，不按 launch 新建。显式 `--rsi-config` 可选另一个已授权库。源目录须为 `testpdf/file-management-experiment` 内已登记实验副本；默认持久 seed 不覆盖已有文件，缺私有素材时至少提供文本样例。

服务费用 checkpoint 保存原请求数、支出、未结算预留和整体上限。重启省略整体预算参数时沿用 checkpoint；显式不同上限会拒绝。新任务仍采用本次服务配置的任务上限，已登记的旧任务保留自己的原上限。预算耗尽停用付费入口，不通过重启清零。真实模式仍需对预览的原摘要确认；库选择和学习不新增文件权限。

页面支持多选源文件、为每个文件生成明确目标路径，展示库版本、激活数、认证/拒绝数、学习开关、匹配/跳过、原请求、估费和未核实账单。产物列表显示来源、目标及实际字节核验结果；恢复预览显示原任务标识、已用请求和累计费用。完整浏览器操作含提交、报告、服务退出、重新认证与恢复。

`run-scenario.py` 对已登记的 v2 durable 文件场景省略 `--rsi-config` 时也使用真实日常库；其它场景不隐式获得学习适配器。`--rsi-resume <原 enrollment 目录> --call-model` 继续原任务，不重新 enrollment。

## 版本化结构与质量

新增 `file_operations_v2`、`sss-operation-graph-v2`、`sss-operation-certification-v2`、`sss-file-operation-quality-v2`。旧标量编译器/在线解释器分别冻结在 `operation_graph_v1.py`、`operation_graph_policy_v1.ts`，原 v1 正好一次认证口径保留。

v2 支持 2–8 节点图、非空唯一字符串数组，长度同时满足实际 MCP schema 的 minItems/maxItems 且不超过 40；`files[].file_id` 仅允许一次有界投影。每个参数都来自当前真实结果和 schema，禁止固定业务常量、任意代码或猜句柄。新增 `pin_files`/`read_files`；工具面从 15 到 17。

同一图可在一个任务中顺序重新匹配：前一轮已完成才开始下一轮，每轮必须有真实模型根决定、实际调用结果、完整结束及原生来源证明。认证按逐轮完成核验，不再把两次合法完成误拒为“必须一次”。原步骤/HTTP/费用和最多两次修复限制同时约束所有轮次。并发重叠的图、通用循环/分支和任意嵌套数组仍不支持。

v2 独立质量在执行前冻结：保留原效果/完整字节/回执/权限标准；配置 `require_source_read` 时覆盖全部原件，`require_result_read` 时覆盖全部产物。Web 当前结构化目标沿用 `require_result_read` 字段；自然语言要求与机械读取口径不一致时须在报告保留缺口，不能把原件未读说成已读。

## 原任务、原权限、原预算恢复

新增 TypeScript `OperationJob` 扩展原 `FileJob`，不另建松散预算。Python 预算代理复用它；原权限、任务哈希、执行版本、请求、步骤、费用、修复数及总共两次传输重试保留。未结算调用按原预留上界落账，未知 usage 禁止训练/认证，不重发作为费用恢复。

MCP 状态保存真实 plans/receipts/pins/reads/results。副作用先保存备份及 before/both/after 边界，再以无覆盖原子发布落盘；只接纳日志证明的边界，未知外部改动拒绝。再次执行已完成计划返回实际旧回执，部分完成只继续剩余动作。

SDK 每次恢复使用独立原生 Runtime 存储，同一原任务与预算账本不变；Web 恢复创建新原生 session 并绑定为旧任务别名，旧 session 不能继续付费。保留每次原始事件及 SHA，汇集只添加 attempt/session/original_seq 标注；学习逐行核对，不伪造原生事件。验收已通过但封存中断时只补原封存，不再调用模型。

认证材料、标准和 started 标记冻结；中断认证定位原 enrollment 和原预算，已封存材料直接采用原记录，未封存的原任务继续执行。认证/激活完成后中断重读原版本，不重复付费或重复发布。原任务代码/题面/schema/版本变化拒绝恢复，需另行新任务和认证，不能借更新绕过守卫。

费用串行写锁最多等待 30 秒以容纳日常提交与认证短时并发；worker/execution 锁仍拒绝第二个活跃拥有者。旧锁和所有失败留档。Python 服务退出、SDK 与 Web 中断、发布边界恢复、认证 checkpoint、旧预算恢复均有免费真实 MCP/原生 Harness 检查；真实费用记录独立。

## CI 核验

用户指出的 [38392885619](https://github.com/jingyio/DeepSeek-Harless/actions/runs/38392885619) 是 10 月 13 日旧失败：两个系统在 PDF 测试缺 Poppler。`01ce885` 已添加 Linux 安装及 PDF 测试前置条件；最新已推送 HEAD `fcdcc48` 的 [38548225640](https://github.com/jingyio/DeepSeek-Harless/actions/runs/38548225640) 成功。本次仅检查和保留日志，没有为旧失败重复改 CI，也没有推送新集成代码。
