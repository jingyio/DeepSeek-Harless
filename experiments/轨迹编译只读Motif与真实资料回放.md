# 轨迹编译只读 Motif：真实资料读取切片

> 2026-09-25。机制与恢复验证，不计入调研报告质量或成本效果分数。冻结 MotifAgent 仓库只作源码参考；以下实现位于 SSS。

## 为什么选择这个切片

原有资料读取已经有哈希绑定和增量复用，但主流程仍是手写控制。这个切片检查能否从**真实工具执行轨迹**挖掘、编译和执行一个只读 Motif，并在新资料任务中保持来源守卫。它不是给来源读取额外包装一个固定 JSON 步骤清单。

`hash_source → read_source` 的训练轨迹由实际读取本地 PDF 的工具客户端产生：后一步的 `sha256` 参数确实取自前一步返回值。编译器需要两条不同内容的训练轨迹、显式参数来源、结构化输出字段和值的逐条一致性；再用未参与编译的第三份资料核对。普通 DSH 工具事件若仅出现相等的输入输出值，**不会**因此获准自动传参。来源、任务和工具契约签名随产物保存，原文不写入编译产物。

## 冻结输入与复现

| 用途 | 文件 | SHA-256 |
| --- | --- | --- |
| 训练 1 | `reference/G-Agent.pdf` | `520402d9418de4b7b68c9d6ffc48860c0ea0f0db19d853a4d5d34da54601105e` |
| 训练 2 | `reference/AutoTool.pdf` | `9ef6334e6f2fcb7facf6aac97fd1a2a5888e02b9bd9ee55d1569f0238507980e` |
| 留出核对 | `reference/Make_Graphs_Great_Again_ATC2026 (6).pdf` | `96fad89059b4ac0779aa28b2eb09720f29f89fbbbb210d25e47d72bebd8ed97d` |

```bash
.venv312/bin/python scripts/compile-source-motif.py \
  --train reference/G-Agent.pdf --train reference/AutoTool.pdf \
  --heldout 'reference/Make_Graphs_Great_Again_ATC2026 (6).pdf'
```

生成的本地忽略产物为 `.local/motifs/research-source-read.json`，本轮产物签名为 `80d9be080c15359321dc27e0d2948f89639c36b816c66bcfb6e255564e0b8ad2`。产物含一条经显式来源验证的 `hash_source.sha256 → read_source.sha256` 参数边。`research-points.py --source-motif-artifact .local/motifs/research-source-read.json` 可让资料收集阶段使用该 Motif；后续语义节点仍由现有逐项调研流程处理。

## 新任务回放与结果

在 `benchmarks/office_research_v0` 的阶段 A 资料上，新内核完成 5 次来源 Motif 执行；在同一临时目录加入阶段 B 的两份资料后，又完成 7 次，其中 5 份旧资料复用、2 份新资料读取。阶段 B 的去重页面与旧资料读取路径完全一致，模型请求均为 0。命令入口的无模型预览也能读取阶段 A 资料，记录 5 次 Motif 执行后进入规划交接。现有测试共 105 项通过，其中包含编译、留出核对、新任务执行、缺参数交接与恢复、工具失败隔离、资料增量复用。

执行失败会产生不含原文与错误详情的凭据，并带本次执行 ID。新增的负向 Motif 候选器要求同一 Motif、输入版本、参数绑定和失败类型在不同执行中重复；随后还要独立失败重放和成功对照。它只生成 `replay_validated_candidate`，**不会自动启用阻断规则**。跨任务的报告质量与成本门槛仍须另做，避免把偶发工具故障永久编译进结构。

同机、同一 `reference/` 三份 PDF 的冷态资料收集各运行 3 次，旧读取路径耗时为 1.033、0.998、0.966 秒；编译 Motif 路径为 0.943、0.960、0.952 秒，均得到 45 个去重页面。这个小样本只是检查新路径没有明显数量级开销；运行顺序、文件系统缓存和 PDF 解析噪声未控制，不能据此宣称加速。

## 仍未证明的内容

- 训练／留出是本地已知论文，阶段 A/B 是合成办公资料；这只能验证执行与恢复边界。它不能证明在未见的真实调研题上合格率提升或每份合格报告更便宜。
- 原有来源读取脚本本来就是零模型调用；此切片也不应宣称节省模型费。新增哈希工具和重复快照核对可能增加读取耗时，须计入后续端到端成本。
- 当前只支持不重复的只读工具序列，通用 MotifExecutor、跨资料组合、写入门、负向 Motif 自动启用和完整轨迹编译仍缺。失败可以进入候选与重放核对，但尚无经过独立任务质量门的自动进化。
- DeepSeek Harness 已用于规划、证据选择与综合的有界语义交接；这里的训练轨迹来自 SSS 本地工具运行，不能称作真实 DSH Agent 轨迹自动学成的 Motif。
