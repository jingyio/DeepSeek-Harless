# 官方元数据批查询与整请求 shadow

- 实验 ID：paper-citation-batch-20261010-v1；2026-10-10，Codex。
- 问题：将重复 arXiv 网页读取内化为批查询 MCP 后，正常模型轨迹能否产生更多可整次替代的控制请求。
- 条件：同一私人主稿的预印本版本取证阶段；不是完整参考文献 PDF 报告或独立论文泛化。真实 deepseek-flash，reasoning_effort=off，输出8192，关闭压缩，无次数上限。原生工具与十个 MCP 工具在两组一致。
- 工具：SSS_PAPER_CITATION_FLOW=1 与 SSS_PAPER_ARXIV_BATCH=1 增加 fetch_pinned_cited_preprint_metadata(citation_id)。固定官方 Atom API、最多64标识、至少3秒请求间隔；HTTP/XML失败明确返回，不称文献不存在。published/updated分开，DOI/journal_reference只作线索。依据：[arXiv 官方 API 文档](https://github.com/arXiv/arxiv-docs/blob/develop/source/help/api/user-manual.md)。工具由正常行为人工提炼；不是新学到的网络调度 Motif。
- 冻结库：沿用 citation-rsi-v2/libraries/modular-v1 的三项诊断结构，摘要 bf528cc0b164e4de18f96dbeb2ab41f9a5ce527632548de6e71baeaa0beba5f2；两份同论文稿件训练、合成协议留出，不新增跨论文认证。

| 组别 | 状态 | 实际请求 | 代理新增估费/美元 | 秒 | 输出范围 | 实际跳过 |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| baseline | completed | 10 | 0.019305132 | 48.079 | 15/15 | 0 |
| shadow | completed | 19 | 0.026609940 | 54.614 | 15/15 | 0 |

两组来源未变；baseline 官方批查询实际取得15/15元数据。范围检查不等于著录、版本结论正确，语义质量未盲评。shadow 在线2候选，完整请求回放与在线位置6、7一致；只有1次纯工具完整机会，另1次含文本需语义审阅。因此机会为1/19=5.3%，不是实际节省。基线更少的请求不能归因于 Motif，shadow 没有接管。

免费回归两端215 Python/92 Node；新阶段权限回归增加至93 Node。原始事件、请求、账本、来源、库/任务快照、triage与shadow-evaluation.json仅在 .local/paper-reference/<ID>/，双端同步且排除dsh凭证目录。run manifest记录实际模型、题面/代码/来源哈希与参数；effective-config-supplement.json事后补录环境、逐请求schema/order摘要、缓存/输出用量。账单与人工修订时间未知，代码尚未提交/推送。

```sh
source .local/remote-env.sh
node scripts/project.mjs python scripts/paper-citation-rsi.py --phase preflight --experiment paper-citation-batch-20261010-v1 --arxiv-batch
# 以下为付费复现说明；已有运行拒绝覆盖，重跑需新ID且继续累计预算：
node scripts/project.mjs python scripts/paper-citation-rsi.py --phase collect --experiment paper-citation-batch-20261010-v1 --arxiv-batch --call-model
node scripts/project.mjs python scripts/paper-citation-rsi.py --phase evaluate --mode shadow --experiment paper-citation-batch-20261010-v1 --arxiv-batch --call-model
node scripts/evaluate-citation-shadow.mjs .local/paper-reference/paper-citation-batch-20261010-v1/runs/evaluate-manuscript-shadow
```

累计代理估费4.70861215/冻结上限4.84521046美元，账单未核对；包括前期失败和学习费用。20%目标未达成。下一轮明确分离取证阶段权限，三组同条件；不得将工具范围变化的收益记为 Motif 因果收益。后续见[阶段权限失败记录](paper-citation-batch-bounded-20261010-v1.md)。
