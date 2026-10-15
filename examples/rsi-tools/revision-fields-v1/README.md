# RSI 生成程序中的字段保留检查

这是从 DeepSeek 已生成的候选中原样提取的字段检查及其变量绑定。原学习运行 `paper-rsi-revision-shadow-20261011-v6` 被人工中止；选中的完整候选开发测试有两项失败，不能标记为成功。失败来自另一个重复计数输出。编译器保留以下局部能力，并另外验收：

| 输出 | true 的含义 |
|---|---|
| existing_fields_preserved | 当前已有 key 的每个对象，除允许修改的 arxiv_id 外，其他字段完整匹配修订前该 key 的某个版本 |
| top_level_preserved | references 之外的报告字段、值和数组顺序完整保留 |

第三个输出 `changed_existing_records` 直接导出模型原程序已经计算的 `mismatched` 变量，列出违规的当前对象；没有另外写一套差异算法。例如下面的 URL 顺序变化样例会返回该条目，单独改变 arxiv_id 或顶层字段不会返回它。模型可以据此对照 before_report 中同 key 的旧对象修复，仍需处理真正的旧版本冲突。

例如原条目 `source_urls=["source-one","source-two"]`，修订后只修改 arxiv_id 时第一个检查通过；将两个 URL 的顺序颠倒时失败。工具不写文件，不修复内容，也不核验 URL 指向的文献真实性。修复和冲突判断仍交给模型。

重复 key 可能对应多个不同的旧对象；程序不会强制选第一份。新增缺失条目不属于“已有字段”比较，另由覆盖检查及独立占位验收约束。来源版本、当前句柄和报告字节变化时，在线绑定重新核验。

提取后的两个布尔输出在 14 个开发样例、21 个原学习会话未见的独立派生样例中全部一致。导出违规对象时重放了同一批样例，不能再算一批新独立认证。这只是同论文的结构检查，不是跨论文或科研事实认证。当前闭合 schema 不接受的字段或类型会拒绝输入并交回模型，不能将拒绝说成保留检查通过。`pairs_without` 的通用宏展开、解释器与验收器由工程提供，具体比较结构由模型生成。

`candidate.generated.json` 可阅读和免费运行；`provenance.summary.json` 保留来源摘要。公开材料未包含私人输入、原始轨迹或完整冻结见证，不是可直接加载的认证库。

```sh
node --experimental-strip-types scripts/check-trace-rsi-tool.mjs examples/rsi-tools/revision-fields-v1/candidate.generated.json examples/rsi-tools/revision-fields-v1/diagnostic-cases.json
```

完整组合工具及 Shadow 结果见[实验记录](../../../docs/experiments/paper-rsi-revision-counts-20261011-v1.md)。
