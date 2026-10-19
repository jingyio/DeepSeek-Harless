# 文件管理原生接口：原始学习 Motif

此包逐字复制真实 DeepSeek 普通轨迹学习并独立认证的当前兼容政策。IR 为 operation graph v2；材料和交付标准为 `sss-management-quality-v3`。本轮公开一张 `pin_files → read_files` 数组参数图，支持同一任务的多次局部读取与多个文件绑定。语义选取文件由普通 Harness 完成。

`catalog.json` 记录原认证摘要、独立任务指纹、实际执行审查摘要和源码锁；`files.lock.json` 校验原政策字节。失败候选和已失效政策保存在私有原记录，不能重新签名来伪装通过。此包默认不激活；私有原认证证据不进入 Git，公开摘要不能代替生产权限或原认证链。

免费检查：

```sh
node scripts/check-operation-library.mjs --bundle examples/motif-library/management-v3-native --require-runtime
```

日常入口使用服务端持久化经验库自动检索、发现、学习、认证和复用。公开包可供前端团队核对协议和部署所需源文件；新环境应在自己的授权、材料和冻结验收程序下重新认证。全流程费用、失败与实际收益记录见 `docs/experiments/management-native-20261015.md`。
