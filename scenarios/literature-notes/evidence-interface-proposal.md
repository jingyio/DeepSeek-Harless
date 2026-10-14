# 证据准备链：共享接口提案与实施状态

2026-10-10用户已授权，提案已落地为 manifest v2 的 `approved_plan_continuation`。下文保留原边界与提案依据；当前字段、逐文件变化和测试见 [实施记录](../../docs/changes/approved-plan-continuation.md)。新的真实在线任务已验证2次跳过、0 embedding；不表示论文理解或净成本验收通过。

## 原版本已确认的边界（保留提案依据）

现有 witnessed-chain 编译器可以从实际轨迹编译 `extract_evidence_windows → verify_evidence_windows → build_evidence_packet`。但在线 `isClosedSourceRead` 只允许同版本、单参数 `source_id`、无默认参数且工具名为 `read_pinned_*` 的固定读取免去语义匹配。新链的工具职责是提取、核验、组装，参数名分别为 plan / extraction_id / verification_id，不符合此规则。

因此新链能离线认证参数关系、通过 manifest 校验，**不等于现有在线插件会自动执行**。当前新入口只提供拒绝 embedding 的本地端点：不提供假向量、关键词分数或恒定相似度。没有获得匹配资格时原生插件必须交回普通 Harness。不能通过改名 `read_pinned_*` 掩盖真实职责。

另一个已确认的输入边界：`witnessedPrefix` 要求锚点必填参数是最多500字符且无控制字符的字符串。最初真实多窗口计划 JSON 超过此限，会在到达相似度门控前回退。**已在场景内解决**：新增 register_reading_plan，把批准的长 JSON 冻结为39字符 `plan_id`，提取消费该凭证；另收集两条真实训练及一条认证轨迹并重新学习。没有放宽共享 scalar。长 JSON 提取仅保留兼容旧入口，默认题面使用短凭证。

提案提交时仅修改场景和相关测试；随后用户明确许可修改共享接口并记录提交说明。下面记录原先列出的最小范围，实际实施以权威接口和变更记录为准。

## 最小提案：经批准计划的确定性续接

| 接口/位置 | 所需变化 | 执行条件与限制 |
| --- | --- | --- |
| 工具契约、编译/认证与 manifest：`src/adapters/tool_contract_loader.py`、`src/adapters/dsh_trajectory.py`、离线编译/导出器 | 添加版本化的续接许可契约，区别于现有 read_only 与 replay_stable；声明授权锚点、工具结果中的许可字段、有限目标工具及允许的参数来源 | 不是任意一候选就自动执行；训练/认证需观察到有效许可及成功连续链；契约摘要包含新政策；旧库默认维持原行为 |
| MCP 结果许可（由本场景提供） | 锚点在模型明确批准计划后签发可核验的 continuation_grant，绑定 task、plan、输入/工具版本与允许的机械步骤 | 来源目录与读取权限来自用户冻结任务；模型选择仅限这批来源；false、任务变更或未批准计划不签发；许可不授权语义结论或用户文件写入 |
| 在线匹配：`src/motif_core/online_skill_runtime.mjs` | 增加独立的 `approved_plan_continuation` 判定路径：验证当前真实锚点许可、认证政策、唯一参数绑定和同版本后，才允许免去相似度匹配 | 有歧义或额外未绑定参数就回退；下一阶段必须携带同一许可/来源链；不能只依靠工具名称、描述或 bool 字段；不扩大原 `read_pinned` 规则 |
| 结果复核与审计：现有 `src/adapters/dsh_online_motif.mjs` | 在既有 pending/result 验证上记录许可来源、失效及回退原因；如果加入许可复核，需与 matcher 使用同一规则 | 只在真实工具调用与版本复核后记录 skip；needs_review 可表示一次调用被跳过，但不能被当成证据包交付成功；失败或许可撤回终止续接 |

实际实施字段为 `continuation_policy`、`continuation_policy_digest`、任务 `continuation_policy_digests` 与结果 `continuation_grant`；新字段由 Python 与 TypeScript 权威校验，使用新 manifest v2。范围只包含只读、有限计划下的凭证续接；不加入通用代码执行、自动分支选择、数组 IR 或用户文件写回。needs_review 在新守卫中不算验证成功跳过，也不算交付成功。

## 验收要求

1. 新工具名不含 `read_pinned`，仍可在合法许可下完成两个真实工具续接；模型继续选择阅读计划。
2. 未学习、未认证、许可缺失/false、许可串任务、版本或 schema 漂移、参数歧义、低文本、工具失败都交回模型。
3. 同计划固定协议中 baseline 与结构执行交付逐字一致；验证实际模型请求与 audit，不把模拟 usage 当真实费用。
4. 旧 Motif 的闭合来源读取、语义匹配、权限拒绝和失败恢复回归不变。
5. 再做真实模型/普通脚本对照，分别记录学习准备成本、机械交付和科研质量。科学理解仍不能据本接口认证。

替代路径是配置一个真实且经过校准的本地 embedding 服务，走现有语义匹配路径；它需要额外部署和阈值验收，仍不能把相似度当许可证明。当前没有安装或启用该服务。
