# F02 当前交接

- 更新时间与交接人：2026-10-24，Codex；Owner @jingyio，Reviewer @peilin6。
- 目标与范围：可运行的共同执行/更新接口、同例演示和待审核 PR；截至 23:12 的窗口内，不扩展 F05/F08 算法或接管 F01/F03。
- 分支 / commit：`codex/f02-protocol-v1-20261024`，基于 #114 的 bb4c8e7；最终 commit/PR 以本分支 Git 和后续状态更新为准，不合并。
- 已完成：`src/adapters/rsi_protocol.{py,ts}`、共享 Schema/小生成器、A/B/C 公共诊断、原生 Harness 接线及 Provider 投影；短 RFC、统一 Issue 模板。六个 Issue 的结果/同例/验收已保存，原文折叠保留。
- 已验证：F02 28 Python/30 Node；三轮原生真实模型均 A/B 各2请求/1派发、C 1请求/0派发；最终实际 call_id 与 task_id 关联一致。smoke/motif:check 通过。冻结源码全量 Python1547过/235skip；Node1405过/15skip/1旧上传失败，#114基线同文件8过/1同失败，未改网关。
- 实验结论：见 [f02-protocol-local-20261024-v1](../experiments/f02-protocol-local-20261024-v1.md)。只支持人工算子与合成输入的局部接线，完整任务、自动学习、泛化和降本未验证。
- 配置与数据：公共示例在 `examples/rsi-protocol-v1/`，权威格式在 `schemas/`；真实原始事件与费用在本轮私有 `.local/f02-protocol-local-20261024-v1/`，凭证仅环境 `DEEPSEEK_API_KEY`。固定 Flash/off/1000输出；费用/次数不限，累计不重置。
- 权限与费用：本轮18请求，峰值保守估费约USD0.00195336；本地历史加本轮7358请求/USD10.45235780，旧3笔未结算与其他主机未知仍保留，账单未核。允许独立分支/PR，不合并、不改正式服务或外部应用。
- 未完成：#114 G0 与 peilin6 的接口审核、F03 ABI 联审、实际独立证书/Registry 发布适配；本机旧上传 typed-413 失败留待网关维护，原基线复核日志已保留。
- 接手下一步：1. 运行 `npm run rsi:demo` 并审阅[短说明](../rsi-protocol-v1.md)；2. 确认当前义务/权限及计量字段后冻结候选接口；3. 由 F03 对接真实任务，F05/F08 接各自更新算法并提供独立证据。
- 回退：本轮为 opt-in 新入口，代码按 PR 回退至 bb4c8e7；不删除原私有账本、失败产物或旧库。实际运行仍依赖 Python 计算样例，不声称无 Python 产品。
