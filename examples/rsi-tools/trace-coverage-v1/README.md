# 从真实轨迹学习出的覆盖检查工具

`candidate.generated.json` 是 DeepSeek 在 `paper-rsi-trace-tools-20261011-v3` 中生成并修复的原始纯数据程序，没有人工改写算法。候选摘要为 `610ce5ded7c551e7ab90da8fd9559b7e6c4efa949a0652b7bc2b900b528d19c6`。程序仅包含通用字段名、运算和缺失占位，不包含私人论文条目、旧结论或来源材料。

它把历史 bash 中的一段检查内化为 `triage_catalog_coverage`：

1. 用目录记录的文件名，将查询项对应回引用键。
2. 比较查询键与报告键，返回缺失、多余及覆盖是否一致。
3. 比较报告中的 arXiv 标识符与目录记录，列出不同的值。
4. 返回当前引用问题的类型序列。

输入的四组数组分别为 `triage_references`、`catalog_query_items`、`catalog_cited_records` 和 `citation_issues`；没有固定文献数量。目录里没有对应标识符时用 `(none)` 表示，**不表示论文不存在**。程序没有联网核验真实性，遵循的是所选原脚本的行为。

`diagnostic-cases.json` 是为公开阅读单独制作的两个合成样例，标识符都是占位。第二个样例应返回缺失 `ref_b`、多余 `ref_c`，以及两项标识符差异。它们不是私人训练/留出资料，也不能冒充独立论文认证。

```sh
node --experimental-strip-types scripts/check-trace-rsi-tool.mjs \
  examples/rsi-tools/trace-coverage-v1/candidate.generated.json \
  examples/rsi-tools/trace-coverage-v1/diagnostic-cases.json
```

真实实验通过三个开发样例、12个未见源反例与MCP stdio检查；全部23个有效源反例复核一致。公开目录省略私有见证与认证文件，**不能直接作为冻结 MCP 库加载**，也不是 Motif 图。生成工具后仍须收集正常使用轨迹、编译衔接并在下一任务 Shadow 评测。

完整范围、失败与成本见[实验记录](../../../docs/experiments/paper-rsi-trace-tools-20261011-v3.md)。
