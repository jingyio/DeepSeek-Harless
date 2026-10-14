# 文献Agent：缺口续修与自动局部更新

已有逐论断修复每次续跑仍审阅全部15字段，且技术失败只留下缺口文本，丢失了模型提案和检索线索。自动结果变化后也只能整稿重读。本次改为只修未解决字段，保存来源绑定的失败诊断，并复用现有依赖图和增量MCP更新发生变化的部分；局部事实修订后自动重新综合完整证据表。

本次只改`scenarios/literature-notes`、相关测试及记录，无新增共享核心、上游Harness、预算代理、依赖或Motif接口变化。此前共享改动仍见`approved-plan-continuation.md`，不要混为本次新增。

## 场景接口变化

| 接口 | 行为 |
| --- | --- |
| `repair --job` / `repair_only` | 默认`repair_scope=unresolved_claims_only`；`--audit-all`保留全量独立提取。没有缺口时不调用模型。 |
| `repair_plan` | 可冻结`target_claim_ids`（增量收据中的变化字段）、父任务与原论断导航；已接受的非目标字段不变。 |
| repair packet / audit | 新增`prior_rejected_proposal`和`rejected_proposals`，提案及错误仅用于导航，不授予引用权限。旧回收稿诊断须绑定原生事件、消息及提案摘要。 |
| pending issues | 新增`literal_number_candidates`：只返回本论断已读片段的字面数字匹配，不认证支持。数字检查也会匹配系统版本名，需要补充真实主体/版本引文。 |
| `synthesis_only` | 冻结空目标集合；`read_claim_repair_packet("synthesis")`读取整份当前表与实际引文；`submit_claim_repair([], hypothesis)`只改综合假设，字段全部保留。局部修复后自动执行；CLI可用`repair --synthesis-only`。 |
| `index --job` / `index_automatic` | 离线重放当前来源，生成逐字段缓存依赖。`index_model_requests=0`独立于任务费用；不覆盖模型请求或研究质量。 |
| graph `reuse_policy` | 新增`automatic_source_bound_unverified`，节点以`source_bound`管理可复用性；旧Human/Codex图继续用`reviewed`。Runtime索引不签发语义或人工审批。 |
| 自动更新 | 未变化字段重放引用后保留；新增/改动PDF只处理对应字段；删论文重算综合；问题、解析器、契约或工作流变化使相关缓存失效。变化字段自动审阅，保留字段不重复审阅。 |
| 版本与审计 | 索引底稿位于版本目录；每次增量运行冻结独立依赖图。来源、合同和提示变化不能覆盖历史证据。 |

依赖路径为PDF/解析器→原文引用→字段→论文笔记→综合假设；自动字段依赖自身PDF、问题、契约、工作流及来源绑定记录。论文集合变化只影响新/删论文及综合，避免使所有旧字段失效。缺口或数值未匹配字段不具备复用资格。

## 边界与依据

这是普通依赖缓存与有界控制流优化，新增验证Motif跳过为0。模型仍做支持关系和综合判断，Runtime只决定范围、权限、版本和停止。它继承旧模型内容的未认证质量，也可能复用旧语义错误；没有以来源重放冒充科学支持。

参考落实：AutoTool借鉴历史参数流而不复用历史结论；G-Agent借鉴局部片段及来源匹配；Graphs借鉴版本/失败守卫；Stagehand借鉴探索→保存→核验重放→失效重探索。逐项说明见场景`reference-design.md`。手写依赖图不等于这些论文的学习算法，也不构成RSI泛化证明。

验证和实际成本见`docs/experiments/targeted-repair-20261010.md`。变更没有提交或推送；私有原文、API key和日志不随Git提交。
