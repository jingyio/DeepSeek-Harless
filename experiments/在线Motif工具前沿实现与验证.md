# 在线 Motif 工具前沿：实现与验证边界

## 目标

在 DSH 下一次模型请求开始前，尝试由已认证的只读 Motif 接管一个工具选择与参数填充步骤。候选来自历史轨迹编译的 `motif_skill_library`，不是本文件预写的场景流程。没有合格候选时原样请求模型。

## 已实现

1. `scripts/export-online-motif-manifest.py` 重新验证完整 Motif 库和工具契约，只导出非重复、至少两个节点、有独立任务验证的只读算子。对未列在工具契约中的版本字段、输入槽和非只读工具拒绝导出。
2. `src/adapters/online_motif_frontier.mjs` 严格解析结构化任务输入。正则只验证显式 ID 的格式。近期成功工具调用须与 Motif 前缀、已记录的参数来源、任务绑定和来源版本同时相符，才能成为候选。局部 embedding 相似度和跨任务支持数用于排序；低分或分差不足时回退。
3. `src/adapters/dsh_online_motif.mjs` 使用 DSH 的 `llm/stream` 插件接口。在 `execute` 模式下返回一条合规的工具调用流，不调用下游 DeepSeek stream。工具仍由 DSH 正常分派。结果版本匹配后才记录 `model_request_skipped_verified`；失败或版本变化记录为未验证，并由后续模型步骤处理。日志只写 `.local/online-motif/`。
4. 默认 `shadow` 模式只记录候选，不跳过模型。没有配置文件时插件保持关闭。

## 结构化任务输入

任务 JSON 保存在本机 `.local/`，至少含 `schema_version: 1`、`task_id`、`session_id`、`intent`、`input_version`、`bindings` 和 `source_versions`。`bindings` 只接受已在导出清单 `slot_rules` 中声明正则的工具参数；`source_versions` 按工具名记录本轮允许使用的版本。插件只服务完全相同的 DSH `session_id`。

## 接入流程

1. 从独立任务轨迹生成并验证 Motif 库；准备已审核的工具契约、根参数正则和工具输出版本字段。
2. 用 `scripts/export-online-motif-manifest.py` 生成 `.local/` 清单；用 `scripts/prepare-online-motif.py` 生成 DSH 插件 patch。两个命令均不调用付费 API。
3. `scripts/run-online-motif-task.py` 接受 Motif 清单、结构化任务、原 MCP patch、研究提示及本机 embedding 端点。默认仅输出预算与输入版本预览；只有显式传入 `--call-model`，且现有本地费用代理已开启，才运行 DeepSeek。脚本自动加载生成的插件 patch，并将敏感轨迹保存在忽略版本控制的 `.local/`。embedding 端点仅允许本机回环地址。一次任务使用独立会话 ID；插件还核对唯一的人类提示及其哈希，避免旧任务状态接管新消息。
4. 先运行默认 `shadow` 模式，核查候选、版本和结果；只有同类独立任务校准阈值并评估交付质量后，才设 `SSS_ONLINE_MOTIF_MODE=execute`。可用 `SSS_MOTIF_MIN_SIMILARITY`、`SSS_MOTIF_MIN_MARGIN` 显式设置经校准的门槛。

## 当前证据与限制

- 单元及插件协议测试证明：符合条件时不会调用下游模型流，DSH 的 `BlockAssembler` 可以接受生成的工具调用；改变版本、缺失参数、无工具权限或语义分数不足时回退。
- 尚未在付费的真实跨应用科研任务上观察到经核验的跳过。现有 AIDD 与 Model RSI 轨迹不能凭空变成可执行 Motif；需要新的独立任务轨迹和完整版本字段。
- 当前在线适配器只支持非重复的线性只读 Motif，一次接管一个工具调用。复杂 DAG、列表前沿、写入工具、独立校准服务和多任务共享进程留在后续验证范围。结构化任务不代替论文相关性或研究结论判断。
- 对照实验仍须保留普通 Harness、简单脚本／缓存及 Motif 三组；统计请求数、缓存命中/未命中 token、embedding 开销、实际 API 费用、人工修订与质量。
