# 论文 RSI 十任务与前瞻 shadow（第一轮完成）

- 实验 ID：`paper-rsi-overnight-20261011-v1`；2026-10-11。
- 用户持续授权累计费用上限提高到 8 美元，包含历史失败、重试和恢复；新 execute 继续暂停。
- 启动时累计代理估费 4.86830662 美元，剩余上限约 3.13169338 美元；这不是实付账单。

## 问题与划分

验证从正常工具轨迹编译的局部参数流和并行批次，能否在新任务请求发出前预测完整纯工具响应。预测只用于 shadow，所有模型请求实际正常执行，不删除模型正文或注入工具结果。

目前只有一篇私有论文，十个任务分别为完整稿、摘要稿、两个引用子集、增量引用范围，以及缺失键、重复条目、错误标识、错误年份、错误 DOI 诊断副本。不能称为十篇独立论文，也不能据此证明完整论文修订流程的泛化。

前三条正常基线训练第一版；后续任务使用事先冻结的库评测，该任务评测结束后才把其基线加入下一版。只从 baseline 学习，shadow 结果不进入训练。保留全部预测、错误分支、无预测及伴随文本，不把可读工具数当作跳过请求数。

## 变更与配置

- `scripts/paper-rsi-overnight.py`：任务生成、正常 baseline、冻结编译、真实 shadow 与逐请求评分。
- `src/adapters/paper_flow_shadow_compiler.py`：从已完成且范围/来源检查通过的正常轨迹挖掘只读节点、参数边和并行批次；不编译语义写操作。
- `src/adapters/dsh_paper_flow_shadow.ts`：公开 Harness 请求钩子，在调用真实 LLM 前记录预测，检查任务、工具 schema/顺序、代码、来源版本、当前句柄和报告摘要；无执行器。
- 新 MCP 能力读取 arXiv 正式版本线索与 Crossref 著录候选；新 `read_current_triage` 只读当前报告，用于编辑失败后的恢复。候选匹配和版本选择仍由模型判断。
- 这轮使用模块化工具，保留基线与 shadow 相同的工具、顺序、提示词模板和输出要求。要求工具阶段不输出仅描述下一步的旁白，实质判断写入报告；不能将此条件的成绩直接归因于 Motif，不能追改旧条件的结果。
- 模型 `deepseek-flash`、`reasoning_effort=off`、8192 输出、无请求次数上限、无压缩、已授权非沙箱终端；只处理私有副本。
- 公共代码基点 `2368235f274329be6227a8393b850633cb943da4`，存在未提交修改；每次运行 manifest 保存实际文件摘要。
- 原始轨迹、任务和配置位于忽略的 `.local/paper-reference/paper-rsi-overnight-20261011-v1/`，不进入 Git。
- 新预算记录摘要 `a7c0dab9b74bc7c0e9475cf6a056613896e53cab7dd3268b193dc13157067031`，旧授权快照保留。

## 当前状态

已完成两端249 Python/109 Node回归、真实元数据MCP预检（11工具，5对arXiv、5次成功Crossref查询）、10条真实baseline和7条冻结库shadow；全部completed且范围/结构/来源通过，语义未盲评。库逐轮从7增至8候选，没有执行候选或实际跳过请求。

初始化发现案例 ID 必须用下划线，生成失败的私有目录保留为 `prepare-failed-cases`，修正案例名后生成十份输入；此失败没有模型费用。

## 复现入口

服务器在项目目录加载 `.local/remote-env.sh` 后：

```sh
node scripts/project.mjs python scripts/paper-rsi-overnight.py --phase preview
node scripts/project.mjs python scripts/paper-rsi-overnight.py --phase baseline --case t01_main --call-model
node scripts/project.mjs python scripts/paper-rsi-overnight.py --phase compile --version v01
node scripts/project.mjs python scripts/paper-rsi-overnight.py --phase shadow --case t04_missing --library .local/paper-reference/paper-rsi-overnight-20261011-v1/libraries/v01/library.json --call-model
```

运行 ID 不允许覆盖。编译在 baseline 完成后执行；第一次冻结须先完成前三个训练任务。

## 结论与边界

已观察：严格整请求24/112=21.4%，最高33.3%，最低13.6%。43次预测中24次严格匹配、12次工具匹配但含文本、7次下一操作不同；另69次无预测。结构校验不认证文献判断，没有盲评不能比较合格总成本。真实跳过0。库从7增至8后局部覆盖趋于停滞，后续需新增有正常见证的查询恢复与产物恢复节点，不能重复同库execute。

API 契约来源：[arXiv 官方 API 手册](https://github.com/arXiv/arxiv-docs/blob/develop/source/help/api/user-manual.md)、[Crossref 官方 REST API](https://github.com/CrossRef/rest-api-doc)。DOI、journal reference、comments 只是版本线索；标题查询返回候选不等于身份确认。


## 第一轮实测

| 任务变体 | baseline请求 | shadow请求 | 严格整请求 | 比例 |
|---|---:|---:|---:|---:|
| t04_missing | 18 | 15 | 3 | 20.0% |
| t05_duplicate | 14 | 19 | 4 | 21.1% |
| t06_wrong_id | 13 | 19 | 4 | 21.1% |
| t07_wrong_year | 7 | 12 | 4 | 33.3% |
| t08_wrong_doi | 47 | 14 | 3 | 21.4% |
| t09_subset_b | 14 | 11 | 3 | 27.3% |
| t10_incremental | 22 | 22 | 3 | 13.6% |

10条基线共171请求，7条shadow共112请求，共283个实际请求。新增代理估费约0.32038246美元，累计5.18868908/8美元，账单未知；成本包含失败编辑、重试和恢复。shadow全部调用模型，不是节省账单。

严格比例分母保留最终回复、模型写/改报告、全部网页查证和恢复；不排除困难任务或有文本的响应。冻结版本从v01至v08，训练数量3至10，候选7至8；新任务使用纳入其baseline之前的旧版库。第一轮数据已同步本地，原始材料不提交Git。

## 质量抽查与反例

- 有报告从Crossref返回404推出DOI不存在/不可解析。这个推论不成立，应该查DOI注册机构/解析来源。Crossref官方API提供独立的注册机构查询，不能将单一库未收录当作不存在：[当前API文档](https://api.crossref.org/swagger-ui/index.html)。
- 有报告将BibTeX键名里的年份当著录错误；键名是内部标识，不是发表年份证据。
- 有报告在未确认正式发表版本时，把预印本统一列为P2；这不足以成立版本修正要求。
- 某报告用一个活动缺失键承载未引用重复条目的说明，结构校验虽然通过，事实对应仍不正确。
- 错误ID任务中出现6次不同下一操作预测，反复读取后的状态不等于重新执行旧续接的理由；后续加入已完成节点的状态守卫。

这些是质量未验收的具体原因。数据不能用于证明合格总成本下降，也不能发布为自动执行证书。

代码历史快照保存在私有`paper-overnight-code-v1.tgz`，库/轨迹/请求摘要保留在实验根。后续第二轮改了工具/提示/状态规则，第三轮仅改离线挖掘与shadow观察器；应单独报告，不能追改本轮成绩。
