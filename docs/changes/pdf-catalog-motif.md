# PDF 文献目录与工作清单 Motif：实施前接口记录

2026-10-12，用户已授权继续多个任务流程的 Motif 效率实验。

本轮新增普通 PDF 的目录创建/增量更新任务。MCP 提供 `read_catalog_plan()`、`read_catalog_packet(paper_id)`、`submit_catalog(entries)`；模型从已读取首页选择标题、作者和可见年份/标识，Runtime 校验逐字段原文锚点、完整受影响集合和原文件版本，保留来源未变的旧记录，生成私有 JSON、Markdown 与 BibTeX。缺失字段显式保留；不联网补全、不自动认定两份文件属于同一学术作品、不修改原 PDF。

**共享核心接口变化：无。** 复用现有 `inventory_witness(..., frontier='incremental')`、`compile_inventory_motif`、`certify_entry_motif`、`sss-entry-incremental-v1`、TypeScript 工作数组控制器、固定公开 Harness 插件与 `run-scenario.py` 预算入口。新工具沿用 `work[].paper_id`、`task_sha256`、`plan_sha256`、PDF/解析/文档版本字段。新场景从自身真实普通原生轨迹学习并独立认证，不能直接替换旧工具名或复用旧认证。

普通组和 Motif 组共享确定性的目录差分、PDF 解析缓存、首页证据包、原文校验和输出渲染。这些是任务实现及公共优化，不计为学习收益。Motif 的唯一组间变化是免模型执行完整工作清单的读取前沿；标题/作者选择及最后总结仍由原 Harness 模型完成。完全未变化的目录走普通程序零模型复用，不启用 Motif。

新增文件仅在 `scenarios/literature-notes/`、相关测试及公开文档；不修改上游、共享编译器、控制器、预算代理、旧场景提示或旧实验。CLI 默认不调用模型，策略默认关闭；私有策略/原始日志留 `.local`。同一版本冻结后做不同工作规模的真实训练、第三任务认证与交错对照，失败与费用全部保留。元数据锚点校验不等于作者/年份/文献身份语义已完全正确。


## 实施结果与 GitHub 提交正文建议

新增普通PDF文献索引/引用目录创建和增量更新任务，保留未变元数据，只读取新增/变化文件首页；类型化原文锚点校验后生成私有JSON/Markdown/BibTeX。复用已有工作数组Motif编译/认证、TypeScript控制器和原Harness Session/预算/完成守卫，无共享核心或上游变化。新库以本任务真实普通轨迹重新认证，默认关闭，Web未接。

修正首次导入可选previous引用、封装文件摘要、短姓名锚点及具体字段错误反馈，H/M统一使用。receipt.artifact_sha256绑定整个JSON封装，catalog_sha256绑定内部目录，原共享守卫不变。旧失败/费用留存。

验证448Python/98Node，3可选Docker跳过，实际MCP/SDK mock正负和未变0模型控制。12对照H28/M19请求、两个任务估费均值下降，但作者缺口、Accepted日期与数学标题解析问题使完整质量等价未成立。全部91请求/代理USD0.10926764含失败/学习/评测，实付/维护未知；详见 [实验记录](../experiments/catalog-work-20261012-f44dece1.md)。
