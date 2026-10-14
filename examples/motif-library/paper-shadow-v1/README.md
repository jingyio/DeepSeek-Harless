# 论文 Shadow 局部候选的可读样例

从2026-10-11真实DeepSeek正常baseline轨迹编译，供理解参数绑定与局部衔接。`candidates.summary.json`只有九个图和训练Session计数，已经移除私有论文、来源/请求/会话见证和工具契约。它不能加载为Motif library，也不授权自动执行；正式可重放样例仍见相邻research-portfolio-v1目录。

例如，模型原生读取当前引用原文后，结果返回当前`citation_id`，候选将它绑定到`fetch_pinned_cited_preprint_metadata`的同名参数。每次从当前结果取得句柄，不记住另一任务的ID。随后正式版本候选查询和恢复查询也可由独立局部边衔接；源码目录、引用集合与版本改变时重新核验，不能缓存旧科研结论。

另一类候选是模型write/edit当前`triage.json`后调用只读`check_paper_triage`。内容与修订由模型提供，Runtime只预测检查调度。校验失败后读取同一报告的新增边只有一个训练Session支持，本轮没有触发，尚未通过独立任务认证。

九个图为局部单步边，可以组合探索更大子图，当前不代表九套完整任务Skill。图的发现来自正常轨迹；可调用能力、安全契约和字段解释仍人工实现。冻结库的执行证据、schema/顺序、版本守卫与实时预测在服务器私有目录，不可用本摘要代替。

三轮严格整请求匹配为21.4%、32.5%、27.4%，实际跳过0；质量问题和失败均保留。详见[最终实验记录](../../../docs/experiments/paper-rsi-overnight-20261011-v3.md)及[接口](../../../docs/interfaces.md)。
