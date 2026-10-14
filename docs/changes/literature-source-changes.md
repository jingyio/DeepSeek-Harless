# 文献Agent：来源变化对照与可定位的参数诊断

实际新增论文时，两条121/125字符的陈述超过120字符上限，但增量工具只返回笼统错误。模型通过修改reason、引文和字段集反复猜测，十次提交未成功，耗尽32步。现在Runtime报告所有超长字段ID及实际/允许字符数，保持原约束，由模型只改有问题的语义陈述；缺字段和数值错误也提供可定位诊断。Runtime没有自动截断文字、补写结论或认证引文支持。

删除论文可能没有字段需要修复，但全局综合必须重新考虑当前选择。增量审计新增`synthesis_requires_review`，场景package将其传给现有TypeScript协调器；默认自动审阅即使0字段变化也读取完整当前证据表重新综合，且逐字段保持其他论文内容不变。这一阶段的真实费用单列计入任务。

新增场景对照入口`compare-source-changes.ts`，只调用已有`runWorkflow`、Harness、MCP和预算入口。默认准备/预览，不调用模型；独立语料副本保留所有版本，在付费前冻结协议，拒绝覆盖已开始实验。逐阶段保存源重放、保留字段逐字一致、旧句柄隔离、删除条目排除、费用和协调时间；科学质量等价不由这些检查自动签发。

## 改动范围与兼容

- 场景：`agent.ts`、`agent-support.py`、`pdf_incremental_tools.py`、`compare-source-changes.ts`及README。
- 相关测试：`test_literature_agent.mjs`的删除0字段综合与保留字段篡改检查；`test_literature_pdf_incremental.py`的Unicode长度、多字段诊断及修正后原5字段完整提交。
- 无新增共享核心接口、MCP成功输入schema、预算规则、依赖或上游Harness改动。此前共享Motif续接接口保留，不属于本轮新增。
- 新实现摘要使旧contract/workflow守卫失效。第二协议重新建库，不强制复用旧图，也不回填历史许可或语义认证。
- 本轮数据仍为私有`.local`副本，原PDF与Key不改；未commit/push/PR。原始失败、旧协议和费用不能删除来美化对照。

完整真实结果、反例、请求/费用/质量边界见[实验记录](../experiments/source-changes-20261011.md)。本轮是普通依赖缓存更新验证，新增learned Motif与验证跳过均为0；不能用“增量更少字段”代替完整同质量降本结论。
