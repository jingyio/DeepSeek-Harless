# Management v4 本地认证经验

2026-10-18，日常库第12版的一个当前兼容政策：`execute_plan → inspect_plan_result`。从两项新的普通 DeepSeek 整理轨迹发现，按 `sss-management-quality-v4` 使用新材料进行一次独立普通决定和两次真实结构执行认证，再在 SDK 新任务与原生前端各验证一次自动复用。最终留出集未参与学习。

政策保持原始字节，公开原认证摘要及运行时源码锁，不重签旧版本。旧 `management-v3-native`、`management-v3-cross-volume` 均保留；当前源码变化使旧包失效，不代表旧经验被删除。

```sh
node scripts/check-operation-library.mjs --bundle examples/motif-library/management-v4-local --require-runtime
```

公开包默认不自动激活，不携带私有执行授权、原始日志、用户文件或凭证。新环境按自己的材料、权限及预算独立认证。私有日常库继续自动检索、学习和认证；此公开包不能替代完整私有备份。两项失败候选及全部学习成本见[本轮实验](../../../docs/experiments/management-local-20261018.md)，不以局部复用宣称总体净收益。
