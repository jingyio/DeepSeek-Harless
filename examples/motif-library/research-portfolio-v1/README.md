# 首发历史 Motif 库样例

这份库来自此前 **DeepSeek Harness + deepseek-flash 的实际执行轨迹**，不是手写 DAG，也不是本次模拟模型重新生成的库。保留历史 4 个 Motif 的全部认证字段、`certified_digest` 和原在线库的 `library_digest`。

任务和资料是仓库里的**合成科研模拟**，不是真实论文或真实跨应用研究。该库用于开发、调试和协议验收；结构认证不等于报告质量合格、真实降本或产品推荐。

## 一条命令验收

在仓库根目录完成 `npm ci` 和 `npm run setup` 后：

```sh
npm run motif:check
```

无需密钥、真实模型或 embedding 服务。检查包括文件哈希、独立训练/认证身份、重新挖掘编译、Python → 在线 manifest 一致性、46 次证据调用的真实 stdio MCP 重放，以及真实 Harness 的 baseline/shadow/execute/旧版本回退。所有新请求仅发给临时回环模拟服务，使用隔离的 Harness 配置与会话，`reasoning_effort="off"`。

只重新编译，不启动模拟模型服务：

```sh
npm run motif:rebuild
```

重新编译必须得到与分发库相同的产物，否则失败；不会自动覆盖仓库样例。结果在 `.local/motif-example/rebuilt/`，验收摘要是其中的 `acceptance.json`。无需旧 `.local` 的任何历史文件。macOS 已验证，Windows/Linux 仍以实机及 CI 结果为准。

## 库里有什么

| Motif | 参数依赖 | 结构职责 |
| --- | --- | --- |
| `edge_motif_f34281780aec` | `pin_resource.source_id → read_pinned.source_id` | 读取已固定版本 |
| `edge_motif_4050d9804b03` | `read_event.root_object_id → pin_resource.object_id` | 固定事件发现的主对象 |
| `edge_motif_2ae59e5055e0` | `read_pinned.value.link_0_object_id → pin_resource.object_id` | 固定第一项已发现关联 |
| `edge_motif_219937bf0a51` | `read_pinned.value.link_1_object_id → pin_resource.object_id` | 固定第二项已发现关联 |

工具名均带 `mcp__research_portfolio_fixture__` 前缀。后两项不是授权盲目追随任何链接：在线执行仍检查契约、发现结果、当前任务允许的对象及版本。`object_lookup` 的目标对象有自己的版本，不能把来源文档的版本当成目标版本。

所有节点与参数边由历史轨迹挖掘得到；重编译只给已挖出的 `pin_resource.object_id` 边补充契约规定的 `object_lookup` 版本关系，没有预写候选图。新场景须收集自己的轨迹、工具 schema/契约和独立验证任务，不能直接把这份库的工具名替换掉就宣称迁移完成。

## 出处与证据

| 划分 | 决定 | 历史模型请求数 |
| --- | --- | --- |
| 训练 | `l_state_update` | 10 |
| 训练 | `r_label_policy` | 8 |
| 独立认证 | `c_protocol_conflict` | 8 |
| 当前运行验收 | `l_retrieval_persistence` | 使用本机模拟 Provider，未加入训练/认证 |

历史模型与记账记录为 `deepseek-flash`、`reasoning_effort="off"`；请求数有逐请求账本对应。原账本和完整日志仍留在私有运行区，没有分发，也没有把代理记录说成实付账单。

历史目录名是 `research-portfolio-v2`，但其三项训练/认证题面的哈希实际匹配 **portfolio v1**；因此本样例按真实语料命名为 v1。来源记录见 `provenance.json`，包括历史代码 commit、原始文件哈希、模型配置和划分。哈希提供出处定位，不是可独立验证云服务身份的签名。

`evidence/` 是从原轨迹整理出的**公开工具证据夹具**，不是原始运行日志。仅保留成功的工具调用与返回；调用 ID/序号标准化、JSON 排序，删除会话、路径、模型回答、遥测及提示。每个返回都先与现有公开 MCP 重放比对一致。夹具重新冻结了身份哈希；旧原始事件/身份哈希只作为出处保存在 `provenance.json`，不能混用。

`files.lock.json` 锁定证据、库、manifest、任务、场景、契约、服务及相关题面/来源。改变输入后应重新认证和版本化，不能只修改摘要让检查通过。更新编译器或运行时时保持此样例为兼容回归；需要变更协议时发布新版本并说明旧版本行为。

## 如何加载到场景入口

`library.json` 供离线检查，`online-manifest.json` 才是当前插件加载的在线产物。`task.json` 对应第四项独立验收任务，并固定该题的来源版本。先预览：

```sh
npm run scenario -- --scenario scenarios/portfolio-v1/scenario.json --case l_retrieval_persistence --mode shadow --manifest examples/motif-library/research-portfolio-v1/online-manifest.json --task examples/motif-library/research-portfolio-v1/task.json --embedding-endpoint http://127.0.0.1:8123/v1/embeddings --embedding-model YOUR_LOCAL_MODEL
```

预览不启动付费模型，也不要求上述 embedding 服务已运行。真实任务运行前要提供真实本机 embedding 服务、审阅预算、为每次运行设置新 `session_id`，并明确授权 `--call-model`；本次没有进行这样的付费运行。执行模式通过 `--mode execute` 切换。不要把本样例的模拟 embedding 向量用于真实科研判断。

## 本次验收能说明什么

本机模拟 Provider 的职责是走完整工具协议、收集新鲜证据后返回对象/版本清单，**不回答科研问题**。模拟 embedding 使用固定向量，只验证匹配接口和参数/版本控制，不能证明语义匹配质量。

2026-10-09 macOS 验收：四组均取得相同的四个来源对象/版本，执行 13 次工具调用；baseline 为 14 次本机 Provider 请求，shadow 为 14 次，execute 为 7 次并记录 5 次经结果验证的批次跳过，旧版本组恢复到 14 次且不跳过。一次批次可包含多个工具，所以工具调用数、批次跳过数与请求差不能直接等同。

额外回归覆盖 manifest 篡改、工具 schema 变化、错误会话、工具失败和返回版本变化。实际资料变更仍需在具体 MCP 中核验；旧快照拒绝检查不是新科研决定的正确性测试。上述请求差仅是协议诊断，不是实际费用节省结果。
