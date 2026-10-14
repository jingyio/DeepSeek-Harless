# 固定阅读计划对照：frozen-evidence-20261010-997d9e47

三轮真实运行观察到：相同证据包下，普通 Harness 每次6个模型请求，普通脚本与 learned Motif 每次4个；Motif 每次2个原生验证跳过、0 embedding。Motif 平均运行更快，但相比脚本的费用差仅约1.8%，第三轮反而更贵。完全相同任务的补充结果缓存基线无需模型。当前支持有限机械续接有效，不支持完整科研质量、稳定净费用优势或跨语料泛化。

## 任务与预先固定条件

- 问题：准备研究笔记更新所需的证据，查看论文对工具、执行轨迹和版本变化的描述。已知同组三篇 PDF，固定三个窗口；这是一个既有真实研究决定的机械执行对照，不是9个新问题。
- 计划来自真实原生运行 `8aab1d0e52ef4e6cb222c1e5ffafa0a6`。入口核对其模型启用快照、成功结果、实际 register 调用、build 收据、证据包摘要，再重放当前来源；不是只信 JSON 中的批准布尔值。窗口选择此前由模型完成，相关性尚未独立评审。
- 冻结 plan SHA-256 `5cb1fbc183d2b39ee7c4732d3f1ad8a5a4d8bfe99b1130bc6aebf8cefb1950c6`；全部交付 packet SHA-256 `4d0284bc594bd7d1e05b693616413e7f4e0ccad1305b14b24389c07918c0a4d4`；沿用 v2 manifest `c2e533b8bf150565e9dc8142249a2fe9bc1bb45f1bcada25eb48600998c74b44`，不重新付费训练。
- 执行顺序在调用前固定：baseline/script/Motif，script/Motif/baseline，Motif/baseline/script；每组各占一次顺序位置，串行、独立会话。模型 `deepseek-flash`，reasoning off、无压缩、max_output=3000、max_steps=24；同一场景七工具/schema/顺序、字节相同的提示和固定计划。
- 共用解析缓存 `reuse`；调用前重放原包，统一预热。API 前缀缓存不可控制或清空，实际 hit/miss 已记录；轮换顺序不能完全排除时间/缓存效应。
- 只测已批准计划的重新执行，重新选页和完整科学笔记不在计时内。script 仍执行相同提取/核验/组装，只在一个 MCP 调用内完成；它不是实际生成式 Code Mode 基线。
- macOS arm64、Node22.22.2、Python3.12.13，分支 `feature/rsi-research-agent`、HEAD `2368235f274329be6227a8393b850633cb943da4` 加未提交修改。私有 `experiment-plan.json` 保存开始时源码、提示、来源、任务、manifest 与工具快照；各运行保留原生 events、ledger、metrics。

## 全部真实结果

| 轮次 / 路线 | 原始运行 ID | 请求 | miss 输入 | hit 输入 | 输出 | runner 秒 | 代理 USD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 Harness | dfa0d70754c2415abe498632c1c5cad3 | 6 | 8216 | 16512 | 1033 | 8.782 | 0.003803472 |
| 1 script | ab0e8d8c7e964234add52c27c0c8bcc8 | 4 | 7331 | 9472 | 1125 | 7.851 | 0.003606132 |
| 1 Motif | 5f01a79ea1c749999181b2d6052a4ac6 | 4 | 7816 | 9472 | 831 | 6.858 | 0.003398832 |
| 2 script | 6785e8fc734548ae9e08e21e4de26d3f | 4 | 7328 | 9472 | 989 | 7.819 | 0.003442032 |
| 2 Motif | 911a66a4900a4d29af4d02eeef1b4045 | 4 | 7832 | 9472 | 740 | 6.302 | 0.003294432 |
| 2 Harness | 62683a0929dc4891a25cfdcc7adf6335 | 6 | 7854 | 16896 | 995 | 8.831 | 0.003651576 |
| 3 Motif | f8c87d6f67dc4dbfb429ef30c954af0d | 4 | 7875 | 9472 | 870 | 6.748 | 0.003463332 |
| 3 Harness | 4c059774715c482088d6cc1b24179ba2 | 6 | 7802 | 16896 | 1120 | 8.760 | 0.003785976 |
| 3 script | 8955e7c74cc94752bf0caf6bda9a38a2 | 4 | 7323 | 9472 | 869 | 7.739 | 0.003296532 |

| 路线 / 3次均值 | 请求 | runner 秒（范围） | 启动到回收秒 | 代理 USD |
| --- | ---: | ---: | ---: | ---: |
| Harness | 6 | 8.791（8.760–8.831） | 10.126 | 0.003747008 |
| 普通脚本 | 4 | 7.803（7.739–7.851） | 9.147 | 0.003448232 |
| learned Motif | 4 | 6.636（6.302–6.858） | 8.312 | 0.003385532 |

42次真实请求，全部 HTTP200，无整轮重试或失败，合计代理估费 **0.031742316美元**；PDF 实验累计 **0.885055476美元**。价格沿用仓库固定高峰表，未核账单；与逐请求原始 usage 重算一致。辅助核对最初直接求和账本中保留8位小数的价格，精度断言失败；改为用原始 usage 重算，不改历史费用、未重跑 API。

来源包完全一致，三篇 PDF 未改，所有计划原生调用均与冻结输入相同。三次 Motif 的 verify/build 实际调用参数、callId、成功收据及 audit 逐项相符；正常6个 Agent 步中只有4个模型请求。以上是机械验收；原文包保留 `research_quality=unreviewed`、`claim_support_assessed=false`，未做专家盲评，也未修复之前科学支持审阅的缺口。

Motif 相比脚本平均费用只少0.000062700美元；平均 miss 输入多513.67 token，hit 相同，输出少180.67 token，主要由输出差异抵消额外输入。第三轮 Motif 更贵，因此不支持稳定降费或统计显著改善。相同请求数下的耗时差也受模型输出和网络影响；这是已观察的固定条件均值，不是普遍保证。

当前库两训练+一认证的历史代理费用0.037871568美元单列；三次 Motif 执行加这笔费用为0.048028164美元，对应三次脚本执行0.010344696美元。训练还能复用于其他任务，但本次没有证明已经摊平，旧库训练/失败费用仍保存在累计记录。原计划选择和交付那次0.009614964美元对所有组同样排除，不把它当成纯选页费用。开发、编译和人工维护/审阅未完整计量，合格总成本未知。

## 补充的强缓存基线

三组付费比较完成后，另存 `cache-followup-plan.json` 再做3次免费核对；明确是后补基线，不追改预注册计划。普通 `reuse-evidence.py` 在当前问题、明确批准计划、来源/解析器/实现仍一致时核验原生来源并复用已有包；新问题、改计划、撤回该输入许可或当前来源变化拒绝。输入许可仍属可信本机边界，不是完整撤回注册表或数字签名。

结果：3次相同证据包、0模型请求、0 API估费，函数核验均值0.142秒，包含新进程启动的均值0.420秒。与上表较可比的是启动到回收时间；函数核验与 Harness runner 的计时边界不同。此基线仅适用于已有完全相同任务结果，不能回答新的语义问题或生成新计划。缓存本身是简单结果复用，不称 learned RSI。

因此同一任务无变化时优先缓存；有新计划但机械链不变时才比较脚本和 Motif。单一固定流程下脚本仍是有力选择。Motif 的潜在价值在多种任务中自动识别可复用链并可靠回退、降低适配维护负担，这仍需要独立材料实测。

## 改动、验证与复现

此次只增加场景入口、相关测试与文档，未修改共享核心、MCP schema、工具实现/执行版本、预算或上游 Harness：

- `run-evidence.py --frozen-plan`：校验当前任务/批准计划、相同提示、输出计划一致性；普通运行不受影响。
- `compare-evidence.py`：默认无模型预览、原生计划来源检查、轮换顺序、剩余总预算、保留失败费用、缺失记账停止；不新建 Agent 循环。
- `reuse-evidence.py`：显式相同请求的结果缓存对照，无 Key 读取和模型入口。
- `check-evidence.py`：固定计划免费验收。三论文免费检查 `evidence-check-0894699977614b82858f29969c2e2b83` 为6/4/4模拟请求，包一致、Motif跳过2、0 embedding/付费。

全部原始计划、输出、快照和核对在 `.local/literature-notes/frozen-evidence-20261010-997d9e47/`；缓存另存 `cache-comparison.json`，不覆盖原付费对照。公开测试使用生成 PDF，不依赖用户资料或私有库。

最新 `npm test`：284 Python+44 Node全部通过；相关场景47项（新对照/缓存17项、证据链30项）。包含实际免费 MCP/Harness/预算下固定计划三组的6/4/4请求，以及失败/许可边界；模拟用量不作为费用或科研质量证据。

```sh
# 默认只预览；本机原始任务和学习库不随 Git 分发。
node scripts/project.mjs python scenarios/literature-notes/compare-evidence.py --plan-run .local/runs/8aab1d0e52ef4e6cb222c1e5ffafa0a6 --manifest .local/literature-notes/approved-continuation-20261010-94934aab/learned/online-manifest.json --repeats 3 --budget-usd 100 --training-cost-usd 0.037871568 --training-cost-source approved-continuation-20261010-94934aab
# 明确要付费重测时追加 --call-model；这不是重现历史统计的离线命令。
node scripts/project.mjs python -m pytest tests/test_literature_pdf_evidence.py tests/test_literature_evidence_comparison.py -q
```

其他机器需按普通入口准备自己的 PDF/问题、收集和认证正常真实轨迹，再使用实际成功证据包的运行目录。后续 [扩展验收方案](literature-evaluation-protocol.md) 要求按整篇/项目留出材料，构造缓存/脚本/Harness/Motif强基线，先验收科学支持再评估完整质量下成本。三篇论文与九次同计划运行均不足以支持该结论。
