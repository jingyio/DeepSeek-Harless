# Distil 与 SSS 的同题对照：接入和试跑记录

更新：2026-09-26。此文件区分接入验证、离线诊断和付费任务效果；**已做开发诊断试跑，但尚无 Distil 或 SSS 的同题合格交付成绩**。

## 固定实现

- Distil：`dshakes/distil` commit `e836dc1540dd390823b26582ad137f73072d6871`，Apache-2.0，本机只读克隆在 `.local/distil-upstream/`。已有源码分析见 `上下文插件与SSS创新边界核查.md`。
- DSH：项目已安装的 `@deepseek-ai/dsh` `0.1.5-rc.3`，官方 `deepseek-official` 适配器。其 `DEEPSEEK_BASE_URL` 可将隔离会话指向本地代理；共享 Web Harness 的配置与进程不改。
- SSS：当前迁移的 MotifAgent 读取／证据状态、局部复用、选证据和语义 handoff。它尚未让 Motif 状态机接管全部顶层科研任务步骤，不能称为冻结论文中的完整执行器。

Distil 在 DSH 与 DeepSeek API 之间处理消息上下文，利用可恢复摘要和 `distil_expand`；SSS 在任务执行侧管理来源版本、节点依赖、结构复用和语义交接。两者可以正交，但**不能预设效果正交**。第一轮至少比较 DSH+Distil 与 SSS+DSH，普通 DSH 为参照；有条件再测 SSS+Distil。

## 已完成的无付费验证

1. `scripts/run-distil-dsh.py` 在隔离子进程启动本地 Distil 代理，并仅给子进程设置 `DEEPSEEK_BASE_URL=http://127.0.0.1:<port>/v1`。`/v1` 是必要的：DSH 追加 `/chat/completions`，而 Distil 对不带 `/v1` 的该路径只会透传。[DeepSeek 官方 WorkBuddy 接入文档](https://api-docs.deepseek.com/quick_start/agent_integrations/workbuddy/)也直接使用 `/v1/chat/completions`。默认 `full` 保留 Distil 自己的 shadow 与输出策略；`--distil-profile context-only` 关闭两者以单测上下文压缩。两种模式都启用原文恢复。`--no-record` 避免 Distil 缺 DeepSeek 价格表时把本地节省账本误按 Claude 计价；真实总费用以 DeepSeek 用量和账单核对。每次试验使用独立 `DISTIL_HOME`，避免前一场测试的找回反馈改变下一组的压缩策略；后续研究自改进时才明确传 `--distil-home` 保持训练状态。
2. `tests/test_distil_dsh.py` 用本地假服务验证：长工具结果在 `/v1/chat/completions` 路线上确实变短、请求带 `distil_expand`；真实 DSH SDK 的 `deepseek-official` 适配器经过该代理；模型请求内容恢复触发的**第二次上游请求**也被预算闸门计入。测试不连接 DeepSeek。
3. `scripts/replay-distil-dsh.py` 只读回放已保存的 MGGA 原生 DSH 轨迹：46 个文本工具结果中 24 个发生变更，4 个图像块未进入文本压缩；文本总量 68,387→11,480 字节，Distil 启发式估计 19,658→4,297 token，24 个恢复 handle 均可解析。**这是每个结果单独压缩一次的资格诊断**；没有重演模型请求、缓存、恢复请求、最终回答或费用，因此不能声称真实节省 78% 或质量相同。私有逐项数据在 `.local/distil-sss/offline-replay.json`。
4. 同一 MGGA 阶段 A 的 PDF 与三份原始 JSON 已给 SSS 读取预览；4 个文件哈希与原生 DSH 基线 manifest 完全相同。通用 JSON 源按顶层数组记录定位。新发现的数值缺口已用通用、源哈希绑定的数值摘要补上：只有字段在所有记录中都为有限数值时才确定性地计算分母、和与均值；摘要标明是从哪些原始记录推导，不能伪装成原文页面。修订后的解析器形成 104 个原始来源片段和 3 个派生摘要片段，每份 JSON 另有可机器复算的私有数值账本。无法自动判断某字段是否应该解释为成功率，仍由语义层和人工审核。历史增量预检释放原有审查说明后，Motif 来源状态复用旧 4 份、读取新增 1 份，模型请求为 0。对应状态保存在 `.local/point-research-runs/`。这只证明输入对齐、数值计算和局部恢复，不证明科学结论正确。
5. `src/adapters/deepseek_cost_gate.py` 已放在 Distil 代理上游。它按 DeepSeek **峰时、未命中缓存**价格和每次请求的 UTF-8 字节数／每张图像最多 1,024 token、最大输出预先占用预算；超限在转发前拒绝。Distil 内部追加的恢复请求也经过该闸门。[官方文件接口](https://api-docs.deepseek.com/guides/files_api/)免费，闸门允许有界图像文件上传，并在后续引用图像的模型请求中计入 token 上界。相同闸门可用 `scripts/run-distil-dsh.py --mode plain` 给 SSS／普通 DSH 使用。假模型测试确认两种路径都能转发，且 plain 路径不注入 Distil 工具。实际费用仍须依提供商账单核对；保守占用可能使试验提前停下。

## 付费同题试验的冻结方案

研究问题沿用已有 MGGA 开发诊断：Figure 7 的 ReAct 柱与原始运行如何对应，终稿基线表如何标注及限定主张。阶段 A 只读投稿 PDF 与三份 2026-08-31 原始运行 JSON；阶段 B 在 A 交付后释放 2026-09-21 的真实审查说明。无相关邮件或会议，Gmail 与日历不适用。全部源文件哈希、问题和三项必答点已保存在 `.local/distil-sss/mgga-stage-a/`，私人内容只留 `.local/`。这项题被用于方法开发，不算独立留出正式成绩。

| 组别 | 模型与控制 | 必须记录 |
| --- | --- | --- |
| 普通 DSH | 现有原生结果作为诊断参照；若要量化归因，按下两组的相同 Flash 推理设置重跑 | 完整工具轨迹、用量、人工提示与修订 |
| DSH + Distil | DSH 自主选工具，Distil `full` 代理压缩上下文、原文恢复并保留其默认质量抽样；`context-only` 作消融 | DSH 请求、Distil 内部恢复与 shadow 请求均计入费用；压缩、扩展、错误与延迟 |
| SSS MotifAgent + DSH | Motif 来源和参数依赖先执行；明确的规划、选证据、综合缺口交 DSH | 结构跳过、守卫阻断、语义请求、来源失效和 B 阶段复用 |

新两组均用 `deepseek-flash`、同一推理设置、相同资料与输出质量门。既有原生基线用了 Flash 高推理和一次 Pro 审核，不能直接与默认关闭推理的 SSS 请求作因果成本比较。不得按模型请求少或启发式 token 少直接宣布胜出。评审先核对三组数值、ReAct/ReAct-ACT 区分、图表映射证据、引用与未决项；再记录合格率、账单费用、人工修订分钟、端到端时间、增量错误沿用和恢复次数。两名领域评审及争议仲裁规则沿用 `同题调研盲评与总成本协议.md`。

两组运行入口已经做好**免费预览**：`scripts/run-distil-mgga-trial.py` 保存 Distil 组的冻结来源、阶段 A/B 提示与 100 次 DSH 请求上限；`scripts/run-sss-mgga-trial.py` 对同样四份资料使用已编译并通过独立轨迹认证的来源读取和跨源检索 Motif，预览确认来源哈希相同。SSS 每阶段最多三个有界语义请求。两组均只在阶段 A 材料产出后释放真实审查说明；执行结果落 `.local/`。付费入口都要求本地预算闸门；SSS 组用 `plain` 模式，防止 Distil 混入自身结果。

**用户已确认单次试验预算：Distil 组 US$5、SSS 组 US$2，合计 US$7。** 按 [DeepSeek 当前峰时价格](https://api-docs.deepseek.com/quick_start/pricing/)在每次转发前保守占用，超过各组上限即拒绝；Distil 的扩展与 shadow 请求也经过同一闸门。两组都限制单次输出最多 3,000 token；Distil 组另限 DSH 可见请求 100 次、累计观测输入 600 万 token。未启用 Pro。

下列初次付费命令已经执行；SSS 因暴露的失败又在其原 US$2 累计上限内做了重入与修订版开发试跑：

```bash
.venv312/bin/python scripts/run-distil-dsh.py --budget-usd 5 -- \
  .venv312/bin/python scripts/run-distil-mgga-trial.py --call-model
.venv312/bin/python scripts/run-distil-dsh.py --mode plain --budget-usd 2 -- \
  .venv312/bin/python scripts/run-sss-mgga-trial.py --call-model
```

## 2026-09-26 开发诊断实测

| 路线 | 请求与时间 | 交付状态 | 费用可见范围 |
| --- | --- | --- | --- |
| 原生 DSH 历史参照 | 45 Flash + 1 Pro；有操作员续跑 | 阶段 A/B 材料已生成，研究者质量待评 | 估算 US$0.1122；实际账单待核 |
| DSH + Distil `full` | DSH 可见 Flash 100 次，代理上游合计 107 次；254 秒 | 阶段 A 达到预设请求上限，未生成可审阅答案；阶段 B 未开始 | DSH 可见 100 次按非峰时价格估算至少 US$0.0440；7 次代理内部请求的实际 token 未被旧账本记录，不能报完整费用。峰时保守占用 US$4.5281，不是实扣 |
| SSS + DSH 初版 | 失败的阶段 A 3 次、重入 1 次、阶段 B 3 次 | 阶段 A 综合输出曾被 1,800 token 截断；提高上限并复用规划/选证据后，A/B 均为不完整答案 | 7 次请求估算 US$0.00455；峰时保守占用 US$0.04178 |
| SSS + DSH 修订版 | Flash 6 次；22 秒 | 三份 JSON 的数值汇总进入有引用的材料；A/B 仍为不完整答案，图柱与终稿决定需人工补证 | 6 次请求估算 US$0.00477；峰时保守占用 US$0.03852 |

修订版是在看到初版失败之后改的开发迭代，不能与 Distil 初次试跑当作预注册的公平效果成绩。三组工具入口、提示、推理设置和人工监督也不完全相同；尤其原生 DSH 历史参照开启了较高推理并使用 Pro。两名领域评审尚未确认任何交付合格，人工修订分钟数也未测。**不能据此声称 SSS 以更低成本完成合格任务，或断言 Distil 本身导致了 100 次循环。**

修订针对真实缺口：原结构最多选两个来源，无法核对三组原始运行；高分原始记录挤掉了已计算的派生汇总；证据打包在总长度较大时又截掉部分汇总字段。现在支持最多四个独立来源，保留每个匹配 JSON 来源的数值摘要，并在证据打包时保留完整摘要。无模型预览另生成 `verified-numeric-ledger.json` 与可直接审阅的 `.md`，将确定性计算与模型写出的数值结论分开；它们的来源 SHA-256 和记录范围均可核对。对应私有账本与运行轨迹保存在 `.local/distil-sss/` 和 `.local/point-research-runs/`。修订后无模型预览可同时看到三组记录的成功、token 和调用量；相关无模型测试通过。

初版另暴露了综合回答被截断后需手工拼接重入输入的问题。现在 `research-points.py --resume-synthesis-from <失败运行目录>` 只接受同一研究问题和必答点、来源文件哈希未变、且明确停在综合阶段的运行；它重验来源与 Motif 决策状态的一致性，复用已验证的规划、候选指纹和选证据结果，记录父运行与丢弃的错误模型输出哈希，只把综合缺口重新交给语义层。所有使用通用 DSH 语义端口的付费请求都须经过隔离预算闸门，不能把直连提供商的地址冒充预算内调用。用同题四份真实来源和一个故意截断的本地综合回复做无模型端到端诊断：失败正确停在综合阶段，重入预览恢复了 4 份来源和检索状态、产生 14 条可核查片段，模型请求数为 0；不经过预算闸门的付费重入在调用前被拒绝。此诊断验证失败恢复边界，**不是合格报告或成本收益成绩**。

增量轮次中，SSS 的来源层复用了旧 4 份并读取新增 1 份，但检索快照、三项证据选择和综合判断全部失效重算。这次真实新审查说明可能影响所有三项问题，保守失效是合理的；本例没有证明更细粒度的增量节省。Distil 在阶段 A 停止，因此没有增量结果。

当前闸门已加上**上游响应 usage 的内容无关记录**，今后的 Distil 内部请求可计入输入缓存命中/未命中和输出 token；这项补丁在本次运行结束后加入，不会补出旧 7 次请求的用量。真实 DeepSeek 账单没有可归因的导出，本次只能给估算与保守占用，不得将它们写成实扣。

## 后续门槛

1. **研究者质量判定**：原生 DSH 的 Flash 与 Pro 对最终图柱选择有实质分歧，`native-dsh-baseline-preview/trial-report.md` 尚标记“待评”。这不妨碍开发试跑，但所有质量/成本结论必须等评审。
2. **质量与成本对齐**：需要研究者裁定原生 DSH、SSS 修订版的事实和引文；Distil 组需要在新冻结任务和相同条件下重测才能评估其上下文压缩对质量的影响。再次付费试验须重新固定预算。
3. **费用边界**：`distil_expand` 可在代理内部再次请求模型，DSH 的 `step/start` 计数看不到这类额外请求。上游预算闸门已接通并做本地假服务测试；正式试跑仍需确认当日价格，并按账单核对。源代码内固定的峰时价格是 [DeepSeek 官方价格页](https://api-docs.deepseek.com/quick_start/pricing/) 2026-09-26 所列 Flash 输入未命中 $0.30／百万、输出 $1.20／百万，以及 Pro $1.32／$3.96。
4. **完整性**：当前 SSS 研究入口只对来源读取、局部复用和有界语义交接使用迁移的 Motif 核心，顶层调度未完全迁入；正式报告须按实际覆盖范围命名，不把该组冒充“完整 MotifAgent”。

无付费复查：`.venv312/bin/python -m unittest tests.test_distil_dsh tests.test_deepseek_cost_gate tests.test_motif_research_sources -v`；两条运行入口不带 `--call-model` 即保存免费预览。每次预算账本的独立路径由代理入口打印，保留于 `.local/`。
