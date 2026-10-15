# 活动引用工具链与真实 Harness 续接

- 日期/执行者：2026-10-10，Codex；`feature/paper-submission`，未提交、未推送。
- 问题：将重复读取、引用集合构建和哈希校验内化为只读 MCP 后，能否从正常轨迹学习更长的参数续接，减少完整模型请求。
- 类型：同一私人论文的主稿、短稿真实阶段任务；另有合成缺失/重复引用的协议留出。不是独立论文泛化实验，不是完整 PDF 报告或修订流程验收。
- 否定条件：漏项、越界、丢失原文/重复项、来源变化后继续执行，或在质量未评审时宣称合格降本。

## 实施与对照

`SSS_PAPER_CITATION_FLOW=1` 在原六个工具之后增加三个工具，默认工具集保持不变：

```text
pin_paper_citations(case_id) → source_id / version_sha256
read_pinned_paper_citations(source_id)
  → 活动引用诊断 / citation_id / version_sha256
read_pinned_citation_records(citation_id)
  → 原始 BibTeX / 哈希 / 缺失与重复 / required_reference_pairs
```

引用集合由当前活动稿件的字面 cite 得到，排除 nocite 和未活动旧稿。批次限64个引用键，句柄只在创建它的 MCP 进程有效；读取前后核验版本。标识列表由原文中的 arXiv 语法候选得到，明确不是真实性确认。保留全部原始记录、同键重复和缺失；不将 Bib 库索引冒充渲染编号。

工具实现是人工从正常 bash 行为提炼的底座，三节点调度结构必须从真实工具轨迹挖掘。Python 使用现有 witnessed-edge/chain 编译与留出认证；在线复用现有 TypeScript 论文插件和共享拦截器，没有新增 Agent 循环。未知程序、出版判断、修稿和最终解释仍交给 Harness。

`scripts/paper-citation-rsi.py` 默认仅预览，原生工具保留，MCP九工具及顺序在各对照组保持一致。没有 selection.json 协议；模型从 MCP 返回的证据继续。主稿训练、短稿训练、合成留出明确分别标识。认证范围仅 `protocol_diagnostic`，不进入普通生产插件或 Web，不并入原参数库第四版冒充学习进度。

## 第一轮失败保留

`paper-citation-rsi-20261010-v1/runs/collect-manuscript`：模型完成20请求，估费0.038822304美元；源码未变，但输出34条，期望15个原始 key/arxiv_id 组合，缺1、额外20。模型还运行环境检查与多次修补。不能将该结果计为合格。

v2 在工具输出明确 `required_reference_pairs`，题面要求精确对应，禁止重复扫描已取得的源码或无关环境检查。新提示适用于全部v2对照，不追改v1；v1费用继续累计。普通六工具被加入离线只读契约分类，避免将已批准的交错只读调用误作未知操作；任意 bash 仍是编译屏障。契约分类变化不改变模型工具集合和题面。

## 环境、预算与复现

服务器 `/root/autodl-tmp/jjy`，先加载 `.local/remote-env.sh`。模型 `deepseek-flash`，推理 `off`，输出8192 token，关闭压缩、不设请求次数上限。费用继续沿用冻结累计上限4.84521046美元；不得用新ID重置。真实数据、请求、事件、库和输出留在 `.local/paper-reference/<experiment>/`，不提交。

```sh
node scripts/project.mjs python scripts/paper-citation-rsi.py
node scripts/project.mjs python scripts/paper-citation-rsi.py --phase preflight
node scripts/project.mjs python scripts/paper-citation-rsi.py --phase collect --case manuscript --call-model
node scripts/project.mjs python scripts/paper-citation-rsi.py --phase collect --case abstract --call-model
node scripts/project.mjs python scripts/paper-citation-rsi.py --phase collect --case fixture --call-model
node scripts/project.mjs python scripts/paper-citation-rsi.py --phase compile
node scripts/project.mjs python scripts/paper-citation-rsi.py --phase evaluate --mode shadow --call-model
```

已存在的运行拒绝覆盖。execute 另需已有完整范围的成功shadow和至少两个候选；候选数量不是整次请求可跳过比例，执行结果复核及真实请求数另外统计。执行模式仍受任务、会话、题面、schema、来源版本和参数来源守卫约束。

## 当前已观察

- 免费真实 stdio MCP：主稿34键/34记录/15标识组合；短稿14键/14记录/5组合；留出2键、缺失1键、重复1键，原文2条；无模型请求。
- v2 主稿正常基线：completed，15请求，估费0.031752876美元，59.909秒；输出精确覆盖15项，来源未变。语义质量未盲评。
- 短稿基线：completed，16请求，估费0.026619552美元，156.014秒；5/5覆盖，来源未变。合成留出：completed，18请求，估费0.008485272美元，26.637秒；无arXiv项，范围检查通过，科研语义质量不计入验收。
- 编译得到一个三节点链，库摘要 `c89a1d2252b528d93d140eaff35445db43c204b625b918d6c83a0cf7404a8898`。训练为两份同论文稿件，合成留出仅认证参数流。
- 初轮真实shadow：completed，17请求，估费0.0306696美元，64.784秒，15/15覆盖；1个在线候选。旧策略下离线回放与在线请求位置一致，仅1/17纯工具完整请求机会（5.9%），实际跳过0。
- 发现闭合读取策略仅识别source_id，排除了citation_id。新增TypeScript论文端点策略，仅允许从已认证父字段直接复制的source形状批次句柄；普通插件默认不开放。模型手选keys、代码转换、其他端点和伪造句柄不能走该策略；共享版本/schema/来源守卫保持。
- 修复后 `shadow-typed-handle`：completed，19请求，估费0.032872596美元，74.608秒，15/15覆盖，但在线候选0。原因是未知bash屏障切断完整链的起点；不能据修复后的回放追改旧成绩。
- 从同一正常轨迹另编译两个局部边及完整链，保存在 `libraries/modular-v1`，显式父摘要，原库未覆盖。摘要 `bf528cc0b164e4de18f96dbeb2ab41f9a5ce527632548de6e71baeaa0beba5f2`。局部新读取通过来源核验后可重新成为入口，未跨越未知操作。
- 模块化shadow：42请求，估费0.078091704美元，400.774秒；2候选、71次web_fetch。下一次长上下文请求被预算代理拒绝（Harness表现HTTP429），未生成triage，不能视为有效验收或计算合格节省。来源未变、实际跳过0；没有付费重试该失败轮。
- 本地/服务器闭合句柄与请求评估回归：204 Python/92 Node通过。新增批查询后为215 Python/92 Node，分别记录于下一轮。

新增独立批查询条件 `paper-citation-batch-20261010-v1`：显式新增第十工具，保持该轮baseline/shadow/execute同一工具及题面，不能与九工具旧轮直接作公平因果比较。官方API单ID只读探测HTTP200；XML解析、结果/版本对应、错误页/实体/重复/越界、源变化等已做免费检查。它是人工提炼的工具，不是新学到的网络调度Motif；元数据线索不认证正式发表或著录一致。

本轮目标仍是至少20%的实际模型调用减少及合格总成本下降。当前只支持输出范围工具化和正常主稿链路可运行，尚未证明该目标。预算代理估值需账单核对，学习、失败、恢复及人工评审成本均保留。
