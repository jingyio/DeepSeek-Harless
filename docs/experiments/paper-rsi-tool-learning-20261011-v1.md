# DeepSeek 原生 Cordis 工具学习与局部 Shadow

- 实验ID：paper-rsi-tool-learning-20261011-v1；日期：2026-10-11；Codex适配，真实DeepSeek生成检查算法。
- 问题：Harness能否自行编写/测试/修复工具，保存后供下一任务复用，再从正常调用轨迹挖掘局部Motif？独立样例失败、后续不可调用或无真实衔接见证，否定对应环节已完成。
- 已观察：生成→独立结构验收→冻结→MCP调用→轨迹编译→前瞻局部预测均跑通。未证明减少模型请求或实际总成本。

## 任务、训练与验收

学习使用3个公开合成开发样例，独立验收11个不同输入：空引用、新标识、漏项、重复、范围外、来源/范围变化、无效数组/条目、顺序、标识冲突、空报告。验收样例未发给模型、未用于修复；只认证有限结构行为，不是任意输入正确性证明。

后续三个任务使用夜间v2同一论文的主稿、摘要、子集报告，分别复制后注入“删一个条目/重复另一个条目”。原报告与原稿不改；不是发现了原生报告新错误，也不是三个独立论文/科研决定。仅修复结构，缺失事实保持待核验，不联网、不生成最终PDF、不判断会议合规或真实性。语义质量未盲评，人工修订时间未测量。

前两个正常任务用于挖掘，第三个在冻结图后前瞻Shadow。三任务用相同题面、MCP/schema/顺序和生成工具版本；Shadow只加观察器。未与旧工具集作公平成本对照，无新增execute。

## 谁在学习、怎样保存

Harness0.1.5-rc.3显式加载原生Cordis插件。模型通过`cordis_define`写host包装，把自己生成的JSON纯数据程序交给`sssPaperRsi.install`，再自测和修复。最终学习会话包含31次Cordis源码定义、92次真实模型请求；失败调试全部保留。候选算法与修复由DeepSeek提供；契约、开发/验收样例、有界解释器、文件访问边界及认证门槛由开发者提供。这是程序/能力库自改进，不修改模型权重；尚未实现任意历史bash自动发现目标并生成通用可靠MCP。

工具输入是报告、源码取得的期望配对和来源版本，输出漏项/范围外/重复配对及版本/范围/结构标志。TS仅解释受限JSON表达式，不求值生成JS；原生Cordis动态host仍有较宽能力，上游VM不是安全边界，不能直接向不可信用户开放此学习进程。

冻结工具通过TS MCP的`read_report`、`write_report`、`check_report_structure`供模型调用。保存副本需当前摘要，来源/代码变化或符号链接拒绝。write→check从真实正常轨迹挖掘，不手填DAG；工具程序与Motif图分别保存。

## 有效配置与复现

- 服务器：`/root/autodl-tmp/jjy`；Linux、Node22.23.3、Python3.10.8、Harness0.1.5-rc.3、Python SDK0.1.5rc1。学习早期manifest未自动采集环境版本，另补录，不追改原记录。
- 分支/基底：feature/paper-submission / 2368235f274329be6227a8393b850633cb943da4；未提交/未推送，其他同学已有改动保留。逐运行manifest记录代码哈希。编译从“纯消息才能提供见证”修正为“实际调用支持局部见证，旁白另记”，不改原消息或严格跳过标准。
- 模型：deepseek-flash；reasoning_effort=off；原生工具模式；输出8192；请求次数不限；关闭压缩、自动LLM重试/标题；独立DSH_HOME；已授权danger-full-access，仅副本实验。
- 预算：原夜间8美元授权、同一全局锁/历史账本；原累计5.61286852美元，不按新ID重置，历史失败/预留继续累计。代理估费未核对实付账单。
- 私有数据：`.local/paper-reference/paper-rsi-tool-learning-20261011-v1/`。逐run保存manifest/config/requests/events.jsonl/cost-ledger.jsonl；生成/认证见`frozen-tool.json`、`provenance.json`、`cordis-definitions.json`、`heldout-validation.json`；图见`shadow-library.json`，前瞻预测与结果见`runs/shadow-subset/work/shadow.jsonl`、`shadow-score.json`。原始轨迹/私人报告不进Git。
- 候选摘要：`c49d9f9e942b5e3fbb1ca03d330ddbdf0bdccd6064586f7d04b0447a76192418`；冻结工具manifest：`673c5434acdf0d70742c4817b8d06eb7a197d68245a247ed6a9ee53f71f051ff`。

```bash
source .local/remote-env.sh
node scripts/project.mjs python scripts/paper-rsi-tool-learning.py --phase preview
# 以下ID已有结果不能覆盖；新付费run须用新label，旧费用仍累计。
node scripts/project.mjs python scripts/paper-rsi-tool-learning.py --phase learn --label learn-v02 --call-model
node scripts/project.mjs python scripts/paper-rsi-tool-learning.py --phase freeze --label learn-v02
node scripts/project.mjs python scripts/paper-rsi-tool-learning.py --phase baseline --case t01_main --label baseline-main --call-model
node scripts/project.mjs python scripts/paper-rsi-tool-learning.py --phase baseline --case t02_abstract --label baseline-abstract --call-model
node scripts/project.mjs python scripts/paper-rsi-tool-learning.py --phase compile
node scripts/project.mjs python scripts/paper-rsi-tool-learning.py --phase shadow --case t03_subset_a --label shadow-subset --call-model
node scripts/project.mjs python scripts/score-paper-rsi-shadow.py .local/paper-reference/paper-rsi-tool-learning-20261011-v1/runs/shadow-subset
```

当前数据路径/训练case固定于这一诊断，依赖服务器私有夜间v2输入；不是新仓库无资料即能重跑的通用场景。默认只预览；冻结和编译免费；新程序不能重复拿已经用于修复的样例冒充独立认证。

## 结果、费用与失败

| 阶段 | 请求 | 新增代理估费（美元） | 结果 |
| --- | ---: | ---: | --- |
| learn-v01 | 0 | 0 | 启动失败：权限列表引用未注册rsi_trial；修复后保留原记录 |
| learn-v02 | 92 | 0.065134128 | 开发通过/工具实际调用成功；独立11/11后冻结 |
| baseline-main | 4 | 0.008767152 | 结构和来源通过，文献语义未评审 |
| baseline-abstract | 4 | 0.007020912 | 结构和来源通过，文献语义未评审 |
| shadow-subset | 4 | 0.008219340 | 结构通过，1局部预测匹配，但有非空模型文本 |
| 合计 | 104 | 0.089141532 | 实际跳过0 |

学习162.790秒，三个任务21.517/18.501/20.525秒；不含环境适配、人工审阅和同步。累计代理估费5.70201003/8美元，剩余上界2.29798997美元，实付未知。生成92请求占本轮主要开销，未验证长期摊销后的收益；开发维护与人工修订未计价，不能当作成本为零。

局部图`learned-check-ca8badc773cd`有两个成功write→check见证，来自不同Session/范围，保留同报告/来源/候选摘要及下一回复含文本的事实。留出第3请求预测无参数检查，实际检查结构通过：**局部匹配1次，严格整请求0/4，实际跳过0**。这不是25%调用节省；不能删旁白来改善指标。初次编译因文本拒绝纯请求见证，修正只生成局部候选，无执行授权。

免费回归：本机沙箱监听端口限制使4个已有测试失败；放开回环后252 Python通过。新增4项有界程序、MCP stdio、来源/摘要守卫和Shadow诊断通过；最终npm入口含新增项。服务器执行同等免费回归。模型行为验收均是真实API。

## 结论与下一步

工具目标、契约、样例和解释器目前人工提供，是这一轮的实施范围，不是RSI的能力上限。后续可由模型提出工具目标、生成契约/测试，乃至提出编译器、解释器和Runtime修改；再由独立资料、既有反例和后续任务验收版本。验收也可自动化，但被测候选不能自行放宽本轮合格标准、删失败样例或更改预算来宣称进步。

支持“DeepSeek Harness能生成/修复一个有界检查工具，保存后供后续任务调用”，支持真实轨迹为生成工具提供局部续接见证。不支持任意bash自动工具化、跨论文通用可靠性、完整论文修订验收、20%请求减少或实际降本；工具可靠性和整请求可跳过性分开评估。

下一步先审阅旁白：哪些承担事实解释/用户交付，哪些仅是调度陈述。丢弃或规则替代须有内容契约与质量验收，不能为指标直接删除。再接入长修订任务的缺证据/失败恢复，让模型学习新的有界工具目标；保留反例与生成开销，不继续重复同条件基线。
