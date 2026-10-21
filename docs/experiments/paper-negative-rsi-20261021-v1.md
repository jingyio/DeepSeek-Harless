# 提示型 Negative RSI 自动闭环验收

## 结论与范围

**提示型闭环已在真实论文恢复任务中跑通；未证明净降本或通用原因学习。** 当前真实失败进入编译器，模型生成建议并独立审核，发布到同一私有store；后继任务冻结版本，遇到当前相容失败后，把建议送入真实模型请求。最终F→G连续局部验证通过，未开启自动早停。

这是一个小点：接通既有Negative编译器、审核、发布和消费，修复可选Positive匹配器初始化失败拖垮Negative的接线问题。未替换生产服务、公共认证库或上游Harness，未修改私人原件，也未新增模型可见工具。分支`codex/paper-negative-learning-loop-20261021`，基于`40d015ca`；每次运行保存实际工作区源码摘要，而非把父commit当作新实现。

## 问题与可否定假设

旧自动worker仅处理completed任务，且latest指针只包含Script/Reuse。失败或取消任务里的真实工具失败容易丢失，负面库需要手工编译和装载。假设：沿用现有结构化失败判定与运行时守卫，能够自动产生有依据的提示，并被后继任务实际使用。

若只有库文件增长、不能确认后继加载的精确版本，或提示未到真实请求边界，则不算闭环通过。提示出现本身不等于错误恢复改善、原因成立、跳过请求或省钱。

## 实现与安全边界

- `script_negative_compiler.py`只读取本任务事件窗口，排除合成dispatch、工具异常和不透明错误。`failed_checks`/`validation_error`与HTTP502、任务失败状态分开；后两者不编译成错误原因。
- `script_negative_learning.py`复用现有编译器；自动模式要求同工具、失败码、来源和schema下至少两个不同任务的原生见证，且工具实现源码快照与当前一致。旧实现漂移的轨迹明确拒绝，不能只替换旧hash。
- 模型只看有界校验摘要和参数形状，提出24–600字符的单行建议，另一请求独立审核。不能修改匹配条件、代码、权限或早停策略；建议明确是历史线索，不是当前根因。
- 所有自动规则强制`prompt_only`，经现有TS在线loader认证再发布。即使sidecar指定enforce，自动库也不能取得早停权。已有手工条件认证入口保持独立。
- `advance-script-motifs.py`沿同一锁、历史和不可变round发布；Negative历史接收completed/failed/cancelled，Positive历史仍只接收completed。不同组件发布到同一generation；审核失败保留兼容的旧库。相同结构化证据复用审核缓存，不重复付费。
- `script_learning_store.ts`支持`negative_file/negative_digest`及Negative-only版本；按owner、路径、摘要和代码锁准入，任务内冻结。加载成功、当前失败命中、提示送达分别记录。
- `optionalScriptRuntime`隔离可选正面匹配器：空库不启动；非空库因Embedding配置缺失等初始化失败时，只记录`script_component_fallback`并停用该匹配器和catalog，Negative/Reuse与原生Agent继续。配置完整时既有cache catalog仍可用，不以executionFrontier为前提。库真实性准入失败仍保守回退。

默认不放`negative-learning.json`，不启用负面学习模型。模型传输复用既有费用预约/结算，分别记入`negative-budget.json`与`negative-ledger.jsonl`；不重置历史，不自动重试。HTTP失败响应新增有界私有诊断并过滤凭证值。

## 任务、划分和配置

沿用已有真实报告失败检查点及原恢复提示词，不重跑Baseline或完整论文检索。A/C/E/F使用一个真实历史结构失败候选，B/D/G使用另一候选；来源是同一论文，**不算七篇独立论文**。当前受保护完整目标来自各失败回执绑定的原目标；没有手写针对当前字符、参考文献或错误码的规则。

- 来源SHA256：`4bd4169416ae7be939a450855617a490719d6ed6780f2ccd3e3c734d257684c8`。
- 原恢复提示词SHA256：`443bd3f6d92210a6092fc24354a0a595eee5a94060befb67f994334d61532ba8`。
- 两个检查点SHA256：`0188dc5654025d69b8f16277144b37800d3a9ab38e1bb14637fff694ea832ba0`、`a25f3c62dca9e2511d5bc6e8e077d692f172962e15b1137ce541f17ee1409c38`。
- 真实DeepSeek Flash，`reasoning_effort=off`，Agent单次输出32768，学习1536，每轮最多1种失败模式；请求/费用不限，`cap_usd:null`、`budget_policy:uncapped_user_authorized`、`reset_history:false`。
- macOS隔离runner，固定项目Python、报告字体与原工具；压缩关闭，未配置Embedding/未调用Embedding。Positive sidecar为shadow，**Negative为prompt干预，不是完全不干预的Shadow对照**。
- A–D恢复最多360秒；E–G是最多45秒的真实局部投递检查，故意取消，不作为完整交付或质量成绩。
- A/B只贡献当前原生失败，未借旧代码版本的失败直接认证。C在任务开始前冻结库，D消费C自动发布库；最终F在任务结束后自动发布，G精确消费F版本。生成/审核缓存不替代当前证据与源码认证。

私有目录`.local/paper-negative-rsi-20261021-v1/`保存授权、计划、A–G日志、学习store、五次学习请求/响应、审核、两次局部worker恢复及汇总。每个run在`.local/script-motif-experiments/<run_id>/`保存manifest、源码与输入摘要、有效sidecar、结果；原事件、输出和费用在相应`.local/web/runs/<run_id>/`。原材料、密钥、完整报告和原始轨迹不提交Git。

复现沿用[自动学习接口](../interfaces.md#可选-negative-提示学习独立私有实验)。在项目环境配置已有私有来源/检查点及store后运行：

```sh
node scripts/project.mjs python scripts/run-script-motif-experiment.py \
  --real-model --mode shadow --report-evidence \
  --source "$PAPER_RSI_SOURCE" --prompt "$PAPER_RSI_PROMPT" \
  --reuse-checkpoint "$PAPER_RSI_CHECKPOINT" --preserve-recovery-structure \
  --recovery-goal-scope "$PAPER_RSI_GOAL" \
  --script-config "$PAPER_RSI_SIDECAR" --learning-store "$PAPER_RSI_STORE" \
  --budget-usd 0 --max-output-tokens 32768 --max-seconds 45
```

此命令需要已有不限额实验授权；本记录不改变公共产品额度。macOS沿用`SSS_LOCAL_SCRIPT_EXPERIMENT=1`及项目Python/字体环境。不是生产自动配置入口。

## 真实结果与全部失败

| 任务 | 原生结束状态 | Agent请求 | 输入Token（命中 / 未命中） | 输出Token | 保守估费USD | 提示送达 | 实际报告 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| A | HTTP502失败 | 14 | 401152 / 25047 | 13046 | 0.108351 | 0 | 无 |
| B | API流失败 | 29 | 952960 / 25641 | 16418 | 0.118161 | 0 | 无 |
| C | 完成 | 36 | 1577344 / 29893 | 36472 | 0.062198 | 2 | PDF，7页 |
| D | 完成 | 53 | 2965376 / 40986 | 45871 | 0.085133 | 3 | PDF，7页 |
| E | 45秒局部取消 | 6 | 115200 / 19250 | 10609 | 0.095479 | 0 | 无；发现组件回退问题 |
| F | 45秒局部取消 | 8 | 198656 / 23050 | 11172 | 0.021513 | 1 | 不验收交付 |
| G | 45秒局部取消 | 11 | 324096 / 24461 | 11932 | 0.023601 | 1 | 不验收交付 |

1. A/B虽然最终因传输失败，先前的明确结构错误仍自动进入Negative历史，没有被任务未完成状态丢弃；任务失败本身未变成模式。
2. B结束的首次学习请求HTTP400，未发布库。提示词补充JSON模式标识后，局部worker恢复成功，1次生成/1次独立审核；这是**人工触发的局部恢复**，不能当作自动触发证据。旧400响应正文未保存，不能完整复核服务端拒绝原因；后续已增加有界HTTP错误诊断。原失败round、保留预约和原始summary均保留。
3. C加载局部恢复版本`297f2816…`，实际提示2次。C结束自动编译、认证、发布`5da69dc7…`，同证据审核缓存命中、学习请求0；D精确加载该版本并实际提示3次。
4. D的新失败观察还覆盖了错误的“8节改成1节”尝试。任务结束自动重新生成/独立审核建议并发布`a570ada2…`，学习2请求；同时既有Positive编译器从正常原生轨迹发布12个算子。这不等于12次执行、跨论文复用或降本。
5. E解析到D指针，但Positive匹配器因缺少Embedding地址抛出`Invalid URL`，整个Runtime回退，**没有达到loaded，也没有提示**。最初误以为空库，实际查明含12个正面算子，诊断已纠正。修复为组件隔离，补空库/非空库/保留cache catalog回归。
6. 修复后对真实轨迹实际重编译并通过当前loader认证，第二次局部worker恢复新增学习请求0；没有只替换旧库hash。F加载`658837a0…`，正面匹配器独立回退，Negative提示1次。F取消后自动发布`a21a7de1…`；G加载相同digest、触发任务确为F，当前失败后再次提示1次。F/G记录事件均含实际学习建议，最终源码摘要与运行快照逐项相同。

C/D有工具交付验收及实际PDF文件，不称科研事实独立合格：没有重做文献检索，也没有对报告做盲评或逐页视觉验收。C/D在最终组件隔离修复之前；最终F/G只做局部投递检查，没有冒充修复后完整恢复验收。D仍尝试过不合法的单章重组；提示不能保证不犯错，其最终说明还保留了旧阶段叙述。A的通用summary把解压出的原论文图片PDF识别为PDF交付，本记录按实际`outputs/documents/.../paper-review.pdf`核对，A计无报告。

runner到summary墙钟A–G分别约90/115/160/255/60/60/56秒，包含启动、上传、学习等待，未含安装；学习时间另保存在各lineage中。A/B原生duration与runner墙钟不一致，两种原值都保留，本轮不据其做时延收益推断。

## 总账与收益边界

- Agent：157请求，输入6723112（KV命中6534784、未命中188328），输出145520；保守估费USD0.514436304。
- 学习：5请求（1次400失败、两组生成/审核），已知输入3274、输出382；已知观测费用USD0.001440600，保留失败预约后估费USD0.004753800。两次手动worker恢复单列；第二次未新增模型请求。C/F/G同证据复用审核，均新增学习请求0。
- 本轮全部：**162请求，保守估费USD0.519190104**。有完整用量的观测费用合计USD0.271771704；未知或待结算预约未释放。新增用量未知3笔（两个Agent传输失败、一次学习400），E另有1笔pending，旧3笔继续保留。
- 既有累计5756请求/USD9.906226032继续计入；新累计**5918请求/USD10.425416136**。这是代理估费，不是供应商账单；V100历史和旧待核项目未完成账单核对，不清零。

没有重跑Baseline，也没有把A/B失败和C/D成功的不同路径当作配对对照。E/F/G仅验证投递，不能与完整恢复共用质量或费用分母。当前没有整次请求skip或自动早停；**机制闭环支持，净降本不支持**。人工开发、检查和本地计算时间未货币量化。

## 回归、限制与下一步

协议诊断覆盖owner/来源漂移、重复事件窗口、合成调用、拒绝/不完整审核、审核缓存、保留旧库、Negative-only/混代指针、强制prompt权限及可选Positive故障隔离。确定性测试与模拟模型只作诊断，真实结论来自上述DeepSeek任务。

最终Python完整1359通过/213跳过；相关Python35、Node34定向通过。首次完整Node1203通过/5跳过；加入组件回归后的完整Node曾有1项MCP子进程5秒期限失败（status:null），单独复跑7项通过、约0.5秒，未修改测试或超时。最终停止真实任务后重跑完整Node，1206通过/5跳过（64.75秒）；并行负载相关仅为推测，原失败未删。日志在私有`negative-learning-node-final-20261021.log`。smoke与motif:check通过，均无模型，仅macOS实测，不宣称Windows验收。

目前只验证一种结构错误家族和同论文不同恢复候选，不是跨场景自发因果学习。自动学习尚不产生执行失败谓词或早停权限；结构匹配来自明确失败条件，未在本轮扩展Embedding选择。正面匹配器在最终缺少Embedding的局部任务中主动停用，不能据算子数量主张其接管收益。

下一步若研究降本，应在这条已接通的轨迹上检查提示后为何仍重写整份参数/报告、能否交接必要局部修订；先做局部验证，不重复完整Baseline，也不据新增库数量宣称收益。当前小点收口，未推送、新建PR、合并或部署。
