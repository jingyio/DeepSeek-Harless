# V14：容量恢复、真实交付与继承程序对照

- 实验ID：`research-ppt-v14-recovery-20261013`；日期2026-10-13。
- 结论：同一新任务的三组原稿均机械导出成功；RSI确实调用继承程序并verified跳过1次请求，本次模型费用低于普通链，但三组原稿均有明确科学错误，不支持相同合格质量下的净降本。另存明确辅助修订稿，不能代替原绩效。
- 代码状态：开发worktree基点`d168e924`加V12–V14未提交改动；服务器仍`6ced827`加部署。V12/V13设计与报告四文件已在隔离发布worktree中文提交`4008d2d`并推送用户分支，无PR；此次文档提交没有发布实验源码。V14未提交/未推送。

## 1 / 问题、假设与任务

V13局部只读旁路生效，但容量恢复、公式与部署错误吞掉收益。V14先修普通工程底座：一次反馈全部容量问题、保留草稿后局部patch、模型前检查真实编译依赖。不扩大候选矩阵。若这些措施仍无法给出科学/视觉合格交付，或生成程序不优于简单脚本，不主张RSI净收益。

评测为BitFit原始PDF（arXiv:2106.10199v5，9页）从头生成4页中文科研介绍，含封面、机制、完整原表1、BERT-large GLUE结果与口径/局限。PDF SHA `56a52ea59f763e312687f8b0c1c8953a508c471925f17733e6c580be832000ed`。图件为PDF第3页完整原表与caption的版本化裁片，不重建数据；三组使用相同字节。BitFit与旧训练/留出来源不同；DoRA仅独立部署认证，不作模型质量任务。

三组统一来源、任务、页数、模板集合、提示、八工具及顺序、模型和上限：

- B0：更新后普通Harness/MCP；模型自己选下一步。
- B1：同底座，手写与生成程序相同的只读选择规则、独立守卫及回执检查。
- B3：同底座，继承V13候选06的认证有界派生程序，不重新发现/生成候选。

DeepSeek官方`deepseek-flash`，思考/压缩off；每组上限$1.50、40步、5000输出token，串行。不限总预算授权沿用；新副本，不覆盖原稿。所有测试、解析、模型、编译与渲染在服务器执行并留日志，本机只编辑、读取、下载/字节核验和查看已渲染图片。

## 2 / 工程实现与认证边界

公共新增`scenarios/research_ppt/ts/template-library.ts`聚合文字问题，图片/来源/路径错误优先拒绝；`template-page-patch.ts`显式合并草稿，绑定job/page-plan/page/artifact摘要，不自动删科学内容。`template_preflight.py`与TS CLI用真实上游checker/finalizer/compiler及独立LO渲染检查模板机械依赖。私有八工具为`read_reference,list_templates,save_plan,read_page,write_page,patch_page,revise_design,export_deck`。

28页型机械短探针：26通过，`researchstudio-editorial-01-cover`及`sleep-science-15-references`因无href的SVG链接被拒；失败页禁用，不放宽checker。报告SHA `1f76d04d7028d0b362f771fce2ca5eb1dced9666389d5955f64bb15d8bc5453a`。这不是实际容量上限、任意公式、科学或审美认证。

新任务目录实际安装并冻结所需图标，源/目标SHA一致，路径不能逃逸。`smoke-bitfit-03`真实stdio33调用、0模型，四页完整导出与LO通过，安装6图标。MCP独占锁与commit-pending标记在未完成提交时fail-closed；SIGKILL遗留锁仍需人工处理，不宣称任意中断自动恢复。

继承只读选择器仅在首次成功save_plan且无任何write/revise/patch时选最多4个未读页面；任一写入尝试永久停止旁路。只有真实读回执及完整后置状态通过才计一次请求跳过，不把4次工具读取算4次模型减少。

八工具需要新部署认证。DoRA实际Harness装配/真实MCP save-read、候选输入/输出和15反例通过。最终部署check SHA `d06985eec013896a9bd6e669b8561af206d0c7dc5d4b2d01d9f8ed8963508366`；manifest SHA `37167379faa21b0211815c9499a9977e1edb2af49e506199a57733a54dbabb3f`，527依赖。原功能证书`c043cede…`与派生码`5bdce766…`保持，旧部署摘要不沿用。

## 3 / 统一新任务成本与恢复

| 组/run | 真实请求 | miss输入 | hit输入 | 输出 | 总token | 代理USD | 阶段秒 | verified |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 `bitfit-b0-03` | 38 | 65,315 | 1,382,656 | 10,561 | 1,458,532 | 0.04056362 | 184.57 | 0 |
| B1 `bitfit-b1-03` | 35 | 62,537 | 1,669,760 | 13,633 | 1,745,930 | 0.04513925 | 190.61 | 1 |
| B3 `bitfit-rsi-03` | 30 | 53,795 | 1,158,528 | 10,752 | 1,223,075 | 0.03599209 | 127.35 | 1 |

RSI本次观察相对B0请求-21.05%、总token-16.14%、代理费用-11.27%。只有1次差额经过结构回执证明，其余7次不能全归因于候选；一题无重复，写稿内容/恢复路径不同，不能推断稳定效果。B1请求下降但费用+11.28%，说明请求数不能代替真实费用。

| 组 | 容量失败call | patch尝试/成功 | 导出尝试 | 原稿机械通过 |
|---|---:|---:|---:|---|
| B0 | 6 | 11 / 5 | 3 | 是 |
| B1 | 11 | 14 / 5 | 3 | 是 |
| B3 | 10 | 11 / 3 | 1 | 是 |

工具次数不直接等于恢复模型费用。摘要`summary-04-final.json`只汇总显式run；零请求首启与后续共用project的当前工具日志不会错误归到首启。保留原run摘要、日志SHA和所有观察，不修改旧记录。

## 4 / 全部尝试与失败费用

- `bitfit-b0-01`漏加载既有私有凭证，0真实请求/$0；未交付。后续加载但不打印值。该run不是免费完成任务。
- `bitfit-b0-02`准备端漏安装项目图标，40请求、1,680,123token、$0.04545532，四次导出失败、40步耗尽；不删除。这个共同部署缺陷单列，不能只加在B0匹配行人为制造B1优势。
- 部署check01 SDK字段snake_case/alias误用、check02复制旧七工具snapshot，两次零模型失败；明确修正后check03通过。随后图标/容量提示改变源码，重新check04/manifest04，不能偷偷重签旧摘要。
- 三组03共103请求、4,427,537token、$0.12169496；含前置失败全轮5尝试共143请求、6,107,660token、$0.16715028。
- 辅助04零模型新副本在p2标签超过11.1单位时安全拒绝，记录保留；辅助05明确缩短非科学标签后成功。新增DeepSeek0，但CPU/AI审阅/人工分钟未知。

预算代理估费不是账单。实付、人工修订/独立人评、服务器/CPU、开发维护金额均未知，不填0。

## 5 / 科学与视觉质量

全部12页原稿AI辅助核原文/实际PNG，不是独立盲评。原表全部行列与caption三组均保留；正文原生文字run分别69/66/69，notes各4，原生chart/table/OMML无本轮成功证据，原表内部仍为图片不可逐格编辑。

原稿均有明确缺陷：三组p2讲稿LN1公式漏残差+x；B0把MLP整体称线性层、4/9说成多数、把6倍与45倍混写；B1突出值与标签错配、81.8错误归给Guo；RSI将带†/‡的Full-FT引用行概括为本文实测，把均值±std泛化至全部V行。B0/B1 p4底部文字重叠，RSI p1/p2标签重复。机械验收没有拦住这些问题，原稿不能视为科研质量合格。

另外生成`reviewed-bitfit-rsi-05`明确辅助稿：修重复槽、残差+x、Full-FT100%参数口径、无标记V实测与T引用归属；原表第3页SVG字节完全保持。真实导出通过（64文字run、4notes），AI辅助全页查看未见原重复/重叠问题，独立人评仍未完成。该稿不是新独立任务、RSI自主发现/修复或原run合格成绩。

## 6 / 学习摊销与结论

继承V13纯候选发现$0.150820872及两部署失败$0.090900588，已知额外历史投入$0.241721460，另有与正常交付重叠的训练/认证任务单列，不重复加总。本轮没有新候选发现成本，但旧投入不能消失；零模型认证仍有CPU/审阅维护开销。

当前证据支持：新任务重新认证部署后，继承程序真实调用并verified旁路1次；普通容量patch/预检工程正常工作。证据不支持：全自主发现、学习机制自我改进、复杂生成同质量净降本、稳定胜过同规则B1。质量不合格不能据$0.00457153单次观察差估计回本点。

下一步先做普通工程：固定位置tspan冲突在付费前/导出前拒绝，数值-标签/引用行/公式IR显式校验；然后1–2新任务统一质量门槛与全部恢复费用比较，再决定是否从真实重复恢复路径学习新结构。保持默认产品renderer不切换，不无目标增加候选。

## 7 / 入口、验证与交付位置

入口：私有根`.local/research-ppt/research-ppt-v14-recovery-20261013/`；`native-fill/prepare.py`准备，`rsi/diagnose_deployment.py`独立部署认证，`rsi/prepare_runtime.py prepare/verify`冻结，`rsi/matched_entry.py`实际运行。先激活服务器项目环境，再只在付费入口加载私有凭证；新job/run ID必须唯一。最短付费参数`--group baseline --scenario <fresh>/scenario.json --job <fresh>/native-fill-job.json --run-id <new> --budget-usd 1.50 --max-steps 40 --max-output 5000 --call-model`；script/rsi另加最终manifest04。源码变化会使冻结配置失效，不复用旧job掩盖漂移。

已验证日志在`test-logs/<ID>/`：根npm test 136Python/29Node、smoke18开发诊断；场景80Node、Python预检8、草稿patch5、选择器15、真实协议21call和完整导出33call。版本不同的同套回归不相加；模拟检查不当费用结论。

本机根`H:/DeepSeekHarness/.local/research-ppt/research-ppt-v14-recovery-20261013/`：

- `audit-b0-03/bitfit-b0-03/delivery/presentation.pptx`
- `audit-b1-03/bitfit-b1-03/delivery/presentation.pptx`
- `audit-rsi-03/bitfit-rsi-03/delivery/presentation.pptx`
- `reviewed-bitfit-rsi-05/project/exports/attempt-01/presentation.pptx`（辅助稿）

V1–V14总报告/逐轮清单/全部PPT索引本机另存`.local/research-ppt/reports/`。总报告不把不同轮任务成本连成持续下降曲线；原日志、论文、密钥不提交。

## 8 / 总实验报告交付核验（2026-10-13）

服务器生成最终`output/pdf-04/research-ppt-v1-v14-summary-20261013.pdf`，18页，新增DeepSeek请求0；全部18页服务器PNG已AI辅助目检，未见报告截断、落单标题、文字方块或版面重叠。报告本身的排版核验不替代实验PPT的独立科学/审美评审。最终PDF 2,527,673字节、SHA `926842813d9a0251b7da63e437cdae84be02b9d9820199eb6a0b50c3ce806c0e`；本机下载与服务器SHA/size一致，保留01–03中间版本。

本机`.local/research-ppt/reports/`同时交付`research-ppt-v1-v14-checklist.md`与`research-ppt-v1-v14-ppt-index.csv`，包含逐轮结果/技术新增/身份、38份历史与V14原稿及另1份V14辅助稿，39路径全部确认存在。PDF含技术线/理论边界、费用与失败、V14原稿/辅助稿全页拼图、五分钟汇报稿；V3/V4与V2累计记录重叠，不给跨轮总成本或持续降本曲线。零模型PDF首次字体依赖缺失和排版修订保留日志，不冒称全部一次成功。文档/公开接口检查不触发新付费矩阵。

## 9 / V14完整证据保全

本机实验根`server-evidence-final-02/{evidence.tar,manifest.json,result.json,restored,local-verification.json}`已下载并恢复：4,175证据文件、164,664,804字节逐项SHA/size一致，0不一致；另有内嵌同字节manifest。archive 173,240,320字节，SHA `fd03974ebcfbd3dfe6139507e2b75049be558facf02db5ad2e8b9d8c6023516d`，manifest SHA `b4d5288c1c3094a17d6f98ab97c76df6cc4dd62fc247c38ddef515ca2f43b2a4`。

范围为V14完整私有目录、全部V14测试日志、35关联validation目录、场景源码/依赖锁及封存时文档镜像；付费日志均在本轮私有目录，不另找到root run。排除凭证、已安装node_modules/环境、既有固定上游和V13另存证据，不称全服务器镜像。首次01因node_modules符号链接保守拒绝，失败记录保持；02明确排除已安装依赖，不跟随符号链接、不删旧包。封存时文档为当时镜像，本节及交接核验结果随后追加，不追改已封存包。
