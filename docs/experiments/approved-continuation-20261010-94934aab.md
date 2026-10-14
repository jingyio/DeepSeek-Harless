# 已批准计划的在线续接验证：approved-continuation-20261010-94934aab

本轮验证的问题是：真实模型已选定并注册阅读计划后，已离线认证的 extract→verify→build 参数链，能否由共享 Runtime 自动执行后两步并通过来源/许可复核。已观察到一个新问题上的两次真实原生验证跳过；没有测出完整科研质量、净成本改善或超越普通脚本的增量收益。

## 任务、边界与配置

- 预先固定计划在 `.local/literature-notes/approved-continuation-20261010-94934aab/experiment-plan.json`，包含来源哈希、两条不同训练问题、第三条留出问题和第四条前瞻在线问题。已知同组三份用户 PDF，没有留出新语料或独立消费者。
- 训练问题分别为高效科研 Agent 的方法/证据启示、复现材料/条件；留出问题为局限/适用条件；在线问题为笔记更新所需的工具/执行轨迹/版本变化原文窗口。任务均止于证据包，不能以原文定位代替相关性或论断支持。
- 使用已有 Harness / MCP / 预算代理，`deepseek-flash`、reasoning off、压缩关闭、max_output=3000、max_steps=24、解析缓存 reuse。总技术预算上限100美元，后续调用扣除已估费额度；沿用用户付费授权，非预期支出。没有自动整轮重试。
- macOS arm64、Node 22.22.2、Python 3.12.13；代码基础 HEAD `2368235f274329be6227a8393b850633cb943da4`，`feature/rsi-research-agent` 工作区未提交。每轮 `evidence-input-snapshot.json` 保存实际版本、工具/题面/策略与共享代码摘要，原生 runner 保存 manifest、events、metrics、ledger。
- 策略 v1 摘要 `0e473c85ba913a2fbf7d7040d20631522b0f89017d32831011ba05e82c94695b`；导出 online manifest v2 摘要 `c2e533b8bf150565e9dc8142249a2fe9bc1bb45f1bcada25eb48600998c74b44`。新库仅来自正常真实模型 baseline，未使用模拟轨迹训练真实库。
- 计划许可是场景/用户边界声明；实际参数边由共享挖掘器、witnessed-chain 编译器与不同任务留出认证得出。有限窗口循环是预建 MCP 工具，不算学到的遍历程序。

## 真实请求与结果

| 阶段 / 原始运行 ID | 真实请求 | miss 输入 | hit 输入 | 输出 | runner 秒 | 代理估费 USD | 交付 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 训练1 `934c826bdc374b1c840a2a439cbd1d59` | 10 | 27805 | 154112 | 2210 | 17.023 | 0.011918172 | 3窗 |
| 训练2 `6c71af32fd124e398cad64e5ebbee623` | 9 | 27073 | 125312 | 2135 | 15.435 | 0.011435772 | 4窗 |
| 留出认证 `89d7f39afbd0421d99905d0fa5948711` | 12 | 29846 | 210304 | 3585 | 23.308 | 0.014517624 | 4窗 |
| 前瞻 execute `8aab1d0e52ef4e6cb222c1e5ffafa0a6` | 6 | 24595 | 60544 | 1561 | 10.749 | 0.009614964 | 3窗，2验证跳过 |
| 合计 | 37 | 109319 | 550272 | 9491 | 66.515 | 0.047486532 | 全部来源重放通过 |

留出任务有一次注册计划总字符超限拒绝，模型修正后成功；所有12请求及该失败费用包含在表内。没有429、没有整轮重跑。耗时是 runner 时长之和，排除本轮开发、编译、审阅及准备时间。费用是固定预算代理估费，尚未核账单；Codex/人工审阅和开发维护成本未计量，合格总成本未知。PDF 实验累计代理估费更新为0.853313160美元。

在线运行为8个原生 Agent 步数、6个真实上游模型请求。审计两条 `motif_bypass_attempt` 的依据都为 `closed_approved_plan_continuation`，随后各有当前真实 `tool/call`、成功工具结果及 `motif_tool_result_verified`、`model_request_skipped_verified`。跳过工具恰为 verify 与 build，embedding 请求0；最后交回模型回复覆盖限制。不能把8步误算成8次模型付费请求。

原始 `.local/runs/<ID>/` 不变；实验目录保存 runs、split、structural-reviews、learned、evaluation、online-mechanical-review、outcome 与完整启动输出。私有最终核对：packet SHA-256 `4d0284bc594bd7d1e05b693616413e7f4e0ccad1305b14b24389c07918c0a4d4`，3窗逐字来源重放通过，原三份 PDF 哈希未变。核对采用确定性重放/原生事件与许可一致性检查，Codex查看事件摘要；不是专家盲评或科学支持认证。

## 固定计划协议对照与回归

免费检查 `.local/literature-notes/evidence-check-21e8a22dc9b94f7c97a6bdc8ddef27a6/acceptance.json` 加载本轮真实学习库，固定三篇首页窗口，经实际 Harness / MCP / 预算代理和模拟 Provider：baseline 9、普通脚本7、Motif7模拟请求；三个证据包完全一致，Motif验证跳过2次，embedding0，API费用0。固定首页仅测试派发/守卫，不证明模型阅读质量。

`npm test`：266 Python +44 Node通过；包括缺/错许可、任务/计划/版本/schema 漂移、错 receipt/阶段、低文本/needs_review、工具失败、shadow、旧 v1 分发库及无许可契约签名回归。场景29项，其中实际 MCP/Harness 两次跳过使用公共生成 PDF 和模拟 Provider，明确不同于真实付费训练库。

开发首轮全仓检查发现 Python preflight 只接受 v1，已补 v1/v2 接入且保留权威 Node 检查。最终原始事件核对辅助脚本首次误用 `data.exec.callId`，实际事件为 `data.callId`；修正核对脚本后通过，未再次调用 API。生成桥接在付费验证后仅去除尾随空白，TypeScript规则未变，保留付费时原始代码摘要，并再次检查生成一致性及在线回归。没有覆盖旧实验或补写旧许可。

## 复现与下一步

```sh
npm test
node scripts/project.mjs python scenarios/literature-notes/check-evidence.py --manifest .local/literature-notes/approved-continuation-20261010-94934aab/learned/online-manifest.json
# 付费命令继续使用已有本机密钥，默认不开模型；本机库不随 Git 分发。
node scripts/project.mjs python scenarios/literature-notes/run-evidence.py --mode execute --manifest .local/literature-notes/approved-continuation-20261010-94934aab/learned/online-manifest.json --question '准备研究笔记更新所需的证据：这些论文如何描述工具、执行轨迹和版本变化？仅选择相关窗口，交付证据包。' --call-model --budget-usd 100
```

其他机器需自行提供 PDF、收集正常 baseline 轨迹、核对来源并用 `learn-evidence.py --split ... --output ...` 生成自己的库；不能依赖本机私有日志。共享改动见 [提交说明](../changes/approved-plan-continuation.md)。

当前证据支持“有许可且参数完全绑定的机械步骤能跳过模型并正确交付来源窗口”。当前普通脚本也减少相同两次决策；没有真实同质量三组重复对照，不能支持“Motif已更便宜或比Code Mode创新”。下一步先冻结同一模型批准计划做 ordinary Harness / 普通脚本 / Motif 的真实重复对照，计入学习、许可、恢复与审阅开销；再在新语料和不满足条件的任务上验证回退。科研支持审阅仍未过先前门槛，应单独继续单论断主体/条件验收。
