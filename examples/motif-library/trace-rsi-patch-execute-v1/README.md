# 从真实正常轨迹学到的两个局部 Motif

这是可读摘要，**不能作为library加载，不授权执行**。完整工具契约、来源/会话见证、认证及版本守卫留在私有实验目录。算法由真实DeepSeek生成，图从正常使用轨迹编译；工程视图、权限、文件应用和排版由开发者提供。

模型先决定哪些引用需改标识、去重或补占位，并调用 `apply_revision_plan`。假设当前报告从版本A变成B，工具返回B对应的新input_id。第一个图把这个当前句柄传给 `triage_revision_audit`，因此检查的是B，不能沿用A的结果。

第二个图把刚检查的当前句柄传给 `export_revision_report`，生成固定私有revision-report.md。文件包括完整修订前后材料、原来源和当前检查；Runtime核对实际文件哈希。模型之后仍须说明修订依据和真实性/正式版本未核验的限制。Runtime没有决定论文是真是假，也没有改写科研结论。

在本轮正常流程中，原生是：模型读取 → 模型决定并提交修订 → 模型要求检查 → 模型要求导出 → 模型最终解释，共5请求。execute把两个中间请求交给Runtime，模型仍做读取、修订与最终解释，共3真实请求。三项合计15→9，实际少6，下降40%；同工具费用只下降13.24%。学习尚未摊平，完整论文和跨论文未验收。

两个图分别有四个正常Session支持，都来自同一论文的控制恢复任务。参数来自**当前工具结果**，不保存另一任务的input_id或复用旧科研判断。这里仍是两个局部边，不是两套完整论文Skill；更早失败检查是否应交回修订还需学习和验证状态前提。

具体字段见[candidates.summary.json](candidates.summary.json)，全部结果/反例/费用见[V4实验记录](../../../docs/experiments/paper-rsi-local-view-execute-20261012-v4.md)及[V2/V3反例](../../../docs/experiments/paper-rsi-local-view-shadow-20261012-v2-v3.md)。实际生成的修订AST见[report-patch-v1](../../rsi-tools/report-patch-v1/README.md)。
