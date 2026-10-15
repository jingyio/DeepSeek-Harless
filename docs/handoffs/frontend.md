# 前端接入当前科研Agent分支

## 最新分支边界与发布状态（2026-10-15）

- 用户要求本任务全部开发改动及已验证内容只发布`feature/rsi-research-agent`，不合入main。RSI实现与Windows兼容修订已推送至`27b5da1`，本次补分支规则和GeneLoop原实现存档；下方“未提交／暂不推送”是历史记录。
- 当前公开库为`examples/motif-library/file-management-operation-v2-winfix/`：4份原始新策略、锁文件和认证摘要；默认不凭公开摘要激活，克隆机器须有兼容的原始准入证明或独立学习／认证。私有日常库第10版：4激活、4旧版本停用，历史证书及失败保留。
- Windows刷新句柄修订后的独立新材料实验：15真实执行／147HTTP／代理估费USD0.082976075，普通3/3与独立认证12/12机械验收，非人工办公质量认证；最终留出不学习。原始证据、费用、失败留私有目录。
- GeneLoop `/management`曾在main完成命令、原生分发和浏览器零模型检查，误合并PR #28需要回退。其完整补丁与来源锁已保存在[接入存档](../../integrations/geneloop-management/README.md)，可在明确的GeneLoop基线逐字节重放。当前分支没有新版GeneLoop前端依赖，尚未完成该入口的运行移植；不能只把旧13工具与17工具v2的名字改成相同就宣称兼容。
- 原日常SDK/Web持续RSI、重复/多文件Motif及原任务恢复实现保留；默认文件管理写权限尚未调整。[分支修正与验证](../changes/branch-correction-20261015.md)。

## 最新本地状态：2026-10-15持久化/批量/恢复

- 已完成用户指定三项，`feature/rsi-research-agent`，HEAD仍`fcdcc48`；无新提交/推送。Python编译/认证、TypeScript在线继续沿用。
- 日常入口 `npm run web -- --scenario file-management --real-model --mode execute` 不必传库配置；真实/模拟分别固定`daily-files-real-v2`/`daily-files-mock-v2`。原凭证由环境变量提供，不写入公共文件。
- 第5版4个v2图；真实6/6新任务机械交付、12/12认证材料交付，163HTTP/USD0.097170133、40次验证跳过。报告缺口与一次工具失败完整保留，未做人工盲评/完整净收益对照。系列代理估费USD8.348467365，账单未核实。
- 浏览器已多选双文件提交/看实际产物、服务重启/恢复原请求4→11、原摘要确认；SDK发布后中断也原请求6→15、一计划两效果。真实默认入口恢复原库和3完成任务，0新增模型调用；认证已封存材料采用原记录0重复费用。
- 新旧源码阶段和全部失败见`.local/persistent-rsi-development-20261015-5f4d87ee`，付费冻结协议/材料在`.local/file-management/fm-persistent-rsi-20261015-a648d606`及`fm-persistent-web-20261015-004257ff`。旧最终集/论文不学习不覆盖。
- 新接口：[详细变更](../changes/persistent-rsi-integration.md)，[实验](../experiments/persistent-rsi-20261015.md)。REST `resume` 仅原中断任务＋原确认摘要；预算与版本变化拒绝。v1旧失败/证书保留，v2独立认证重新学库。
- GitHub旧CI `38392885619`已被`01ce885`修复；最新已推送`fcdcc48`的`38548225640`成功。本次只检查旧失败，不重新推送。
- 最终检查：639 Python/216 Node通过（3可选跳过）、18免费smoke及SDK/Web/认证恢复通过；逐文件旧数据保留核验见开发档案。
- 当前边界：一个已登记文件MCP、17工具、2–8节点顺序图、非空唯一数组≤40；不支持并发图/任意循环/任意其它MCP。预算耗尽停止；未知费用或未核实轨迹拒绝训练。后续扩场景须单独适配，不能降低质量标准。

## 当前接手状态（2026-10-15，Codex）

- 目标/范围：用户要求先扩文件管理、再接默认前端；通用MCP算子契约、有界参数图学习、原生来源、独立认证/激活/回退与Web队列已实现，仅本地，暂不推送。
- 分支/版本：feature/rsi-research-agent，HEAD fcdcc48；本轮和先前脏工作均未提交，不能把本机新能力当GitHub已同步。旧发布库/许可证/证书原字节保留。
- 当前实现/接口：[通用MCP操作图实施记录](../changes/generic-mcp-operation-rsi.md)，Python离线发现/认证、TS在线执行；新schema为mcp-learning-contract和operation-graph。真实适配器为file_operations_v1，其它MCP需登记权限/材料/验收；不是任意流程全部学会。
- 验证：632Python、211Node通过，3可选跳过，18smoke；免费真实CLI/SDK/MCP与Web API及取消结算通过；真实严格文件流6/6普通交付、两代2→5节点图和3节点后缀独立激活；真实Web5/5，验证17次请求跳过。[全部结果/负面证据](../experiments/generic-mcp-operation-rsi-20261015.md)。
- 入口：`npm run web -- --scenario file-management --budget-usd 5 --request-limit 96`免费；`web:real`才真实，原/tasks预览确认不变。服务器可传--rsi-config/--files-dir，客户端只能选择已登记文件目标。当前私有配置`.local/file-management/fm-operation-rsi-20261015-a3adca6c/rsi.json`；库与来源指针`.local/rsi/operation-current.json`，旧只读指针不改。新克隆没有本机库，从空库普通运行学习。
- 数据/完整成本：本轮59真实执行/470HTTP/USD0.237622092，含第一轮worker缺审计失败、失败调用屏障修订及2个保守拒绝候选。全系列1084尝试/10888HTTP/USD8.251297232，原USD1000余991.748702768（代理估计，非账单）。净收益只记录，开发人工/语义质量未核实，最终留出禁止学习。
- 权限/预算：仅testpdf有标记的新副本；每原任务≤USD5/96步与HTTP/4000输出/2次验收修复，学习池≤USD25且计入系列。502/503同任务最多2次重试，每次记费，未知usage不训练。取消及在途结算保留原预留；本次23个当前版本预留全部结算。
- 失败/版本：旧bfd735a4长图因省略失败调用的采集缺陷事后明确停用；原证书/失败/费不改。a3adca6c严格来源审计通过。额外pin/read候选因隔离认证要求恰好一次完成而保守拒绝，未改标准重签。
- 保全/回退：`.local/general-rsi-development-20261015-244a9c2b`含before/after/diff/完整日志/final保全；267609个旧私有文件无删除覆盖，仅1日志追加原SHA前缀。移除--rsi-config回普通CLI；Web baseline关闭图执行，可observe停止自动学习。任务冻结原库版本，旧版本不重签。
- 未完成/接手下一步：其它真实MCP适配器及业务验收；重复图/多产物认证与新操作服务跨进程恢复；浏览器视觉/真实办公质量/长周期完整成本观察。现有默认UI已加文件目标表单，但本轮端到端验证为真实HTTP任务API，不冒充浏览器视觉验收或公网产品上线。

## 此前版本记录

下面状态是历史快照，若与上面的当前状态冲突，以当前状态为准；旧证据和失败保持。

2026-10-15新增显式普通CLI连续Motif学习服务：`--rsi-config <private.json>`接任务结束封存、自动发现/独立认证和版本发布。只读文件报告真实两版学习/6交付通过；最新服务复验被503中断，免费621Python/199Node通过。默认SDK/Web/HTTP前端尚未挂接此调度；原任务、权限、预算和失败保留不变，暂不推送GitHub。[接口与入口](../changes/continuous-rsi-integration.md)、[实验/费用/限制](../experiments/continuous-motif-rsi-20261015.md)。

此前[工作流结构报告与新RSI验证](../experiments/file-management-report-delivery-20261014.md)完成102次新执行：task_result身份/快照/真实回执由当前MCP状态生成，模型填写摘要/缺口；原实际字节与权限验收不变。新诊断H/回退各6/6；两轮当前版本经验学习/独立认证/自动激活后均在下一任务零HTTP执行。日常H5/6、S/F/R各6/6，最终正常H/S/R各8/8、F7/8，8版本安全停止。R完整API USD1.325444比F1.390140低约4.65%，但F未全部合格，预定同质量净收益门槛仍未满足；普通回退备份仍需修复。603 Python/185 Node及smoke通过，系列估费USD7.836915368；失败/排除/轨迹/费用与旧最终留出保留，仅本地、默认SDK/Web未启用、暂不推送GitHub。[共享契约](../changes/file-management-report-delivery.md)。


最新[回退修复与持续学习验证](../../docs/experiments/file-management-fallback-rsi-20261014.md)完成142次真实运行：跨计划重复SHA写入在执行前拒绝，提交时检查原始字节组完整覆盖。第二版新诊断H/回退均6/6；新两轮经验自动认证激活并在后续实际执行。最终正常H7/8、S8/8、F8/8、R7/8，8版本安全停止；R完整API USD1.149742低于F1.207199约4.76%，但最终质量较低，不支持同质量净收益。未知目标失败的文件正确但缺实际报告，原失败/费用留存，最终不学习。599 Python/185 Node通过，系列估费USD7.197809948。本轮仅本地，暂不推送GitHub、默认SDK/Web未启用。[共享接口](../../docs/changes/file-management-fallback-guard.md)。


## 最新 本地自动经验控制器 2026年10月14日

- 新TS dsh_experience在显式私有SSS_EXPERIENCE_BINDING下检索统一版本库，核验当前MCP事实/goal/rule/schema/权限/状态/源码；没有profile_id提示或正确脚本ID。新代码尚未提交/推送，默认SDK/Web及HTTP契约不变。
- [接口](../changes/file-management-auto-rsi.md)与experience-registry schema提供对象/版本摘要、active/candidate/disabled和源码依赖；入口不允许任意脚本执行。计划仍原durable job组合绑定。
- 两轮自动升级/新独立认证/普通回退已验证，最终正常H/S/F7/7、R6/7；完整费用RSI仍高，不适合宣传净收益或生产上线。[结果](../experiments/file-management-auto-rsi-20261014.md)。前端后续接入应明确版本兼容与原任务/权限/预算，不能将历史认证当当前授权。

库提交 `02bcc21` 已推送到 `feature/rsi-research-agent`，GitHub分支引用和全部18个分发文件的blob哈希已核对；其余本地开发改动仍未提交。

## 最新 Motif 库可下载 2026年10月14日

- 用户恢复了本次库分发推送授权，目标 `feature/rsi-research-agent`。公开 [file-management-v1/catalog.json](../../examples/motif-library/file-management-v1/catalog.json) 提供9个已学习库/策略、3个manifest及来源/认证摘要，格式 `sss-public-file-management-library-v1`。
- 本次没有发布尚未提交的G4运行服务/持久化任务接入。索引是静态库清单，不是自动选择/执行接口；`default_activation=false`。前端下载库后须校验来源兼容，再通过当前任务权限与预算入口接入，不可沿用历史指纹授权。
- 原SDK/Web默认与HTTP任务接口未改，固定脚本库另存；私人 `.local`、费用和失败完整保留。免费发布检查6项通过，云费用0。[分发说明](../../examples/motif-library/file-management-v1/README.md)。

新增[脚本变化/第二版验证](../experiments/file-management-script-adaptation-20261014.md)：4模板/8认证/40新五组留出，H/S/L2正常各6/6、M5/6、L1 4/6，10版本停止未交付；L2从头API USD0.374614224，预写脚本API仍最低。新v2只私有实验patch，现有HTTP任务kind、预算/确认与默认SDK/Web不变，不能暴露任意脚本/目录执行。[守卫与来源接口](../changes/file-management-script-adaptation.md)。代码仍本地未推送，前端产品集成与真实业务验收待另行实施。

最新[学习脚本复用](../experiments/file-management-script-reuse-20261014.md)首批两复制流程四组24新留出完成，四组正常/边界各4/4，8版本停止仍未交付；学习脚本执行0API，加建库/认证USD0.100006092，预写脚本API仍最低。新模板只有私有实验patch，未增加MCP工具、CLI公共参数或HTTP任务kind，不能直接暴露通用脚本编辑/任意目录执行；默认SDK/Web保持。新增[格式与来源/守卫接口](../changes/file-management-script-reuse.md)，已有任务HTTP接口不变，仍暂不推送。

六流程[第五阶段新H/S/M留出](../experiments/file-management-workflow-holdout-20261014.md)54次完成：正常/边界H11/12、S/M各12/12，18V停止仍未完成；本批普通脚本费用最低，M加准备费无完整成本优势。原job整Harness冷启/预算权限不重置和原token恢复已实测。新增固定测试插件仅私有patch，默认SDK/Web与已发布HTTP任务契约不变；前端不能因此开放任意目录、40项能力、多库/自动恢复。共享实验[接口](../changes/file-management-workflow-holdout.md)、原[显式计划绑定](../changes/file-management-workflow-online.md)；库/证据保持，新留出未学习，仍暂不推送。

当前协作要求（2026-10-13）：用户已暂停后续推送；dfe4fcc为此前已推送基线。后续开发与验收先留本地，用户明确恢复后再同步GitHub。下面的已发布安装命令与历史提交状态仍保留；动态文件任务前端尚待接入。

新增[40项覆盖规划](../../scenarios/file-management/workflow-discovery.md)及[六流程实验设计](../../scenarios/file-management/workflow-evaluation-plan.md)仅在本地，是候选清单，不是前端可直接启用的40项能力。三种TaskContract kind保持；新目录合并/备份/恢复等名称不可作为kind提交。六流程已完成54次H/S/M新留出；新增两复制流程24次H/S/M/L新留出。动态任务前端尚未接入这些实验策略。

## 最新文件任务契约（2026-10-13）

重命名/转换/空文本的新TaskScene最终24次新留出均通过机器验收。使用既有分支更新后的`scenarios/file-management/task_tools.py`作为MCP入口，保持原14工具、stdio配置及`FM_TASK_FILE`/`FM_OUTPUT`变量；场景继续显式`acceptance_guard={"kind":"file_management","max_repairs":2}`。旧服务和旧任务不会自动升级口径。

在原本私有任务JSON（含workspace、initial_snapshot、objective、rules、allowed_operations等）增加如下字段；这里只展示新增部分，不是可独立执行的完整任务。工作目录仍必须是授权testpdf实验副本并有标记，任务JSON与交付目录在.local。

```json
{
  "family": "rename",
  "report_contract": {"version": "sss-file-report-v3", "kind": "task_result"},
  "task_contract": {
    "version": "sss-file-task-v1", "kind": "rename",
    "source_prefix": "inbox/", "destination_prefix": "normalized/",
    "allow_optional_original_reads": true
  }
}
```

转换使用`kind/family=convert`与`conversions=[{source,destination,format}]`（format=text/csv/jpeg），按需求设置`allow_output_verification_reads`、`require_output_verification_reads`。分类用`kind/family=content_classify`、`source_prefix`与`routes=[{literal,destination_prefix}]`，按首个不区分大小写的字面命中选择，保留相对路径；仅docx/txt/md必读，空白实际读后原位，全部为空则无需操作计划。

前端显示`read_task.reading_contract`中的必读原件、可选读取和允许/必读产物，以及正确编号/完整候选路径。只有当前程序验收通过才显示完成；不要把`submit_report.status=delivered`单独当任务成功。最终task_result的file_ids须包含所有当前身份。结构预校验可用[JSON Schema](../schemas/file-task-contract.schema.json)，服务端继续执行跨字段/相对路径/版本/权限校验。

新TaskScene继承原认证读取图，私有L2需明确policy/scope才启用；新效果契约不代表整个Agent已经认证或Web可任意选择用户目录。[逐项接口变化](../changes/file-management-task-contract.md)、[两版质量/费用/失败](../experiments/file-management-task-quality-20261013.md)。

2026-10-13。代码分支：`feature/rsi-research-agent`，仓库 `jingyio/DeepSeek-Harless`。这是开发联调版本；首个源码包`47d9218`已于北京时间19:46推送，本轮任务契约修订继续同步到该分支，下面安装命令取得最新HEAD。

## 安装与免费联调

推荐Node22.18+、Python3.12；PDF能力另需Poppler的 `pdfinfo` / `pdftotext`。依赖按锁文件安装。私人PDF、凭证、轨迹、库及实验文件不随Git分发。

```sh
git fetch origin
git switch feature/rsi-research-agent
git pull --ff-only origin feature/rsi-research-agent
npm ci
npm run setup
npm run smoke
npm run web:tasks:check
npm run web
```

`npm run web`默认模拟模型，监听127.0.0.1:3080。使用本次启动的认证地址建立Cookie后，以同源方式访问 `/tasks` 和API。认证地址写在私有 `.local/web/runs/<RUN_ID>/access-url.txt`；不要硬编码或提交令牌。密钥通过私有 `.env` 的 `DEEPSEEK_API_KEY` 配置。显式 `npm run web:real` 开启真实连接，任务仍须预览并确认预算。

## 已有HTTP契约

主路由 `/api/harless/tasks`，兼容 `/api/sss/tasks`。请求保留原用户输入，服务端负责能力、文件、版本和预算约束。前端不要构造任意工具或插件路径。

| 操作 | 请求 |
| --- | --- |
| 列表 | `GET /api/harless/tasks`，返回tasks和aggregate |
| 详情 | `GET /api/harless/tasks?task_id=<ID>` |
| 预览 | POST `{ "action":"preview", "request": { "instruction":"用户任务", "request_id":"唯一请求ID", "mode":"baseline", "budget_usd":0.25 } }` |
| 执行 | POST `{ "action":"submit", "task_id":"预览ID", "confirmation_digest":"预览原值" }` |
| 取消 | POST `{ "action":"cancel", "task_id":"ID" }` |
| 附件 | POST `{ "action":"upload", "task_id":"未执行ID", "name":"文件名", "data":"规范base64" }`；256KiB上限，上传会更新预览摘要 |

调用使用 `credentials:'same-origin'`、JSON请求头。`request_id`相同且内容不变保持幂等；同ID内容变化返回409。预览摘要变化必须重新展示并使用新 `confirmation_digest`。服务目前单活跃任务；其他任务执行中返回 `task_busy`。

状态：`awaiting_confirmation` → `running` → `completed` / `failed` / `cancelled` / `budget_exhausted`。显示 `failure`、`fallback_reason`、`provider_mode`、`paid_calls_enabled`；真实实付未知时不要用估费冒充账单。详情中的 `answer` / `delivery` 是用户结果；`artifacts`只是记录名称，没有通用任意文件下载接口。

`mode`为baseline/shadow/execute，execute缺少可用认证库时仍回普通Harness。它不自动开启最新文件管理L2库；这两套显式入口不能互相混用。

## 新增有界验收修复

服务端文件管理场景可显式设置：

```json
"acceptance_guard": { "kind": "file_management", "max_repairs": 2 }
```

该配置通过公共SDK适配器及普通Web preset加载同一TypeScript停止钩子。FM_TASK_FILE、FM_OUTPUT由服务端原场景配置提供，客户端不能提交这些路径。固定Python验收器核对原任务、真实收据和文件结果。失败现场先保留，再在同Session交普通DeepSeek修复；Motif保持关闭，共用原预算、步数和MCP授权。最多2轮；取消、预算耗尽、任务版本改变、不可逆历史范围违规和次数耗尽不能继续。

启用此守卫的Web任务，仅最后一次程序验收通过才显示completed；验收失败或缺少验收记录显示failed。`stats.acceptance_repairs`、`stats.acceptance_checks`、`stats.acceptance_passed`可用于显示修复次数和最终结果。CLI还返回 `acceptance_trace_dir`，这是私有证据定位，不能直接作为前端下载路径。

```sh
# 免费真实Harness/MCP修复闭环、次数耗尽、预算耗尽
node scripts/project.mjs python scripts/check-acceptance-repair.py --case pass
node scripts/project.mjs python scripts/check-acceptance-repair.py --case exhaustion
node scripts/project.mjs python scripts/check-acceptance-repair.py --case budget
# 新任务契约走同一闭环
node scripts/project.mjs python scripts/check-acceptance-repair.py --task-contract --case pass
```

普通文件管理目前通过指定实验副本和CLI运行，不是一个可任意选择用户真实目录的成品HTTP服务。复制、移动、转换、隔离和恢复均须遵循现有工具权限；前端不能通过选择execute或修复按钮扩大授权。实现细节见[接口变更](../changes/acceptance-repair.md)、[场景入口](../../scenarios/file-management/README.md)。新克隆缺少本机私有库时先用普通Harness或公开Motif样例，不复制别人实验库或构造认证摘要。

## 文献入口与限制

`npm run web:literature -- --papers-dir <服务端PDF目录>`将文献任务绑定到上面的官方任务API；`--real-model`才使用真实连接。另有独立本机工作台 `node scenarios/literature-notes/agent.ts serve --port 8765`，其 `/api/jobs`、`/api/run`属于另一套场景协议，不能与 `/api/harless/tasks`混用。该工作台写请求还要求同源及页面会话许可。

新闭环的程序验收不认证科研理解，也不能抹掉此前22项基准失败。依赖审计仍有2项high告警（MCP TypeScript SDK、sharp）；本分支适合限定输入的内部联调，公网发布前须解决并回归。多用户隔离、跨启动恢复和真实文件管理产品入口仍待验收。

CI补记：首次Ubuntu/Windows失败来自一个实际调用Poppler的文献测试漏标外部依赖。已补依赖条件；Linux CI安装poppler-utils以执行全部PDF检查，Windows无Poppler时明确跳过相关PDF测试，不当作Windows PDF能力认证。本机保留完整检查。首次失败日志留私有开发归档，没有删除断言。
