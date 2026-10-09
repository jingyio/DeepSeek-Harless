# 首发历史 Motif 库结构验收

- 日期：2026-10-09；macOS，本次本机诊断，无新增付费调用。
- 目的：同学取得 main 后，不需要旧 `.local`，即可加载、重编译和调试已有 Motif；服务后续科研场景开发，不直接交付研究结论。
- 产物：`examples/motif-library/research-portfolio-v1/`；入口 `npm run motif:check` / `npm run motif:rebuild`；源码与配置版本以本次提交及该目录 `files.lock.json` 为准。
- 来源：历史 `deepseek-flash`/`reasoning_effort="off"` 的 2 项训练决定与 1 项独立认证决定，26 次请求有本机账本记录。四个算子的原认证摘要和 library 摘要保留，当前重新挖掘编译一致。原始账本不分发、不等同账单实付；模型配置、历史 commit、文件摘要和划分见 `provenance.json`。
- 数据：portfolio v1 公开合成科研来源。历史目录名字带 v2，按题面哈希核对后仍属于 v1。分发的是经实际 MCP 比对的 46 次工具证据夹具；重新冻结公开身份，原始身份摘要只作出处。不存在私人论文、原始日志、密钥或本机绝对路径。
- 配置：Node Harness `@deepseek-ai/dsh` / `dsh-llm` 0.1.5-rc.3，Python SDK 0.1.5rc1，MCP 2.2.0；工具集合/顺序取 `scenarios/portfolio-v1/scenario.json`；插件使用当前 `.mjs` 在线子集。`l_retrieval_persistence` 没有进入训练/认证。当前 Provider 为本机脚本，embedding 为固定向量传输夹具，阈值 0.8/0.1，输出上限 1000，模拟 Provider 上限 24 次请求；配置及会话隔离，`reasoning_effort="off"`。

| 组别 | 本机 Provider 请求 | 工具调用 | 经结果验证的跳过批次 |
| --- | --- | --- | --- |
| baseline | 14 | 13 | 0 |
| shadow | 14 | 13 | 0 |
| execute | 7 | 13 | 5 |
| execute，旧版本快照 | 14 | 13 | 0 |

四组均返回相同的四个来源对象及版本清单。shadow 只报告候选；execute 以实际工具结果完成为准；旧快照拒绝复用并回到模型端口。批次可包含多个调用，不能把批次数、工具数和请求差互换。

- 验证：当前工作区通过 136 项 Python、29 项 Node 回归；公开 MCP 重放、库/manifest 哈希、独立身份与重新编译一致通过；其他安全回归覆盖篡改、schema 变化、错误会话、工具失败和返回版本变化。18 题 smoke 保留为独立工具诊断。没有模型生成的科研报告、人工盲评或真实 embedding 匹配质量评测。
- 费用与耗时：新增付费 API 请求 0；不提供估算节省或账单结论。当前本机模拟服务速度无研究效果解释价值。人工科研修订时间未测，旧实验报告质量未在本次重评。
- 结论：支持这份历史结构库可在当前协议中重编译及受守卫执行；不支持真实科研质量或降本主张。后续换 MCP 应从新轨迹和契约编译，不能仅替换工具名称；真正科研验收须另行固定任务、预算和盲评。
