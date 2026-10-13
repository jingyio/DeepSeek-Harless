# 普通文件管理跨流程学习实验

最新[报告契约修复与第六阶段完整基准](../../docs/experiments/file-management-report-benchmark-20261013.md)已完成。inspection全部检查成员、literal_search实际命中/搜索收据、task_result当前效果结果分开；显式阶段范围在选集合前验证，三组共用同一普通契约。两失败修订全部保留，新版本重新获取并认证两代库。36新质量三组各12/12；144完整基准H60/72、L2 62/72，60共同合格配对610→401HTTP、估费−16.02%。22主验收失败保留，未证明整体完全合格或真实业务泛化。

当前fm-report-quality-20261013-d3053cd5，指针.local/file-management/report-current.json；两库零留出前冻结，未用质量/基准再训练。完整基准第二段再入为0，再入增量只见于两阶段新质量。效果/恢复仍普通Harness，未组合单独PlanScene认证；全系列439次/3972HTTP/峰值估费USD3.399507360，实付未知，68失败及全部纠正费用留存。接口与版本见[实施记录](../../docs/changes/file-management-report-contract.md)，默认SDK/Web不开。

```sh
# 新版本prepare后获取/认证，已有attempt禁止覆盖。
node scripts/project.mjs python scenarios/file-management/report_study.py
node scripts/project.mjs python scripts/run-report-pipeline.py --experiment <NEW_EXPERIMENT>
# 完成实验仅离线汇总/审计；辅助SDK为0云请求。
node scripts/project.mjs python scenarios/file-management/report_study.py --experiment <EXPERIMENT> --summary
node scripts/project.mjs python scripts/audit-report-study.py --experiment <EXPERIMENT>
node scripts/project.mjs python scripts/summarize-report-study.py --experiment <EXPERIMENT> --negative-version <NEGATIVE_VERSION>
node scripts/project.mjs python scripts/check-report-contract.py --experiment <EXPERIMENT>
node scripts/project.mjs python scripts/check-report-sdk.py --experiment <EXPERIMENT> --arm L2 --stale
```

完成后本README已更新，使当前源码与付费冻结hash不同；付费重现需归档源码或prepare新版本。原模板Office/图片及PDF只复制，无新版式作者化；查询只覆盖已交付正文，未盲评或账单对账。重命名全局编号以及转换产物/空文本读取口径需要另版本明确，旧结果不追改。

## 先前第五阶段（历史）

最新[第五阶段两代库闭环](../../docs/experiments/file-management-rsi-cycle-20261013.md)完成45次：L1运行6新学习/3独立认证任务，从5份真实native残余图学习L2；在6新条件×H/L1/L2×两次重复的36次留出中，H10/12、L1 6/12、L2 7/12合格，盘点各6/6而内容检索仅4/6、0/6、1/6。L1/L2共同合格盘点6次请求65→45、估费−15.29%，尚不支持整体质量等价降本。全系列201次/1693HTTP/峰值估费USD1.457616816；实际账单未知，15项本轮失败与此前失败均保留。

L2以不可变parent L1加新next图，只在首集合完整完成后等待模型读真实followup.txt数据并选择第二集合。插件不预选、不使用留出或Runtime参数节点训练；语法/两次上界由工程限定，未认证任意图或语义报告。共享CLI/TS/来源/守卫见[接口记录](../../docs/changes/file-management-rsi-cycle.md)。当前ID为fm-rsi-cycle-20261013-7f6a246a，指针.local/file-management/rsi-cycle-current.json，库锁/源码/原事件/逐HTTP/失败/最终副本/分析源码均私有留存。默认SDK/Web不开启。

```sh
# 新实验：准备冻结，依次获取L1经验/独立认证、导出L2、评测新留出。
node scripts/project.mjs python scenarios/file-management/rsi_cycle.py
node scripts/project.mjs python scenarios/file-management/rsi_cycle.py --experiment <EXPERIMENT> --role learn --call-model
node scripts/project.mjs python scenarios/file-management/rsi_cycle.py --experiment <EXPERIMENT> --role certify --call-model
node scripts/project.mjs python scenarios/file-management/rsi_cycle.py --experiment <EXPERIMENT> --learn-l2
node scripts/project.mjs python scenarios/file-management/rsi_cycle.py --experiment <EXPERIMENT> --role evaluate --call-model
# 已完成实验只读汇总/独立审计与离线配对；本机SDK检查0云请求。
node scripts/project.mjs python scenarios/file-management/rsi_cycle.py --experiment <EXPERIMENT> --summary
node scripts/project.mjs python scripts/audit-rsi-cycle.py --experiment <EXPERIMENT>
node scripts/project.mjs python scripts/summarize-rsi-pairs.py --experiment <EXPERIMENT>
node scripts/project.mjs python scripts/check-rsi-cycle.py --experiment <EXPERIMENT> --arm L2
```

源码/两库/材料/划分在首次付费前冻结，L2在零留出时另锁。已有attempt不覆盖，完成后README更新已改变当前源码hash；付费重现须使用frozen-source或prepare新实验。第五阶段受限机制闭环已完成，内容检索质量和第六阶段完整冻结基准仍待推进，修订应另建冻结版本。

## 先前批量脚本对照与计划认证

[批量脚本对照与计划认证](../../docs/experiments/file-management-batch-plan-20261013.md)完成：读取三组18次全部验收合格，H/S/M请求55/37/37，脚本估费最低，主要收益可由普通批量调度解释，未观察到认证Motif的额外费用优势。计划链新增3普通训练/2认证与5份实际文件重放，4对评测M4/4、H3/4；共同合格3对请求23→19、估费−3.55%，清理题费用+5.08%。两组预登记故障都用原授权恢复。验收程序异常和H误恢复仍为失败，不追改。

新PlanScene独立于原FileScene，13工具两组一致；只在冻结实验副本授权copy/move/quarantine，preview→authorize→execute实际版本/权限/收据守卫，restore由模型决定并精确绑定同token，部分执行不自动重试。共享API/TS/权限/持久化/限制见[接口记录](../../docs/changes/file-management-batch-plan.md)。默认SDK/Web不开启；单进程串行、同文件系统、字节快照，未认证一般恢复图或Office转换。全系列156次/1231请求/代理估费USD0.990767448，实付未知。

```sh
# 新读取三组；旧原生认证库在私有parent目录。
node scripts/project.mjs python scripts/file-batch-study.py --parent <COLLECTION_EXPERIMENT>
node scripts/project.mjs python scripts/file-batch-study.py --experiment <BATCH_EXPERIMENT> --call-model
node scripts/project.mjs python scripts/audit-file-batch.py --experiment <BATCH_EXPERIMENT>
# 新计划准备，普通训练/认证后才加载新库评测。
node scripts/project.mjs python scenarios/file-management/plan_study.py
node scripts/project.mjs python scenarios/file-management/plan_study.py --experiment <PLAN_EXPERIMENT> --role explore --call-model
node scripts/project.mjs python scenarios/file-management/plan_study.py --experiment <PLAN_EXPERIMENT> --role certify --call-model
node scripts/project.mjs python scenarios/file-management/plan_study.py --experiment <PLAN_EXPERIMENT> --learn
node scripts/project.mjs python scripts/check-file-plan.py --experiment <PLAN_EXPERIMENT>
node scripts/project.mjs python scripts/check-file-plan.py --experiment <PLAN_EXPERIMENT> --stale
node scripts/project.mjs python scenarios/file-management/plan_study.py --experiment <PLAN_EXPERIMENT> --role evaluate --call-model
node scripts/project.mjs python scripts/audit-file-plan.py --experiment <PLAN_EXPERIMENT>
node scripts/project.mjs python scenarios/file-management/plan_study.py --experiment <PLAN_EXPERIMENT> --summary
```

当前指针.local/file-management/batch-current.json与plan-current.json分别指向fm-batch-20261013-41304bfb和fm-plan-20261013-b2a877a4。单题5美元，读取64步/计划40步/输出4000，全系列1000美元保护；默认prepare/preview免费。已有attempt/learned禁止覆盖，README更新也会使旧源码检查失效，付费重现须用冻结源码或新prepare。计划旧失败fm-plan-20261013-596394ac及两次免费批量准备失败留存。

## 先前集合读取阶段

最新[集合读取阶段](../../docs/experiments/file-management-collection-20261013.md)已完成22次运行：6普通探索、4独立认证、6对H/M评测全部通过独立验收。从不同大小的真实模型选定集合见证一个foreach(pin/read)+gather图；未训练的增量流程用于认证、内容检索用于评测。实际请求54→39、峰值估费−15.58%，其中一对费用+1.15%。相同14工具下比较，尚未验证优于普通批量脚本或旧标量Motif。全系列估费USD0.778423656，实际账单未知，所有失败/恢复继续保留。

集合协议、共享TypeScript适配、离线编译与CLI见[实施记录](../../docs/changes/file-management-collection.md)。仅接管模型选定后的读取调度，文件选择、索引和语义报告仍由模型负责，默认SDK/Web不开启；写关系和语义分支尚未认证。

```sh
# 创建新材料、任务和冻结源码；复用此前验证的私有作者资产。
node scripts/project.mjs python scenarios/file-management/collection_study.py
node scripts/project.mjs python scenarios/file-management/collection_study.py --experiment <EXPERIMENT> --role explore --call-model
node scripts/project.mjs python scenarios/file-management/collection_study.py --experiment <EXPERIMENT> --role certify --call-model
node scripts/project.mjs python scenarios/file-management/collection_study.py --experiment <EXPERIMENT> --learn
# 准备器旧日程全H先；用独立冻结调度器在0评测时平衡3对H先/3对M先。
node scripts/project.mjs python scripts/run-file-collection-eval.py --experiment <EXPERIMENT>
node scripts/project.mjs python scripts/run-file-collection-eval.py --experiment <EXPERIMENT> --call-model
node scripts/project.mjs python scripts/check-file-collection.py --experiment <EXPERIMENT>
node scripts/project.mjs python scripts/check-file-collection.py --experiment <EXPERIMENT> --stale
node scripts/project.mjs python scripts/audit-file-collection.py --experiment <EXPERIMENT>
node scripts/project.mjs python scenarios/file-management/collection_study.py --experiment <EXPERIMENT> --summary
```

集合新指针`.local/file-management/collection-current.json`；当前ID`fm-collection-20261013-264b9fc2`。源码/协议/策略/见证/原事件/逐HTTP/最终副本均留存；已完成任务与learned不得覆盖。文档更新不改冻结源码，旧实验只读汇总/审计，付费重跑须使用归档源码或prepare新版本。此轮复用已有二进制模板，新增路径/数量/文本/空文件/损坏条件，未人工盲评或真实办公泛化。集合任务64步、每题5美元，全系列1000美元预算保护。

## 先前标量读取阶段

在线阶段完成两版共60次完整任务对照，详见[报告](../../docs/experiments/file-management-online-20261013.md)。第一版全12流程整体未省费；修正13来源历史保留后，盘点/索引/内容检索6对全部通过，请求44→36，估费−11.68%，其中仍一题费用上升。生成材料与定向重复验证不代表真实办公泛化，默认入口没有全面启用。

共享manifest的显式读取声明、TypeScript守卫、历史保留与摘要兼容见[接口记录](../../docs/changes/file-management-online.md)。库/旧失败保持，写关系只作候选。

```sh
# 默认准备/冻结新配对任务，PARENT为已真实探索并独立认证的私有实验目录。
node scripts/project.mjs python scenarios/file-management/online-study.py --parent <PARENT>
# 定向13来源范围；省略families即全12流程。
node scripts/project.mjs python scenarios/file-management/online-study.py --parent <PARENT> --families inventory index content_search
# 显式启动已授权云实验；已有attempt不覆盖。
node scripts/project.mjs python scenarios/file-management/online-study.py --experiment <EXPERIMENT> --call-model
node scripts/project.mjs python scripts/audit-file-management.py <EXPERIMENT>
node scripts/project.mjs python scripts/collect-file-management-graphs.py <LATEST_EXPERIMENT> <OTHER_ONLINE_EXPERIMENT>
```

两组每对input/prompt/schema一致、同目录从pristine恢复、交替顺序，每次最终副本先保留。单题5美元，系列累计1000美元。源码归档/轨迹/账本/错误留私有目录。README更新不回写冻结源码；重现实验应使用归档源码或重新prepare新版本。

任务基于三篇真实 PDF 与生成的 Word、Excel、图片、文本。数据放在忽略的 `testpdf/file-management-experiment/`，原始三个 PDF 保留。每任务独立副本、Session、工具收据和费用记录。

## 当前入口

使用 Codex bundled Python 运行 `author_fixtures.py --output <assets>`；用 bundled Node 与 artifact-tool 运行 `author_sheets.mjs <assets>`，通过 `FM_ARTIFACT_MODULE_ROOT` 指定 bundled node_modules。作者工具只在准备材料时需要，普通运行不依赖 artifact-tool。Word/表格作者流程执行渲染检查。

在仓库根目录：

```sh
node scripts/project.mjs python scenarios/file-management/prepare.py --assets .local/file-management-author/assets-v3
node scripts/project.mjs python scenarios/file-management/experiment.py --limit 6
node scripts/project.mjs python scenarios/file-management/experiment.py --limit 6 --call-model
node scripts/project.mjs python scenarios/file-management/experiment.py --role explore --call-model
node scripts/project.mjs python scenarios/file-management/experiment.py --role certify --call-model
node scripts/project.mjs python scenarios/file-management/experiment.py --summary
node scripts/project.mjs python scenarios/file-management/learn.py --experiment <private-experiment-directory>
```

准备入口冻结24探索、12认证、24待评测任务。默认只预览；授权系列总上限1000美元，单任务保护5美元、48模型步、4000输出 token，所有尝试累计记账。失败不覆盖，也不自动整轮重试；修改后创建新实验版本，旧费用继续进入系列账本。估费沿用现有预算代理峰值费率，不代表实付。

## 工具和修改范围

12个场景 MCP 工具通过现有 Harness 执行，不新建模型循环。读取与内容判断分开：模型选择文件和类别，服务负责版本绑定、解析、索引、摘要、计划检查、写入与恢复。图片只读属性，不声称 OCR；PDF 当前仅前两物理页、正文最多6000字符，显式标记范围与截断。

修改只发生在具有实验副本标记的目录。先签发计划，再执行；拒绝覆盖、路径越界、符号链接、未授权操作和失效文件身份。操作保存原文件、每步进度和后置摘要，恢复检查后来是否有其他操作。收据、日志、索引写到私有 `.local/`。

## 学习边界

统一保留包括写操作与失败在内的原始执行图；时间顺序边和观测状态不是自动执行条件的证明。现有编译器认证有实际参数来源的只读局部 Motif，至少两个独立训练任务和第三个认证任务，真实文件重放、工具 schema 和执行版本须一致。新集合编译器仅支持四角色的受限foreach/gather形状，以实际变大小成员传递及完整覆盖认证；未知分支、效果操作和其他数组控制仍为候选，不把手写文件工具、合成材料或普通缓存当作学得成果。

首次探索输出只证明任务、轨迹和局部学习；之后标量与集合阶段分别完成显式在线对照，结果见各自报告，不能混合不同接口的费用当作产品增益。真实 PDF 的科学理解不在本轮验收范围。生成材料中的检索/分类检查与文件完整性另行验收。

## 首轮结果

正式实验 `fm-20261013-01c48298`：24探索任务完成、20通过冻结验收；12认证任务完成、11通过。完整保留36张观测执行图（762工具节点、118派生写操作节点）、18种连续序列候选和47类观测状态转移。它们不等于已经认证的分支或写操作规则。

从18个独立训练任务、跨10类任务的117条真实参数传递中学出1个 `pin_file → read_file` Motif，并经独立认证、213份文件读取重放及权威Node manifest校验。库位于 `.local/file-management/fm-20261013-01c48298/learned/`；当前不默认启用。

正式36任务292请求、代理估费0.20159148美元；包含6项试跑，总42任务336请求、0.239280204美元。5项未通过验收、17次工具错误（试跑12、正式5）和一次离线收集器修复均保留。内容检索结果集合、重命名编号作用域需要下一版本明确；原始失败不追改。详见实验记录。
