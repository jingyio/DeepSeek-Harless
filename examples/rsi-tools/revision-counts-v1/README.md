# RSI 生成程序中的可复用计数分支

DeepSeek 在 `paper-rsi-revision-shadow-20261011-v3` 中生成了一个修订审计程序，开发样例通过，但完整程序在独立验收中失败。编译器原样保留其中五个计数表达式，再把正确的初始重复计数表达式的输入从 before_report 绑定到 after_report，得到当前重复计数。没有重写计数算法，也没有把完整失败程序改记为通过。

`candidate.generated.json` 是可阅读、可独立运行的受限程序，`provenance.summary.json` 记录来源摘要。这里没有私人输入、原始日志或完整认证见证，不能作为冻结 Motif library 加载，也不授权自动执行。

例如，修订前的 key 序列为 `a,a,b`，修订后为 `b,c,c`：

| 工具字段 | 输出 | 含义 |
|---|---:|---|
| before_count | 3 | 修订前实际对象数 |
| after_count | 3 | 修订后实际对象数 |
| before_duplicate_key_count | 1 | 修订前出现两次以上的 key 有一种，即 a |
| added_key_count | 1 | 新出现的唯一 key 是 c |
| removed_key_count | 1 | 已不出现的唯一 key 是 a |
| after_duplicate_key_count | 1 | 当前出现两次以上的 key 有一种，即 c |

对象总数没有变化，但集合发生变化。重复 key 的种类数、冗余对象数与移除的唯一 key 数是不同指标，不能相互替代。当前重复计数大于零时，不能宣称已去重。这六个输出不校验字段保留、引文真实性或正式发表版本。

私有服务器验收使用 27 个未提供给原学习会话的新构造计数样例；原来 30 个留出样例只作历史诊断，不重新算作独立验收。这是同论文数据派生检查，不是跨论文泛化证明。编译器随后将这些表达式与此前通过源脚本重放验收的覆盖检查程序组合，保留双方来源与独立的认证范围。

公开两例是合成诊断，可以免费运行：

```sh
node --experimental-strip-types scripts/check-trace-rsi-tool.mjs examples/rsi-tools/revision-counts-v1/candidate.generated.json examples/rsi-tools/revision-counts-v1/diagnostic-cases.json
```

完整实验及失败记录见[实验记录](../../../docs/experiments/paper-rsi-revision-counts-20261011-v1.md)。
