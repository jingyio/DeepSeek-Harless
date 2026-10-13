# 多窗口读取 Motif：独立认证、完整任务和同包组件对照

2026-10-12开始，2026-10-13完成。实施前接口/提交说明见[变更记录](../changes/pdf-window-continuation.md)，候选来自[40流程探索](../../scenarios/literature-notes/workflow-discovery.md)。

## 结果先说

现有跨调用参数边和批量Runtime可用于新的文献检索任务，**无共享核心修改**。模型选择查询/窗口，原pin工具验证并签发source_id后，Runtime可自动读取多个窗口，保留来源/版本检查并交回原模型。两个普通原生训练任务9/10条实际参数边，第三独立研究问题6条认证见证；新manifest只在私有实验显式加载，默认SDK/Web/正式Agent不变。

同一真实模型选定窗口的组件对照，6个原文包完全一致，H每次6个请求，M5/5/4；每轮恰有1次读取调度绕过，平均估费−5.09%、输出−9.85%、时间−11.34%。完整任务的两题结果不同：两篇效率证据检索平均请求−18.92%、估费−3.76%；三篇编排比较请求不变、估费+44.41%。不支持默认启用或完整科研理解的普遍效率收益。

## 实现与配置

- 新`pdf_window_tools.py`/场景配置/契约/题面，复用WorkflowProbeScene/PdfScene。pin的paper_id/page/start/length必填字符串；page/start/length采用有界规范十进制，转整数后执行原PDF工具。位置仍由模型选择，Runtime只复制已签发source_id。旧探针的整数参数没有改写成训练样本。
- Python复用原provenance/edge mining/edge compiler/certifier/library builder/exporter；在线复用原`sss-online-motif`/proposeReadyBatch/原生工具回调、manifest v1、原SDK及预算代理，没有复制或修改上游/共享核心/旧库。当前只是已有机制在新任务里的认证复用，不称新的遍历算法或完全自主RSI。
- 闭合source读取不用embedding；SDK要求的loopback端点拒绝embedding请求并记录访问，训练/正式对照/组件均0embedding。没有模拟向量授权执行，也不使用GPU/A100。
- 模型DeepSeek Flash、reasoning off、native；每次输出4000token、单任务预算保护上限0.25美元。正式两题各3轮H/M，共12次；次序H/M、M/H、H/M；同题同PDF/同题面/工具集合与顺序/检查/预算。原文缓存两组共用，provider缓存命中不能控制，全部记录。不做上下文压缩、不更换前端。
- 原PDF只读，语料/派生报告/原事件/账本/库/代码快照全在.local。本机macOS arm64/Node22.22.2/Python3.12.13/DSH+SDK0.1.5-rc.3；三篇已知开发PDF及其子集，没有跨新论文泛化。
- 题面直接含具体研究问题，read_workflow_input还必须核对冻结题目/清单。两训练3/2篇，一认证1篇，各问题不同；认证前对所有实际成功调用、完整来源结果、发布工件和tool schema逐项重放，没有人工审批/科研真值标注。

## 独立认证与失败历史

合格训练/认证在`window-continuation-20261012-4e9c093c`：39实际上游请求/代理USD0.039686664。两训练原run为82da7786…和97c03e8b…，第三7456f057…认证。见证数9/10/6；原正常provider消息、call/result和source_id流向真实存在，不用sss/mock/PTC事件训练。

manifest摘要`1e1f3782744f67afd63bb8d9ead18db6903c55c6a73629ac7c9b4dca7d5ec14b`，主实验`.local/literature-notes/window-continuation-20261012-0bc4ddc5/learned/`。正式评测复用完全不变的合格库/模型轨迹，没有再次收费学习。

开发失败全部保留：

1. 首任务成功交付，但收集器重放了失败pin，离线报错。修为只重放成功实际调用，3次参数错误和10次API费用保留；恢复实际原轨迹不再付费。原ID1acfc276，新诊断ID1d0b9795。
2. 离线稳定ID曾用不受支持的冒号、MCP schema序列化用input_schema而binder要求inputSchema；修正离线标签/表示，真实事件不改。06e2ab2c尝试复用已完成真实轨迹，没有新增API，但最终独立认证拒绝。
3. 第一组任务问题虽在实际工具输入/返回中不同，会话题面相同；原认证器因此拒绝独立决定。没有放宽校验或编辑原SDK manifest。初始3次正常运行39请求/USD0.033870732保留为**认证拒绝**，不算合格训练。随后把问题写入会话题面，在新ID4e9c093c重新运行上述合格3项。
4. 首个评测pilot H15请求，M12请求+4Runtime批次，M在16 SDK步数上限前已发布报告，但无法完成末尾结束，NativeBudgetExceeded；不能当完整成功。pilot27请求/USD0.031876104保留。原预算接口把Runtime步骤也计入，正式评测改为双方32步骤、新ID0bc4ddc5；预算共享核心不改。

这些失败不是429；本轮实际云请求全部HTTP200。成功工件存在不等于SDK完整结束，收集器已分开记录incomplete_workflow和有效来源回执。

## 正式完整任务：两题各三轮

| 问题 | H实际请求均值 | M实际请求均值 | M输出变化 | M代理估费变化 | M原生耗时变化 | 完整结束/机械覆盖 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 三篇编排、执行反馈与验证器比较 | 10.33 | 10.33 | +35.29% | +44.41% | +23.38% | 两组均3/3结束、全目标、0机械缺口 |
| 两篇工具成本、效率与失败恢复证据检索 | 12.33 | 10.00 | −2.88% | −3.76% | −5.12% | 两组均3/3结束、全目标、0机械缺口 |

三篇H/M每次代理费均值USD0.009927732/0.014336720；两篇0.012598672/0.012124348。全部12次129请求/USD0.146962416，H68请求/M61；总费用H0.067579212/M0.079383204，M总体仍贵约17.47%。包含错误/恢复，不以成功子集美化。

实际19个Runtime读取批次、36条实际读取结果，全部source_id来源、窗口/文档版本与当前来源重放一致；H13个纯读取模型响应/1722输出token，M纯读取模型响应0。H/M非纯读取请求55/61，抵消了一部分局部绕过，因此总差是7个实际HTTP请求，不能按19批报19个净节省。

6个配对的阅读窗口集合和交付引用集合均不同，模型后续路径不受控；整体请求/费用差不能全部归因读取边，更不能声明同等科学质量。所有模型解释仍有普通LLM理解/引文支持风险，本轮未做完整科学支持验收。41个工具错误留账，其中37为窗口字符串类型错误，4为报告长度/字段错误。为复用旧核心而采用字符串是工程折衷，不证明它优于数值接口；两组共同承受，不能把表示适配本身算Motif收益。

## 同一真实窗口计划：隔离读取续接

补充实验`window-component-20261013-be643eb9`在运行前单独冻结。计划取正式首轮普通Harness真实成功调用：每篇第一个成功检索、第一成功pin，3篇3窗口；不是人为填好未知论文答案。先完整回源验证，再两组同一计划/题面/检查。原选择任务的USD0.009662064已计入完整任务，不再次记账；从组件计时中等量排除。只要求读取/位置确认，不作科学解释。

| 指标 | H三轮 | M三轮 | 相对变化 |
| --- | ---: | ---: | ---: |
| 实际请求 | 6/6/6，均值6 | 5/5/4，均值4.67 | −22.22% |
| 输出token均值 | 2075.33 | 1871.00 | −9.85% |
| 代理估费均值USD | 0.006087344 | 0.005777624 | −5.09% |
| 原生耗时均值秒 | 13.762 | 12.201 | −11.34% |
| 原文包严格相等/完整结束 | 3/3 | 3/3 | 6包全部等于预先回源的包 |

32实际请求/USD0.035594904、0工具错误/0embedding；M3个读取批次/9实际源结果，H3个纯读取模型请求/634输出→M0。总少4请求中可直接确认读取续接省3；第三轮额外1次来自模型把独立搜索与pin合在一条消息，不能都归因Motif。费用/时延是小样本观察，缓存/模型输出仍波动；不外推论文理解或整Agent普遍收益。

此组件平均每次费用差仅USD0.000309720，尚未摊平学习/开发支出。没有本任务真正Code Mode或手写合并的对照，不宣称优于它们；旧四组组件对照负面结果仍有效。用户目前以相对普通Harness改进为主，这里支持**可验证的局部减少模型调度**。

## 总账与测试

全部不同真实run去重：初始认证拒绝39+合格训练/认证39+失败pilot27+正式任务129+同包组件32=**266HTTP200/26run/代理USD0.287990820**。复制/导入同一训练run只计一次；无429。未缓存输入493507、缓存读取2977920、输出101726、推理0token；账单实付与开发/维护时间未知。原始逐请求账本及总审计在主实验`total-cost-audit.json`，开发关联在`development-history.json`。

- 新参数/来源回归10项，合计24专项通过；全仓487Python/98Node通过，3可选Docker跳过。
- 实际MCP自定义窗口/前导零负例通过，API0；免费原生SDK+实际MCP/mock Provider：3窗口1读取批次、3 mock请求；错误版本0批次、4 mock请求并正常走原模型；均0云API/0embedding，明确不作为训练或性能证据。
- 全部真实任务及组件的当前源、工具结果、工件SHA、真实HTTP/模型消息计数核对；原PDF哈希不变。主实验捕获的共享Runtime/adapter/compiler/runner文件SHA与当前一致，本轮共享核心没有变化。
- 未commit/push/PR，旧工作区/服务/密钥/历史资料保留。本轮默认不开Web/不组合其他library。

## 复现与后续判断

```sh
# 新克隆需要自己的三篇开发PDF及真实普通轨迹，不分发用户PDF/私有库
node scripts/project.mjs python scenarios/literature-notes/window-study.py
node scripts/project.mjs python scenarios/literature-notes/window-study.py --experiment .local/literature-notes/<返回ID> --phase train --call-model
node scripts/project.mjs python scenarios/literature-notes/window-study.py --experiment .local/literature-notes/<返回ID> --phase learn
node scripts/project.mjs python scenarios/literature-notes/check-window.py --experiment .local/literature-notes/<返回ID>
node scripts/project.mjs python scenarios/literature-notes/check-window.py --experiment .local/literature-notes/<返回ID> --stale
node scripts/project.mjs python scenarios/literature-notes/window-study.py --experiment .local/literature-notes/<返回ID> --phase evaluate --call-model
node scripts/project.mjs python scenarios/literature-notes/summarize-windows.py --experiment .local/literature-notes/<返回ID>
```

原已执行attempt拒绝覆盖；来源/代码变化要新ID。组件用`window-component.py --parent <正式目录>`先预览，再`--experiment <返回目录> --call-model`。取消manifest回原Harness，不能直接复用旧探针整数参数的策略。

我的判断：本轮把候选推进到了**真实学习、独立认证、在线批量读取与实际普通Harness对照**，但只支持局部效益。保留显式实验入口，不把这条默认推广到三篇比较。后续转到引用工作集/资源状态分支，避免继续为细小字段反复调整这条路径；数值位置接口的类型支持若以后做，须先详细记录共享协议变更并重新认证，当前没有实施。
