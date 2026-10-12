# 真实轨迹驱动的 RSI 工具发现与生成

- 实验ID：paper-rsi-trace-tools-20261011-v3；2026-10-11；Codex接入通用基础设施，DeepSeek选择工具目标并生成算法。前两版失败保留在各自私有实验目录。
- 问题：能否先读正常任务轨迹，再由模型决定值得内化的操作、输入输出和实现，而不是由开发者指定一个检查器让模型填代码？源重放不一致、输入依赖不足、生成程序不能独立重放或无法经MCP调用，均否定对应环节完成。
- 已观察：轨迹读取→自主提案→生成/开发修复→未见源反例验收→冻结→实际MCP加载调用跑通。新增正常论文任务、Motif编译和Shadow尚未运行；实际跳过0，不能据此声称减少模型调用。

## 真实来源、目标与验收范围

两条正常Shadow Session来自同一论文的既有阶段，模型照常执行，未启用execute。私有来源是 `paper-rsi-sequential-20261010-v1/runs/continuation-shadow-round-{2,3}-shadow`。根Session共20次bash记录全部保留，包括不支持的命令；只有两个Python heredoc源操作能用当前有界解释器复现历史stdout。退出码缺失不冒充成功，传输isError=false不是shell成功证明。

有界AST解释器只读登记内存文件，不执行旧shell、网络或任意Python。一个源打印dict时仅允许键顺序差异，其余结果保持严格比较。当前工作快照能复现观察输出，不能证明任意历史中间版本都已恢复。

DeepSeek自行选择round-3源中的五个输出，工具名为 `triage_catalog_coverage`：

| 输入投影 | 用途 |
| --- | --- |
| triage.references的key/arxiv_id | 当前报告条目及标识符 |
| catalog.query_items的item_id/id/source_path | 当前查询集合与条目路径 |
| catalog.cited_records的key/record_path/arxiv_ids | 路径到引用键及目录标识符的映射 |
| triage.citation_issues的kind | 当前问题类型序列 |

输出为 `keys_match_query_items/missing/extra/arxiv_id_mismatches/issue_kinds`。模型决定范围、名称、字段及算法；通用编译器按样例推导结构schema。没有内化文件哈希、完整必填字段、事实核验、正式发表版本判断或整个论文流程。当前schema保留原目录结构要求，例如查询项需同时有id、item_id和source_path；新场景须适配投影或重新编译，不能直接称为通用题录标准。

源程序产生反例的固定方式为更换字符串标识、删除/重复/倒序数组、置空首项字段；期望值来自原AST，候选程序不生成自己的答案。先冻结三个开发样例及12个未见留出样例，再生成实现；留出不反馈给模型修复。按选中输入去重后共23个有效case；两个源程序自身无法处理的反例记录为拒绝，未伪造答案。相同投影输入对应不同源输出则拒绝整个提案，不能静默删冲突。

三个开发样例通过；12/12未见留出通过；实际MCP initialize/list/call的12/12通过，名称、schema、候选摘要与库字节一致。随后对全部23个有效case复核一致，包含开发/留出，不另称23个独立任务。认证范围为**所选输出的同源反事实**；不是独立论文泛化、形式证明、论文语义质量或整次模型请求替代。

## 失败、修复与各方提供的内容

| 版本 | 真实请求 | 新增代理估费（美元） | 结果与处理 |
| --- | ---: | ---: | --- |
| v1 / learn-v01 | 72 | 0.085653060 | 最终提案只回显scope却夸大描述；Cordis跨realm对象又被适配器误拒。没有合格程序，不发布 |
| v2 / learn-v02 | 74 | 0.066640704 | 多个提案JSON多括号、嵌套包装错误，且把数组字段投影用在整个对象；未接受提案，不发布 |
| v3 / learn-v03 | 162 | 0.122146236 | 自主选择五项输出，57次Cordis定义、36个已安装候选版本；模型修复作用域/表达式/输出错误后通过开发、试用、独立验收 |
| 合计 | 308 | 0.274440000 | 无新execute、无新增Shadow、实际跳过0 |

基础设施修复跨realm提交边界、提供字段类型结构，简化提案格式并返回具体错误；增加纯回显/常量拒绝、投影依赖充分性、schema与真实数据一致检查。没有人工修补最终模型程序或把留出结果用于模型修复。最终成功试用有output摘要；冻结入口现要求成功试用，错误trial不能提供通过见证。

开发者仍提供通用解释器、源重放器、输入权限、预算及独立验收机制，新增四个通用算子sort/split/at/keys。模型提供领域目标、参数投影、输出范围、工具算法和修复版本。工具算法自动生成不代表上游Cordis VM安全隔离；本轮仅在已授权服务器独立学习进程使用。不可信任意代码的自主运行/环境搭建尚未开放。

## 配置、复现与数据

- 分支/基底：feature/paper-submission / 2368235f274329be6227a8393b850633cb943da4；未提交/未推送，保留其他同学工作。源码包v01/v02/v03及每次运行manifest保存实际学习代码摘要。最终冻结试用守卫是在学习结束后收紧，未重跑或追改真实模型记录；生成成功试用见证已人工核对，验收结果不依赖失败trial。
- 服务器 `/root/autodl-tmp/jjy`，加载 `.local/remote-env.sh`；Linux/Node22.23.3/Python3.10.8/Harness0.1.5-rc.3/Python SDK0.1.5rc1。
- 模型deepseek-flash，reasoning_effort=off，原生Cordis工具模式；输出8192，无请求次数限制，关闭压缩和自动LLM重试/标题；SDK等待上限600秒，host VM单次5000ms；独立DSH_HOME。累计授权8美元沿用旧账本，不按实验ID归零。
- 源bundle摘要 `0e9ae4d8356a2ccdd8c95b60f0d0f625c62238cb7e94385498f11348c7b98674`；候选摘要 `610ce5ded7c551e7ab90da8fd9559b7e6c4efa949a0652b7bc2b900b528d19c6`；冻结manifest `a84415d2cae2b2cc92e9bd48b19423a5b34e32982638ad2369dc4ab4cb6d4bef`。
- 私有目录 `.local/paper-reference/paper-rsi-trace-tools-20261011-v{1,2,3}/`。各run保存manifest/config/patch/prompt、逐请求、事件、账本、候选版本及开发审计。v3保存accepted-proposal、oracle反例、训练/留出摘要、frozen-tool、Cordis定义、heldout-validation、mcp-validation、all-source-validation及summary。原始资料与日志不进Git；两端结果已同步，服务认证路径仍为服务器私有路径。
- [公开程序与合成阅读样例](../../examples/rsi-tools/trace-coverage-v1/README.md)保留模型原程序及相同候选摘要，省略私有认证，不是可直接加载的冻结库。

```sh
source .local/remote-env.sh
node scripts/project.mjs python scripts/paper-rsi-trace.py --phase preview
# 已有v3结果不可覆盖；新学习需显式换experiment/label，不得重置累计预算。
node scripts/project.mjs python scripts/paper-rsi-trace.py --phase prepare --experiment .local/paper-reference/<新实验ID>
node scripts/project.mjs python scripts/paper-rsi-trace.py --phase learn --experiment .local/paper-reference/<新实验ID> --label learn-v01 --call-model
node scripts/project.mjs python scripts/paper-rsi-trace.py --phase freeze --experiment .local/paper-reference/<新实验ID> --label learn-v01
node --experimental-strip-types scripts/check-trace-rsi-mcp.mjs \
  .local/paper-reference/paper-rsi-trace-tools-20261011-v3/frozen-tool.json \
  .local/paper-reference/paper-rsi-trace-tools-20261011-v3/heldout.json
```

## 成本、验证与结论

学习三轮耗时172.046/146.323/279.661秒，共约598秒；不含环境适配、编程、同步和人工审阅。三轮合计缓存命中输入17,049,600、未命中输入204,812、输出92,249 token。费用含失败与修复：本轮新增代理估费0.274440美元，含历史累计5.976450/8美元，余额上界2.023550；实付账单未知。人工修订和开发维护未计价，不视为零成本。程序结构经人工阅读，文献语义质量未评审。

免费回归：两端npm test为265 Python/139 Node通过；已有无模型smoke通过。源重放/权限/错误/版本/跨realm回归保留；公开两例诊断通过。模型行为验收是真实API，没有mock代替。完整MCP可只用Node运行，轨迹准备与实验预算仍依赖Python；Windows和独立插件分发未验收。

这轮支持“先有真实轨迹，再让DeepSeek自主提出并生成一个可保存、可调用的结构工具”。不支持所有bash均已自动工具化、完整论文验收、实际调用下降或长期降本。下一步将冻结工具加入正常论文任务，收集真实使用与恢复轨迹，再挖掘局部衔接并冻结新Motif，在后续任务Shadow验证；生成工具本身不能被算成一个已认证的Motif，也不能把308次学习请求从成本里拿掉。
