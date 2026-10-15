# 普通文件管理跨流程学习实验

2026-10-15日常v2入口已完成持久经验库、批量重复Motif及原任务恢复。直接 `npm run web -- --scenario file-management --real-model --mode execute`；默认库`.local/rsi/daily-files-real-v2.json`。新版本不覆盖旧标量库。详情见[共享接口](../../docs/changes/persistent-rsi-integration.md)、[真实实验](../../docs/experiments/persistent-rsi-20261015.md)。SDK中断用 `node scripts/project.mjs python scripts/run-scenario.py --rsi-resume <原enrollment目录> --call-model`；Web在原任务卡确认恢复。

2026-10-15最新：已接通工具名无关的 MCP 学习契约与2–8节点参数DAG，并扩展到原授权文件写操作；真实新流从两节点前缀学习并独立认证五节点图，3个新图激活，严格文件流6/6普通任务合格。既有默认 Harness Web 的 file-management profile 已接同一库、任务后封存与自动学习队列；真实Web5/5合格，17次结构续接经实际结果验证。632 Python/211 Node通过、3可选跳过、18smoke；本轮59真实执行/470HTTP/代理USD0.237622092，包含所有失败与认证，最终留出不学习、暂不推送GitHub。其它MCP仍须登记真实权限/材料/验收适配器，任意控制流及稳定完整净收益未验证。 [完整实验](../../docs/experiments/generic-mcp-operation-rsi-20261015.md)、[共享接口与入口](../../docs/changes/generic-mcp-operation-rsi.md)。

```sh
npm run web -- --scenario file-management --budget-usd 5 --request-limit 96
# 真实模型显式开启，预览后确认：npm run web:real -- --scenario file-management
```

以下为此前版本的历史记录；其中“默认Web未接”等表述仅对应当时版本。

2026-10-15新增显式普通CLI连续Motif学习服务：`--rsi-config <private.json>`接任务结束封存、自动发现/独立认证和版本发布。只读文件报告真实两版学习/6交付通过；最新服务复验被503中断，免费621Python/199Node通过。默认SDK/Web/HTTP前端尚未挂接此调度；原任务、权限、预算和失败保留不变，暂不推送GitHub。[接口与入口](../../docs/changes/continuous-rsi-integration.md)、[实验/费用/限制](../../docs/experiments/continuous-motif-rsi-20261015.md)。

此前[工作流结构报告与新RSI验证](../../docs/experiments/file-management-report-delivery-20261014.md)完成102次新执行：task_result身份/快照/真实回执由当前MCP状态生成，模型填写摘要/缺口；原实际字节与权限验收不变。新诊断H/回退各6/6；两轮当前版本经验学习/独立认证/自动激活后均在下一任务零HTTP执行。日常H5/6、S/F/R各6/6，最终正常H/S/R各8/8、F7/8，8版本安全停止。R完整API USD1.325444比F1.390140低约4.65%，但F未全部合格，预定同质量净收益门槛仍未满足；普通回退备份仍需修复。603 Python/185 Node及smoke通过，系列估费USD7.836915368；失败/排除/轨迹/费用与旧最终留出保留，仅本地、默认SDK/Web未启用、暂不推送GitHub。[共享契约](../../docs/changes/file-management-report-delivery.md)。


最新[回退修复与持续学习验证](../../docs/experiments/file-management-fallback-rsi-20261014.md)完成142次真实运行：跨计划重复SHA写入在执行前拒绝，提交时检查原始字节组完整覆盖。第二版新诊断H/回退均6/6；新两轮经验自动认证激活并在后续实际执行。最终正常H7/8、S8/8、F8/8、R7/8，8版本安全停止；R完整API USD1.149742低于F1.207199约4.76%，但最终质量较低，不支持同质量净收益。未知目标失败的文件正确但缺实际报告，原失败/费用留存，最终不学习。599 Python/185 Node通过，系列估费USD7.197809948。本轮仅本地，暂不推送GitHub、默认SDK/Web未启用。[共享接口](../../docs/changes/file-management-fallback-guard.md)。


## 有界自动RSI入口（本地，2026年10月14日）

新增auto_rsi.py：先准备，免费check-auto-rsi-sdk.py，再显式--call-model运行两轮普通探索/独立认证/自动升级，最终新H/S/F/R留出不学习。统一经验库与事实检索不使用profile_id预选模板；源/权限/预算不符交普通Harness。

本批两轮升级真实完成，66运行/633HTTP/USD0.477517296；正常H/S/F各7/7、R6/7，8V停止，完整成本仍无优势。未知目标改写的普通回退失败保留。新代码未推送、默认SDK/Web不启用。[记录](../../docs/experiments/file-management-auto-rsi-20261014.md)、[契约与命令](../../docs/changes/file-management-auto-rsi.md)。

## 最新 脚本变化与第二版验证

[65次完整记录](../../docs/experiments/file-management-script-adaptation-20261014.md)：7旧脚本验证、10新普通探索（8学习/2排除）、8独立认证、40新五组留出。H/S/L2正常各6/6、M5/6、L1 4/6，10版本中断未交付。L2执行0API，含首版/新验证修复学习认证USD0.374614224；预写脚本API仍最低。790HTTP/USD0.715712544，全系列USD5.416158404，失败费用/轨迹/旧版本保留，不推送。[接口](../../docs/changes/file-management-script-adaptation.md)。

```sh
node scripts/project.mjs python scenarios/file-management/script_adaptation_study.py --experiment .local/file-management/fm-script-adaptation-20261014-8872b28c --summary
node scripts/project.mjs python scripts/audit-script-adaptation.py --experiment .local/file-management/fm-script-adaptation-20261014-8872b28c
node scripts/project.mjs python scripts/check-script-adaptation-stale-sdk.py --experiment .local/file-management/fm-script-adaptation-20261014-8872b28c
```

免费SDK新副本版本拒绝检查不调用云模型；新实验study默认prepare，显式--call-model才付费，候选先冻结/独立认证后才冻结留出。新克隆没有这些私有材料/证书；仅两复制流程受限DSL，默认SDK/Web不加载。

## 最新 学习脚本复用首批

[完整记录](../../docs/experiments/file-management-script-reuse-20261014.md)：5新普通探索（4学习/1排除）、2完整复制模板、8认证与24新H/S/M/L留出；正常/边界四组各4/4，8版本停止保留。L与S执行均0HTTP；L含建库/认证USD0.100006092，本批完整API无对S优势。37执行/274HTTP/USD0.203031636；全部费用/轨迹/失败/接口保留，不推送。只FM05合并去重/FM17从实际备份恢复、显式契约匹配，不是任意代码/40项能力/前端自动脚本库。

```sh
node scripts/project.mjs python scenarios/file-management/script_reuse_study.py
# 新ID免费检查 -> --role explore --call-model -> --learn -> SDK免费检查
# 候选冻结后 --role certify --call-model -> --certify -> --freeze-holdout
# 新留出 --role holdout --call-model，最后独立audit；完整命令与失败补探索见记录。
node scripts/project.mjs python scenarios/file-management/script_reuse_study.py --experiment .local/file-management/fm-script-reuse-20261014-ef863a4d --summary
node scripts/project.mjs python scripts/audit-script-reuse.py --experiment .local/file-management/fm-script-reuse-20261014-ef863a4d
```

原冻结实验不重跑或改候选；新源码/题面/权限需要新实验和认证。默认调用只准备/预览，--call-model显式启用授权副本操作；旧服务/旧库不动。

## 最新 第五阶段新留出H/S/M完成

[54次结果](../../docs/experiments/file-management-workflow-holdout-20261014.md)：六流程×N/E/V×H/S/M；正常/边界H11/12、S12/12、M12/12，18版本停止不计交付成功，H全局编号失败保留。全部HTTP292/116/193、代理USD0.194854178/0.086595528/0.144017954；M加USD0.235778764准备为0.379796718，本批脚本最低。11共同合格条件M/H执行费−16.53%，M/S+76.71%，未证明学习来源的增量优势。

```sh
node scripts/project.mjs python scenarios/file-management/workflow_holdout.py
node scripts/project.mjs python scenarios/file-management/workflow_holdout.py --experiment .local/file-management/<NEW_ID> --free
node scripts/project.mjs python scripts/check-file-workflow-holdout-sdk.py --experiment .local/file-management/<NEW_ID>
node scripts/project.mjs python scenarios/file-management/workflow_holdout.py --experiment .local/file-management/<NEW_ID> --call-model
node scripts/project.mjs python scripts/audit-file-workflow-holdout.py --experiment .local/file-management/<ID>
```

默认只冻结/预览；显式执行包括固定规则S的零Model效果。每运行5USD/96请求步/4000输出/2修复，54理论270USD，原系列1000USD；同job最多1冷启，不重置原权限预算。H原循环；S在FM01/13/21同Model选择、批量读，FM05/17/38确定规则可0Model；M使用旧认证读取/计划图，FM17普通回退。恢复及版本负例使用[冻结TS实验边界](../../docs/changes/file-management-workflow-holdout.md)，不默认启用新能力。

workflow-holdout-current指向427b924b，protocol-lock/源/材料/库/三组顺序/每轮文件与Model/API/费用/故障/验收/冷段及独立审计私有保留；已有outcome不能覆盖。原54材料、旧留出、七实现、29库和三PDF不变，新54不学习/修库。18+18MCP、9普通脚本、4SDK模拟冷启、565Python/167Node、18smoke和54全量审计通过，0额外免费云费用。

本批601HTTP/USD0.425467660；全系列583尝试/5606HTTP/USD4.497414224，98未通过交付保留，原预算余额995.502585776，实付未知。用户本轮不折人工金额，未做语义盲评/办公前瞻；G5初筛完成不等于通用上线或总经济收益。默认SDK/Web关闭，暂不提交/推送。

## 此前 认证计划与持久化任务在线组合已验证

[结果](../../docs/experiments/file-management-workflow-online-20261014.md)：9控制场景+1最终源码新副本复验，10项符合冻结预期、7交付通过、3按原请求/美元预算或撤权停止且字节不变；71HTTP/代理USD0.040261063。原task/grant/limits、服务外层+组件、旧library-lock与在线模块SHA一同核验，工具/Schema/题面失败持久化停用；受控缺报告1次普通修复后复验通过，真实MCP退出75后由模型原token回滚。自动restore未认证，旧三类库和证据不改；本次观察2/4源件，认证见证仍2/3。

```sh
node scripts/project.mjs python scenarios/file-management/workflow_online.py
node scripts/project.mjs python scenarios/file-management/workflow_online.py --experiment .local/file-management/<NEW_ID> --case normal-count4 --free-sdk
node scripts/project.mjs python scenarios/file-management/workflow_online.py --experiment .local/file-management/<NEW_ID> --case normal-count2 --call-model
node scripts/project.mjs python scripts/audit-file-workflow-online.py --experiments .local/file-management/<ID>
```

第一条只冻结8个新开发条件；免费SDK选择normal-count2/4、stale-runtime、request-limit或revoke-before-execute，使用模拟Provider，0云费用；真实--call-model仍原系列1000USD、每题最多5USD/96请求与步骤/4000输出/2修复、最多1已有边界冷重启，request-limit另冻max_requests=3。已有结果拒绝覆盖。0.01USD条件另冻65ac206a，只发1个真实请求后因下一请求预留不足拒绝，job仍running/未完成，没有增加预算。

底层公共CLI需已有 --file-job、--plan-policy/--plan-task 和 --file-plan-binding，原限额必须完全相同；未开始且显式绑定才启用，不改变默认SDK/Web。[共享接口和回退](../../docs/changes/file-management-workflow-online.md)。最终在线源码改变使旧绑定失效；主9ecabaa2与美元65ac206a原源码/失败/费用保留，bcb96582新副本通过最终代码复验，workflow-online-current指向bcb96582。6免费实际SDK/MCP、565Python/164Node和18smoke通过，测试/审计初版拒绝日志保留。

系列529尝试/5005HTTP/代理USD4.071946564、79未通过交付保留；实际账单、人类语义质量与维护成本未知。原54模板/oracle/pristine、3PDF、旧七实现和29旧库文件不改；留出先不动、G5未启动、暂不推送GitHub，不代表六流程完整成本优势或可上线。

## 此前 G4按版本学习与独立认证完成

[本轮结果](../../docs/experiments/file-management-workflow-learning-20261014.md)：14工具读取边/完整集合图、15工具预授权计划图共3类产物，独立认证和权威Node校验通过。新3训练+7独立普通认证全部机器合格，135HTTP/USD0.071586688；空MCP说明的离线拒绝修订后只引用原成功训练，不重复收费。8类实际MCP/TS免费重放通过，原stdio中断辅助失败保留，0云费用。

候选在认证前锁定；library-lock分开绑定WorkflowScene、RecoveryScene外层和PlanScene实际组件及源码依赖。读取105份观察重放，失败/Runtime/免费/probe/holdout不训练。G4当时只观察rename/move和不超过3源件，自动restore未认证；该阶段durable_job CLI禁止plan_policy组合，后续显式组合见本页首节，默认SDK/Web不加载新库。[接口和版本边界](../../docs/changes/file-management-workflow-learning.md)。

```sh
node scripts/project.mjs python scenarios/file-management/workflow_learning.py
node scripts/project.mjs python scenarios/file-management/workflow_learning.py --experiment <NEW_EXPERIMENT>
node scripts/project.mjs python scenarios/file-management/workflow_learning.py --experiment <NEW_EXPERIMENT> --role explore --call-model
node scripts/project.mjs python scenarios/file-management/workflow_learning.py --experiment <NEW_EXPERIMENT> --learn
node scripts/project.mjs python scenarios/file-management/workflow_learning.py --experiment <NEW_EXPERIMENT> --role certify --call-model
node scripts/project.mjs python scenarios/file-management/workflow_learning.py --experiment <NEW_EXPERIMENT> --certify
node scripts/project.mjs python scenarios/file-management/workflow_learning.py --experiment <EXPERIMENT> --audit
node scripts/project.mjs python scripts/replay-file-workflow-motif.py --experiment <EXPERIMENT>
```

当前workflow-learning-current.json指向fm-workflow-learning-20261014-d93e4c44；compiled/candidate-lock、libraries/workflow14与recovery15、library-lock、费用/独立审计、free-replays和analysis-source私有保留。单题原5USD/96请求步骤/4000输出/2修复，原系列1000USD；已有结果不覆写、旧证书不回写。原54材料/留出、七实现、29旧库文件与三PDF不变。留出先不动、暂不推送；后续在线组合已验证，G5新H/S/M仍未运行。

## 最新 普通真实探索和观测图汇集完成

[G3结果](../../docs/experiments/file-management-workflow-exploration-20261014.md)：首轮10/12，两个恢复读取违规保留失败；补读取前守卫后新材料2/2。两版共14尝试、206HTTP/USD0.123931013，59工具错误保留。统一14图/343节点，12份合格轨迹按14/15工具与实际执行版本分组，后续G4状态见上文；不代表业务人审合格。

恢复read_task返回实际计划/原授权/日志状态；读取范围为空时只用目录和哈希，恢复不会扩大原权限。SDK冷启动使用新传输Session和同持久化任务、同预算/修复限额；真实模型观察到MCP重连和原授权回滚，整Harness冷启动由本地模拟Provider另验。[接口修订](../../docs/changes/file-management-workflow-runtime.md)。

```sh
# 创建新探索材料和源码冻结；无模型调用。
node scripts/project.mjs python scenarios/file-management/workflow_study.py
# 修复版仅重建FM38的新文本，不覆写原失败。
node scripts/project.mjs python scenarios/file-management/workflow_study.py --workflows FM38
# 免费实际MCP预检；显式--call-model才付费。
node scripts/project.mjs python scenarios/file-management/workflow_study.py --experiment <NEW_EXPERIMENT>
node scripts/project.mjs python scenarios/file-management/workflow_study.py --experiment <NEW_EXPERIMENT> --call-model
# 只读原任务及归档源码，写派生审计和观测图；不认证或启用Motif。
node scripts/project.mjs python scripts/audit-workflow-exploration.py --experiment <EXPERIMENT>
node scripts/project.mjs python scripts/audit-workflow-exploration.py --pool <EXPERIMENT_1> <EXPERIMENT_2>
```

本机workflow-explore-current.json指向fm-workflow-explore-20261014-bbefcf67，workflow-observations-current.json指向workflow-observations-20261014-2f267505；原workflow-current仍是54份免费材料。每题5USD/96请求与步骤/4000输出/2修复，最多一次固定边界冷启动，原系列1000USD；已有outcome拒绝覆盖。原54pristine、认证/留出、三PDF及旧七实现不变；G4需新库和独立认证，G5再做新留出H/S/M。565Python/146Node及33MCP/18smoke通过，3Docker跳过；仍本地未推送。

## 先前首批六流程免费准备

[本轮记录](../../docs/experiments/file-management-workflow-free-20261013.md)完成54模板、新工作区和固定验收；33项实际MCP探针通过，另有真实Harness/本地Provider的9次模拟HTTP、一次普通修复、两轮验收。六个外部变化条件仍是停止结果。留出/所有pristine未改，真实API和模型费用新增0，未推送。

恢复入口现为显式recovery_tools.py/15工具，只组合全局重命名与自身计划回滚；任务/权限/执行版本/预算/请求/步骤/修复计数持久化，不能清零重启。新状态逻辑在TS，Python仅固定MCP/价格桥接/离线验收。新普通流程workflow_tools.py/14工具；旧入口和库SHA保留。[逐项接口](../../docs/changes/file-management-workflow-runtime.md)、[Workflow Schema](../../docs/schemas/file-workflow-contract.schema.json)。

```sh
# 均为免费；新prepare需要已有有效模板或传--assets，不覆写旧实验。
node scripts/project.mjs python scenarios/file-management/workflow_prepare.py
node scripts/project.mjs python scripts/check-file-workflows.py --experiment <PRIVATE_EXPERIMENT>
node scripts/project.mjs python scripts/check-file-workflow-sdk.py --experiment <PRIVATE_EXPERIMENT>
```

私有workflow-current.json指向fm-workflow-free-20261013-de2f6604。免费脚本与模拟轨迹不学Motif。恢复CLI必须提供已有--file-job和原5USD/96步/4000输出值，显式durable_job，普通baseline；当前不接动态Web、不支持未认证库组合。资料变化或整目录freeze哈希改变时prepare新版本；历史按frozen-source重现。

## 先前40项覆盖设计（历史）

当前新增[40项业务流程覆盖清单](workflow-discovery.md)与[首批六流程实验方案](workflow-evaluation-plan.md)：下载整理、目录合并、多版本比较、字节备份与恢复演练、资料包交付、中断恢复。清单18项可组合、20项需工具、2项需运行整合；六项只是设计完成，未生成新材料或运行新探索/认证/留出。

[覆盖JSON](workflow-catalog.json)和[方案JSON](workflow-evaluation-plan.json)均为规划数据，不是可执行场景或新的task kind。下一步先准备前五项新题面、固定验收和免费实际MCP探针，FM38须先组合任务权限/版本/持久化预算/修复次数。最新三类任务24次复验见[任务质量记录](../../docs/experiments/file-management-task-quality-20261013.md)；它不代表十二类或本表40项全面合格。本轮无运行接口改动，0真实模型请求/估费USD0，用户仍暂停GitHub推送。

## 先前报告契约与完整基准（历史）

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

## 当前任务质量修复入口

新任务用task_tools.py、显式sss-file-task-v1及sss-file-report-v3/task_result，配置acceptance_guard最多2轮。重命名rename_targets统一编号，建议显式allow_optional_original_reads=true；转换指定conversions并区分原件/产物核验；分类只读前缀内docx/txt/md，含0字节/空白，完整collect_reads后判断，无变化直接报告。

最终新12条件×H/L2为24/24；首轮24中4失败及全部费用保留。两版513HTTP/USD0.338547576；仅生成/模板材料的机械验收。读取图和旧L2不改，确定性守卫不是learned Motif收益；效果验收单独记版本。[完整结果](../../docs/experiments/file-management-task-quality-20261013.md)、[前端字段/Schema](../../docs/changes/file-management-task-contract.md)。

准备新实验：node scripts/project.mjs python scenarios/file-management/task_quality_study.py（本机需既有私有模板，不调用模型）；显式--call-model才执行。此前report_study.py和历史协议保留，精确重现使用frozen-source，不改旧结果。
