# 论文 PTC 模式真实基线与原生对照

- 实验 ID：`paper-ptc-baseline-20261009-v1`；2026-10-09；关联 `paper-native-baseline-20261009-v2`。
- 状态：真实 PTC 工具链及报告补交完成；复核发现明确错误，质量未人工盲评。
- 用户要求：尝试 PTC 看效果；延续不设请求次数上限、累计 1 美元上限和本次私有非沙箱授权。此前约 0.118548 美元与 109 次请求全部继承，未重置预算。

## 问题与对照

对同一私人论文检查编译、引用和排版，不做会议合规判定。假设：PTC 能否在相同质量门槛下减少原生逐步决策成本？报告缺失、证据误读或成本上升均不能支持该收益主张。

重新从原 ZIP 建立干净工作目录，原题面字节同 v2；相同模型、输出上限、编译环境与权限。区别是工具呈现从 native 改为 ptc，并通过官方插件接入 TypeScript worker。没有专用 MCP、Motif、RSI 认证工具或手写任务 DAG，模型自行选择步骤。两模式首次均输出截断，后用字节一致的分段补交提示恢复。只做一次同一决定的探索，不是独立评测集或统计结论。

## 配置、来源与复现

代码基点 `2368235f274329be6227a8393b850633cb943da4`，有未提交改动。Ubuntu 22.04、Node 22.23.3、控制器 Python 3.10.8、原生 bash 的 python3 为系统 3.10.12；DSH 0.1.5-rc.3 / Python SDK 0.1.5rc1。两端启动接缝与预算代理哈希一致，未改上游或公共运行时。

`deepseek-flash` / `reasoning_effort="off"`，线上 thinking disabled。代理 request_limit=None、通知守卫 max_model_requests=None、累计费用 1 美元、单次输出 3000 token。关闭压缩、额外付费搜索、自动重试、标题模型；沿用本次私有 danger-full-access，不改变通用权限或现有 Web 服务。

仅在私有 patch 设置：

```yaml
- id: tools
  config:
    mode: ptc
- insert:
    - id: code-runtime
      name: '@deepseek-ai/dsh-code-runtime-worker-thread'
```

官方默认 maxParallelSubCalls=10；worker computeMs=60000、maxWallMs=600000、maxOutputBytes=67108864、maxOldGenerationSizeMb=512。worker 不是系统沙箱，不能据此宣称目录隔离。128 个实际请求均只暴露 run_code；底层工具由生成 SDK 的 tools 绑定调用。工具 schema 集合与顺序摘要一直为 `523576f78160907f73f3bf4451777459c1c917abb178800132e08b476e756e56`。

私有题面/ZIP、有效配置、请求快照、事件、各阶段账本、PDF、报告、verification.json 与 codex-audit.md 保存在两端 `.local/experiments/paper-ptc-baseline-20261009-v1/`，来源哈希同 native v2。原始报告不改写。

已执行入口（锁定，不要直接重跑；重新实验须新 ID 并累计账本）：

```sh
source .local/remote-env.sh
node scripts/project.mjs python .local/experiments/paper-ptc-baseline-20261009-v1/run.py --run
node scripts/project.mjs python .local/experiments/paper-ptc-baseline-20261009-v1/finish.py --run
```

固定 SDK 无法跨进程打开原 Session，补交为新 Session，继承此前原生与 PTC 主阶段全部 181 次及费用。记录 effective-config.json / effective-config-finish.json；代理与环境元数据各自指向本阶段实际账本。

## 结果、失败与质量

- 主阶段 72 次 HTTP 200、71 次 run_code，最终 max-tokens，指定报告不存在。编译/诊断脚本多次调试，发生字符串转义错误与失败构建；证据保留。
- 相同分段补交提示恢复后 56 次 HTTP 200、55 次 run_code，completed。报告 291 行 / 18,427 字节，主 PDF 14 页、独立辅助 PDF 3 页。报告路径 `work/artifacts/report.md`。
- 合计 126 次 run_code、148 个工具子调用：bash 118、todo_write 2、read 5、write 14、edit 1、read_image 8。124 个外层程序有子调用，20 个有多个，最多 4 个；批量不等于并发，不等于跳过模型。
- 原始脚本用不存在的 failed 字段将失败计为 0；独立复核按 isError 发现 1 次二进制 PDF 的 read 失败。shell 非零退出未必变成 isError，必须核对真实退出码。首次构建各步骤退出 1，修复后全部 0；不删除失败证据。
- 原 ZIP 以及解压目录中 34 个原始文件哈希未变，正常编译禁止 shell escape。实际生成 14 张页图、查看 5 个独立页图（8 次），8 次上传页图到 DeepSeek API；未检索文献权威资料，不等于无网络传输。
- 报告正确识别重复表格标签/标题及部分日志统计，但仍把未被当前正文引用的重复文献键声称已渲染、解释错浮动体警告、混淆 nocite 与正文引用标记，检查覆盖口径也不完整。
- 轨迹实际写入多个 /tmp 文件/固定临时实验目录，报告却声称未修改工作目录外文件；提示词没有提供可靠边界。Codex 不自动清空这些路径，避免影响其它任务。私人论文原件未改不等于所有路径约束通过。
- 质量未人工盲评、未全篇视觉验收、未核验文献真实性/科研数据，不算投稿通过。Codex 独立只查看 05/09 页及相关来源/日志，问题在私有 codex-audit.md 逐项列明。

## 费用与耗时

以下均包含各自报告补交，代理估费不是账单实付：

| 模式 | 主阶段 + 补交请求 | 新增估费（美元） | 模型阶段耗时 |
|---|---:|---:|---:|
| Native v2 | 53 + 32 = 85 | 0.0992524 | 268.077 秒 |
| PTC v1 | 72 + 56 = 128 | 0.1360066 | 372.710 秒 |

本次 PTC 请求多约 50.6%、费用多约 37.0%、模型阶段时间多约 39.0%。不含环境安装、同步、审阅、人工修订与维护耗时；不能称端到端合格总成本对照。

PTC prompt 6,291,286 token，缓存命中 6,182,272 / 未命中 109,014，输出 55,174，total 6,346,460，推理 token 0。阶段耗时 225.740 / 146.970 秒；均在真实代理/事件账本中记录。

含此前 Native/失败诊断累计 237 次，代理估费约 0.2545546 美元，低于 1 美元，剩余估算约 0.7454454 美元；实付账单未核对。重试、恢复不作为新预算。私有同步曾因混合审计文本与 tar 数据导致本地解包拒绝，随后纯归档流重传成功，无额外模型调用。

## 结论与下一步

已观察：PTC 可以在当前固定 SDK 中运行，部分程序批量组合工具；报告经补交可生成。本次没有观察到降本或减少模型决策，仍有重要质量错误。仅一次、质量未合格，不支持“PTC 普遍更差”或“原生已能可靠验收”，也不支持 Motif/RSI 收益。

下一步先封装有结构化输出的活动来源/引用/标签检查、编译退出码、字体与页图覆盖 MCP，解决临时模型脚本的转义、统计和路径边界问题。质量门槛明确并通过人工评审后，再在独立任务上对比 Native/PTC/普通脚本/Motif 的实际合格总成本。
