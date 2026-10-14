# 文献 Agent 第一阶段：三任务实验与指定论断修复

## 问题与最终行为

此前四组实验只覆盖同一个已批准证据准备计划，不能显示完整阅读、缺口修复与资料更新的瓶颈。新增场景编排入口串联这三个任务，全部语义调用仍由原 Harness、MCP 和预算入口执行；失败与追加修复保留原始日志和费用，不要求用户人工审批，不修改原 PDF。

真实运行发现自动支持检查仍可能接受缺少否定对象的截断引文。新增指定论断复核入口，仅修改目标字段，再重新综合，其他字段逐字校验保留。允许从私有文件提供独立来源核对意见，明确它不是 Runtime 拒绝、参考答案或科学认证，模型仍须读取实际来源。

## 修改范围与接口

- `scenarios/literature-notes/run-phase-one.ts`：实验准备、代码/来源冻结、三个任务及无变化控制、阶段费用与真实运行关联。默认预览，`--experiment` 加 `--call-model` 执行；拒绝覆盖既有结果。
- `scenarios/literature-notes/phase_one_tasks.py`：已有完整稿没有自然缺口时，单独建立一条方法缺失的诊断副本。标记受控案例，重放来源，不伪造原生事件、不改原稿。
- `scenarios/literature-notes/repair-selected.ts`：`--job`、`--claim-ids`、`--budget-usd`、可选 `--source-feedback`；默认预览。目标集合经既有工具校验，修复与综合共用本次总上限；来源/解析/契约必须一致，工作流版本变化显式记录。
- `scenarios/literature-notes/repair-pdf.py`：新增可选 `--source-feedback <私有JSON>`。要求 `schema_version=1`、`origin=independent_source_check`、`input_sha256` 绑定当前稿、唯一 `issues[{claim_id,issue}]` 属于目标集合；限制文件大小和意见长度，加载 Key 前验证。有效意见摘要与实际提示保存在私有运行快照。未提供此参数时保留原路径。
- 相关 Python/Node 测试与场景协议、交接。

没有修改共享 Harness/Motif/预算接口、计价或上游依赖；没有新增 HTTP 参数、前端审批或任意模块加载能力。SDK 与 Web 默认行为保持原入口，新增能力目前是场景 CLI。新辅助入口不等于 learned RSI。

## 认证、版本与回退

运行前固定三篇来源及新增次序。完整实验后检查初轮代码和原 PDF 未变，再记录追加修复的代码/诊断意见摘要。后续修复入口变化使工作流版本变化，既有自动依赖/结果缓存需重新核验；不能为了命中强制继承旧版本。

原始结果、两次追加支持修复和零调用缓存分别保留。独立来源核对发现的语义反例不因最终修复成功而删除。回退可继续使用现有 `agent.ts` 和 `run-pdf.py`，不删除论文、Key、历史结果或私有诊断。

真实结果和质量边界见 [实验记录](../experiments/phase-one-20261012-8a865a78.md)；任务定义见 [第一阶段协议](../../scenarios/literature-notes/phase-one-protocol.md)。
