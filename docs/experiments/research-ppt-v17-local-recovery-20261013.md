# V17：失败草稿局部恢复的真实交付结果

本轮一对真实任务都交付了15页可编辑PPTX和实际PDF/PNG。宿主组请求32→28、总token下降28.69%、代理估算模型费下降52.50%。这些是**尚待用户质量审阅的单任务观察**，不能称为质量合格的端到端降本，也不能称新RSI收益。本轮未生成新工具、未执行Motif、未晋级候选。

## 问题、假设与任务

设计见[同轮方案](research-ppt-v17-local-recovery-20261013-plan.md)。V16恢复反复要求模型重交完整计划，使输出和后续上下文扩大。本轮保留失败草稿，让模型明确修改指出的页面/字段，检查来源、版本、非目标内容与渲染后交付；普通组沿原子步骤执行。失败或权限/版本问题不能被自动改内容掩盖。

真实来源匿名名`last-ai.pdf`，75页，SHA256 `9fde92cba4d50a38a42570c25b89fe116312f746659e560290d344ead91f7a9b`。任务是15页中文论文汇报，至少3幅不同完整原图，保留来源页和notes，区分RSI定义/层级、HCI口径、初步工业证据及其限制。两组独立阅读、选材和规划，不传递计划；这不是训练/认证任务。

- B0：普通DSH逐步生成、检查、验收、交付；宿主恢复工具禁用。
- B1：同DSH，宿主执行固定交付脚本并保留失败计划，通过显式局部patch恢复。
- 两组同来源、任务、共享提示前缀、21个工具schema及顺序、模型、模板和质量要求；组合入口两组都拒绝由模型直接选择。脚本调度及恢复能力是组间差异。

## 实际配置与定位

- 运行ID：`trial-20261013T133803Z-706a7c89`；baseline运行`912d01c173f44beeb556eaf1f58f620e`，optimized运行`dd09acfa1d0a4007b6e9f76dc7021b92`。
- 服务器项目：`/mnt/sevenT/junjiex/DeepSeekHarness-v9`。所有测试、模型、PPT生成和渲染均在服务器激活`.local/activate.sh`后执行。本机只接收和校验副本、查看预览。
- 有效快照：`.local/research-ppt/trials/<运行ID>/trial.json`、`effective-runtime.json`、两组`*-schema.json`；逐请求和工具证据在对应`.local/runs/<运行ID>/`。原始记录不提交。
- 冻结trial SHA256：`a4f3e9e891bfe9d63c8a772b58347e14c4de59ea1ae6949457e40ee338d48fca`；实际schema SHA256：`52a78383b6770f12042bebb174e59d4a550494ee31ef35378ef3d1db51d25c82`。
- 运行源码快照SHA256：`b3cfb679b5a615ecc793175c968b27d3fefc519eb49fc7cfbaa75c919e7bbfd9`，服务器Git基点`6ced8277d7743bcb260975290665af26d105274a`加未提交增量；不能把该基点当成本轮代码已发布。
- Linux/glibc2.27，Python3.12.15，Node22.23.2兼容封装，SDK0.1.5rc1，DSH/DSH-LLM0.1.5-rc.3，LibreOffice7.6.7.2；实际字体与环境哈希保留在快照，兼容封装独立来源记录未配置。
- DeepSeek官方`deepseek-flash`，`reasoning_effort=off`、压缩off；模板lab，解析缓存关闭。持久资料库仍保留来源和组件，不把库核验事件算成模型旁路。
- 两路总预算上限$1、各$0.50，40步/路、每请求最多8000输出；这是上限，不是实付。`allow_rsi=false`，无active/candidate，无embedding匹配。

新任务最短入口（默认只预览，真实运行仍需已有对应授权）：

```sh
source .local/activate.sh
python -m scenarios.research_ppt.trial --input .local/inputs/paper.pdf --slides 15 --min-original-figures 3 --template lab --budget-usd 1 --max-steps 40 --max-output 8000 --allow-output
python -m scenarios.research_ppt.trial --trial <刚生成的trial.json> --call-model
```

历史trial只运行一次；重算统计不能重新执行付费入口、改旧冻结配置或重签旧候选。

## 结果与全部成本

| 指标 | B0普通DSH | B1宿主与局部恢复 | B1相对B0 |
| --- | ---: | ---: | ---: |
| 真实上游请求 | 32 | 28 | -12.50% |
| 未命中输入token | 65,258 | 58,589 | -10.22% |
| 缓存命中输入token | 1,685,888 | 1,210,752 | -28.18% |
| 输出token | 48,594 | 14,135 | -70.91% |
| 全部token | 1,799,740 | 1,283,476 | -28.69% |
| 代理估算模型费 | $0.0880055 | $0.0418032 | -52.50% |
| 入口端到端时间 | 375.628秒 | 266.545秒 | -29.04% |
| 工具调用 | 51 | 46 | -5次 |
| 失败/不可解析工具结果 | 6 | 5 | 已计入上述费用 |
| 初始完整计划提交 | 7次 | 1次 | B1未重交整稿 |
| 局部草稿读取/修复 | 0 / 0 | 4 / 4 | 由模型明确修改 |
| 最终机械交付 | 15页通过 | 15页通过 | PPTX/PDF/15PNG齐备 |
| 科学/用户审阅合格 | 待评审 | 待评审 | 不能据此算合格总成本 |

两路合计60请求，代理估费$0.1298087。双方0上游失败、0未结算请求；失败工具和恢复过程中发生的模型请求已经包含在各自总账。独立恢复费用仍无法精确拆分，不填0。实际账单、人工修订分钟、AI辅助评审、CPU及开发维护成本未知。

总token含大量计费较低的缓存命中输入，不能按总token直接推费用。B1输出下降与免于重交整稿一致；双方阅读页数30/27、抽图6/5、选材不同，n=1也不能把全部差额精确归因局部恢复。`model_requests_skipped_verified=0`，没有认证Motif旁路；请求减少不等于发生该指标的可验证跳过。

## 汇总误判与追加校正

原`comparison.json`将B1机械交付误判为false：`PlanRecovery.repair`在宿主已完成并记录结果摘要后，追加`pending_plan`、`local_repair`、`automatic_retry`；共享`feedback_learning._host_receipt`拿最终外层回执核对内层摘要，导致不匹配。实际工具事件、宿主审计、验收checkpoint及文件已证明交付完成。

修复先要求最终完整回执与`adapter_tool`的工具名/参数/结果审计全部一致，再剥离三个指定恢复外层字段核对原宿主摘要。原策略摘要、原始参数、script执行ID及started/completed证据继续必须匹配。文件字节、验收通过、来源和目录范围仍独立校验；不能仅凭文件存在或`delivered=true`记成功。

校正为新的`comparison-corrected-01.json`、两份`*-delivery-receipts-corrected-01.json`，绑定原comparison摘要、原运行事件/账本摘要及新分析器版本。**原comparison、原配置与账本全部保留；请求数、token、费用和运行时间未改；重算新增模型请求0。** 不重签运行快照或借重算让旧候选满足新的源码锁。

之前两个未完成入口`trial-20261013T130633Z-6330d44d`、`trial-20261013T133456Z-3c141951`及日志保留，双方记录的上游请求与代理费均0。曾出现HTTP400；仅凭后续浅层schema运行成功，不能断言已独立证实DeepSeek供应商schema根因。入口故障仍造成开发/等待成本，不能计为0或删去负面记录。

## 验证、质量与用户交付

服务器日志统一为`test-logs/research-ppt-v17-local-recovery-20261013/`：已有场景构建、94项Node场景测试、根146项Python/47项Node测试及smoke通过；schema兼容修复后也保留`schema-fix-01/`复核。真实MCP局部恢复烟测有实际渲染，新增模型0。最终回执修复的`test_trial.py`/`test_feedback_learning.py`55项通过，包括缺少任一层审计、回执或参数篡改、失败验证与文件变化时拒绝。诊断测试不是科学质量证据。

两份PPT的15页PNG已查看拼图作初步版面检查，但未进行完整来源逐条核对、独立人评、PowerPoint GUI编辑或人工修订计时；密集原图的投影可读性仍需用户判断。机械交付成功与科研正确、可用演示分开记录。保持`scientific_quality=not_reviewed`，不因成本下降自动准入学习。

本机私有交付根目录：`H:/DeepSeekHarness/.local/research-ppt/research-ppt-v17-local-recovery-20261013/review/`；其下`baseline/`、`optimized/`各有`presentation.pptx`、`presentation.pdf`、15份`slide-XX.png`、`overview.png`及实际文字/notes清单。43个交付文件已逐项SHA/大小一致核验，ZIP SHA256 `5081f7aa53c887ac48e7873cbdfba96469e08f8586d8c055bc8678a23d2db911`。完整原始运行证据仍留服务器，不随代码公开。

下一步只等用户审阅、记录必要修订，再按明确通知整理中文commit并推送`feature/research-ppt-agent`，无PR。当前没有commit/push；上传范围为必要产品代码、安全回归和公开历轮报告，排除原论文、PPT、私人参考模板、密钥及原始日志。本轮不扩大实验或生成新候选。
