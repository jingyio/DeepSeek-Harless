# PPT 用户轨迹后台学习接线

## 问题、范围与假设

实验 ID：`ppt-user-learning-20261019`。以 main `a1c0fa2` 为基点，在 `codex/ppt-user-learning-20261019` 开发，当前未提交/部署。目标是让普通使用产生的真实轨迹经过现有离线编译器、独立认证和后续验证后自动保留；用户不用填写问卷，后台不另开付费任务。

只接受当前支持的 `pin_source→convert_source`、`convert_source→read_converted_source` 两条边；不接管 Bash、科研选材、叙事或任意生成代码。假设为：已有守卫的结构可以在后续实际任务安全执行，并在机械交付不退化时降低包含重试的代理费用。没有后续实际调用、完整成本或合格交付，则不支持晋级。自动机械检查不能证明科学事实/审美或人工时间不退化。

## 实现与任务划分

- TypeScript manager 接现有 Web 任务结算、对照成品保存、下一任务准入及普通负反馈；Python worker 只做离线编译/认证/核验，环境不含模型密钥。
- 账号/scope私有存储：`<output>/learning/ppt-<SHA256(user + NUL + scope)>/`。来源原件、任务、账本、评审和成品不公开，不跨账户共享。
- 至少三项来源版本、问句和研究决定独立的 completed 原始 Baseline：2训练、1永久独立留出；来源、schema顺序、模型/推理、提示/技能版本须兼容。相同证据认证失败不重复编译；失败仍保留。
- 候选仅下一任务开始时进入 `probation`，不改变正在进行的会话任务。需两项后续独立 paired 任务、准确候选库SHA与真实旁路审计、不可变 PPTX/PDF/PNG 及完整重试账本、更低费用，才自动 `active`。无对照时不额外调用模型补验证。
- 普通踩/可选明确负评或撤回、费用增加、交付失败、代码/来源/证据失效则停用回原库。普通赞不算科学人评。自动 `mechanical_cost_promoted` 和有明确人评的 `quality_cost_promoted` 分开记录，人工分钟未提供时为 unknown/null。
- 当前是既有两条受限结构的用户内重认证、验证与持续监测；不宣称自动发现任意未知图、生成新工具或无限代际进化。

## 配置与复现

运行在用户服务器的隔离目录 `/mnt/sevenT/junjiex/DeepSeekHarness-ppt-learning-20261019`，源自 main `a1c0fa2` 加当前未提交改动；Python 3.12.15、Node 22.23.2、DSH 0.1.5-rc.3。环境复用旧项目私有工具链，不修改旧项目或原累计账本。有效源文件/测试摘要另存私有快照。上述诊断不使用模型；后续真实验收采用 DeepSeek Flash、`reasoning_effort=off`、压缩关闭，费用、请求次数、额外输出上限均为 null。逐次代理账本保留，实际支出与交付以下方最终记录为准。

公共入口仍是 `npm run web:real`；由服务器私有环境提供凭证和完整字节锁定技能。定向诊断可复现：

```sh
python -m pytest -q tests/test_web_ppt_learning.py tests/test_harless_paper_product_bundle.py
SSS_PYTHON="$(command -v python)" SSS_PURE_CODE_PYTHON="$(command -v python)" node --test tests/test_harless_ppt_learning.mjs
npm test
npm run smoke
npm run motif:check
```

完整公共回归需要可嵌入中英文字体，本次仅在隔离 `.local/fonts` 解包系统公开 `fonts-wqy-microhei 0.2.0-beta-3`，以 `HARLESS_REPORT_FONT` 指向其 TTC；没有改系统目录或放宽字体守卫。Root requirements 外的可选依赖缺失产生 skip，不能当成全部场景验收。

兼容发布 `ppt-master-v9` / `paper-web-v14` 通过 `reexport-ppt-learning-compat.py` 校验序列化旧库与当前 exporter 输出完全相等；旧库、证据、完整schema和认证主张保持。它不是新真实训练，也不证明新降本。

## 诊断结果与失败记录

新测试使用合成事件、真实文件/PDF与现有离线编译器，明确不是云效果验收：

- 新 Python 最初24项，收尾追加2项后26项通过；Node 生命周期 2 项通过。覆盖无review的完整自动3→2晋级、独立性、账户/scope隔离、失败重试全费、后台进程失败、重启继承、证据篡改、即时负反馈停用和认证失败幂等。
- 发布库 14 项通过；字体修复后交付检查13通过/1可选依赖跳过。
- 全量首次：4失败、892通过、199跳过。两项为历史证书对新代码应拒绝的测试预期未更新；改为同时核对新版本准入与旧版本明确拒绝，旧证书不修改。另两项因缺CJK可嵌入字体导致真实PDF检查拒绝，安装字体后原检查通过。
- `npm run smoke`、`npm run motif:check` 通过，均无付费模型；后者使用诊断Provider/embedding，不能将其示例旁路数当作本轮用户收益。
- 原接线版本 `npm test`：Python 898通过/199跳过，Node 849通过/3跳过；追加下述工具结果兼容修复后为898/855通过。收尾分组与撤回保护修复后的最终重跑：Python **900通过/199跳过**（155.56秒），Node **855通过/3跳过**（23.45秒），0失败。可选依赖未安装的199项Python检查不算通过；Node三个既有可选检查亦未执行。本次不扩大到所有场景真实验收。smoke 和 motif:check 均通过，0付费模型；后者的5次示例旁路只属于诊断。

私有日志：`.local/test-logs/ppt-user-learning-20261019/`。初次本机Python测试因缺 `fitz` 收集失败；转服务器运行，没有用模拟模型代替真实模型验收。首次新测试中认证器零候选的子进程异常未捕获，补为认证拒绝、保留失败且相同证据不重试；该失败记录保留。

收尾只读复核修正两项闭环边界：认证样本按模型/工具/提示等有效配置分组，旧配置不再阻塞新配置的三条独立证据；负反馈在事件持久化后更新永久代际标记，worker在读取快照前冻结代际、在线准入重新核对，防止较早的后台任务重新启用已撤回候选。新增旧配置+三条新配置、编译中撤回及在线代际失效检查均通过，未增加模型调用。未发布兼容版本按最终代码重新导出，旧版证据不变。

## 真实验收边界与下一步

旧服务器私有凭证文件仍存在，可正确加载；激活环境本身不加载凭证，未展示密钥。官方 `v6.6.0` 标签和发布 ZIP 最初只有12,899/13,016文件一致。追溯上游 `hugohe3/ppt-master` 的 `440557b8dc7c7257b69c04a0b014d5c50a78e6cb` 后，已取得13,016/13,016文件完全符合原锁的安装，package SHA256为 `7dc4ca13eb0bc6ab9cf794c53ad3569171356b7af8b8a005cd732269726bb794`；没有修改技能锁或用旧生成器替代。安装与来源收据保存在私有隔离目录。

真实验收从原生上传与 `session/prompt` 接口发起，保留 main 的 `/ppt` 场景控制、同模型/技能/Schema 两路执行及原结算接口。普通独立 `web:real` 没有自动配置 paired comparison，不能仅凭启动它宣称已完成用户闭环；本次在隔离配置中使用现有 `web_budget_broker.mjs` 和 paired policy，继续记入同一实验账本。完整账号沙箱部署与浏览器画面验收另列，不能由原生 HTTP 成功替代。

首次客户端20秒超时中止了附件分析任务，费用和不完整回执保留；两次隔离预算路由配置错误在模型调用前被拒绝，也保留失败任务。旧Ubuntu环境的 Node 需沿用已有 `warm-report.cjs` 兼容预加载；直接裸 Node 曾导致隔离成员进程退出139，没有通过关闭沙箱放行。本轮最小兼容验证已结束；尚无新候选真实晋级或同质费用节省结论。后台编译模型请求0，实际账单/CPU/人工/维护费用未知，不能写总成本0。

### 新版原生工具结果兼容失败及修复

第一项真实任务为上传 Attention PDF、独立生成三页中文汇报，交付可编辑PPTX、备注、PDF和PNG。两路均完成，后台自动收录一条合格原始Baseline；没有人工伪造轨迹、评审或晋级。

| 修复前两路 | 真实请求 | 代理峰值估费（美元） | verified skip | 交付 |
| --- | ---: | ---: | ---: | --- |
| Baseline | 188 | 0.313435596 | 0 | 三页PPTX/PDF/PNG/备注 |
| Execute | 203 | 0.312394368 | 0 | 三页PPTX/PDF/PNG/备注 |

两路科学/视觉质量未独立评审，人工时间未知。约0.33%的费用差不构成RSI收益；Execute请求反而更多。真实审计显示工具执行成功，但观察器将其判断为 `tool_result_failed`，两条已认证边均未触发。DSH 原生工具事件存在两种表现：MCP 的执行值仍可为 envelope，外层文本投影则是其中的 payload；直接 Native 工具还可返回 JsonValue 对象。原诊断仅覆盖旧事件外形，不足以定位所有格式。中途曾错误地将 envelope 与 payload 直接比较，导致既有 literature 真实 SDK/MCP 诊断失败，已修复；不能单独归因为“新版工具都返回直接 JsonValue”。

修复限于项目适配器 `dsh_online_motif.mjs`，不修改上游或迁移核心：MCP 按既有语义解码，未提供 structuredContent 时比较解码 payload 与外层投影；既有 structuredContent 权威性保持。直接 Native 对象要求成功的执行值与完整单条 JSON 文本投影摘要相等。错误、矛盾、多余文本或版本变化不旁路。最终七项回归覆盖旧事件、原生 MCP、直接 Native、版本变化、矛盾结果及工具错误；服务器通过。既有 literature 原生 SDK/MCP 的学习→旁路→过期回退诊断也通过（1项/40.12秒、合成Provider、0云费用）。中间失败记录保留。两个未发布兼容版本在私有备份后重建，旧发布库不改，原IR/证据/Schema保持一致；运行期间没有替换源文件或中断任务。

账号沙箱已通过真实启动、PPT会话和Execute/RSI准入检查（0模型请求），不等于账号浏览器完整生成验收。隔离paired启动时还需重新加载新证书描述，不能复用内存/策略里的旧锁；旧描述被正确拒绝，未关闭认证绕过。

### 最小真实读取复验与最终边界

修复后仅补一个真实原生上传→固定来源→转换→读取的 paired 探针，不重新生成整份PPT。comparison ID 为 `comparison-ea608bff-2ae2-455a-9a62-a2578b22ae8d`，Baseline/Execute task 分别为 `ee1e4636c2114282acaec4e8f3d5e5c6` / `18e2e40c792443fc83883c4755fa9d92`。两路 Flash/Off、同输入和技能、无压缩、额度 null；上传图文分析和重试均在原账本。实际配置、完整工具顺序与源码/库摘要保存在各任务的 `effective-config.json` 和私有快照，不只记录默认配置。

| 最终读取探针 | Baseline | Execute |
| --- | ---: | ---: |
| 真实请求（含附件分析） | 17 | 15 |
| 输入 token | 181,374 | 137,066 |
| 缓存命中 / 未命中输入 | 150,269 / 31,105 | 106,493 / 30,573 |
| 输出 token | 7,566 | 6,971 |
| 总 token | 188,940 | 144,037 |
| 代理峰值估费（美元） | 0.019312314 | 0.018176058 |
| 任务耗时（秒） | 68.723 | 63.526 |
| 真实 verified skip | 0 | 2 |

审计连续记录两次 `motif_bypass_attempt`、两次 `motif_tool_result_verified` 和两次 `model_request_skipped_verified`，对应 `pin_source→convert_source`、`convert_source→read_converted_source`。请求少11.76%、总token少23.77%、估费少5.88%，但这是来源读取的单次局部验证；没有PPT成品，不属于完整生成降本，也不是用户新候选的晋级证据。前一次错误兼容版读取探针两路均17请求/0旁路，费用分别0.022593768/0.019205922美元，保留为失败诊断，不择优删除。

后台真实状态为 `waiting_for_eligible_tasks`：1项完整合格Baseline，至少需3项；读取探针因没有PPTX/PDF/PNG被正确排除。自动3项认证→2项后续对照→晋级/负评停用已由诊断测试验证，**尚未在自然用户任务上完成新的真实晋级**。后续让正常独立用户任务积累证据，不为凑样本启动大矩阵或手工修改状态。

本轮累计461个真实请求、账本逐回执峰值估费合计0.711649760美元，包含附件超时、失败探针及完整成品任务；不是新增闭环的学习成本，也不是实付账单。后台离线编译未调用模型，计算/维护/人工成本未知。原始账本、事件及失败留在私有目录，不入Git。

最终私有诊断摘要 `final-evidence.json` 与日志保存在两端 `.local/test-logs/ppt-user-learning-20261019/`。完整三页成品已逐项SHA核验同步到本机 `.local/deliverables/ppt-user-learning-20261019/comparison-b2d5f299-8aed-43f2-aa53-caa3469a8dbf/`，包含普通/优化两份PPTX、PDF和逐页PNG。当前只完成隔离开发及检查，未commit/push/PR、未切正式服务。旧feature分支仅参考，未合入或修改。

### 提交前审计（2026-10-19）

用户授权确认接通后提交到 `feature/research-ppt-agent`，自行准备PR。开发起点仍为上述 `a1c0fa2`；提交前已同步最新 main `b939cd5`。新增主线改动仅服务生命周期与管理员认证，没有改变PPT学习依赖；两库分别47/88项源码锁逐项匹配，覆盖102个不同源码文件，Git索引里的实际提交字节也全部匹配。沿用v9/v14证书，不冒充重新训练。正式网站后续必须走 `npm run service`，本次不部署或重启正式服务。

旧feature仅有两项main未包含的历史提交。以main当前实现为准保留提交历史，并保留其独有的[前端真实验收报告](research-ppt-frontend-rsi-20261014.md)，不恢复旧场景内自建Agent循环。候选版本在新的独立服务器目录 `DeepSeekHarness-ppt-learning-20261019-submission-audit` 验证，不覆盖原实验目录或账本。源码快照1571文件逐项SHA一致，归档摘要 `cce86be4f2e7e65d5b8b4bfed5e544c5ce4070cfac23b7e10f6f430ef0b04900`。

首次候选回归920通过/199跳过、4失败：隔离源码包没有`.git`，四项需要记录HEAD的模型配置/产品提示/原生SDK诊断拒绝运行；没有改测试或绕过版本检查。由本机main Git bundle补齐准确`b939cd5`元数据后再复验，失败日志保留在 `.local/test-logs/ppt-user-learning-submission-20261019/npm-test.log`。本次提交审计不增加模型调用，之前461请求的原始账本不改。

补齐版本元数据后最终 `npm test`：Python **924通过/199跳过**（166.96秒），Node **855通过/3跳过**（23.19秒），0失败。相较开发轮多出的24项来自最新main的服务生命周期/认证检查，不计为新增PPT能力或模型收益。源码审阅未发现未解决的闭环阻断；认证与晋级仍限已有两条结构，真实用户样本仍为1/3，不能把诊断的3→2晋级说成自然用户已晋级。

提交前 smoke / motif:check 同样通过，均0付费模型。随后main合入PR #87，仅调整AGENTS服务器路径说明和服务文档定位；已快进同步至 `d422d77`，可执行代码与上述已测版本一致，未为文档更新重复跑模型或测试。提交范围35文件，只含接线、守卫、必要回归、兼容库和报告；不提交私人论文、PPT产物、凭证或原始日志。
