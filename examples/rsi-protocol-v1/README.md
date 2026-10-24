# F02：同一个局部操作怎样换任务使用

完成本例可以看到：两种完整任务共享一个“按组汇总”操作；系统在当前证据和权限合格时实际执行，条件失效时停止并解释原因。

- 任务 A：为科研实验报告按组统计观测数量。
- 任务 B：为活动报名汇总按组统计人数。
- 共享的只是局部计数操作。研究解释、报名状态判断和最后写报告仍需要当前任务自己的决定。

这是公开合成数据的协议开发诊断。算子由人工定义，样本不构成自动挖掘、独立科研任务泛化或降本证据。演示不会改正式服务、原有认证库或外部应用。

```sh
npm run rsi:demo
npm run rsi:check
```

A 的输出为 `control:2, treatment:1`，B 为 `poster:1, workshop:2`。改版本时显示 `evidence_invalidated`，撤销权限时显示 `permission_denied`，没有当前必要性时显示 `semantic_obligation_missing`；这些分支不派发程序。

先读[简短说明与接口](../../docs/rsi-protocol-v1.md)，真实原生 Harness 结果见[本轮记录](../../docs/experiments/f02-protocol-local-20261024-v1.md)。生成的大 JSON 可由小生成器复核。新旧规则、Matcher 代码的生成分别由 F05/F08 实现；F02 先提供共同格式和校验接缝。
