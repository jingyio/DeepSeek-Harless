# 论文校对 当前交接

## 2026-10-21：数据驱动证据程序复用实验

- 分支`codex/motif-cost-learning-20261021`，实现`76ca3e2`；新增从真实原生代码及前后快照学习的配对证据程序，独立新输入认证，TypeScript按模型选择、当前输入和版本守卫执行。不是模型权重训练。
- 最新匹配25→16次请求，864,346→501,764总Token，USD0.03208103→0.02229210，实际认证执行1次。全部数字／p95／配对t区间及判定用独立实现复算一致；没有人工科研盲评，不宣称稳定同质降本。
- 此例仅覆盖固定配对协议的证据复算，研究问题与审阅判断仍由模型完成，不替换原校对／Script RSI库。普通路径、File SDK和上游DSH保留；实验默认关闭，线上仍7e167ed。
- Linux完整Python1718／Node1359通过（各4skip），smoke/motif通过。所有旧失败、训练／认证／机械重放和费用见[成本学习记录](../experiments/three-scene-motif-cost-learning-20261021.md)；本地可审阅包位于`.local/deliverables/geneloop-motif-cost-learning-20261021/`，私有原轨迹不提交。
- 后续扩大稿件与协议覆盖；先用[接口](../interfaces.md#artifact-motif-独立实验接口2026-10-21)独立复测，正式发布仍走统一服务入口。以下段落按其历史日期保留。

## 2026-10-21：提示型 Script RSI 闭环

- 更新时间与交接人：2026-10-21，Codex。
- 目标与本次范围：只接通提示型Negative Motif自动生成/独立审核/发布/后继使用的小闭环。沿用已有编译器与同一私有store；未扩大自动早停、生产或外部写入权限。前轮Positive描述闭环及费用保留在Git历史与对应实验中。
- 分支 / 代码：`codex/paper-negative-learning-loop-20261021`，基于本地`40d015ca`，已通过`3a295837`同步main `73591f62`并保留两侧文档，兼容实现为`99e1b031`。已推送并创建[PR104](https://github.com/jingyio/GeneLoop/pull/104)，未合并/部署；远端CI以该PR当前检查为准。父PR100状态不等于本分支CI。Desktop/SSS的其他脏工作区未动。
- 已完成：`script_negative_learning.py`复用当前原生失败编译，两个不同任务且工具源码一致才有候选；有界模型生成+独立审核，强制prompt_only，审核缓存与失败不自动付费重试。`advance-script-motifs.py`区分完成任务Positive历史和已结束任务Negative历史，发布同一不可变round。`script_learning_store.ts`接入negative_file/digest与冻结加载；Runtime实际失败后投递建议。默认无negative-learning.json不启用。
- 接线修复：自动生成12个Positive算子而实验未配置Embedding，曾因Invalid URL连带停用整个Runtime；`optionalScriptRuntime`现对空库直接跳过，对非空匹配器初始化失败仅局部回退，Negative/Reuse和原生Agent继续。完整配置下原cache catalog保持可用。库摘要/来源/代码锁失败仍保守拒绝。初判为空库已纠正，不以新增算子数量称收益。
- 已验证：最终完整Python1359通过/213跳过，最终完整Node1206通过/5跳过；相关Python35、Node34定向通过，smoke与motif:check通过。确定性测试仅作诊断。完整Node曾有1项既有MCP子进程5秒期限失败，单独7项复跑及停付费任务后的完整Node均通过，未放宽超时、未删除失败日志；并行负载原因尚属推测。
- main兼容更新：使用DSH的`isAgentLoopRequest`标记绕过compaction等辅助请求；自动提示规则逐失败见证绑定目标参数schema，无关工具新增允许提示复用，目标变化仍失效，早停规则不放宽。合并后Python1517通过/235跳过、Node1357通过/15跳过；相关Python38/Node38、smoke/motif通过。见[main兼容记录](../experiments/paper-rsi-main-compat-20261021-v1.md)。
- Windows CI修复：首轮2项失败定位为worker发布指针使用系统反斜杠，违背共享POSIX路径协议，继承时被拒绝。已统一三种资产指针为`as_posix()`并保留安全校验，原发布/继承回归补充格式检查；首轮失败不删除，远端结果以PR104最新提交为准。该序列化修复不另跑付费实验。
- 真实结论：见[Negative闭环验收](../experiments/paper-negative-rsi-20261021-v1.md)。同论文两种历史失败候选，非七篇独立论文。A/B任务传输失败但原生结构错误仍自动采集；学习400后做了一次局部worker恢复。C自动发布5da69dc7…，D精确消费并提示；D结束自动重新生成/审核提示，另编译12个正面算子。E局部发现组件接线问题。第二次局部重编译/当前loader认证后，最终F/G均在当前代码下真实命中并投递，F自动发布a21a7de1…由G精确加载，源码与冻结快照一致。两次人工worker恢复单列，不冒充自动触发。
- 质量与限制：C/D均有实际7页PDF及工具交付回执，但在最后组件隔离修复前；最终F/G为45秒投递检查，主动取消，未重复完整恢复。没有重检文献真实性或逐页视觉验收，不能称完整论文质量合格。D仍尝试不合法单章重组且保留旧说明；提示不保证修复成功。A通用summary把原论文图片PDF算成报告，本轮已按真实documents产物纠正统计，未改旧原始summary。
- 费用：本轮Agent157请求/USD0.514436304保守估费；学习5请求（1次400失败+两组生成/审核）/USD0.004753800，合计162/USD0.519190104。已知观测费用USD0.271771704，其余预约保留。新增未知用量3笔、E汇总时1笔pending，旧3笔继续待核；供应商账单与V100历史未核。本轮无完整请求skip、无自动早停、无净降本证明；局部取消与完整恢复不共用分母。累计5918请求/USD10.425416136，历史不清零，人工与本地计算未货币量化。
- main兼容真实检查：两次60/180秒局部任务均取消，无报告PDF；第一次未到失败匹配，第二次精确加载前次自动发布库，在44工具环境送达5次Negative提示，无skip/早停/fallback，无人工worker恢复。未证明恢复成功或净降本。新增学习2请求、Agent32请求，合计34/USD0.217089456；累计5952/USD10.642505592保守估费，新增pending1/unknown0，旧6笔unknown及1笔pending保留。当前压缩为`native-pressure-checkpoint-v1`，不可沿用前轮关闭压缩配置；所有新快照与账本在`.local/paper-rsi-main-compat-20261021-v1/`。
- 配置与数据：`.local/paper-negative-rsi-20261021-v1/`包含授权、计划、A–G日志、两次manual-recovery、learning-store、请求/响应、审核、所有失败、aggregate、final-verification；逐run配置/源码快照在`.local/script-motif-experiments/<run_id>/`，原始事件与报告在对应web runs中。真实DeepSeek Flash/off；Agent输出32768，学习1536/max_rules1；正面mode shadow、Negative prompt（有干预）；未调用Embedding，压缩关闭。原恢复prompt SHA443bd3f6…、来源SHA4bd41694…，均沿用历史真实输入。私人材料/日志/凭证未提交。
- 最短入口：按README项目环境启动现有`run-script-motif-experiment.py`，同一`--learning-store`与私有sidecar，store放严格配置`negative-learning.json`：schema_version1、implementation_files为受信工具实现相对路径列表、model deepseek-flash、max_output_tokens1536、max_rules1、cap_usd null。完整有效JSON、变量化复现命令见接口及实验。必须保留既有无限额实验授权和账本；不是公共产品付费默认。
- 权限与预算：沿用已授权本地真实API实验，cap_usd:null / uncapped_user_authorized / reset_history:false；请求不限、输出有界、全部失败/重试/预约累计。本轮没有新自动execute，原生工具只写授权隔离报告产物；未改原件、投稿、生产或外部应用。已停止本轮所有真实任务，不安排后台继续付费。
- 未完成：自动学习仍只生成有依据的历史检查建议，未生成执行失败谓词/早停权限或通用因果机制；仅一个结构错误家族与同论文恢复变体。正面匹配器因无Embedding配置在最终局部任务中停用，不能据12算子评估正面执行收益。
- 接手下一步：兼容回归、局部实测及PR104提交已完成；检查其CI并由用户决定是否合并，不自动合并/部署。若继续降本，先分析提示后重写完整参数/报告的调用，设计一次有类型局部修订交接；不重跑完整Baseline，不扩大到其他场景或用库数量代替收益。
- 回退与风险：移除新store中的negative-learning.json可停用负面学习；已有自动负面指针仍会加载，若需完全停用同时从实验sidecar移除learningStore与negativeLibrary并停用worker环境。保留历史store与账本，不清空.local。旧库迁移必须实际重编译/认证，不能改hash绕过。仅本地macOS验收，未宣称跨平台生产支持。

## 2026-10-20：批量控制与PR100历史记录

- 更新时间与交接人：2026-10-20，Codex。
- 目标与本次范围：本轮优化批量选择、连续执行与完成交接，保持同库做真实BibTeX局部任务。用户最新明确以RSI闭环跑通作为本轮验收目标，报告质量不作为当前阻塞项；现有真实局部验证足够，本轮不再追加完整论文、全场景或Baseline测试。未部署。
- 分支 / 代码：实现提交30ee31d，基于a590080（已跑通自动Script RSI），验收说明50f1b5c。[PR100](https://github.com/jingyio/GeneLoop/pull/100)已按用户授权合并至main，merge commit为1055a4f；合并前Ubuntu/Windows的push及PR四项CI全部通过。未部署生产，原Desktop/SSS工作区未改。
- 已完成：script_execution_frontier.ts支持一次选择1–8片段/最多16节点，旧candidate_id兼容，严格候选/版本/回执校验，失败停止后续队列。完成不再伪装邀请；初始候选可提前提供，稳定目录置前、当前绑定/随机ID置后。script_motif_runtime.ts允许scratch未创建时绑定批准上传，减少重复目录并保留不适合自动绑定算子的显式缓存入口。无新工具/算子、无阈值放宽、无上游Harness修改。
- 已验证：最终npm test为Python1329通过/213跳过、Node1201通过/5跳过；相关定向36通过，smoke和motif:check通过。当前M发布库的owner/摘要/执行代码锁加载通过；这些检查属于免费诊断，真实模型证据另见实验。
- 实验结论：[批量控制实验](../experiments/paper-frontier-batch-20261020-v1.md)。9次真实局部运行E–M连续接管3–8个程序，原生工具/过期选择错误均0。G/H/I/J/K/L/M与旧C/D实际加载的programs和contracts逐项相同、题面/工具Schema相同，改代码后真实免费再认证，未只重算SHA。E/F使用稍后库，仅作开发观察，不作同库归因。
- 费用与反例：旧100条18请求/$0.025559700、26条6/$0.007911264；最终L为7/$0.018895596（-26.1%）、M为4/$0.007330920（-7.3%）。同配置H/I分别-6.7%/+16.9%，不能只选便宜一次。J仅2请求，但K便宜52.4%且质量失败，不计合格降本。接管数不是净少请求数；当前只支持局部费用观察，不证明完整论文或稳定同质量收益。
- 质量与成因：K把实际100条/99唯一键写成98唯一键，采用了后来覆盖不全的原生解析，还混淆行号/序号。补充冲突交接提示后L仍将无BOM写成有BOM，并有头部格式前后矛盾。J/M核心26条盘点可核对，但文字未全面合格。提示没有解决事实校验，不把新提示称为编译Negative Motif；未独立人工盲评。全部回答/不合格结果保留。
- 自动学习：M当前使用固定旧D对应算子，结束后在新的私有learning-store自动发布12算子/1契约，12.31秒、模型请求0，供下一任务使用。旧store/库未改。前轮A2→B、C→D精确自动交接证据见[RSI闭环](../experiments/paper-rsi-live-loop-20261020-v1.md)，本轮未破坏该接线。
- 配置与数据：.local/paper-frontier-batch-20261020-v1/含prior-runs、授权、E–M回答/breakdown、aggregate、各次免费再认证、source/effective-config摘要与learning-store。输入SHA前缀1142caced119（26条）、4005000c6d65（100条真实子集）；题面沿用d055aeefc57f…。真实DeepSeek Flash、off、输出8192、费用/请求不限、reset_history:false、压缩关闭、无embedding调用。最短复现见实验文档。
- 权限与累计：只读任务副本，不联网、不导出、不改私人原件、不写外部应用。新增57请求/$0.095528316代理估费；累计5698/$9.828635508。新增pending/unknown0，旧3笔、服务器历史和账单仍待核。编译模型调用0，开发/计算/人工未量化；所有真实任务已结束。
- 验收与后续：论文独立实验入口的RSI机制闭环已跑通，本轮收口，不新增模型实验。用户随后明确授权合并PR99和PR100；PR100已合并，PR99的组合检查见主线交接和该PR最终状态。没有额外完整论文、全场景或Baseline付费测试。计数/原文位置的机器验证、必要原文片段复用及完整论文交付质量作为后续非阻塞工作保留；不改写失败记录或宣称稳定净降本。代码合并不等于生产部署。
- 回退与风险：去掉script-config/learning-store走原生路径，或切回a590080并用其旧认证库。当前代码使用本轮实际再认证库；不要把旧代码锁改SHA当兼容。生产/公共认证库/认证数据/全局配置未动；真实沙箱仅本地macOS验收。其他历史检索/报告/Negative结果由前轮实验文档保留，不因本轮局限否定已观察的局部收益。
