# 文件管理当前交接（2026-10-19，Codex）

- 本次范围：从本地长期积累分支移植文件管理到最新 GeneLoop main，增加原生 `/file 文件管理`，其他三个场景不改。集成分支 `codex/geneloop-file-rsi`，原分支和私有运行资料保留。
- 已完成：File 专用 SDK 桥接、原生事件/交付/高风险确认、账号独立长期库、自动学习认证与失效回退、原任务中断恢复；执行/RSI自动开启，无额外开关。当前公共种子 `motif-libraries/file-v3` 共3项策略，旧版本保留。
- 已验证：真实前端复制/读取/重命名、下载、原任务恢复、冷重启、当前新库自动匹配复用；最后任务8/8全文覆盖、3次模型请求跳过。免费最终覆盖1337Python/1022Node通过，3/5跳过，smoke与Motif check通过；其他场景锁与原本地文件均未改变。
- 失败和边界：高风险确认机制通过，但覆盖任务额外创建备份，独立严格质量未通过；未解析目标仍复核。事件投影与账号目录旧验收问题修复，原失败/费用不删除。未验证实际服务器部署、任意目标或稳定净收益。
- 权限/费用：原1000美元预算与学习25美元内的5美元本轮封套；448真实HTTP，代理估费USD0.30137615，实付未核对。原旧未知预留保留，原累计账本追加本轮费用，不清零。
- 入口/契约：`npm run web:real` 后选择 `/file`，参见 [使用说明](../management-local.md)、[接口](../interfaces.md)、[本轮实验](../experiments/geneloop-file-main-integration-20261019.md)。凭证只读私有环境，原日志/资料/恢复和账号库均在 `.local`。
- 发布：测试后复查main并创建PR，由用户审阅合并；不自动合并或部署。原临时测试服务停止，原本地服务未动。回退只撤销本PR的文件专用扩展，不清理私有库或用户工作区。
- 接手：先按PR的CI与差异审查确认集成；实际部署后再核验真实登录、账号持久挂载与恢复。下文为原main文件场景历史，结论和数字不追改。

---

# file-management 当前交接

## 2026-10-14：Files Web 产品接入（待审）

- 分支 `codex/harless-research-branches-20261014` 的 PR #14 增加 `Files` 前后端场景。菜单只发送服务器 ID `files` 与 `allow_output` 选项；Registry 绑定 `web-scenario.json` 的 13 MCP 工具和 `web-prompt.md`。用户/Session/Task 工作目录、上传收据、预算与既有 RSI Runtime 继续使用公共路径。
- `PlanScene` 保留实验原有限制，同时新增 `FM_WEB_WORKSPACE` 服务器绑定的 Web 任务副本范围；只读任务以空写授权启动，写任务须有批准上传文件。任务配置摘要隔开预览前后状态，避免持久化计划串扰。Web 只允许受限复制、移动、隔离及同授权恢复，最多 6 步，不接通任意主机文件或实验库。
- V100 四项新单测已验证只读拒绝、跨工作区拒绝、预览后来源变化隔离、授权复制/恢复、4 MiB Office XML 上限与 Excel 元数据边界；含 Registry 共 10 项通过。完整五场景免费 Harness 检查通过 30 组合/25 冻结草稿、5 场景实际 MCP/上传、空文件可写提交拒绝与双用户隔离。两名 bwrap 成员共 10 个五场景草稿及隔离通过。真实 DeepSeek Flash 只读任务 4 请求/4 MCP/0 工具错误/0 Verified Skip，预算代理估费 USD 0.001964256，账单未核对。人工办公材料质量、浏览器交互与认证库发布未验收。
- 入口：`npm run web:scenes:check`；定向：`$SSS_PYTHON -m pytest -q tests/test_file_web_scene.py tests/test_harless_scenarios.py`。公共契约见 `docs/interfaces.md`、`docs/harless-controls.md`。私有输入、凭证、原始日志和历史库留 `.local/`，未进 Git。回退 Files Registry 项及 Web scope 适配，不改旧实验记录。

## 最新：重命名/转换/空文本契约修复及新留出完成（2026-10-13）

- 当前feature/rsi-research-agent；本轮新增TaskScene/task_contract固定工具和验收、新实验控制/独立审计、11项契约回归、前端结构Schema。具体共享变化docs/changes/file-management-task-contract.md；旧File/Collection/ReportScene、原22基准失败和库证书不改。
- 最终fm-task-quality-v2-20261013-f3079826：12新条件×H/L2，24/24机器验收/文件后置通过；225HTTP/USD0.153151224，4工具拒绝计费，0验收失败/后端修复。编号在预览前验证，转换分必读原件/真实产物，空白实际读取且保持原位，全空目录不写。
- 首轮fm-task-quality-20261013-580d0285：20/24主验收、文件22/24，288HTTP/USD0.185396352；两个重命名读取口径失败、两个L2分类路径/集合错误未完成，49拒绝/7失败阶段/3次修复保留。修订只展示适用字段与完整候选路径，重命名显式允许可选读取，再换新路径/文本冻结，不追改成绩。
- 两版48任务/513HTTP/USD0.338547576全部计费；独立审计原来源/源码/事件/回执/每轮副本/HTTP/token/费用，原三PDF SHA不变。系列495attempts/4593HTTP/USD3.836167800，74任务失败保留，预算估费余额996.163832200USD；实际账单和人工盲评未知。
- 最终H/L2均12/12，请求126/99、估费0.077127624/0.076023600，总体仅约−1.43%；转换/分类较低、重命名较高，L2额外24获准但非必需读取。34首集合核验批次/0后继、140自动工具；不证明再入增量、普遍降本或语义泛化。
- 读取图四方法、实际schema和四个依赖源码不变，原L2 SHA/digest锁不改；新操作/验收另记task_execution_version。新留出未训练库，效果/语义仍普通Harness。默认普通Web不全局启用私有库。
- 最终561Python/139Node通过、3Docker跳过，18smoke、14工具MCP兼容预检通过；实际免费Harness/MCP一次修复、两轮权限不足、两请求预算停止均通过，0API。原审计计数口径错误及修正日志保存。
- 入口task_tools.py；前端按docs/handoffs/frontend.md新增显式task_contract和MCP路径，旧入口继续旧口径。完整质量/费用docs/experiments/file-management-task-quality-20261013.md，Schema docs/schemas/file-task-contract.schema.json。
- 私有.local/file-management两ID留protocol/frozen-source/library-lock/mcp与源兼容/overlap/tasks/attempts/summary/independent-audit；.local/task-acceptance全部逐轮证据；.local/task-contract-development-20261013改前/调度/测试/审计与失败日志；testpdf pristine/retained-final副本。不提交原日志/PDF/库/密钥。
- 接手：1按显式新契约接前端并实测动态任务，2真实材料/人工盲评和维护总成本，3继续持久化权限/版本/恢复组合认证及独立插件分发。分支同步以最终提交状态为准，旧交接的commit/未推送表述属历史。

## 最新：验收失败后的普通Harness修复已验证并推送（2026-10-13）

- 用户已恢复推送授权：要求原权限/预算内补最多2轮修复，真实验证后北京时间20:00前推项目分支。源码提交47d9218已于北京时间19:46推送feature/rsi-research-agent，远端SHA已核对；main未改。当前交接补记另随分支提交同步。
- 同Session TypeScript停止钩子+固定Python程序验收；每轮不可覆盖证据，原预算/96步/MCP状态不变。失败后全部Motif禁用，普通DeepSeek修复并复验；不能用重置或放宽任务通过。
- 真实两版本共8任务：6成功/2预期权限不足失败，108HTTP/USD0.098112864；15验收含9失败阶段、7修复通知及15工具拒绝全部留存。两次重命名闭环、新L2索引失败后普通模型补齐真实通过。独立审计证明修复后无自动工具、原权限不增、预算不重置；原22基准失败仍保留。
- 最终550Python/139Node通过、3可选Docker跳过；实际免费三类恢复检查、18smoke/13Web HTTP通过。文件系列447任务/4080HTTP/峰值估费USD3.497620224，实付未知。
- 前端入口docs/handoffs/frontend.md，接口与逐项改动docs/changes/acceptance-repair.md，完整结果docs/experiments/acceptance-repair-20261013.md；Web暴露修复次数，仅最终验收通过才completed。文件管理仍显式副本场景，新库默认Web不全启；2项依赖high/多用户/跨启动/科学质量限制保持。
- 密钥、私有库/PDF、原轨迹及所有费用/失败保留.local/testpdf且不推送；当前公开代码内容审查通过。以下暂停推送与旧实验记录均为历史，被本次用户授权更新。

## 最新：报告修复与第六阶段完整基准已完成（2026-10-13）

- 用户本次要求已执行：报告契约修复→新质量留出→144次完整基准，接口/费用/失败完整保留。原六阶段实验机制链与基准已运行；通用RSI、真实办公/科学质量和完全合格的产品仍未完成。
- 分支feature/rsi-research-agent、HEAD2368235，大量历史未提交工作共存；未commit/push/PR，无外部部署。普通Harness主基线、脚本辅助解释，继续RSI研究；预算1000USD、仅testpdf副本、原三PDF保留，沿用DeepSeek/off、不压缩、无embedding。
- 当前report-current.json指向fm-report-quality-20261013-d3053cd5。v1 e1f92d4d三十质量14合格/16失败，347HTTP/USD0.333062184，阶段范围混合，安全停止后未跑基准；标记恢复/控制记录保存。v2 7c213732十四获取9合格/5失败，133HTTP/USD0.113065740，盘点只列第二批导致残余支持不足，L2编译拒绝，未跑质量/基准。两版失败及旧L1全部保留。
- 当前sss-file-report-v3：inspection完整检查成员（含首批）、literal_search真实命中及search_receipt、task_result当前效果结果。inspection_stages以prefix/实际notice扩展名守卫选择，错误在集合创建前拒绝；报告在成功交付前校验实际覆盖/query/版本/集合。三组共用普通程序，不算学得语义。
- 新执行版本需重新学习认证，未改旧摘要：3普通训练/2独立认证新L1，再6 L1新经验/3独立认证新L2；14全部合格，136HTTP/USD0.116559168，175实际读取重放。L1 digest c1beac460bb7a100f9a3e0bc5601f751c3b0c3169a4c9004c4002916c5dca1ad；L2 digest 7bd3ac95725b9e3f69f36c884fa56121e0d00b1e5555d7675a0658cd359d971a。六残余大小5/2/9/4/13/5、首个合格独立认证构库，其余认证重放保留；零新留出前锁两策略。
- 36新质量（三目录×盘点/检索×H/L1/L2×两重复）全部合格，含大小写/字面符号/空命中。H/L1/L2请求177/134/101，估费USD0.159377412/0.135963120/0.122644668；工具拒绝20/2/2全部纠正计费。L2/H−23.05%、L2/L1−9.80%，生成条件机械验收，非真实业务盲评。
- 质量门及审计通过后完成12流程×2材料条件×H/L2×三重复144基准。主冻结验收H60/72、L2 62/72；全体请求746/505、估费USD0.520919892/0.440298360，工具错误4/5。72配对共同合格60、仅L2合格2、共同失败10；共同合格610→401HTTP/估费−16.02%。输入未命中增加、命中及输出减少，不能单按调用数换费用。
- 22基准失败：9重命名（H5/M4）全局编号被误做成每扩展名编号；12转换产物正确但额外读产物、1H内容分类正确但跳过空文本，均不符严格完整读取验收。原状态不追改。事后先前文件后置诊断13项范围失败文件结果正确，H67/72、M68/72，仅解释口径，不替代主质量/成本结论。
- 完整基准L2核验260batch、第二段再入0；其收益主要首集合，不能把本表当跨全流程L2对L1增量或认证对手写脚本优势。再入增量只由36两阶段对照支持。所有效果/恢复/语义仍普通Harness，使用FileScene副本权限/日志，不冒称已组合独立PlanScene持久化认证。
- 回归540Python/132Node通过、3Docker跳过。实际MCP三新查询拒绝/正确交付检查0API；SDK H/L1/L2两集合11/8/5模拟HTTP，L2陈旧input11/0续接。9成员第二段5批，辅助旧3批常量失败已改按容量8核对，失败0API和原事件/源保留，在线规则不改。
- 独立审计194次通过原事件/source/input/prompt/schema/HTTP/tokens/费用/实际参数/策略锁/效果来源/最终副本；1985读取、33搜索收据、5普通见证和7续接见证重算。Runtime参数或新质量/基准不训练。统一11实验433图/13076节点、214普通/213库干预/6脚本，184合格普通图，4104Runtime节点排除；scalar观察器不认证任意图。6早期pilot不在图但计费用。
- 全费用：第三版194任务172合格/22失败，1799HTTP/USD1.495762620；本次含两负版238任务/2279HTTP/USD1.941890544，43失败保留。全系列439任务/3972HTTP/USD3.399507360、68失败，授权估费剩余USD996.600492640，实际账单/工时/人工盲评未知。修复/获取USD0.562687092条件性481合格题摊销，全部本次API研究成本条件性1659题，非产品回本承诺。
- 源码：新report_tools.py/report_study.py、10项契约测试；六helper check-report-contract/check-report-sdk/run-report-pipeline/audit-report-study/summarize-report-study/collect-file-management-graphs。TS内核、共享CLI、上游Harness、原FileScene/CollectionScene/common、依赖/预算未改。报告Enum/schema/源guard/执行版本单独记录，旧库不强行适配。
- 私有记录：protocol/frozen-source/ancestor-L1/L2/L1/L2/library-lock/tasks/attempts/summary/quality-gate/independent-audit/paired-analysis/secondary-file-postconditions；原事件/逐HTTP.local/runs、pristine/retained-final testpdf副本。analysis-source六helper+SHA、shared-interface-revisions.patch/json、documentation-before-final、原调度器与失败状态/SDK失败/停止控制/学习排除均留存，不提交密钥/原日志/用户文件。
- 复现入口report_study.py默认prepare，依次bootstrap/bootstrap_certify --call-model、--learn-l1、learn/certify --call-model、--learn-l2、quality/benchmark --call-model（质量门后）；--summary/--gate只读。run-report-pipeline.py顺序调度并保留日志，--from-stage只续未执行阶段，旧调度状态归档；现已全部完成，别重跑旧attempt。完成后场景README改变当前freeze hash，付费重现用归档源码或prepare新版本。
- 后续1：另冻结版本明确全局编号与转换产物/0字节读取口径，验证真正任务质量；2：真实业务材料/人工盲评及维护工时；3：研究恢复分支/跨库组合和更新总成本。旧三版本/失败/证据/费用不覆盖，默认SDK/Web新策略关闭，不以有限机制闭环宣称自主一般学习。
- 文档：[完整结果](../experiments/file-management-report-benchmark-20261013.md)、[接口/修订](../changes/file-management-report-contract.md)、[入口](../../scenarios/file-management/README.md)。以下旧交接均为历史，以本节为准。

## 最新：第五阶段两代库闭环（2026-10-13）

- 当前状态：原第五阶段受限L1→新经验→L2→新留出机制闭环已完成；整体语义质量等价、通用RSI与第六阶段完整冻结基准尚未完成。用户明确继续RSI计划，普通Harness为主要对照，脚本辅助解释收益，先前脚本结果不能作为取消研究的依据。沿用DeepSeek、系列1000美元、仅testpdf副本，全部接口/费用/失败保留。
- 工作区仍feature/rsi-research-agent、HEAD2368235，未commit/push/PR，大量历史未提交改动共存。本阶段shared改前快照.local/file-management/interface-before-rsi-cycle-20261013，不以整份Git diff称本轮增量。
- 最新实验fm-rsi-cycle-20261013-7f6a246a，rsi-cycle-current.json指向它。6新L1学习/3独立L1认证/36新H/L1/L2留出，共45次，30合格/15失败；六种三组顺序各两次、三组各位置4次，相同14工具/schema/题面/input/字节，无embedding/压缩。
- 库：不可变L1来自集合264b9fc2，digest=3c6dd3ebb791bc75af5e8e6fc44b1790fe77af90821fca8e802918b5e09075a9，原文件/证书未改；新L2独立sss-collection-reentry-v1，digest=054ae4be28cc812a8f0ae2b540241d88a3dcd7dd284dca9f5278b54af1f8b614。L1/L2各在私有子目录，holdout-library-lock.json零留出时锁两文件SHA，实际配置/装载全审计一致。
- 新经验：stage_a中followup.txt真实JSON数据读完并gather后，模型选择stage_b，L1第二集合普通执行。从其原seq/usage/call-result残余区域学习；旧Runtime只证明父完成，不当新参数发现。6学习5通过、3认证2通过，5新native见证大小5/2/4/13/5、103实际读取重放；5训练+首个合格独立认证构库，其余认证重放保留。两失败排除学习但收费/事件保留，无补跑刷绿。
- 学习边界：L2包含原parent和新next，工程限定两次上界/再次进入语法；真实经验支持残余参数和父完成→新模型选择关系。不是任意图发现、模型权重更新、通用库组合或语义认证，未用留出修库或按收益自动晋升/淘汰。
- 全体留出：H/L1/L2合格10/12、6/12、7/12，请求155/125/88，输出57890/46963/29027，估费USD0.140712072/0.129666096/0.110134416，耗时346.535/292.428/212.208秒。盘点各6/6；检索4/6、0/6、1/6。13检索失败均报告正负file_id任务集合错误，实际两集合读取/gather/第二批索引检查通过，不能声称整体质量等价降本。
- 合格配对：H/L1 6对76→65/估费−7.03%；H/L2 7对89→52/−21.70%；L1/L2 6次盘点65→45/−15.29%、输出24111→14794、时间151.350→107.270秒。六次仅三独立条件，须并报全体质量；排除L1首段退出样本5对52→38/−12.63%。
- 回退/错误：evaluate-1-inventory-r1-L1因invalid_or_changed_model_selection退出自动调度，普通模型合格完成，非工具错误。evaluate-2-inventory-r1-L2提交陈旧ID被拒，刷新恢复合格，1工具错误/9HTTP全部计费。13检索+2学习/认证失败原样留存；学习盘点多次声明/漏读Word，认证报告错误。未放宽工具/验收来通过。
- 运行证明：L2留出12实际模型再次选择边界，第二段120真实读取/52完整核验batch；全L2核验96、L1 39。Runtime总读取L1 149（含获取/认证）/L2 208。核验batch不是反事实少模型请求数。
- 验证：530Python/132Node通过、3Docker跳过，18题smoke及14工具MCP预检通过。真实SDK/MCP本机脚本Provider H/L1/L2两集合11/8/5模拟HTTP；L2失配input11/0自动batch，正常第二段3核验batch，0云请求，脚本不训练/不当付费收益。45运行/12重复三组独立源码/input/prompt/schema/当前字节/最终副本/HTTP/库锁及6使用原生证据重算通过，无Runtime参数训练/留出重叠。原三PDF哈希不变，无active.lock；未盲评，实付未知。
- 费用：第五阶段462HTTP/USD0.466849368；9获取/认证94HTTP/USD0.086336784（含两失败），36留出368HTTP/USD0.380512584。全文件系列201attempts/1693HTTP/USD1.457616816峰值估费，25验收失败留存，估费剩余USD998.542383184；本阶段每题5USD/96步/输出4000保护。合格盘点平均USD0.001679338节省、全部获取/认证成本条件性52题回本，未计工时/实付或检索质量损失，非整体回本承诺。
- 归档：protocol/tasks/attempts/L1/L2/holdout-library-lock/summary/paired-analysis/independent-audit/sdk-checks私有保存；原事件/逐HTTP.local/runs，pristine/retained-final在testpdf副本。frozen-source含付费/学习源码，analysis-source含四helper及SHA，documentation-before-final含更新前文档；模拟任务不混真实学习/成本。不提交密钥/私人文件。
- 统一图：8实验195图/5661工具节点，110普通/79库干预/6脚本、99合格普通图，1459Runtime节点排除学习。6早期pilot不在图但计费用。旧scalar observer不完整表达数组/授权/reentry，证明各在独立artifact，观察收集器不认证图/不凭状态赋执行权限/不反训旧评测。
- 共享变化：offline/reentry_compiler验证旧完成后原native残余；TS collection_reentry_policy复用createCollectionController，实际新模型select结果后再进第二段。dsh_entry_motif新增互斥gate；run-scenario配对--reentry-policy/task、SSS_REENTRY_MOTIF_POLICY/TASK、私有regular文件/工具/Node/schema/session/prompt/普通清空环境及摘要/reentry_epoch_batches_verified；旧collection审计追加library_epoch/role，旧核验计数含两段。experiment.run_one可选策略hash。未改common/FileScene/CollectionScene字节、旧L1、上游Harness/依赖/预算代理。
- 复现：rsi_cycle.py默认prepare，--role learn/certify --call-model获取，--learn-l2导出，--role evaluate --call-model留出；--summary离线汇总。check-rsi-cycle.py --arm H/L1/L2 [--stale]本机SDK；audit-rsi-cycle.py/summarize-rsi-pairs.py --experiment离线。已有attempt/learned不覆盖；README完成后更新使当前源码hash不同，付费重现须用frozen-source或prepare新版本。
- 回退/边界：删显式reentry选项回原Harness；失败/输入/工具/schema/版本变化或第三集合停止自动调度。每集合最多32、每批8；模型仍选文件/query/索引/报告。本轮复用已QA二进制模板，新文本/目录/notice/数量/空/损坏条件，无真实业务或科学质量评审。默认SDK/Web关闭新策略；旧计划授权/恢复限制沿用下文。
- 下一步按RSI方向：另冻结版本明确检索报告目标集合与模型语义交接，再用新留出和真实业务材料评质量，保留本轮库/失败/费用；之后第六阶段完整冻结基准，原24条件×两组×三重复144次未跑。继续研究跨经验库更新/恢复分支/组合图，不能以受限认证称通用自主学习。当前授权阶段五已完成，本轮未启动阶段六。
- 最新文档：[本阶段实验](../experiments/file-management-rsi-cycle-20261013.md)、[本阶段接口](../changes/file-management-rsi-cycle.md)、[入口](../../scenarios/file-management/README.md)。先前完整交接保留下方，历史“本轮/当前/下一步”均为先前时点，以本节为准；更新前全文亦已存documentation-before-final。

## 先前批量/计划阶段交接（历史）

- 更新时间与交接人：2026-10-13，Codex。
- 授权/目标：普通Harness跨流程探索、统一轨迹学习、独立认证和合格成本对照；本轮按用户要求补手写批量基线，再认证计划权限/版本/幂等/恢复。沿用DeepSeek，全系列1000美元，只用testpdf实验副本，全部失败/恢复/费用和共享接口差异保留。
- 工作区：feature/rsi-research-agent，HEAD2368235；大量历史未提交改动与本轮共存，未commit/push/PR。共享改前逐文件版本在.local/file-management/interface-before-batch-plan-20261013，不以整份Git diff冒称本轮增量。
- 读取最新结果：fm-batch-20261013-41304bfb，6条件×H普通/S手写/M认证库，共18次均验收合格。H/S/M实际请求55/37/37，估费0.062135496/0.050006484/0.051180840美元；S/H−19.52%、M/H−17.63%、M/S+2.35%。同14工具/题面/守卫/批次8，六种顺序各一次；S不加载学习库。普通批量足以解释主要收益，没有观察到认证来源的额外费用优势；学习适配/维护工时未量化。H一次报告长错误计费，重复旧条件不称新泛化。
- 新计划实现：独立PlanScene13工具，preview_actions→authorize_plan→execute_plan，仅冻结副本copy/move/quarantine、最多6动作。授权绑定原路径/目标前缀/操作/恢复许可、当前字节/计划/preview/输入/执行版本摘要；execute/restore都要求精确authorization_id。持久化plan-state/journals/backups和无覆盖字节发布；成功重复收据、部分失败禁重做、同token恢复、后来不同字节变动/未知状态拒绝。旧FileScene12工具和库不改。
- 新计划学习：fm-plan-20261013-b2a877a4，3普通训练copy1/move2/quarantine3、2独立认证新目录copy3/试运行move2后恢复，共5实际文件重放。认证1条受限三角色计划链，policy_digest=847b59b055b7390b5460a7df69d30c1f6b6be2d4cacee99f00b5f1650de5627f。Python编译/认证、TS实际preview后续接授权/执行；动作/报告由模型选，失败后交回模型restore，尚未认证自动恢复分支或任意控制流发现。
- 计划对照：4对评测M4/4、H3/4，全部HTTP31→24/峰值估费−5.55%；H移动后误读通用试运行提示主动恢复，最终目标失败，不能称质量等价。3对共同合格请求23→19/估费−3.55%，清理费用+5.08%。两组第一项后预登记故障都恢复初始字节，M停自动续接、模型用同授权恢复。4评测M共8Runtime工具/7已核验续接，失败的execute不记完整核验。
- 验证：修正版523Python/127Node通过、3Docker跳过，18题smoke及新13工具预检；真实SDK/MCP正常计划4模拟HTTP/2核验续接、旧input6模拟HTTP/0续接，实际字节效果一致，0真实API。读取18与计划13原事件/HTTP/schema/权限/backup/最终副本/轮换顺序独立审计通过，审计保留失败。原三PDF SHA不变，无active.lock。
- 本轮失败：两个免费批量prepare错误（common审计列表改变执行版本、schema序列化key）保留草稿目录；common恢复逐字节保持旧读取认证。计划旧fm-plan-20261013-596394ac首项copy后验收错误重新加载初始目录抛ValueError，9HTTP/USD0.004298748补记原账本，验收失败保持；新版本重新训练，scope只读冻结快照，run_one捕获验收异常保证失败/outcome/费用不消失。计划修正版训练1工具错误、评测3工具错误全计费；H误恢复为新增任务失败。
- 费用：本轮32任务/234请求/估费USD0.212343792（读取18/USD0.163322820、计划含旧失败14/USD0.049020972）。全文件系列156任务/1231请求/USD0.990767448，剩余授权估费USD999.009232552；实付账单未知，开发/维护/人审工时未折算。旧8任务失败不追改，新增2验收失败保留。
- 当前配置/数据：batch-current.json与plan-current.json在.local/file-management，分别指向41304bfb和b2a877a4。protocol/frozen-source/tasks/attempts/learned/summary/independent-audit/sdk-checks/analysis-source均私有；逐HTTP/原事件.local/runs，pristine/retained-final在testpdf/file-management-experiment。实际SDK模拟任务与真实学习分开保存；不提交密钥/原日志/私人文件。
- 统一图：7实验150图/3733工具节点，98普通/46Motif/6脚本，701Runtime节点全部排除学习，旧scalar observer不完整表达新数组/授权，证据另在learned和原事件。该归档不认证任何图，计划证书单列；6早期pilot不在图中但计费用。收集器现识别全部sss-及脚本来源、无parent/previous的新协议，不反训旧评测。
- 共享变化：collection_read_policy拆出同守卫执行器；新collection_batch_script、authorized_plan_policy TS及plan_compiler Python；dsh_entry_motif后选择gate新增脚本/计划；run-scenario新增--collection-script/task、--plan-policy/task、互斥/私有路径/Node验证/session/prompt/环境清空/独立指标；run_one可选策略hash与验收异常失败记账。无上游Harness/依赖/预算代理变化，默认SDK/Web不启用，Node22.18+。
- 复现：scripts/file-batch-study.py --parent <旧集合实验>准备，--experiment/--call-model运行；plan_study.py默认prepare，--role explore/certify/evaluate --call-model，--learn编译。check-file-collection.py --script/--stale与check-file-plan.py --stale免费SDK；audit-file-batch.py/audit-file-plan.py --experiment离线审计；--summary只读。已有attempt/learned不覆盖，README更新同样改变旧冻结源码；付费重现用归档源码或prepare新版本。
- 边界/回退：仅macOS、单服务串行、同文件系统hardlink、路径/内容哈希，未认证并发/任意掉电/同字节inode替换/元数据。可信私有state摘要不是数字签名。计划材料四文本，未验证Office/PDF转换/归档或真实业务语义；未人工盲评。关闭显式脚本/计划选项回原Harness，别删除.local或原PDF。
- 下一步：优先把普通受限批量程序作为读取产品优化；补清晰真实题面/真实文件及人工交付评审，量化维护工时。计划再补简单手写执行对照和权限冲突/变化的真实条件，之后再研究恢复分支/组合图，不因证书就默认启用或声称一般泛化。
- 历史：正式fm-20261013-01c48298学标量pin→read；60在线首轮全流程不省费、历史保留修后44→36/−11.68%。集合fm-collection-20261013-264b9fc2从6训练/4认证学foreach(pin/read)+gather，6对54→39/−15.58%，policy3c6dd3eb…075a9。库及旧失败不覆盖，各原报告保留。
- 文档：[本轮实验](../experiments/file-management-batch-plan-20261013.md)、[共享接口/GitHub依据](../changes/file-management-batch-plan.md)、[集合实验](../experiments/file-management-collection-20261013.md)、[旧在线](../experiments/file-management-online-20261013.md)。
