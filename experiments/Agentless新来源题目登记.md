# 新来源固定题：Agentless 的仓库修复流程

> 2026-09-24，在本题任何模型调用前登记。论文为作者发布的 [Demystifying LLM-Based Software Engineering Agents（FSE 2025）](https://lingming.cs.illinois.edu/publications/fse2025.pdf)，本项目此前未用它开发研究流程。下载的 24 页 PDF SHA-256 为 `e780f7ccaa72815c259b3d3810e467eb9abe02f804010eded52b4babda121301`。两组共同使用只含原 PDF **前 10 个物理页**的抽取文件，SHA-256 为 `1aa79470e864cbcdbf3328e5ee9d801a7a7dd867e36519beb2d7ab635088e361`，存于被忽略的 `.local/benchmarks/agentless/reference/Agentless-main.pdf`；页码与原 PDF 前 10 页一致。为制定人工评分已读 pp.6–10，这是新来源开发验证，并非严格盲评。

固定问题：**Agentless 如何在不依赖代理自主工具决策的情况下，依次定位需要改动的代码、生成候选补丁，并用测试挑选最终提交的补丁？** 只据固定来源回答，给每项物理页码。七项人工验收标准见[JSON 清单](Agentless修复流程必答点.json)。逐项分为直接、部分、缺失；凡涉及先后顺序、过滤或回退条件，漏掉条件只算部分；引文存在不自动代表结论正确。

两组都用 `deepseek-flash`、非思考模式、无模型工具调用、同一问题与七项清单。两组先预览，再各运行一次；不为修分调词或追加付费重试。

1. **一次调用检索脚本**：人工关键词固定为 `repository structure,embedding,skeleton,edit locations,Search/Replace,reproduction test,Issue reproduced,regression tests,Issue resolved,majority voting`。每来源最多取 10 页，每项可以引用共享候选池；综合最多 1,800 输出 token。
2. **逐项结构流程**：每项先规划检索词，结构层核验候选页，模型按项选页，运行时重验哈希并在 10,000 字符原文预算内打包/复用来源片段，综合最多 1,800 输出 token；规划与选页各最多 900 输出 token，总共至多 3 次调用。同页候选 ID 归一仅在来源、页码、哈希完全相同且映射唯一时允许，并保存审计记录；其他越界选页仍停止。

记录两组逐项质量、完整请求数与失败费用、未缓存/缓存输入、输出、API 估算费用及人工准备。模型输入/检索策略不同，所以本题只诊断产品流程，不直接证明图表示相对脚本的因果增益。两组都未合格时，不计算合格任务节省率。WorkBuddy 免费版因内部用量不可见，不与 API 费用作精确换算。
