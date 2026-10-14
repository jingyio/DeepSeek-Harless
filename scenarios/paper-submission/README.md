# 论文检查：只读证据与 Motif 诊断入口

当前已跑通真实 Harness → MCP → 轨迹挖掘 → shadow/execute。相同题面、相同六个 MCP 工具的对照中，execute 将模型请求从 3 次变为 2 次；费用与耗时没有下降。见[实验记录](../../docs/experiments/paper-motif-shadow-execute-20261009-v1.md)。这只是结构协议诊断，不是论文检查质量验收或生产认证。

## 工具与权限

`server.py` 是 stdio MCP，使用 `checks.py`。运行者通过私有 `SSS_PAPER_INPUTS` JSON 注册案例；模型只能传案例 ID 或本次 MCP 进程实际返回的句柄，不能传路径、命令或生成代码。

| 工具对（Harness 名称前缀 `mcp__paper_checks__`） | pin 输入/输出 | read 输入/结果 |
| --- | --- | --- |
| `pin_paper_sources` → `read_pinned_paper_sources` | `case_id` → `source_id`, `version_sha256` | `source_id` → 活动文件、引用/标签/浮动体诊断 |
| `pin_paper_build` → `read_pinned_paper_build` | 同上 | `source_id` → 既有日志计数、已记录步骤/真实退出码或未知 |
| `pin_paper_pdf` → `read_pinned_paper_pdf` | 同上 | `source_id` → pdfinfo/pdffonts 元数据与字体嵌入诊断 |

六个工具均只读。所有注册路径限于项目 `.local/`，拒绝越界、符号链接、错视图和失效句柄；版本包含源文件、派生产物、配置、检查器、Python 与 PDF 工具二进制摘要。每次读取前后复核。MCP 不执行 LaTeX、不修稿；已有 PDF 不等于编译成功。静态源码分析不等于完整 TeX 解释、文献真实性或页面视觉验收。

可选的第七个工具：设置 `SSS_PAPER_REFERENCE_RECORDS=1` 后，`read_pinned_paper_references(source_id, keys)` 使用 `pin_paper_sources` 的实际句柄，批量返回完整 BibTeX、条目/文件哈希、缺失与重复项。每批 1–64 个唯一键，保留 Bib 原顺序和同键多条；源变化、不支持语法或过大输出拒绝。它从历史 bash 的 `for/cat/sha256sum` 行为人工提炼，共用 `src/adapters/paper_bibliography.py`，不执行历史脚本、不核验真实性；版本包含解析器摘要。默认仍是原六工具，旧实验契约不默默变化。真实 MCP 无模型验收 34 条原文通过，见[工具化记录](../../docs/experiments/paper-bash-toolization-20261010-v1.md)。新工具尚未编译成调度 Motif，没有调用下降结论。

`SSS_PAPER_INPUTS` 格式为 `case_id -> {root, source_dir, main, pdf, log, bbl, build_record?}`，路径字段相对该案例 `root`；`root` 必须在受信任私有目录内。记录示例结构见实验生成的 `inputs.json`；公共工具契约由 `scripts/paper-motif-experiment.py` 的 `contracts()` 定义。

## 从轨迹编译

1. 用三个不同受控短稿采集真实模型轨迹：干净稿、缺失引用稿、重复标签稿。两份用于挖掘，第三份留出验证。模型自主调用工具，未给定调用顺序。
2. `infer_dsh_provenance` / `mine_witnessed_parameter_edges` 从成功调用中找到实际 `source_id` 传递；不是把“论文检查”关键词映射到手写 DAG。
3. 复用现有 edge compiler、留出认证与 library exporter，得到三个两节点 Motif。冻结实际工具参数 schema 摘要、参数流、版本字段、支持轨迹与留出身份。
4. 三份合成稿只验证协议迁移。库标记 `certification_scope=protocol_diagnostic`；普通生产插件拒绝加载。独立科研决定认证仍未完成。

实际 manifest 的结构片段如下（省略摘要及工具前缀）：

```json
{
  "tools": ["pin_paper_build", "read_pinned_paper_build"],
  "transfer_evidence": [{
    "from_tool": "pin_paper_build", "from_field": "source_id",
    "to_tool": "read_pinned_paper_build", "to_param": "source_id"
  }],
  "local_programs": {
    "read_pinned_paper_build": {
      "language": "sss-local-ops-v1",
      "target_tool": "read_pinned_paper_build",
      "steps": [{"op": "copy_verified_field", "from_tool": "pin_paper_build",
                 "from_field": "source_id", "to_param": "source_id"}]
    }
  }
}
```

完整 library/manifest 还含认证摘要、来源身份、只读契约、schema 哈希、版本字段与 slot 约束。JSON 是可执行结构契约；自然语言说明只是辅助信息。当前不是完整场景程序，更没有自动学习编译失败恢复或语义判断规则。

## Runtime 行为

新入口 `src/adapters/dsh_paper_motif.ts` 复用 `dsh_online_motif.mjs` 的权威拦截器，不维护第二套在线规则。实验显式开启 `SSS_PAPER_MOTIF_DIAGNOSTIC=1`。不使用 embedding；仅唯一、封闭、已认证的来源读取可接管，需要语义排名则回到真实模型。

- **shadow**：在模型请求前记录候选，照常调用模型，不新增执行。
- **execute**：所有任务/会话/题面、权限、schema、参数来源、版本守卫通过后，返回标准工具 stream，由 Harness 正常派发工具。三个独立读取可合成一个 batch。
- **复核**：只有整个 batch 的真实工具结果均通过守卫，才计 `model_request_skipped_verified`。工具错误、来源漂移或不支持的分支交回模型，不能以“尝试接管”代替安全跳过。

本次仍需模型决定 pin 的范围，并解释证据生成报告。手写“pin 后 read”的脚本也可能实现同等效果；需要更多不同任务、变化与失败分支的公平对照才能证明 Motif 的额外价值。

## 实验入口与限制

服务器先加载隔离环境，再通过统一 Python 入口运行。默认预览，不付费：

```sh
node scripts/project.mjs python scripts/paper-motif-experiment.py --experiment-id <新实验ID>
```

按顺序用同一 ID 执行 `--phase prepare`、`collect`、`compile`、`compare`；`prepare` 的 `--private-case` 指向已准备的私有 PTC 实验目录，`collect/compare` 必须显式 `--call-model`。不要重用已有运行 ID，不能覆盖结果或重置预算。

当前控制器是本服务器论文实验入口：依赖 Linux `fcntl`、已有五份 Native/PTC 私有预算账本、既有证据目录和 PDF/LaTeX 工具；不是新克隆即可付费运行的通用产品入口，Windows 未验证。`prepare` 会编译受控夹具的私有副本（`-no-shell-escape`），私人论文仅复制已生成的证据；在线 MCP 全程只读。所有材料、请求、事件、账本、库与答案保存在 `.local/paper-motif/<ID>/`，不提交 Git。

模型 `deepseek-flash`、推理 `off`、输出上限 3000、压缩关闭、不设请求次数上限；累计论文预算 1 美元。历史和所有实验 ID 的新增费用累加（跨实验锁），账单仍需核对。当前修正过检查器的 `.bbl` 注释解析与未知 shell-escape 表达；旧运行版本与结果保留，旧 task 的版本守卫会失效，需要新的快照才能再执行。

## 原生完整参考文献报告对照

用户新题面冻结于 `reference-audit.prompt.md`，要求全部参考文献/正文引用、权威来源及正式版本核验和逐页复核的 PDF。新入口 `scripts/paper-reference-experiment.py` 默认预览；真实 `collect -> compile -> compare` 各阶段同一个 ID，模型阶段须显式 `--call-model`，使用原生工具及原始 ZIP 新副本，计划五次采集、两次 execute。v2 第一条正式基线 98 请求后 max-tokens 结束，未生成完整报告；v3 的 16000 输出配置仅无模型预览，预算答复前不付费重跑，尚无五条库或效果结论。进度、失败预试、编号依据与费用详见[当前记录](../../docs/experiments/paper-reference-five-native-two-motif-20261010-v2.md)。

正式运行的模型、题面和工具集合/顺序固定，v2 输出上限 8000；当前 v3 入口统一 16000，无请求次数上限、推理 off、压缩关闭。沿用论文累计 1 美元预算，不将更换 ID 当预算重置；控制台保守预留不等于已结算费用。原始主稿的 `\nocite{placeholder}` 使编号依据须明确说明；新 Session 与目录不等于非沙箱下文件访问隔离，要审计跨运行答案读取。同题重复库标记 `same_task_repeated_runs`，只作诊断，不冒用独立科研决定认证，不接入普通生产插件或 Web。

## 活动引用/官方批查询 RSI 诊断

详见 [最新场景交接](../../docs/handoffs/paper-submission.md)。`SSS_PAPER_CITATION_FLOW=1` 是9工具，另加 `SSS_PAPER_ARXIV_BATCH=1` 为10工具；原六工具不变。`paper-citation-rsi.py --arxiv-batch --bounded-evidence` 只对阶段试验限制实际模型7工具。默认预览、实跑在服务器且需--call-model；不同工具条件不能直接归因比较。literal引用/arXiv元数据不等于正式版本与整稿核验。当前累计代理4.739188258/冻结4.84521046美元，无次数上限；历史余额不适用于新试验。完整报告/20%及真实错误恢复尚未验收。

复合取证opt-in：SSS_PAPER_COMPOSITE_EVIDENCE=1 独立增加 collect_paper_citation_evidence(case_id)，不必开启旧citation-flow。新的五工具实验由 --composite-evidence --arxiv-batch --bounded-evidence 启用；--delivery-check off/shadow/enforce 与分组固定，共享 ../../schemas/paper-citation-triage.schema.json。--budget-record 指定已授权的私有累计记录并冻结，默认旧记录不变。六次真实测试完成且结构/范围通过，execute不再显式检查，但与基线合计均14请求、估费高30.3%；语义未盲评，20%总体下降未达成，Hook尚未自动学为Motif。详见 ../../docs/experiments/paper-composite-delivery-20261010-v2.md 与当前场景交接。
