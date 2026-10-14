# 文件管理学习库公开分发 2026年10月14日

用户明确恢复了将已学习 Motif 库上传 `feature/rsi-research-agent` 的授权。本次仅发布库、公开来源索引、完整性检查和交接说明，原 `.local/` 忽略规则与全部私有产物不变；此前暂不推送的记录属于当时授权范围。

公开入口为 `examples/motif-library/file-management-v1/catalog.json`，格式 `sss-public-file-management-library-v1` / schema 1。`files[]` 使用包内相对路径、原始文件 SHA-256、kind、历史/最新认证状态、原实验及 protocol 哈希；manifest 通过 `paired_library` 绑定原库。`runtime_groups` 保留认证服务版本及逐文件源码依赖，`runtime_validators` 记录现有加载校验器的实际字节。`default_activation=false`；索引是分发/兼容信息，不是新的执行权限或自动选择策略。

15 份原样 JSON：9个库/策略、3个 manifest、3份认证/冻结摘要。重复产物通过 aliases 关联，不重新生成学习结果或摘要。在线 manifest 是原完整 artifact 的投影，不能把其 `certified_digest` 当成投影的自签名。目录哈希锁另行绑定所有公开内容。检查器验证原库与 manifest 关系、原 G4 认证锁、指纹角色分离，并调用已提交的 TS 校验器；源码不兼容单列报告，显式 `--require-group` 时失败。

本次没有修改公共 Harness、MCP、IR 或默认运行模式。G4 新工作流服务及持久化任务接入仍是本地未提交开发，不能宣称只下载此库就可执行新流程。原 SDK/Web 默认、任务授权、预算、版本守卫和失败回退要求继续适用。固定脚本库不包含在此 Motif 分发目录。

验证结果与推送状态见 [库 README](../../examples/motif-library/file-management-v1/README.md) 和当前交接。此次无云模型调用、费用0；失败/负面结果没有删除，原产物与逐步发布审计留在 `.local/motif-publication-current.json` 指向的独立归档。
