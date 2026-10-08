# AIDD 基线后续：PBCNet2.0 公开数据预检

2026-09-26。目标是核对 AIDD Agent 建议的第一个实务动作能否执行：先复算突变测试结果，再检查训练／测试是否存在生物学层面的相似或时间泄漏。本记录是公开数据的机械核查，不是 Motif 效果实验，也没有调用付费模型。

## 固定来源与重现方法

- [PBCNet2.0 作者仓库](https://github.com/YuJie-0202/PBCNet2.0/tree/b3563f119864e51177af363a690419214d624194)，commit `b3563f119864e51177af363a690419214d624194`。使用 `data/Mutation/` 下八个目标的 `predict.csv` 和 `Result_in_paper/2.4_section/Supplementary Data 6.xlsx`；各文件 SHA-256、目标映射保存在 `benchmarks/research_weekly_loop_v1/pbcnet_mutation_public_manifest.json`。
- [Zenodo 训练数据记录](https://zenodo.org/records/18299525) 的 `training_data_8_6.csv`，38,413,018 bytes，发布方 MD5 `6407a4a64969e8d8d9166c08b1a4e509`，本地校验一致。仓库 README 指向旧版本 `15656365`；两者属于同一 Zenodo concept DOI `10.5281/zenodo.15656364`，本次只使用有可下载索引文件的新版本。不要把不同版本数据默认为逐字节相同。
- 公开文件快照仅保存在 `.local/benchmarks/research-weekly-loop/aidd-next-preflight/public-data-preflight/`。运行 `python3 scripts/recompute-pbcnet-mutation.py` 与 `python3 scripts/audit-pbcnet-training-index.py`；两程序先核对固定哈希，完整结果分别写入同目录下的 `mutation-recomputation.json` 和 `training-index-audit.json`。

## 已核实的结论

八个目标共有 **65 对** `Label`／`pre`。对每个目标分别计算 Pearson 和平均秩 Spearman，再对八个目标做等权均值，得到宏平均 Spearman **0.529680735930736**。八组相关系数逐一匹配补充表中的缓存值，宏平均也匹配。论文的 **0.53 可以从作者公开的预测值和标签复算**；先前 Agent 因未读取补充数据而说“本次未核验”，这是当时运行状态，不再是当前证据状态。

这一步只验证汇总统计和公开预测文件的一致性。我们没有从原始蛋白／配体结构重新运行模型，也没有验证标签采集、样本选择或零样本泛化解释。

训练索引有 **85,998 对记录**、**6,983 个 BindingDB 前缀组**。八个突变目标的测试 CSV 有 65 对、73 个不同的文件名。训练与测试的完整配体文件名、绝对文件路径及测试 PDB 代码在训练索引的名称／路径中均无字面命中。两种文件使用不同命名空间，因此这个零命中只能排除最表面的同名，不支持“没有训练／测试泄漏”。

## 泄漏审计尚缺的对应关系

训练 CSV 有 SMILES、配对相似度、标签和指向 `bindingDB_...` 结构文件的路径；没有蛋白序列、口袋残基、结构沉积年，也没有将 BindingDB 前缀组映射到测试目标 UniProt/PDB 的字段。突变测试 CSV 有 PDB 代码、突变文件名、标签和预测值；仓库另有该测试集的 PDB/SDF 文件，但 CSV 本身没有可直接与训练 SMILES 比对的字段。Zenodo 还提供约 5.4 GB 的训练结构压缩包，本次未下载、未审计。

因此原 Agent 提出的四项“纸面泄漏审计”——蛋白序列同一性、口袋残基同一性、配体骨架相似度、沉积年份——**不能仅靠已下载的两个 CSV 完成**。下一步要先建立训练 `bindingDB_...` 组与蛋白／结构的可验证映射，并从公开测试 SDF 与训练 SMILES 计算配体相似度；沉积年份应回查结构来源。取得映射后再预设相似度阈值及样本单位，避免看过结果后移动判据。任何重叠只能限定该基准对“零样本泛化”的证明力，不能直接证伪用户的局部状态对象研究想法。

## MCP 工具可执行性检查

结构化科研 MCP 的 `aggregate_records` 现支持通用 `pearson_correlation`／`spearman_correlation`，输入均为 Agent 指定的两个数值字段。通过 MCP 客户端实测 `pin_source → inspect_records → aggregate_records`：`P15121.csv` 的 6 行得到 Pearson `0.3440668136892681`、Spearman `0.2571428571428571`，与独立复算一致；38 MB 训练索引可完成相同的来源固定和字段检查，`count` 返回 85,998 行。数据工具的版本编号在每次调用时重新核验来源哈希。这证明真实公开来源可使用结构化工具，但该客户端冒烟检查是人工发起，不能计为 Agent 工具轨迹或可挖 Motif。

## 对 Agent 与 Motif 实验的作用

这次修正是实际研究交付中的**后续证据事件**：早期 Agent 报告对 0.53 只能引用，补充文件到位后可局部更新为已复算；“可能泄漏”的判断仍需新的映射与语义审核。它适合作为增量失效／恢复案例，但本次人工脚本执行**不能伪称 Agent 已调用工具或 Motif 已复用**。要比较 Motif 与普通 Harness，仍需把相同资料事件交给独立任务轨迹和同等质量门。
