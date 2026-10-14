# 正反轨迹学习续接条件：状态 Shadow

2026-10-11，Codex。完成：状态学习、历史反例回放、三条真实前瞻 Shadow；未做 execute，未证明模型请求减少。

## 问题与条件的来源

上轮局部图只知道“读报告→检查”，导致已检查的报告在末尾重读后仍被预测再检查。本轮从原有合格正常 baseline-main / baseline-abstract 学习正反例，不使用上轮 Shadow 作为训练。

工程提供二值特征 `prior_same_input_check`：本 Session 是否成功调用过生成工具，且返回的 input/report/source/candidate/catalog 摘要与当前收据完全相同。特征不判断论文真实性，也不缓存旧科研结论。条件值由真实轨迹选择，不预设为 false；正负例冲突则标为 ambiguous 并不预测。没有负例时不虚构条件。

实际观察：读取后的检查有2个正例，重复读取后修订或结束有2个负例；编译得到 `prior_same_input_check == false`。正例来自两个 Session，负例只来自一个 Session，尚不是独立论文认证。写入后的检查只有2个正例、0负例，保持未加条件的局部候选，不能声称所有分支均已认证。

## 实现与版本

- `trace_rsi_state_compiler.py` 复用原编译器完整正常声明、调用、结果、来源和质量验证。保留负例的下一请求及工具集合，不把多工具、失败或未完成的同工具尝试当成成功见证。
- `dsh_trace_rsi_state_shadow.ts` 复用原 Shadow 参数/版本/结果守卫；只过滤预测，所有实际模型请求继续执行。会话状态来自实际成功结果；报告变化重新判定，工具失败清除完成事实，跨 Session 不共享。
- `paper-rsi-state-shadow.py` 复用任务、提示和累计预算；只有 preview/compile/shadow/verify/score，无 execute。
- `replay-trace-state-shadow.mjs` 在隔离副本复原报告字节，按完整历史消息/调用/结果回放；不调用模型或 MCP，不改历史产物。

原生成程序、MCP、提示及旧观察器均保持字节不变。只允许增加上述三个状态观察/编译/控制文件；原训练库原样保存，派生库显式记录新增代码摘要，不把旧见证说成新代码下的模型训练。状态库 kind 为 `trace_rsi_state_shadow`，execution_policy 为 `shadow_only`。

manifest：`99457cae7f839fe36d2c83833f909b750201a6e738e67a46dde18459b85779fc`；文件摘要：`ba3af7913999c039b9beec75ea4f70bf8ff89c320f06fa6dc6e0360eae831bcf`。状态特征及有界学习器是人工工程实现，不称为模型自行发明任意守卫。

## 历史反例回放：已验证

回放上轮 shadow-subset / shadow-incremental，各6个真实历史请求：新守卫各保留2次正确检查预测，并拒绝最后1次错误续接。合计正确预测4次保留、错误预测2次拒绝；0新增模型请求、0实际跳过。

训练没有使用这两条 Shadow，但这些反例此前已被人工看到，所以这里只是回归复核，不是未见数据认证，也不是新前瞻结果。

## 本轮真实前瞻：已验证及限制

同论文范围派生及报告故障注入，结构/已有字段保留门槛沿用上轮；不核验文献真实性。subset-a 是不同于训练的范围，incremental 是原评测范围的复测，main 是训练范围的复测。均为新 Session，不算三篇独立论文。

| 运行 | 请求 | 完整工具集合/参数/结果匹配 | 严格整请求 | 不完整预测 | 新增代理估费/美元 | 模型运行秒 |
|---|---:|---:|---:|---:|---:|---:|
| shadow-subset-a | 5 | 2 | 0 | 0 | 0.008725464 | 21.60 |
| shadow-incremental | 5 | 2 | 0 | 0 | 0.008453052 | 20.06 |
| shadow-main-recheck | 5 | 1 | 0 | 1 | 0.011564736 | 24.08 |

合计 **5/15=33.3%** 局部完整调度匹配；6次预测中5次完整匹配，另一次不完整，预测精确率83.3%。严格整请求 **0/15**，实际跳过 **0**；所有匹配请求仍带模型文字。没有删文字、改变提示或缩小分母。

三条交付均完整配对、无重复、既有字段原样保留、只添加待核验占位、来源/代码未变。科研语义质量未盲评。三条均没有出现末尾单独重读后结束，因此学习条件拒绝此类续接的效果只在历史回放验证，不能宣称已在新结束分支认证。

主稿请求4同时调用 `triage_catalog_coverage` 与 `read_task_state`。图只预测前者，即使前者的参数/结果正确，也不能替代整个请求。这是新的批次覆盖反例，保留并计入分母。请求5有已检查状态，但原单锚点守卫已因上一请求有多个结果而停止预测，不能把它归功于新状态条件。

从上轮6请求变为本轮5请求是原生模型行为变化；Shadow没有删除任何调用，不归因于本方案。不同范围的33.3%与上轮33.3%也不能说明收益增加或减少。

| 运行 | 缓存命中输入token | 缓存未命中输入token | 输出token |
|---|---:|---:|---:|
| shadow-subset-a | 31744 | 7834 | 5154 |
| shadow-incremental | 30592 | 7633 | 4983 |
| shadow-main-recheck | 35456 | 14732 | 5777 |

## 配置、费用与复现

基底 `2368235f274329be6227a8393b850633cb943da4`，feature/paper-submission，未提交/推送。deepseek-flash/off/8192，无次数上限，无压缩，独立DSH_HOME，继承私有副本的非沙箱实验授权；不投稿、不写外部应用、不重启Web。

本轮训练新增模型请求0；评测15请求，新增代理估费 **0.028743252美元**。包含此前学习、失败及重试，累计约 **6.075568/8美元**，剩余额度上界约1.924432美元；账单未知。开发、同步、免费回放及人工修订时间未计量；没有净收益结论。

```sh
source .local/remote-env.sh
node scripts/project.mjs python scripts/paper-rsi-state-shadow.py preview
node scripts/project.mjs python scripts/paper-rsi-state-shadow.py compile
node scripts/project.mjs python scripts/paper-rsi-state-shadow.py shadow --case t03_subset_a --label shadow-subset-a
node scripts/project.mjs python scripts/paper-rsi-state-shadow.py shadow --case t10_incremental --label shadow-incremental
node scripts/project.mjs python scripts/paper-rsi-state-shadow.py shadow --case t01_main --label shadow-main-recheck
```

上述标签及库已存在，禁止覆盖。重核现有产物用 verify/score；回放用 `node --experimental-strip-types scripts/replay-trace-state-shadow.mjs <原运行目录> <状态库>`，零模型费用。新付费重测须新实验ID，继续累计历史费用。

私有 `.local/paper-reference/paper-rsi-state-shadow-20261011-v1/` 保存原库/派生库、正反见证、配置/代码/来源/提示摘要、版本、逐请求、事件、账本、报告、独立验收、预测、评分、回放与汇总。最终本地及服务器 **298 Python / 162 Node** 免费回归通过；服务器无模型smoke 18题/83工具调用通过。同步时Mac元数据条目触发版本守卫，免费拒绝后改为仅打包明确源码，零请求，记录保留。

## 下一步

机制支持从实际非衔接轨迹学习局部状态条件，并在同类历史反例保留正确路径、拒绝重复续接；不支持实际请求降本、任意结束判断或跨论文认证。下一步学习完整多工具批次及参数关系，并给控制文字与科研判断定义明确交接。暂停execute，继续保留严格自动统计、人工文字判断和实际跳过三个口径。
