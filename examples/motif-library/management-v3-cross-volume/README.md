# Management v3 跨卷修复后的认证经验

2026-10-16，持久库第 11 版当前兼容的 1 个原始政策：`execute_plan → inspect_plan_result`。从新五类文件的普通 DeepSeek 决定中学习，经过新材料的一次普通决定认证和两次真实结构执行认证。认证沿用 `sss-management-quality-v3`，没有使用最终留出集。

政策字节、摘要和认证记录摘要直接导出，未重签旧政策或删除失败候选。旧 `management-v3-native` 公开包作为原认证版本留存；其源码锁不适用于本次跨卷修复。

```sh
node scripts/check-operation-library.mjs --bundle examples/motif-library/management-v3-cross-volume --require-runtime
```

公开包默认不自动激活，不包含私有执行授权、原始日志、私人文件或凭证。新部署须按自己的材料、权限及原预算独立认证。工具仍须核验真实目标、任务/源码版本、文件摘要与一次性高风险确认；政策不授予额外权限，也不选择用户未要求的文件操作。

新 SDK 五类文件任务和原生多文件整理任务均交付合格、各验证跳过一次模型请求。完整建库、失败认证和复用成本见 [实验记录](../../../docs/experiments/management-native-20261015.md)；不能用局部跳过次数证明总体净收益。
