# 科研 PPT 双路试用

这是课题组试用入口。接收已上传到项目 `.local/` 的 1–8 份 PDF/PPTX、自然语言要求和 1–30 页，默认 `lab` 朴素组会风格，可显式选 `academic`。复用现有公共 DSH SDK、可靠 MCP、预算代理和真实 LibreOffice 验收，不另造 Agent 循环。

同一次任务准备两个独立 job，工具集合及登记顺序均为可靠入口的当前固定 21 工具（V16历史19，V17增加两项恢复工具）。来源、要求、模型、设计指导、模板、容量和验收相同；公共提示前缀相同，仅最后的执行策略不同：

| 组 | 执行策略 | 机制边界 |
| --- | --- | --- |
| baseline | `baseline_steps`：普通 DSH 分别生成、检查、渲染、交付 | 宿主禁止直接调用三种组合工具，保留同一真实 schema与全部机械验收 |
| optimized | `host_delivery`：模型提交合法计划给 `render_deck`，宿主执行固定交付脚本 | 手写普通工程优化，不是新 RSI/Motif；失败仍由模型审阅实际反馈 |

本入口不默认加载历史私有证书，也不生成或认证新工具。新任务默认 `--execution-policy controlled`，两组直接调用 `build_delivery/render_delivery/revise_delivery` 均被真实服务拒绝；优化组的频繁交付脚本由宿主路由，模型不再次选择脚本。原始工具事件、冻结job、TS启动/策略/脚本审计和文件回执共同证明策略实际执行。前述两路主要验证固定工程脚本的实际效果；不能把差额归为 RSI。来源改变、代码/构建摘要改变或工具 schema 不一致会拒绝旧配置。旧任务缺少策略字段时保留原来的 `steps/composed` scope，`--execution-policy legacy_model_selected` 仅用于历史诊断，不追改旧结果为新受控实验。

V17 `host_delivery`在可恢复的计划/布局失败时保存草稿；模型凭回执中的`draft_id/version_sha256`调用`read_pending_plan`读取1–5个明确页面，或用`repair_pending_plan`发送显式局部修改。未完成草稿存在时拒绝整稿重交，最多8次patch、6次恢复渲染尝试；版本失效、来源变更或权限失败不能借恢复绕过。普通组仍广告相同schema，但服务端拒绝两项恢复工具。最终恢复回执须同时绑定adapter完整审计、原host结果摘要和实际验收/文件，不能仅凭`delivered=true`记成功。它是普通工程恢复，不默认生成新工具。

## 1．准备、显示预算和预览

在服务器完成根和场景依赖安装、构建，加载本项目环境。输入论文先按项目要求下载到本机，再上传服务器 `.local/`，不将论文和轨迹提交 Git。

```sh
cd <项目目录>
source .local/activate.sh
mkdir -p test-logs
python -m scenarios.research_ppt.trial \
  --input .local/research-ppt/inputs/paper.pdf \
  --instruction '生成6页中文组会汇报，解释方法和实验条件，保留主要原图与来源，不使用装饰性卡片堆砌' \
  --slides 6 --template lab --operation generate \
  --budget-usd 3 --max-steps 60 --max-output 8000 --allow-output
```

默认只准备和预览，不解析 PDF、不调用模型、不生成 PPT。打印 `trial.json`、两路输出位置与复用预览的执行指令。`--allow-output` 只授权本次两份新稿的私有目录，不修改原文件；没有该授权的预览不能在执行时偷偷提高权限。

预算为 **双路合计上限 $3.00，每路各 $1.50**，不是预计费用。两路串行，默认最多各 60 步、每请求 8000 输出 token；模型 `deepseek-flash`，`reasoning_effort="off"`，默认不启用上下文压缩、解析缓存或语义匹配。可显式 `--document-cache` 令两组使用相同持久解析缓存并冻结此开关；它是普通缓存，不能算 RSI 收益。费用表按固定配置留摘要，代理估费需另外核对账单。

可增加 `--order optimized-first` 改变运行顺序并留记录。API 缓存会受时间和顺序影响，小样本结果不等于稳定因果收益；首次任务与重复任务需要分别比较。

需要完整原图时，显式增加 `--min-original-figures 2`。两组冻结相同数量并在生成、修订前去重验收；默认0，正值仅适用于含PDF的generate任务。不能用同图重复裁取、整页或局部嵌入素材凑数，无法定位时明确失败。该合同不认证图意、数值或引用的科学充分性。

## 2．明确启动两路付费任务

确保私有环境已有 `DEEPSEEK_API_KEY`；不打印密钥，不写公共配置。将预览实际打印的 `trial.json` 代入：

```sh
set -o pipefail
python -m scenarios.research_ppt.trial \
  --trial .local/research-ppt/trials/<trial-id>/trial.json --call-model \
  2>&1 | tee test-logs/<trial-id>.log
```

执行前再次显示预算、影响和输出位置，并用真实 MCP `--export-schema` 冻结两组 schema；预检失败不发付费请求。每份预览仅执行一次，失败与中断目录保留，修复后使用新的试用 ID，不能覆盖旧结果。新任务不继承另一组的 plan、读取状态、交付或模型答案。

已有 PPT 改风格使用 `--operation restyle --slides <实际页数>`。这是受限字体/配色副本转换，不保证任意动画、母版或复杂对象完全无损；内容重写与页数变化应使用 `generate`。任意外部 PPT 的精细修改仍需单独验收。

## 3．查看与下载两份结果

所有原始内容位于 `.local/`：

| 文件 | 内容 |
| --- | --- |
| `trial.json` / `effective-runtime.json` | 输入版本、代码/构建摘要、模型/环境/工具 schema、策略及预算 |
| `baseline-result.json` / `optimized-result.json` | 公共运行目录、失败情况、每路费用和交付文件清单 |
| `baseline-harness.log` / `optimized-harness.log` | 完整子进程输出；原始模型事件、费用 ledger 位于所关联 `.local/runs/` |
| `*-delivery-receipts.json` | 实际成功交付回执、事件 SHA 和 PPTX/PDF/PNG 文件 SHA |
| `comparison.json` | 两路单独费用、双路总支出、未知项与质量未评审状态 |
| `review-template.json` | 逐页人工质量和修订时间记录表 |

从每组 `deliveries[].files[]` 下载实际返回的 PPTX、PDF 与逐页 PNG。存在 PPT 文件不代表任务完成：只接受真实交付工具成功回执并再次核文件 SHA；仍然只说明机械交付，科学事实、图件语义及审美需要逐页审阅。

费用分别记录缓存命中输入、未命中输入、输出、真实上游请求、失败请求、代理估费、预算占用和耗时。usage/最终 metrics 不完整时总数保持未知、保留观测小计；不能删掉失败记录。全部恢复已包含在总费用中，现有公共记录不足以精确拆分恢复费用时标 `null`，不写零。人工、账单实付、维护与历史学习成本也不偷偷视为零。

## 4．追加人工评审

复制 `review-template.json` 为同一私有目录的 `review.json`，填写真实评审人。逐页核原论文、PPTX 和 PNG，将科研事实、图件/引用、可编辑与渲染、实际可用性填写为 `true`/`false`；未评审保留 `null`。记录重大错误和实际人工修改分钟数；自动检查不能代填。

```sh
python -m scenarios.research_ppt.trial \
  --trial .local/research-ppt/trials/<trial-id>/trial.json \
  --review .local/research-ppt/trials/<trial-id>/review.json
```

该命令不发模型请求，新增 `reviewed-<id>.json`，不追改原结果。只有两组均评审合格、机械交付与记账完整时才计算同质量单路模型代理费用差；仍未折算人工、维护、历史学习和实付。两组费用相加是试用对照的实际总支出，不能称优化组单路成本。

AI辅助评审明确填写 `reviewer_kind="ai-assisted"`，人评填写 `human/user`。AI辅助输出不标为独立人评，也不授权候选生产晋级；AI审阅耗时与人工修订分钟分开记录，后者未知保持 `null`。反馈学习使用 [evaluation-only入口](feedback-learning.md)，需另外绑定实际AI审阅JSON与SHA。

## 5．部署反馈与离线学习

准备时显式增加 `--collect-feedback` 才授权将两路版本、费用和待评审记录登记到项目私有 `.local/research-ppt/feedback-learning/`。可用 `--feedback-store` 指定另一个项目私有库。默认 `learn=false`，科学/视觉 `pending`、独立任务身份尚未确认；不能自动作为认证证据或晋级新工具。反馈模块故障单独留错误记录，已有交付不受影响。后续按 [反馈与学习入口](feedback-learning.md) 完成用户评审、独立任务冻结和离线学习，在线服务继续使用冻结稳定版本。

准备时可选 `--use-active-learning`，仅继承该反馈库已经显式晋级且依赖认证仍有效的 manifest。没有 active 版本时继续普通工程对照并记录原因；有 active 时仍走公共 `cli.run` 的输入、准入程序、证据锁与 Runtime 版本检查。证书/工具不兼容或守卫拒绝不放宽检查；此时需要新预览或回退，不能将影子运行或未命中算请求旁路。该可选预览会为了既有准入守卫解析文档，但仍不发模型请求。报告保留请求/实际模式、候选版本及 verified 旁路数量；组合脚本＋Motif两机制同时开启时，总差额不能全部归因于 RSI，历史学习投入仍须单列。当前active继承链尚未经过本轮真实模型验证，首批试用使用默认普通对照。

## 验证边界

首个已认证候选使用 `--candidate-version <version>` 显式创建隔离评测，与 `--use-active-learning` 互斥。它不改 active，沿用公共准入与版本守卫；无实际 verified 请求旁路的评测不能作为候选收益晋级依据。候选/active 路径需先完成已有准入程序准备，默认双路工程入口不依赖历史私有证书。

源码编辑不等于部署成功。需要在部署服务器检查无模型预览、schema预检、权限/版本拒绝、费用缺失行为，再做实际双路任务和逐页人工评审。当前入口不宣称任意 Windows 真实渲染支持，不保证所有任务必然省钱，也不把请求差、模拟测试或一次成功当作稳定净降本。
