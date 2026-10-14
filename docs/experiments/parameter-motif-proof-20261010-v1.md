# 参数化读取与并行查询局部证明

- 实验 ID：`parameter-motif-proof-20261010-v1`，2026-10-10，Codex。
- 问题与假设：旧原生诊断编译器以完整调用/输出/文件版本哈希分组，23 候选各仅出现一次。将参数与具体证据从结构身份分离，在明确选定输入后，Runtime 是否能完成独立证据节点的调度与汇合，并跳过整次真实模型请求？反例为影子预测不覆盖输入、结果未验证、工具/来源变化仍执行，或代理请求未实际减少。
- 类型：真实历史轨迹挖掘 + 新真实局部前瞻验证。同一私人稿件，不是跨论文泛化，不是完整报告对照。只验证读取/网页获取，暂不评价整份论文核验质量。

## 训练与结构

训练来源为 `paper-reference-five-native-two-motif-20261010-v5` 的 baseline-01/02/03；04/05 仅记录留出观察，不用于选择原型。`parameter_motif_compiler.py` 从实际成功根会话调用抽取有文件快照的完整 `read` 参数槽，以及 arXiv 页面 `web_fetch` URL 参数槽。工具和 URL 模板来自实际调用；执行契约为人工实现的受限协议，不把任意历史脚本直接求值。

| 原型 | 训练成功实例 | 训练运行 | 留出成功实例 | 历史同类并行批次 |
| --- | ---: | --- | ---: | ---: |
| 完整本地文本读取 | 2 | 01、03 | 4（04、05） | 0 |
| arXiv 页面获取 | 17 | 03 | 0 | 5 |

参数/文件版本/输出字节保留为每次执行的证据，不再参与原型身份。重复频次作为支持度，不再通过原生诊断的 2+1 精确 body 门槛授权。本次只有显式版本化输入绑定可授权执行；scope 为 `parameterized_continuation_probe`，不能加载为生产科研决定认证库。

图为受限的 `foreach selected_items -> collect -> all_selected_items join -> semantic_handoff`。这是基于只读无写契约的可交换调度算子；查询有历史并行见证，读取的并行性由契约判断。它没有从历史轨迹学出完整工作流拓扑，也没有学习自动决定要读哪些文件/查哪些文献。

## 公平条件与配置

每个局部任务在 baseline、shadow、execute 使用完全相同题面、选定输入集合与 native 工具。题面明确先读取绑定文件，再完成选定证据收集；三组都能读取该文件。这是控制权移交的受控证明，不能当成未提示流程的原生完整论文基线。

文件来自已有 ZIP 字节，解压子目录改为 `inputs/renamed/`，选定项顺序反转；查询标识符从训练成功调用中选择，并要求存在于同一原始 Bib 来源。没有把旧网页答案复制给模型；各组都实际查询网页。题面、工具/输入/配置/代码哈希和逐请求数据保存在每条私有运行下。

- 环境：服务器 Ubuntu、Node 22.23.3、项目 Python 3.10.8、Harness 0.1.5-rc.3；模型 `deepseek-flash`，provider `deepseek-official`，`reasoning_effort="off"`；关闭压缩；单次输出 4096；无请求次数上限。
- 权限：仅既有私有副本非沙箱实验授权，不修改原稿、不写外部应用、不投稿。插件复用共享 `attachMotifInterceptor` 与标准工具流，不修改 Harness 核心。
- 预算：起点累计代理估费 3.84521046 美元。新增最多 1 美元，本轮冻结累计上限 4.84521046，另保留此前 5 美元总封顶。账本包含所有此前失败/重试/未结算预留；新任务、严格守卫重测不重新计零。
- 初版六次运行后补强网络守卫，要求真实工具报告 HTTP 200、页面自身 arXiv ID、标题与作者字段；原代码保存在私有 `code-history/first-pass-code.tar.gz`。随后只重测查询 shadow/execute，旧记录不覆盖。前六次 manifest 未自动采集 commit/dirty/patch 摘要及全部共享代码哈希；有本轮代码摘要、原 patch、运行配置和执行代码归档，缺项不声称已全采集。严格重测补齐这些字段。

## 真实运行结果

| 局部任务 / 模式 | 实际 API 请求 | 工具调用 | shadow 验证项 | verified skip | 新增代理估费（美元） | 耗时（秒） |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| read baseline | 3 | read 3 | 0 | 0 | 0.004151796 | 6.54 |
| read shadow | 3 | read 3 | 2 | 0 | 0.004272696 | 6.98 |
| read execute | 2 | read 3 | 0 | 1 | 0.004013280 | 5.41 |
| query baseline | 3 | read 1、web_fetch 2 | 0 | 0 | 0.004599996 | 8.73 |
| query shadow（初版） | 3 | read 1、web_fetch 2 | 2 | 0 | 0.004506060 | 7.62 |
| query execute（初版） | 2 | read 1、web_fetch 2 | 0 | 1 | 0.004381848 | 10.75 |
| query shadow（严格守卫） | 3 | read 1、web_fetch 2 | 2 | 0 | 0.004576296 | 8.73 |
| query execute（严格守卫） | 2 | read 1、web_fetch 2 | 0 | 1 | 0.004265580 | 6.44 |

全部 completed；没有未验证的 bypass。两类主要 execute 各跳过一整次模型控制请求，真实 Provider 仍参与首次输入理解和最终解释。全部选定输入都得到实际工具结果；shadow 每项验证，execute 等全部结果通过才计整个 batch 的 skip，乱序返回不影响汇合。

运行控制器审阅交付：读取组文件声明/标题/覆盖项一致，查询组两篇页面标题/覆盖项一致。其余解释没有盲评；未验收完整论文报告，没有人工修订计时。本轮总新增代理估费约 0.03476757 美元，含历史累计约 3.87997803 美元，其中仍有历史未结算保守预留；实际账单未知。局部费用差异及耗时有波动，只主张实际请求减少，不外推总体降本比例或端到端收益。

两端私有备份压缩包 SHA-256 一致：`32fb1551f7dc22cad5d0528ce8cf2b0ecc38ecbed57db0fcf2fe903749132845`。八次运行逐请求账本计数与控制器 actual_requests 一致；所有题面 SHA 相同，library 摘要为 `e1419f52521389a6d1e63231989af2dbbae221bbfd9b1e8cd2c422e16ec7ab5e`。

| 对照 | 输入 token 总数 | 缓存命中输入 | 未命中输入 | 输出 token |
| --- | ---: | ---: | ---: | ---: |
| read baseline | 26775 | 15616 | 11159 | 592 |
| read shadow | 26758 | 15616 | 11142 | 697 |
| read execute | 18992 | 7680 | 11312 | 478 |
| query baseline | 28245 | 15616 | 12629 | 598 |
| query shadow（严格） | 28242 | 15616 | 12626 | 579 |
| query execute（严格） | 20485 | 7680 | 12805 | 315 |

少掉的请求主要减少缓存命中输入；未命中输入并未随请求数同比降低。因此不能把 3→2 的请求变化等同三分之一费用节省。每组一次，未做统计显著性判断。

## 守卫与诊断验证

运行时分别绑定 Session、冻结用户题面、库摘要、绑定文件摘要、输入来源字节、真实工具 schema/顺序和独立 item 身份。本地读取核对完整行内容及前后字节；网络获取核对实际 URL、HTTP 200、页面 ID/标题/作者字段，不使用历史网页内容哈希，也不认证科学判断。结果缺失不提前汇合；失败计 unverified，后续回模型。

免费测试：本机 `npm test` 最终 170 Python / 64 Node 通过；服务器编译专项 16 项、当前参数 Runtime 13 项通过。覆盖来源/绑定/schema/工具顺序/会话变化、完整读取、并行结果乱序、部分或失败结果、不跳过请求的 shadow、网络错误状态、错误页面 ID、缺作者字段及超时。最初本机全量因沙箱不允许回环监听失败 4 项；允许免费测试使用回环后全部通过，没有删测试。

最终服务器全量同为 170 Python / 64 Node 通过。同步测试导入行曾因 shell 引号丢失导致 Node 语法错误；修复该行后通过，失败日志 `final-free-tests.log` 和成功日志 `final-free-tests-fixed.log` 均保留，没有新增 API。最后预览核实既有累计上限仍为 4.84521046，没有随重测提高或重置额度。

## 复现与交接

```sh
source .local/remote-env.sh
node scripts/project.mjs python scripts/parameter-motif-proof.py --phase preview
# 依赖服务器保留的五条私有轨迹；新编译在既有记录冻结后不覆盖重编译：
node scripts/project.mjs python scripts/parameter-motif-proof.py --phase compile
# 仅未运行的实验执行，已存在 run 会拒绝覆盖；真实 API 授权和冻结预算仍须有效：
node scripts/project.mjs python scripts/parameter-motif-proof.py --phase run --call-model
```

输入契约为 `schemas/parameter-motif-binding.schema.json`；动态安全校验在 TypeScript 中。私有根 `.local/paper-reference/parameter-motif-proof-20261010-v1/` 含 library、contracts、compile-summary、effective-budget、各运行绑定/题面/requests/ledger/events/审计/answer/metrics 和实际代码历史。原始稿件、网址明细和响应不提交。

结论：在明确选定输入、稳定工具契约的这些局部条件下，支持 Runtime 代替一次并行收集调度，实际请求 3→2。尚不支持自动匹配完整论文流程、脚本复用、编译修复、多层依赖 DAG、子 Agent 汇合、跨任务收益或生产认证。下一步在真实论文流程中让模型产出一次可审阅的选定输入/目标绑定，再测 Runtime 能否连续接管多个已编译节点；不能把局部预选任务冒充已完成全自动 Motif 挖掘。
