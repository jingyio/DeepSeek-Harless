# 科研 PPT 设计 Skill 与布局 RSI 实验

- 实验 ID：`research-ppt-v5-design-rsi-20261010`。
- 状态：原五题三组的 15 次真实 API 运行已完成，确认交付 15 份 PPTX、共 138 页；布局 RSI 已完成真实提案、训练与独立机械认证。全页 AI 辅助审查发现 14 份需要修订、1 份未观察到重大问题。后续 P1/P2 六运行工程 pilot 已交付并辅助审查全部 45 页：5 份需修订、1 份未观察到重大问题。另行 F1 QLoRA 反馈精修已交付，7 页辅助审查未发现重大问题，仍有 3 项小问题。原 29 页与 pilot 17 页报告的全页辅助视觉检查均未发现排版阻断。各 cohort 单列，不回补原矩阵；独立人工盲评及合格总成本仍未完成。
- 授权：用户已授权继续真实实验且不限制预算；每次运行仍设置防失控上限。未经另行告知和确认不 commit/push。
- 记录更新：2026-10-10，Codex；以下方案保留开始前约定，实际配置与结果以末节冻结证据为准。旧记录中的“尚未调用”状态由本记录修订，不改写旧实验结果。

## 问题与可否定假设

吸收可分发设计 Skill 后，Agent 能否在不同篇数、听众与页数要求下生成更易阅读且可编辑的科研 PPT？同一 Skill、来源、模型、工具顺序及质量门槛下，认证 Motif 能否减少真实请求和费用？真实 DeepSeek 从训练排版诊断提出的受限策略能否在独立材料上保持内容并改善几何指标？任一内容丢失、独立认证失败或成本反例均保留；没有人工盲评不能称质量等价或合格总成本下降。

## 划分和对照

历史正常 DeepSeek 草稿选至少两个含原图任务作布局训练，另一个独立来源任务仅用于一次冻结认证。按旧权威汇总中的 cohort/run ID 固定计划 SHA、交付证据映射。训练允许最多三次完整策略提案，失败也计数；留出不向模型反馈，不用同一留出再调参。训练改善标准为失败减少，或原图平均面积增加至少 10%；认证要求无回归、内容与 notes/来源保持。此标准仅是机械/几何代理，不能称审美认证。

计划的新 API 任务使用本机先下载再上传的 RAG、T5、QLoRA、DPO、InstructGPT 论文，覆盖单篇解读、两篇比较及多篇决策。五题是五个分别交付的任务，不是把五篇合成一个固定 PPT；来源可重叠，报告这一限制。实际题面由研究者自拟，属于真实论文 API 工程任务，尚非真实使用者前瞻验收，也不是仓库的 18 个合成开发题。每题比较：设计 Skill＋普通 DSH、同 Skill＋认证 Motif、同 Skill＋Motif＋独立认证布局策略。若没有合格证书，第三组明确跳过。历史确定性回放与新 API 任务单列。

## 原理和实现边界

- DeepSeek：论文理解、选材、叙事、图表解释及布局策略提案，关闭思考与默认压缩。
- graph：历史正常轨迹编译认证的 `pin_source → read_source` 参数依赖；实时 schema/来源/版本守卫。继续只复用该短路径，不把 Skill、模板或手写流程称 Motif。
- code：PDF/PPTX 读取、图注几何候选、原生可编辑生成、真实 LibreOffice 预览、完整性核验、七字段策略执行和失败回退。
- RSI：真实模型读取训练反馈、提出七字段布局策略、真实回放、有限修订、独立认证与版本锁；不生成任意执行代码、不改科研内容或验证器。上线再次校验完整证据；新任务策略失败只对枚举布局错误回退，保留失败目录。
- Skill：固定 MIT harness-anything 的工程思路与独立科研设计规则，版本和许可见场景 SOURCES/provenance；不是开发时 Codex Skill 自动运行在服务器。

## 配置、复现与验收

全部构建、测试、真实 API 与渲染在 `/root/autodl-tmp/xjj`，先加载 `.local/activate.sh`；凭证从受保护项目环境加载，不输出值。原始材料、快照、轨迹、冻结提案与产物在 `.local/`；所有测试及实验保留 `test-logs/`。上传前备份场景并记录 SHA，不覆盖公共主线交接。

先执行场景 Node/Python 回归、实际 MCP smoke及根 `npm test`/`npm run smoke`。布局学习使用 `python -m scenarios.research_ppt.layout_learning`；前瞻矩阵入口 `python -m scenarios.research_ppt.experiment_v5` 默认预览，付费须 `--call-model`。单运行预算上限 $0.75、最多40步，矩阵上限 $15；布局训练另外限 $0.75/最多10步/三次提案。这些是防失控限制，不是另行向用户收紧预算。

冻结代码、依赖、题面、来源、工具 schema与顺序、Skill SHA、manifest/guard/策略证据、reasoning/压缩配置。逐运行记录真实请求、缓存命中与未命中输入/输出 token、代理估费、重试/回退、耗时、失败和人工介入；账单实付未知时明确标注。全页拼图下载后逐页辅助审查，用户/独立人工盲评尚未完成则写质量未盲评。不能把来源页合法与几何完整等同于科学事实正确。

## 结果与后续记录

### 总结果与证据冻结

原 cohort 为 `research-ppt-v5-design-rsi-20261010-2b9512aa`，服务器私有目录为 `.local/research-ppt/experiments/research-ppt-v5-design-rsi-20261010-2b9512aa/`。`summary.json` 绑定 `config.json`、`matrix.json` 及 `run-01.json` 至 `run-15.json`；本机只读核对副本在 `.local/research-ppt/v5-design-rsi-20261010/frozen-original-metadata/`。本节只统计这 15 次原运行，没有混入历史 R1/R2、开发失败、学习请求或后续 pilot。

| 冻结证据 | SHA-256 |
| --- | --- |
| 原矩阵 `summary.json` | `df54bcc8ba3371708a024eb9ddb14e85da2e86684585010751fdffafc2502452` |
| 有效配置 `config.json` | `f5d5c3be14540aa92538d934b0d021ff5e84f897d3a101012ad2c6190a6fef00` |
| 题面 `matrix.json` 文件字节 | `11d47f0bcbf4fdc45765e22c65c8519baa666bce4bb8e7528804047e061fe0bf` |
| AI 辅助审查 `visual-review.json` | `5b3883b96b68e944c4d42574596a39742b213f3d47386891ac245373af5cbafa` |
| 学习运行 `rsi-run.json` | `c6957f2a8fbafd07098779cc9c7922ed683deab8b05185cca4cdf9d72c954b8e` |

配置内 `matrix_sha256=d31fe176ea1d73633cbb974769710ef1c6a312321552a2a4ce71089a5eff7d09` 是排序并规范化 JSON 后的逻辑摘要，区别于上表文件字节 SHA。辅助审查与学习运行资料位于服务器及本机的 `.local/research-ppt/v5-design-rsi-20261010/`；历史布局计划来源映射保存在同目录 `layout-origin-map.json`。原始日志、论文、PPT 与私有证据不提交。

已观察到：Motif＋RSI 组相对普通组的实际请求减少 15.63%、全部 token 减少 9.82%、API 代理估费减少 9.49%。反例同样保留：单独 Motif 组请求增加 7.29%、token 增加 35.97%、代理估费增加 24.48%。这些是各题一次生成的观测，包含不同重试和恢复；不证明质量等价，也不能将总差额都归因于 Motif 旁路或 RSI。

### 1 / 数据集与真实任务

| 任务 | 来源 | 要求页数 / 模板 | 交付目标 |
| --- | --- | --- | --- |
| V1-rag-briefing | RAG | 8 / lab | 中文组会：检索动机、方法流程、实验条件与局限 |
| V2-qlora-deployment | QLoRA | 7 / academic | 有限显存微调工程决策；区分微调与推理 |
| V3-preference-comparison | InstructGPT、DPO | 10 / lab | 统一维度比较 RLHF 与 DPO，不拼接跨条件排行榜 |
| V4-knowledge-access | T5、RAG | 9 / academic | 参数内知识与外部检索的职责、更新与适用条件 |
| V5-research-pipeline | RAG、QLoRA、InstructGPT、DPO | 12 / lab | 问答助手组合方案；区分原文事实与待验证推论 |

共 5 篇真实公开论文，任务间存在来源重叠；各题各组三份独立生成，组间执行顺序在题间轮换。所有组均完成会话并确认工程交付，各组 46 页，总计 138 页。每题每组仅一次，样本不足以判断显著性或稳定产品收益。题面支持其他篇数、页数和任务要求，不把此矩阵当作固定产品流程。

### 2 / 让模型在结果出现之后做决定

本轮受限布局 RSI 的真实学习 run 为 `c21d5944d5e846dcae1765cdc536b490`。DeepSeek 读取训练布局反馈后只提出 1 次候选，训练通过，再对未反馈给模型的独立材料认证通过；没有利用同一留出反复调参。

| 阶段 | 冻结材料 | 原图数量 | 平均原图面积，平方英寸 | 结果 |
| --- | --- | ---: | --- | --- |
| 训练 | 历史 R2 E1 普通、E5 普通，2 份计划 | 5 | 18.95294857 → 22.38322557（+18.10%） | 无失败，内容、notes 与来源保持 |
| 独立认证 | 历史 R2 E2 组合、旧 CLIP 独立认证，2 份计划 | 2 | 27.16283333 → 33.01041117（+21.53%） | 无回归，内容、notes 与来源保持 |

晋级的完整策略为：

```json
{"schema_version":1,"media_position":"right","media_fraction":0.66,"body_columns":2,"body_font_size":21,"table_font_size":18,"body_gap":0.18}
```

策略 digest 为 `f7e30bfccfa76927cba649b2af25c45fe85c3f2a7cd49498514480635d9a1c93`；证书 SHA 为 `c024ce7fc3d42ab0ef7e9a92eb1b4486c48cc1f8543f744bc22a6dc592c2ed07`；资料集 SHA 为 `b301b24a6892e2ef1730dd26053f0b509d7e9341d312011d6a1c35355f532a96`。

此闭环是真实模型提案、历史真实计划确定性回放与机械/几何认证。它没有训练模型权重、生成新工具或新 Motif，且 `code_nodes=[]`。图面积变大不证明原图内部标签适合投影，更不证明科研内容正确或审美合格。原矩阵中策略遇到布局错误共回退 7 次：V1 1 次、V3 4 次、V4 1 次、V5 1 次；失败目录保留，不能称所有页面一直使用候选策略。

历史旧 RSI 最终回到原基准规则、未观察到优化收益的结论保持不变；本轮新布局策略是不同机制、资料与版本下的新证据。

### 3 / 与普通 DSH 的流程对比

三组均加载相同科研设计 Skill 与新渲染器，DeepSeek 均负责论文理解、选材、叙事、图表解释及科研判断。普通组使用默认布局；Motif 组增加已认证来源读取结构；Motif＋RSI 组再增加本轮冻结布局策略及有界回退。

Motif 仍只有真实正常轨迹编译认证的 `pin_source → read_source`，运行时检查参数来源、工具 schema、来源版本及证据。它省掉抄写已返回 `source_id` 并决定读取的一整次模型请求，仍真实执行读取。两种 Motif 组各观察到 5 次 verified bypass，每个运行各 1 次；这不意味任意多文档任务永远只有一次旁路。

Skill 由场景自行编写并随场景分发，实际加载 SHA 为 `2122fd41dfb786fcc5ae36f85b337f1726be35f5307d930e2114cbbf5e4554a1`。它参考 MIT `yb2460/harness-anything` 固定 commit `e1924f8499ad6aaa11c579d5492205cfaa89c5d6`，吸收 JSON 内容/渲染分离、信息层级、等比图片、真实预览与分项校对，新增 `takeaway` 与原生可编辑 `process`。没有复制上游脚本、品牌资产或 WPS COM，也没有让开发端私有 Skill 执行器自动运行在服务器。来源与许可见 [SOURCES](../../scenarios/research_ppt/SOURCES.md)。

本轮三组都有相同新 Skill，因此不能从组间对照推出“旧基础模板 → 新 Skill”的总体视觉收益。普通组合脚本 `build_delivery` 仍是代码优化，不计为学得 Motif；本轮原矩阵没有单列组合脚本组，相关旧对照保持独立。

### 4 / 费用比较

| 指标 | 普通 DSH＋同 Skill | Motif＋同 Skill | Motif＋RSI＋同 Skill |
| --- | ---: | ---: | ---: |
| 确认工程交付 / 会话 done | 5 / 5 | 5 / 5 | 5 / 5 |
| 实际上游请求 | 96 | 103 | 81 |
| 缓存命中输入 token | 3,006,720 | 4,131,200 | 2,697,600 |
| 缓存未命中输入 token | 183,076 | 215,419 | 183,000 |
| 输出 token | 91,227 | 114,735 | 78,370 |
| 全部 token | 3,281,023 | 4,461,354 | 2,958,970 |
| API 代理估费 USD | 0.182435520 | 0.227094900 | 0.165129600 |
| 运行耗时秒 | 439.789 | 541.430 | 433.285 |
| verified 整次请求旁路 | 0 | 5 | 5 |

全部 token 包含缓存命中输入，不能用其单独代表账单成本。费用采用完整账本的 `budget_accounted_usd`，不是实际账单；`observed_peak_usd` 的逐项四舍五入可能有微小差异。15 个运行的 `token_accounting_complete` 和 `ledger_cost_complete` 均为 true。组耗时为各运行 elapsed 累加，不含组间等待、学习、后续辅助审查和人工修订。

Motif＋RSI 组相对普通组耗时少 1.48%；单独 Motif 组耗时多 23.11%。原矩阵共 280 请求、10,701,347 token、$0.574660020 代理估费。未完成人工统一质量门槛、修订耗时与账单核对，不能称合格总成本下降。

### 5 / 调用次数与全部运行记录

下表均按“普通 / Motif / Motif＋RSI”顺序；未挑选较好重试替代原运行。

| 任务 | 实际请求 | 全部 token | API 代理估费 USD |
| --- | --- | --- | --- |
| V1 | 29 / 20 / 20 | 947,827 / 524,642 / 544,221 | 0.047873844 / 0.018519348 / 0.024245136 |
| V2 | 17 / 19 / 10 | 405,047 / 541,400 / 182,937 | 0.025193664 / 0.024010248 / 0.011918784 |
| V3 | 17 / 24 / 23 | 645,560 / 1,137,016 / 1,073,386 | 0.034657344 / 0.062402196 / 0.054294648 |
| V4 | 19 / 18 / 15 | 692,206 / 607,544 / 520,669 | 0.039473844 / 0.028574532 / 0.038563560 |
| V5 | 14 / 22 / 13 | 590,383 / 1,650,752 / 637,757 | 0.035236824 / 0.093588576 / 0.036107472 |

运行 ID、job、来源/产物及日志映射在冻结 `summary.json` 的 15 项 `runs` 中。矩阵主日志为 `test-logs/research-ppt-v5-real-matrix-20261010.log`，每个子运行的日志路径同时记录在对应 `run-XX.json`。计入实际请求和最终失败后的恢复成本；没有把 Agent 步数当成实际上游请求。

### 6 / 报告质量与评审边界

全部 138 页已做 Codex AI 辅助逐页审查：14 份 `needs_revision`，1 份 `no_major_issue_observed`；后者是 V4 Motif，仍有小问题。这是辅助审查，非独立人工盲评或用户验收，不能将“不曾观察到重大问题”写成正式质量合格。

代表性反例保留如下：

- V1：RAG 开发/测试集条件混用，标准 TQA 与 TQA-Wiki 比较错误，四题全 SOTA 的过强表述，训练与推理流程混合。
- V2：可见正文遗漏 65B/48GB 的微调条件，99.3% 指标及 GPT-4 评判范围说明不足。
- V3：将原图左/右称为上/下、原图细字仍小、PPO 与 PPO-ptx 混同、IMDb 与 GPT-4 评测混同。
- V4：普通组将 MSMARCO 的 ROUGE-L/BLEU 归到 FEVER；RSI 组流程混合前向与微调。
- V5：Motif 组把 175B InstructGPT 的 85±3% 偏好率误归 1.3B，跨规模比较的维度不齐。

页码合法、文字保持、产物 SHA 一致和几何无溢出不能代替图注正确、实验条件准确或科研判断成立。对这些问题的后续修订不能追记为原模型自动合格；人工修订分钟、Codex 辅助成本和账单实付仍未知。

### 7 / 逐题展示与后续 pilot

原 15 份 PPTX、对应 PDF、逐页 PNG、全页拼图及组间并排导航按原 cohort 打包。按同伴八节结构生成的原矩阵报告共 29 页，已完成 1–16 与 17–29 页的全页 AI 辅助视觉检查，未发现报告排版阻断；这是报告展示检查，不改变第 6 节 PPT 科研质量结论，也非用户验收。报告已下载至本机 `.local/research-ppt/v5-deliverables/original-matrix/report.pdf`，文件 SHA 为 `c65319077d8f87c1548cc5ec1cfeb6128cf687ce0c128c2bb35daa59d8c7be8f`；原矩阵包 SHA 为 `4357791ee2d486b810db57afcaa3e4b12fcdf643df8e75cd78fb20e392675bf7`。

辅助审查后另做最小契约修复：计划中缺失 `bullets` 规范化为 `[]`，显式 `null` 仍拒绝；复制计划操作并记录规范化，不能删除已有内容。原矩阵始终保留当时冻结代码、初稿及失败目录。

P1/P2 是引入原稿审查反馈并使用后续修复的两题六运行工程 pilot，主日志 `test-logs/research-ppt-v5-real-post-review-pilot-20261010.log`。P1 仍使用 RAG、8 页 lab，要求核验原稿的开发/测试集、TQA 比较、监督与训练/推理混用；P2 仍使用 QLoRA、7 页 academic，要求把 65B/48GB 微调条件及 99.3% 的基准/评判条件写入正文。三组共享各题相同反馈、来源、模型、Skill 与工具条件。这两题复用原 V1/V2 来源且已经得到原稿审查反馈，不是新独立数据或留出认证。

pilot cohort 为 `research-ppt-v5-design-rsi-20261010-5c076f4a`，服务器目录 `.local/research-ppt/experiments/research-ppt-v5-design-rsi-20261010-5c076f4a/`；本机核对副本 `.local/research-ppt/v5-design-rsi-20261010/frozen-pilot-metadata/`。六运行均 `done` 且确认工程交付，每组 15 页、总计 45 页；六个运行 token 与费用账本均完整。45 页已全部进行 AI 辅助审查：5 份需修订、1 份未观察到重大问题。独立人工盲评、修订时间与账单仍未知。以下只统计 pilot，不与原 15 运行合算效果，也没有替换原 V1/V2 或移除原反例。

| pilot 指标 | 普通 DSH＋同 Skill | Motif＋同 Skill | Motif＋RSI＋同 Skill |
| --- | ---: | ---: | ---: |
| 确认工程交付 / 会话 done | 2 / 2 | 2 / 2 | 2 / 2 |
| 实际上游请求 | 41 | 41 | 37 |
| 缓存命中输入 token | 1,521,408 | 1,196,288 | 1,035,520 |
| 缓存未命中输入 token | 61,720 | 68,195 | 65,812 |
| 输出 token | 54,984 | 29,862 | 27,768 |
| 全部 token | 1,638,112 | 1,294,345 | 1,129,100 |
| API 代理估费 USD | 0.093625248 | 0.063470628 | 0.059278320 |
| 运行耗时秒 | 225.321 | 156.743 | 150.608 |
| verified 整次请求旁路 | 0 | 2 | 2 |

| pilot 任务 | 实际请求：普通 / Motif / Motif＋RSI | 全部 token：普通 / Motif / Motif＋RSI | API 代理估费 USD：普通 / Motif / Motif＋RSI |
| --- | --- | --- | --- |
| P1-rag-reviewed | 27 / 27 / 19 | 1,338,097 / 930,013 / 623,960 | 0.074603244 / 0.040823424 / 0.034630764 |
| P2-qlora-reviewed | 14 / 14 / 18 | 300,015 / 364,332 / 505,140 | 0.019022004 / 0.022647204 / 0.024647556 |

pilot 共 119 请求（41＋41＋37）、4,061,557 token、$0.216374196 代理估费，不含既有学习成本。此前记录将请求合计误写为 117，现按冻结三组账本求和修正，分组数据与原账本未变。两题单独 Motif 的总请求与普通组持平；P2 两种 Motif 组的 token 与估费高于普通组，Motif＋RSI 还增加请求。这些反例不能被 P1 或两题总量掩盖；AI 辅助审查仍发现需要修订的科学表述，不能宣称合格成本下降。

pilot `summary.json` 文件 SHA 为 `b882bfdf5a3c5acacb4e5691166bdfbc3e0423989fd280140bb61eaf0b6c8c11`；`config.json` SHA 为 `b6e6f1db752fc83d1bb7a2234b9151f456403475cc6fa71c110e90af9fb5f4e1`；`matrix.json` 文件字节 SHA 为 `1812f75bfc0fcb25836b29c5f783395014a72da14e46eb1bdf0710312e40205d`，配置中的题面逻辑摘要为 `967c35386d4d4d390c39e1a07bc957a773fb58082074860aeb9e9f5bbf1181f5`。有效配置仍为相同模型、Skill、12 工具 schema、布局证书、40 步、6,000 输出 token 与 5 秒间隔；`service.py` 因契约修复变化，pilot 快照 SHA 为 `cace690c1647770dcaeb24442a5ddadb565cf2bbe5c684b786285e100765bfc7`，故不能与原矩阵视为同一代码版本。

pilot 辅助审查记录为 `.local/research-ppt/v5-design-rsi-20261010/review-pilot-p1.json`、`review-pilot-p2.json` 及合并 `visual-review-pilot.json`；合并文件 SHA 为 `d4eef09f13a49050a9c7613d99967ae09068252bd3bac2b92379ec684fa285a7`，逐项绑定本次 run，不套用旧矩阵的同题结论：

| pilot 任务 | 普通 DSH | Motif | Motif＋RSI |
| --- | --- | --- | --- |
| P1 RAG，三组各 8 页 | 需修订 | 需修订 | 未观察到重大问题，仍有小问题 |
| P2 QLoRA，三组各 7 页 | 需修订 | 需修订 | 需修订 |

P1 三组均观察到原稿测试/开发集、TriviaQA 与监督条件等主要问题的改善；但普通组标题“学习到的检索优于替换或冻结”遗漏 FEVER 的 BM25 反例，Motif 组将 Jeopardy 成对“更事实”比例写成易被误解为绝对准确率的指标。P1 RSI 未发现重大或中度问题，仍有可选解码方式误连为串行流程、正文 EM 单位遗漏、原图细字和过强动机表述等小问题。这不构成独立人工合格或 RSI 因果收益。

P2 三组均已改善 65B/48GB 微调条件及相对 ChatGPT 分母的说明，但普通组把部署/权重占用表头笼统写为“显存”；Motif 组把 GPT-4 的十分制评分误写为百分制；RSI 组把真实 Figure 1 组件示意误解成带显存横纵坐标的定量图，并有正文 68B/65B 笔误。三组仍有条件或不确定性只写在 notes 的遗漏。图件定位正确不保证解释正确，布局晋级没有解决该语义缺口。

pilot 同伴结构版报告共 17 页，已下载至 `.local/research-ppt/v5-deliverables/post-review-pilot/report.pdf`，SHA 为 `66361ea42e8d2dbe04f2b5f1116341e2e6b96e3b938f9f04afe388457f975be9`；pilot 包 SHA 为 `cb7eee76ed457d43e81ef045ec7a1c0776abe3989b497b429ecfded36b8bb46a`。报告 1–9 与 10–17 页已完成全页 AI 辅助视觉检查，未发现排版阻断；这是展示检查，非 PPT 科研质量认证，独立人工盲评仍未完成。

另行反馈精修任务 `F1-qlora-final-revision`，cohort 为 `research-ppt-v5-design-rsi-20261010-93c19f6a`，使用原 QLoRA PDF 与已有 P2 RSI PPTX，根据外部反馈重新生成 7 页 academic 稿。只有 Motif＋RSI 一组实际运行，普通与 Motif 组没有执行，不能将配置中未执行的组记为零费用对照。实际 run 为 `cb5873c042a346b983453fd693d3ec95`，10 请求、219,570 token（缓存命中输入 190,208、未命中输入 24,818、输出 4,544）、$0.014039448 API 代理估费，42.35 秒，1 次 verified bypass；token 与费用账本完整，会话 `done` 且已确认工程交付。此任务有已有稿与反馈参与，不是全自动新任务，也不是三组对照；精修费用另列，不回补 pilot 或原矩阵。

F1 全部 7 页及 2 张拼图已辅助目检并核对关键论文原文，审查记录 `.local/research-ppt/v5-design-rsi-20261010/review-final-qlora.json` 对应本次 run，SHA 为 `c80fde101ea1dc1bb3a60c36ff0a49f5dc2958b3bfec4bc6f5a63eec1bba65da`，结论 `no_major_issue_observed`。原图已按组件、梯度与分页解释，没有沿用不存在的显存坐标；65B/48GB 微调、MMLU 条件及 GPT-4 十分制/相对评分说明已修正。仍有 3 项 minor：第 2 页 33B/24GB 的 sources 应补第 6 页定位；第 3 页“四步”中的共同前提与三项互补机制应明确，连线不能暗示严格时间顺序；第 6 页 99.3% 的 sources 应补 Table 6 所在第 10 页。图内细字仍需人工投影核验。“未发现重大问题”是辅助观察，不代表人工合格、质量等价或机制因果收益；修订分钟仍未知。

F1 服务器冻结目录 `.local/research-ppt/experiments/research-ppt-v5-design-rsi-20261010-93c19f6a/`，本机副本 `.local/research-ppt/v5-design-rsi-20261010/frozen-final-qlora-metadata/`。`summary.json` SHA 为 `6a9c16d54611715346c3968817131f2b7b09177f3754c93061a069d8b24a12fe`，`config.json` SHA 为 `041ac1c53426ac46e6b891669c5c91273e47a46c509553be3a7b7a53dd7f2d3f`，`matrix.json` 文件字节 SHA 为 `22053b36d806c6c6ab3baa6ad1dfac4c30ce3112743c4f627f3dd7b5324c756c`，题面逻辑摘要为 `710079e93a50c1c441305b11e6bf45c97818afe4fb22ac8ac0d84ca70729ab94`。该稿 PPTX SHA 为 `a16f70a4c652dabb6bae70c1e3b87795f3e98ac56a9faa20206f708f8cfb83f0`，PDF SHA 为 `5fbc4aa35d88d65a0608e6e07ce0a837cef754bccf10b9b1dc73272b45058b2a`；真实日志 `test-logs/research-ppt-v5-design-rsi-20261010-93c19f6a-03-F1-qlora-final-revision-motif_rsi.log`。两份精修样例包已下载核验，本机 `.local/research-ppt/v5-deliverables/final-refined-examples/` 含 `rag-lab/rag-lab.pptx` 与 `qlora-academic/qlora-academic.pptx`、PDF及逐页图；ZIP `.local/research-ppt/v5-design-rsi-20261010/final-refined-examples.zip` SHA 为 `4d007ebb0d36080f5cc4b0d9560e7090c6cb66d260d1cf3076b41d0f314beca3`。包内19项PPTX/PDF/逐页PNG均按交付证据核验，现有原矩阵和 pilot 报告不替换为新结果。

### 8 / 学习成本、复现与适用范围

本轮布局学习实际 3 请求、6,104 token，其中缓存命中输入 2,816、未命中输入 2,157、输出 1,131；reasoning token 为 0。代理估费 $0.002021196，学习运行耗时 19.698672 秒。若单列“原矩阵＋本轮学习”，合计为 283 请求、10,707,451 token、$0.576681216；该口径不含既有 Motif 学习、后续 pilot、开发/维护人力、服务器算力，不能称全历史支出或合格成果均费。历史 Motif/旧 RSI 学习成本见 [旧结果记录](research-ppt-v2-20261010-results.md)，不重复归入每个新 cohort。

另列累计已记录的 API 运行支出以核对账本，以下只用于支出追踪，不把不同 cohort 合成效果对照，也不称合格成果均费：

| 支出覆盖范围 | 累计实际请求 | API 代理估费 USD |
| --- | ---: | ---: |
| V5 原矩阵＋布局学习＋pilot | 402 | 0.793055412 |
| 再加 F1 外部反馈精修 | 412 | 0.807094860 |
| 再加历史已记录运行（592 请求 / $0.983503248） | 1,004 | 1.790598108 |

这些累计值包含已有记录中的失败、重试与修订调用，账单实付、Codex 辅助成本、人工修改与开发维护时间及服务器算力仍未采集；历史和本轮学习不能再次重复归入每个 pilot。

原矩阵有效配置如下，完整逐文件来源及运行哈希以冻结 `config.json` 为准：

- 代码基线 `883ee5c6e667b93feda35c439e1a80b13f55b3f4`，场景有未提交改动，不能仅检出此 commit 即称复现当前代码。
- Linux 服务器，Python 3.12.15、Node 22.23.2、LibreOffice 7.3.7.2；SDK 0.1.5rc1、MCP 2.2.0、pypdf 6.19.0、PyMuPDF 1.26.7、python-pptx 1.0.2。
- `deepseek-official` / `deepseek-flash`，`reasoning_effort=off`，入口默认关闭压缩，steps 模式，max output 6,000、max steps 40、每 run 上限 $0.75、矩阵上限 $15；实际间隔为 5 秒，区别于入口默认 30 秒。
- 三组相同的批准 12 工具集合与顺序。实际 MCP schema SHA 为 `3fc91f0678bd6910bd4797b38249d6e7a93b93af9f9f9dde703573ce794c7a78`，这是 MCP list-tools 证据；Provider 面向请求的完整 schema 哈希/顺序和内部重试策略未采集。
- 结构匹配，不启用语义 embedding；记录的 `min_similarity=0.8`、`min_margin=0.1` 不代表本轮使用语义检索。manifest digest `b0e8511bfee3347612fe4f7e433c60f16e61839470778e248bbc4814b9f13c36`；guard SHA `a46914bba50aed5dbc307a11a7270a8c93f13c2700811993e2502ac9e417f843`。
- 缺项明确保留：账单实付、独立人工盲评、人工修订分钟、Provider 请求端 schema 及内部重试。配置或来源变化应创建新实验目录，不能覆盖旧快照。

在匹配冻结代码与私有证据的服务器环境中，最短矩阵预览为：

```sh
cd /root/autodl-tmp/xjj
source .local/activate.sh
python -m scenarios.research_ppt.experiment_v5 \
  --inputs .local/research-ppt/v5-inputs \
  --certificate .local/research-ppt/jobs/9f2ef62e80fa41d1a8e5ff8d15cc4cdc/layout-rsi/certificate-e4c36a3adeeb4c308b67646bfab04d4a.json \
  --per-run-budget-usd 0.75 --total-budget-usd 15 --max-steps 40 --interval-seconds 5
```

真实调用须在已获付费授权、凭证已在受保护项目环境的前提下追加 `--call-model` 并保存新的日志；以上未自动开启付费。本实验的独立布局准备、提案和认证步骤见 [场景 README](../../scenarios/research_ppt/README.md#v5-布局策略学习与复现)。当前代码若与原配置哈希不同，只能得到新版本复测，不能称字节级重现原结果。

服务器工程验证与日志：场景 Node 17 项通过，`test-logs/research-ppt-v5-node-final2-20261010.log`；后续契约修复的场景 Python 38 项通过，44.164 秒，`test-logs/research-ppt-v5-python-post-review-contract-20261010.log`。公共底座 `npm test` 的 136 项 Python 在 17.76 秒通过，29 项 Node 通过，日志 `test-logs/research-ppt-v5-root-test-20261010.log`；`npm run smoke` 通过，日志 `test-logs/research-ppt-v5-root-smoke-20261010.log`。底座检查没有付费模型调用，属于开发诊断。真实布局与 RSI 日志为 `test-logs/research-ppt-v5-real-layout-rsi-20261010.log`、`test-logs/research-ppt-v5-rsi-operation-20261010.log`。这些测试证明工程边界和链路，不代表科学或视觉质量合格；本机没有执行测试或真实模型实验。

另保留 post-review 场景 smoke 的首跑失败：模拟 Provider 将 `inspect_deck` 返回值中的 `deck_id` 错判为尚未 inspect，重复检查，达到 12 次限制后返回 500。该失败在模拟 Provider 的状态识别与 smoke 链路，不是 DeepSeek 付费任务或前述公共根 smoke 的成功结果；不能删除失败或将它写为真实模型质量反例。旧失败日志 `test-logs/research-ppt-v5-post-review-mcp-smoke-20261010.log` 保留；`smoke.py` 已按实际 scope 修复并在服务器复验通过，日志 `test-logs/research-ppt-v5-post-review-mcp-smoke-fixed-20261010.log`。此项仍是模拟 Provider 配合真实 MCP 的工程诊断，不是付费模型或科研质量认证。

当前证据支持受限布局策略的机械晋级、短来源路径的整次请求旁路，以及这些外部反馈下的部分内容纠错；不支持通用工具自生成、任意科研判断蒸馏、稳定审美改善或质量等价下的合格总成本下降。精修稿下载包已核验，下一步由独立人工按统一门槛盲评、记录修订时间并核对账单；通过质量门槛后才比较产品收益。未经用户提交确认，不 commit/push。
