# 跨资料检索 Motif：从真实工具轨迹到逐项候选

> 2026-09-25。无模型机制实验；不计入真实报告质量或总成本成绩。冻结 MotifAgent 仓库只读。

## 实现边界

在已编译的资料读取 Motif 之后，新切片把 `snapshot_sources → retrieve_point` 作为跨资料检索 Motif。训练轨迹来自两个实际工具客户端运行：公开论文 `reference/` 和合成办公资料 `office_research_v0`；留出轨迹来自 DR³-Eval 中文 003 的本地公开资料快照。`snapshot_sources.sha256 → retrieve_point.snapshot_sha256` 必须有可信的参数来源记录、跨任务变化和留出核对。检索词与来源范围是明确声明的集合入口参数；未声明的列表不能进入自动执行。

`retrieve_point` 内部目前仍调用旧的确定性检索与引文核验算法。**Motif 内核持有的是来源快照依赖、参数守卫、执行／暂停／重入控制**；这还不是把整个检索算法迁成 Motif 节点。语义规划仍由已有的 DSH 类型化 handoff 产生检索词。若 Motif 缺少检索词，会暂停为槽位请求；经验证的集合参数可以重新进入同一个 Motif。来源变化时，执行前核对会停止。

## 复现

先按 [DR³-Eval 输入说明](../benchmarks/dr3_zh003/README.md)准备 `.local/benchmarks/dr3-zh003/sources/`。训练和留出定义固定在 [`retrieval_motif_cases.json`](../benchmarks/retrieval_motif_cases.json)。运行：

```bash
.venv312/bin/python scripts/compile-retrieval-motif.py
```

本轮产物为 `.local/motifs/research-retrieval.json`，Motif ID `motif_ebf7d110`，签名 `c64e9894f35acdc99567787bfa71a689ff178fbdbb60e8dde5b7280371743b7a`。产物只存来源任务指纹、工具／参数边与契约签名，不存论文正文。命令入口使用 `--retrieval-motif-artifact .local/motifs/research-retrieval.json`；它也可与 `--source-motif-artifact .local/motifs/research-source-read.json` 连用。与旧实验产物的签名不同，是因为来源快照工具现在把输入版本也纳入绑定，防止增量恢复时复用旧快照。

## 实测范围

DR³-Eval 中文 003 使用同一份本地诊断检索计划作**无模型预览**。旧路径和检索 Motif 路径都生成 16 个候选，候选 JSON 相同。两段 Motif 连用时，记录 16 次资料读取 Motif、4 次跨资料检索 Motif，仍得到同样的 16 个候选；模型请求数为 0。测试共 107 项通过，包含真实文件上的训练／留出／新任务执行、缺检索词交接与恢复、来源变化停止，以及更换资料读取 Motif 后禁止误用旧缓存。

检索 Motif 现在将绑定证据保存到被忽略的 `motif-retrieval-state.json`。用 `--previous-retrieval-state` 再运行相同资料、问题和检索词时，4 个逐项检索结果都从旧绑定命中，候选仍为 16 个；来源文件或解析器／资料读取 Motif 版本变化会使整个检索快照失效。恢复时还重验旧候选的来源哈希、页哈希和引文片段。该复用节省的是确定性检索工作，尚未证明能减少模型调用。测试中恢复后的 4 个 `retrieve_point` 均命中缓存；快照工具在同次执行中也会多次命中，不能把所有命中数都算成任务收益。

另在 DR³-Eval 资料的**临时副本**中修改 `web-01.txt` 后带旧检索状态重跑，记录 `retrieval_snapshot_invalidated`、旧检索记录 5 条全部失效、逐项检索缓存命中 0 次，随后重新得到 16 个候选；两次命令都正常完成。这里采取整份来源快照失效的保守策略，尚未做到“仅重检受该文件影响的问题”。

这仅证明结构执行与候选一致。诊断检索词是预先给定的，资料读取和检索算法本身都不需要模型；**不能宣称 token、费用、报告质量或人工工作量改善**。DR³-Eval 中文 003 已用于开发，不能当作最终留出效果题。下一步必须让 Motif 管理逐问题证据选择与报告更新的依赖失效，并在不同研究题上比较合格报告和总成本。

同机交替运行旧检索和编译 Motif 检索各 3 次，无模型预览耗时分别为旧路径 0.670、0.679、0.724 秒，Motif 路径 0.737、0.693、0.769 秒；中位数约 0.679 对 0.737 秒。这是很小的诊断样本，含进程启动和 PDF 解析噪声，但至少说明本切片**没有展示速度收益**。若后续跨任务复用决策和增量恢复不能抵消额外守卫开销，就不应将其放进默认产品路径。
