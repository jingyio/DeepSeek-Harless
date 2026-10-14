# RSI 生成的局部修订程序

这个纯JSON AST由真实DeepSeek Harness根据两条正常修订轨迹生成，未人工改写算法。它接收当前key/数组位置及模型本次计划，输出标识替换、倒序删除和最小占位追加。不同任务从当前报告重新定位行，不记住历史路径或科研结论。

- `candidate.generated.json`：实际认证程序与schema。
- `diagnostic-cases.json`：18个合成独立变体，覆盖空数组、多个重复key、两位数位置、替换/删除/追加；不含私人论文。
- `provenance.summary.json`：匿名来源与生成/认证摘要，不授权自动执行。

模型决定修订什么；工程宿主限定可改字段、拒绝冲突版本、校验版本并应用操作。完整原字段写入本任务副本，报告排版由工程渲染器完成。初次49个生成请求包含失败与修复，不能把它说成单次成功或整体净收益。

```sh
node --experimental-strip-types scripts/check-trace-rsi-tool.mjs examples/rsi-tools/report-patch-v1/candidate.generated.json examples/rsi-tools/report-patch-v1/diagnostic-cases.json
```

完整正常轨迹、认证和可运行库保留在私有`.local`；本公开样例不能单独加载为生产Motif library。真实Shadow/execute对照与边界见[实验记录](../../../docs/experiments/paper-rsi-local-patch-execute-20261012-v1.md)。
