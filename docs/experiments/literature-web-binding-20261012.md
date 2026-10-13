# 文献 Agent 官方 Web 接入验收（2026-10-12）

## 结论与范围

已接入官方 Harness `/tasks` 和 `/api/harless/tasks`，每个文献任务在自己的一个 Session/turn 中完成阅读、逐论断自动支持复核、最多两轮补缺及最后综合。两个不同真实问题修复后分别交付15字段/17引文/0程序缺口和15字段/16引文/0程序缺口，共43真实请求、代理估费USD0.176891508。不是科学正确性认证、专家盲评或Motif净收益证据。

沿用用户的API授权、普通PDF、自研最终前端、无需人工科研审阅。没有修改原PDF/上游Harness/预算计价，没有新learned Motif。当前默认baseline；新web工具名称/执行结构不在旧library认证范围，缺库时shadow/execute显式回退。暂不运行质量未校准的效率比较。

## 协议与环境

私有实验ID：首版`web-binding-20261012-8d701dd9`；修复后`web-binding-20261012-aaf962ec`。开始前保存protocol（研究问题/来源哈希/代码哈希/model配置/预算/请求上限）。同一个Web进程顺序执行两问题，工具13项/顺序固定，deepseek-flash/off/不压缩，输出上限8000，每任务90请求/USD3，每次启动180请求/USD6。保护上限不是预期费用。未进行整任务自动重试，修复后的新版本是独立开发验证，旧结果保留。

题面1：这三篇论文的方法、实验证据和限制，对构建高效科研 Agent 有什么启示？

题面2：在不改变模型权重的前提下，这三篇论文哪些操作可用于科研文献Agent的结构复用，哪些科研判断仍需模型？

语料为既有/testpdf的UnifiedPlayers、Paper2Agent、MetaRSI三篇已知论文。不是训练/留出泛化实验。macOS arm64、Node22.22.2、Python3.12.13、DSH0.1.5-rc.3；没有A100/服务器/其他平台新增验收。

## 真实结果及反例

| 版本/问题 | task_id | 请求 | 估费USD | 执行秒 | 引文 | 程序缺口 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 首版/1 | 181cb742ab314e9687607537df512b27 | 24 | 0.092495556 | 105.802 | 11 | 4 |
| 首版/2 | 99a4e70a15de41d8afb7cd899f3ab2b5 | 25 | 0.089043888 | 95.319 | 16 | 1 |
| 修复/1 | b9cafff78fd34873bb2e1f04bfb6ab14 | 22 | 0.100008924 | 90.171 | 17 | 0 |
| 修复/2 | 8b759006d315456ab21ae933ed06094d | 21 | 0.076882584 | 81.218 | 16 | 0 |

首版第二轮没有传入第一轮原始证据历史；撤回字段丢失引用后，模型沿用旧citation_id受到拒绝。修复复用既有RepairScene的history_input_directory/history_input_sha256/prior_proposals，重新重放旧来源并按论断签发权限。普通阅读工具在复核阶段拒绝，必须走claim专用预算工具，未放宽支持检查。

修复版本两项第一轮各4缺口，第二轮只修各4项，最后程序缺口为0；各自一个不同Session/一个原生turn，首次list_pdfs的题面和完整PDF清单与冻结输入逐项一致。没有未知引用或坏JSON自动补写；仍有30/24条pending拒绝诊断（不是54次独立模型失败），题面2一次过早read_final_synthesis被阶段守卫拒绝，随后模型实际完成。所有请求/纠正费用计入，没有人工修改科研答案。自动完成守卫实际续接均0，不能冒充该守卫恢复实测。

修复版usage合计：输入5,507,303（命中5,133,568、未命中373,735），输出28,308，总token5,535,611。长Session可能积累大量重复上下文，不能只用请求次数下降认定更便宜。首版与修复版不是随机同质量对照，题面1修复后费用反而更高。

本轮付费合计92请求/USD0.358430952，全部HTTP200；修复版43请求账本舍入估值USD0.176891490，与摘要差−1.8e−8，记录在real-audit。先前PDF代理累计USD2.603995936→USD2.962426888。没有核对供应商实付账单，开发/Codex/维护/专家评估成本未计量。Web预算口径为保守峰值估计，actual_paid_usd未知，不写成精确账单。

## 免费工程与界面验收

完整回归378 Python+66共享Node通过（Python中包含既有场景Node包装，不重复相加）；新增7 Python/2 Node覆盖独立题面/句柄/产物、来源变化、任意路径/版本/附件拒绝、强制自动复核与完整表综合、跨阶段读取拒绝、历史权限与拒绝诊断、关闭信号转发。通用动态Web的13组HTTP/MCP诊断也通过，API0。

最终免费真实Harness/HTTP/MCP协议验收`web-binding-20261012-51ad10a4`：同进程两个不同问题各43模拟请求，15字段/15显式缺口，另一个取消任务0请求。每个任务独立Session/输入/preset/产物/预算，重复请求不重跑，错误确认摘要拒绝。模拟故意不理解论文；估费数字只是代理协议计算，实际支出0。

另外保留早期免费83ffdc17、4fd3b156及原始40531492诊断。启动包装器旧版SIGTERM未转发，偶尔留下子进程占端口，导致6b82834e真实入口启动失败/0上游调用；修复forward+wait并新增真实关闭测试，未删除原失败日志。实际Browser验收只做预览和取消，0付费；服务端登记全部PDF，隐藏通用图片/小附件入口，预览显示题面和论文而非内部提示词。UI元信息修正发生在付费实验后，不修改模型读写、额度、Guard或原实验结果；随后免费端到端和回归再次检查。

## 复现与后续

```sh
npm test
node scripts/project.mjs python scripts/check-web-tasks.py
node scripts/project.mjs python scenarios/literature-notes/check-web-pdf.py
# 以下显式启用付费API；两问题总保护上限6美元
node scripts/project.mjs python scenarios/literature-notes/check-web-pdf.py --call-model
npm run web:literature -- --real-model --papers-dir ./testpdf
```

密钥复用已有`.local/deepseek.env`或环境变量，不复制进公共配置；认证地址仅私有access-url.txt，日志/论文不提交。SDK与8765旧工作台保留，Web新增路径没有接入旧工作台的结果缓存/增量更新全套功能。`/tasks`为临时前端，最终自研前端复用同一认证任务API。

下一步先冻结质量和预算条件，建立普通Harness/普通脚本/learned Motif的可重复对照；没有当前web认证库之前不强开旧库。后端仍固定off，思考模式对照待实现，不能用前端按钮代替真实参数。参见[对照协议](literature-web-comparison-protocol.md)。
