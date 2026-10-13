# 科研 PPT：可靠局部修订、真实工具生成与新 Motif

- 实验 ID：`research-ppt-v6-tool-rsi-20261011`。
- 开始日期：2026-10-11；状态：功能闭环与真实对照完成，科研质量需修订，尚未人工盲评。
- 用户已授权真实实验不限预算、生成可调用工具及学习新 Motif；随后明确授权本轮结束后中文 commit/push 到 `feature/research-ppt-agent`，不创建 PR，提交前告知范围。全部构建、测试、付费调用及渲染在 `/root/autodl-tmp/xjj`，保留 `test-logs/`；论文先下载本机再上传。不覆盖原论文、用户 PPT 或公共主线交接。

## 问题与假设

1. 本场景生成的 PPT 能否按显式页号局部修订，并证明其余页面文字、notes、媒体、表格、图表与几何保持？
2. DeepSeek 能否依据历史正常工具轨迹提出、编写并修复一个真实图件目录准备工具，通过真实 PDF 的训练检查和独立认证，随后用于新任务？
3. 新目录工具的参数流能否从后续正常轨迹编译成新 Motif，在新任务中安全跳过整次模型请求？

工具代码由 DeepSeek 生成，开发端提供受限编译/执行宿主、固定验证标准和实际 PDF 读取原语，不预写候选代码。纯 JSON 转换代码不能更改科研内容、权限或验证器。素材定位与科研解释分开；未知或多候选图件仍交模型判断。新工具不自动算 Motif，须另有正常轨迹、独立认证、在线守卫及真实旁路证据。

## 任务与对照

工具生成读取旧 V5 训练侧真实轨迹，仅提供重复调用与失败反馈，旧评测结果不重新计入本轮。功能训练使用两份历史论文的真实页面几何，独立认证使用新材料；认证不反馈后继续调参。新材料预定 FlashAttention、Switch Transformers、Toolformer、Speculative Decoding 与 Self-Consistency，下载时冻结 URL、PDF SHA 与用途。后续正常任务训练至少两题、独立 Motif 认证至少一题；新的使用任务另行记录，来源重叠如实标注。

最小对照固定设计 Skill 与默认布局：普通逐页准备、人工批量目录、模型生成目录、模型生成目录＋新认证 Motif。各组题面、来源、交付与审查门槛相同；目录准备方式为显式差异。实际工具 schema 与顺序按各版本快照记录，不能隐藏工具集合/提示/缓存变化。局部修订单列同一任务续写，不计为独立训练或认证任务。

## 配置与预算

模型沿用 `deepseek-official/deepseek-flash`，`reasoning_effort=off`、压缩关闭；所有真实调用经过公共预算代理并保存账本。正常任务单 run 防失控 `$1`、40 步、最多 6000 输出 token；工具生成单请求防失控 `$0.75`、最多 8000 输出 token、持久最多三候选，总防失控 `$20`。这些是运行限制，不是新增用户预算上限。实验驱动复用公共 Harness 与离线编译器，不修改上游或新增第二套在线 Motif 规则。

基线服务器分支 `feature/research-ppt-agent`，HEAD `883ee5c6e667b93feda35c439e1a80b13f55b3f4`；已有未提交场景与公共改动分别保留。新增源文件、契约、工具 schema、Skill、生成代码、证书、manifest、来源和有效配置均冻结 SHA。真实运行开始前备份场景；公共主线交接 SHA 应保持 `86ca43033a49e55b0236d51261790efd337955e194ac5ea14e53078006945e2f`。

## 质量、成本与否定条件

先检查真实交付、来源、关键数值/比较条件、图意及逐页视觉。自动审查和文件完整性不代替独立人工盲评；未盲评写明。局部修订的非目标页变化、候选编造图 ID/页码/边界、来源或代码版本失效仍被复用、任务未交付，均否定相应功能主张。没有比普通脚本更好的合格成本则缩小 Motif 主张。

分别记录工具学习、训练/认证、正常任务、修订、失败与恢复的请求、缓存命中/未命中输入 token、输出 token、代理估费和耗时。账单实付、人工修订分钟、开发维护及辅助审查成本未采集时写未知。真实模型运行、真实文件诊断、模拟测试与历史回放单列，保留失败证据，不追改 V5。

## 实际结果

### 任务、划分与实际配置

本轮是研究者定义的真实论文文件任务，既非18题中的子集，也不是研究者真实前瞻采纳实验。工具学习使用旧 V5 RAG/QLoRA 正常付费轨迹和真实 PDF；模型决定 accept 后，首次处理隐藏 FlashAttention PDF 作独立功能认证。正常任务训练为 Switch、Toolformer，独立 Motif 认证为 Speculative Decoding，新任务评测为 Self-Consistency：6页初稿，再只修订第6页 takeaway/notes。局部修订是同一任务续写，不算第二个独立任务。独立身份已冻结，但其科研决定独立性尚未人工确认。

新下载的5篇论文 URL、完整 PDF SHA256 与用途保存在私有 `inputs/sources.json`：arXiv `2205.14135/2101.03961/2302.04761/2211.17192/2203.11171`。评测来源 SHA256 为 `1a49ce0373afc89d2d6e97fb1aa8230f6b818c70590d732a3187f753f4df6aba`。各组沿用相同科研设计 Skill、默认布局、题面、来源和交付要求；V5布局证书绑定旧代码，本轮未使用。manual/generated/generated_motif 的实际有序 MCP schema SHA256 相同：`4da93e07a31c1c9ee266c89029e3c758face985a6cf5f3e59cba8ddf558a7e0b`；baseline schema 为 `4f77dfc77a9a0d5773bec1f019bee06e40c1ef2de016d0094da9f5be9c354af1b`，无目录工具。

环境实际值：Python 3.12.15、Node v22.23.2、DSH npm 0.1.5-rc.3、SDK 0.1.5rc1；provider/model 为 `deepseek-official/deepseek-flash`，reasoning off、压缩关闭，已记录运行全部 `reasoningTokens=0`。各 run 保存代码/未提交改动、工具集合与顺序、版本、配置 SHA、schema、代理账本和完整事件；provider实际请求工具schema哈希/顺序、内部重试策略、账单、人评及人工修订分钟仍缺失，不能声称已完整采集。

### 可靠修订与工具 RSI

- `read_deck_plan/revise_deck` 已在四组真实任务中调用：新副本只指定第6页字段，真实核验其余5页 OOXML、正文/notes、几何、表格、媒体字节、图表及嵌入数据和共享资源保持，然后重新 inspect/validate/deliver。仅支持同一 MCP 服务会话内本任务生成并保留原计划的稿件；服务重启恢复与任意外部 PPTX 局部修改未实现。
- 工具名 `read_pinned_figure_catalog`，源码由真实 DeepSeek 提案与修复，实际 TypeScript 编译/Node执行，并在新任务作为 MCP 调用。开发端事先固定“真实候选目录整理”的范围、宿主和 oracle；模型分析正常轨迹、写代码、看训练结果后作 accept 决定。属于受限工具 RSI，不能称完全自主功能发现。
- 第1候选因 for 循环和动态索引越出 AST 纯 JSON 子集拒绝；第2候选通过两个真实来源训练检查。模型 accept 后独立 FlashAttention 功能认证通过，证书只认证字段保持、排序和来源一致，不认证选图、图意或科研判断。
- 学习3请求、39,152 token、代理估费 `$0.009565572`、40.125秒。代码 SHA256 `eeee54e36654bad031f5655fbd2b5332f54e56a43031bf21b9d338c1f006d83b`；证书 SHA256 `738051a1eeb6f9e4f1f389037ed795da818197d6b76eb40a8babb9147b0942f2`。候选、证书及其依赖留私有，不随仓库分发。

### 从轨迹得到的新 Motif 与实际旁路

首次相邻 `sequence` 挖掘未得到目录读取参数边。唯一 artifact 实际是 `pin_source → pin_figure_catalog`，没有 `transfer_evidence`，不能执行有效来源读取旁路；此前将它称为旧 pin/read 的口头描述已纠正，原结果保留。

因真实调用间交错 `read_source`，改用仓库已有 `compile-witnessed-read-chains.py` 的参数边挖掘，不裁剪正常事件、不手写 DAG、不改公共在线规则。两个正常训练决定与一个独立认证决定支持：新目录边 `edge_motif_67fd12eaad68`（`pin_figure_catalog.source_id → read_pinned_figure_catalog.source_id`），普通来源边 `edge_motif_cb44e8637402`（`pin_source.source_id → read_source.source_id`）。`code_nodes=[]`；生成工具 TS 在 MCP 宿主内，不能称 Motif code node。

Self-Consistency 新任务实际 batch `sss-batch-3553bfed-d63d-49a4-91c6-41c2b84c0102` 执行并核验以上两个 read 工具，**跳过1次完整模型请求**。没有跳过实际读取、科研理解、选图或叙事。manifest digest `788b413ebc2ab2c95a979c1492c72b302d5ea2fd5790093afe9a3049b4281916`；证据在私有 `new-motif-witnessed/` 和 `bypass-audit.json`。结构认证和一次 verified 旁路不自动产品注册或成本晋级。

### 全部付费运行与成本

| 用途/组 | run_id | 请求 | 未命中输入 | 缓存命中输入 | 输出 | 总token | 代理估费 USD | 运行秒 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Switch训练 | `49cc449fb6694b4aa0b52382340d8530` | 12 | 30,330 | 252,672 | 9,106 | 292,108 | 0.021542232 | 55.203 |
| Toolformer训练 | `0dd953245d294a5cb7d404f271b8e389` | 13 | 24,582 | 264,960 | 6,753 | 296,295 | 0.017067960 | 45.282 |
| SpecDec认证 | `01afc86c4727494fb16d3f16b69453a9` | 16 | 21,850 | 398,208 | 16,345 | 436,403 | 0.028558248 | 78.829 |
| 普通DSH baseline | `78a2bc0fbc09469ab3d451ce6c751805` | 15 | 34,369 | 319,488 | 4,766 | 358,623 | 0.017946828 | 44.076 |
| 人工目录脚本 manual | `e4da3bf0084547248f3ac915b5a654a9` | 21 | 28,333 | 592,384 | 17,982 | 638,699 | 0.033632604 | 95.745 |
| 生成工具 generated | `75a83be57cc34f79a70dd499c8259c60` | 23 | 41,110 | 669,312 | 9,312 | 719,734 | 0.027523272 | 69.901 |
| 生成工具＋Motif | `7cb2d7455e9c446eb9df2ed29b693417` | 18 | 27,801 | 476,416 | 11,677 | 515,894 | 0.025211196 | 75.104 |
| 工具学习（3个真实调用） | 见 `tool-learning-r2/summary.json` | 3 | 15,423 | 19,712 | 4,017 | 39,152 | 0.009565572 | 40.125 |

本轮累计 **121请求、3,296,908 token、代理估费 `$0.181047912`**，包含工具学习、训练/认证和四组评测；不是账单实付或合格成果成本。重试/恢复已包含相应运行账本，人工与开发维护成本未采集。首次缺API环境的学习失败为0请求/0费用，仍留记录；旧V5费用不混入本轮。

generated→generated_motif 观察到请求23→18（−21.74%）、总token719,734→515,894（−28.32%）、估费−8.40%；但 motif 相对普通DSH仍多20%请求、43.85%总token、40.48%估费。实际 `read_page` 调用为 baseline/manual/generated/motif：6/3/12/3，`render_deck`：1/7/3/4；模型内容、选页、失败恢复、输出量和缓存均不同。每条件仅1次，四组都需事实修订，**不能把5次请求差全部归因于1次verified旁路，也不能宣称同质量降本**。

### 交付质量与失败

三份训练稿共18页，四组各初稿/指定修订稿共8份48页，合计11份66页。7份最终稿42页与完整原文作AI辅助核对：6份需修订，Toolformer主要结论有来源支持但仍有小修；共12项中度、15项轻微问题，非人工盲评。四组Self-Consistency最终稿均不能据本审查算统一质量合格。例：Motif稿第4页notes将22.1错误归为未归一化加权平均，原文是归一化；manual稿UL2提升下界应为3.2个百分点而非1.8；generated稿边缘化对象应为推理路径，不能写答案；baseline的规模增益/线性费用表述过强。完整审查在私有 `review-packet/factual-review.json`，原稿保留。

逐页辅助视觉检查显示原生可编辑流程/表格和页面结构可用，但论文原图偏小；版式整齐不能替代事实质量。原生chart旧PPT样式修改曾被已有资产字节保护拒绝，原因未确定，兼容问题未修复；没有降低保护来放行。首轮AST enum别名误拒绝已修复，工具首候选受限语法拒绝、首次无API环境失败、相邻挖掘负例及渲染恢复均保留。

### 工程验证、复现和下一步

全部验证在服务器，工程测试不当作科研质量或效果结论：场景69项Python，根136项Python/29项Node，公共smoke与场景MCP smoke通过；生成工具真实stdio MCP32/32检查、0API；交错参数边编译7项诊断通过。日志分别在 `test-logs/research-ppt-v6-scene-final-20261011.log`、`research-ppt-v6-root-test-20261011.log`、`research-ppt-v6-root-smoke-20261011.log`、`research-ppt-v6-mcp-smoke-20261011.log`、`research-ppt-v6-real-generated-mcp-checks-20261011.log`、`research-ppt-v6-witnessed-compiler-checks-20261011.log`。

最短新任务、工具学习及Motif编译命令见 [场景README](../../scenarios/research_ppt/README.md)；原本轮执行命令、有效配置与哈希分别保存在私有 `train-*/config.json/run.json`、`eval-*/config.json/run.json` 和 `tool-learning-r2/config.json/summary.json`。记录根为 `.local/research-ppt/v6-tool-rsi-20261011/`；重跑须新目录/实验ID，禁止覆盖旧账本。新克隆不带私有工具/证书/Motif，须自行收集正常任务并独立认证；旧私有准入guard是本轮复现依赖，不是公共安装即有的证书。

下一步先修订已发现事实并独立人工盲评、记录修订分钟，再固定schema与布局在新论文上重复对照和核账单；另补MCP重启后的可验证状态恢复。当前证据支持受限工具RSI和真实学得目录参数边的执行闭环，不支持稳定同质量总成本收益。

### 最终报告与下载核验

同伴八节结构报告已在服务器生成22页，全部22页辅助视觉检查未发现排版阻断。11份原始PPTX/PDF、66张逐页PNG、全页蒙太奇、HTML初稿/修订对比、匿名运行表及费用摘要已下载；包中104个文件逐项核SHA，清单本身另核，合计105文件。不包含来源论文、密钥、原始API事件或生成候选代码。报告目检只认证报告可读，不能把含已知错误的PPT计作合格。

- 服务器：`.local/research-ppt/v6-tool-rsi-20261011/deliverables-reviewed/`。
- 本机下载：`.local/research-ppt/v6-deliverables/reviewed/`，入口 `index.html` / `report.pdf`。
- 报告SHA256：`9e867c26afb75126daba9e0eade5e0d36431a3fac7692a894ce09c1048f007a0`。
- 下载ZIP：`.local/research-ppt/v6-tool-rsi-20261011/deliverables-reviewed.zip`，SHA256 `8b6fab0c456993935a55f04d59c5caaa2e1edd47ff927962a37f3f4f4ae20916`。
- 清单SHA256：`5b0c7b834a38ce78d95c7446df734bd604b3b023d3d15954b0c16ca9e9b53321`；生成日志 `test-logs/research-ppt-v6-deliverables-report-reviewed-20261011.log`。

此前23页版本因零请求失败行token汇总显示未知、空介绍页和边界说明不完整而另存后修订报告；不改实验运行、账本或PPT原稿，新增模型请求为0。最终报告明确学习3请求/39,152token、同会话状态限制、开发端固定目录能力边界与真实1请求旁路。

### 提交与同步状态

用户已明确授权中文commit/push至 `feature/research-ppt-agent`、不PR，提交前已告知范围。服务器中文功能提交 `3e29f8ed46043a1b5f2393da53d3425f0db44487` 已完成，树 `794b1f998a8e83d9e8049489ef690314217a4447`，以GitHub当前目标头 `2368235f274329be6227a8393b850633cb943da4` 为parent，吸收旧未推送PPT实验seed的场景与必要兼容补丁；不含他人主线交接改动、私有材料或原日志。旧seed及所有运行配置保留，不追改历史实验版本。

2026-10-11已完成GitHub同步、未创建PR：用户开启本机7890代理后，已有Git凭证可用；从任务私有bare副本普通快进推送 `2368235f274329be6227a8393b850633cb943da4 → ea1d9c3ddd164802cfd3970dce285c9147b4862b`，包含功能提交 `3e29f8ed46043a1b5f2393da53d3425f0db44487` 与中文记录提交，随后通过 `ls-remote` 核验远端HEAD。未force、未改共享本机检出的Git状态，未修改全局代理配置。另补中文文档提交记录同步成功；最终HEAD见Git历史及私有 `submission/final-receipt.json`。

先前连接失败保留：连接器写Git树返回403（Resource not accessible by integration）；本机12000代理未监听，直接HTTPS Git读取重置，服务器HTTP/1.1读取超时，本机SSH无可用公钥，当时Git凭证helper无现成认证。该限制已通过7890代理和已有Git凭证解决，不是缺少用户授权或自动审批拒绝。提交状态凭据及可推送Git包留在私有 `submission/`，不是实验产物质量认证。
