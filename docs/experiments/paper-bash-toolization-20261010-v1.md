# 从原生 bash 轨迹提炼参考文献读取工具

- 日期/执行者：2026-10-10，Codex；`feature/paper-submission`，未提交/未推送。
- 问题：能否将论文核验中重复生成的读取/哈希脚本内化为有输入输出、来源版本和失败边界的 MCP 工具。
- 类型：正常真实轨迹的只读分析与真实 stdio MCP 回放诊断；没有新的模型运行、工具自动合成或模型调用下降结论。
- 否定条件：丢弃重复条目、改变原文、偷偷选择同键第一条、把 Bib 索引冒充论文编号、来源变动后继续读，或把工具化数量当作模型节省。

## 轨迹与取舍

来源为 `.local/paper-reference/paper-rsi-sequential-20261010-v1/runs/continuation-shadow-round-3-shadow/` 的 root Session。该轮 16 次 bash：前 9 次是目录/源码/引用/条目读取和哈希；2 次额外网络查询；4 次 sleep；最后 1 次 Python 输出集合与字段核对。完整来源 manifest 的 SHA256 为 `1d5f33bc5c8de18e7df33c63d1ef6ee9ec7d427494b33390005c43e3f7f25af8`。

优先提炼第三条批量 `cat` 和第八/九条 `sha256sum` 的公共行为：读取选定参考文献原文及其版本。这里没有原样重放任何历史 shell，也没有把私人路径、论文键或修复结论写进公共实现。脚本中的具体参数由调用时的句柄和 keys 提供。

后续候选为活动引用图、输出集合/字段校验；可以复用已有静态检查与质检实现。网络批查询需要超时、状态、来源及版本契约，不能把搜索候选当作正式出版结论。等待应定位真实后台句柄与终止条件，再交给调度器，不把固定 sleep 秒数编译成科研技能。正文和版本冲突的科学判断仍交给模型。

## 已实现工具

显式设置 `SSS_PAPER_REFERENCE_RECORDS=1`，同一论文 MCP 新增：

```text
pin_paper_sources(case_id) → source_id / version_sha256
read_pinned_paper_references(source_id, keys)
  → records / raw_bibtex / record_sha256 / bib_file_sha256
    / missing_keys / duplicate_keys / version_sha256
```

工具复用真实来源句柄，限注册案例的活动字面 `\input`/`\bibliography` 文件。每批 1–64 个唯一引用键；按各 Bib 文件原顺序返回，保留同键多条。`entry_index_in_bib` 是从零开始的文件条目索引，不是论文参考文献编号。缺失明确返回，宏保留原文、不推断值，真实性和正文渲染编号检查均为 false。

读取前后核对版本，拒绝越界、符号链接、错视图、失效句柄、动态 input、未闭合/不支持的 BibTeX；输出超过 1 MB 时拒绝并要求缩小批次。`record_sha256` 对返回 raw_bibtex 的 UTF-8 字节计算，`bib_file_sha256` 对原文件字节计算；前者不是带分隔换行的整个旧 records 文件哈希。

`src/adapters/paper_bibliography.py` 由原准备器的字面解析逻辑提取，供准备器和 MCP 共用；新增忽略嵌套 `@comment`/标题中的伪条目。它仍不是完整 BibTeX/TeX 解释器，括号式条目等不支持语法明确拒绝。检查器版本包含解析器代码摘要；改变代码会使旧来源视图版本失效，不能静默继承旧认证。

默认 MCP 仍为原来的六个工具，只有 opt-in 增加第七个；没有修改原六工具实验的 tool schema/order，也没有自动给现有 Web 加工具。不执行命令、模型生成代码、网络检索、LaTeX 编译或修稿。MCP 服务依赖 Python，与 TypeScript 权威在线 Runtime 的分工一致。

**工程来源是人工从正常 bash 轨迹提炼并审查**，不是自动 Motif 编译器已经生成了这个工具。尚未从新工具的正常模型轨迹学习出 pin/read 或更长调度 Motif；没有往第四版库里手工塞 DAG。下一次真实评测必须在各对照组固定同一七工具契约与顺序，先观察自主使用，再学习、冻结并在后续任务 shadow。

## 免费验收与复现

服务器 Node 22.23.3、Python 3.10.8，既有项目隔离环境；`scripts/check-paper-reference-tools.py` 使用真正 MCP Client/stdio 服务，模型 Provider 不参与。历史私人副本只读，原稿未修改。私有输入/output 路径限制 `.local/`。

```sh
source .local/remote-env.sh
node scripts/project.mjs python scripts/check-paper-reference-tools.py \
  --input-run .local/paper-reference/paper-rsi-sequential-20261010-v1/runs/continuation-shadow-round-3-shadow \
  --output .local/paper-reference/paper-bash-toolization-20261010-v1
```

已完成目录不可重用，诊断拒绝覆盖；复跑选择新的 output。该诊断仍假定输入 run 的 `work/source/main.tex` 和既有 catalog，是历史回放辅助，不是产品通用启动器。

结果：

- 原 Bib 库解析出 315 条；34 条正文引用对应的原文与历史记录逐项一致。
- 默认六工具、opt-in 七工具 inventory 通过；34 条由一次批量 read 取得，版本与 pin 相同，原目录全部来源哈希未变。
- 伪造 source_id 被 MCP 拒绝；错误日志是有意的负例，不是成功读取失败。
- 本地及服务器 `npm test` **201 Python / 88 Node** 全部通过；新增六项覆盖原顺序、中文/嵌套字段、重复与缺失、句柄/范围、读取中源变化及不支持语法。
- 本轮模型请求 0，新增 API 费用 0；Agent 是否选用、是否少请求和报告质量未评测。原论文累计预算仍约 4.415383/封顶4.84521046，余额上界0.429827，账单未知。

私有诊断保存 `inputs.json`、两种 `tool-inventories.json`、`reference-records.json` 和 `verification.json`；后者记录源 manifest 与执行代码摘要。两端同步包 SHA256 为 `d9c1436ff326893750a27f35f5d1e9bc254285b5777601aa5ff747467f249da5`。原轨迹、库、预算与旧评估不覆盖，原始论文与工具输出不进入 Git。

## 结论与下一步

在此范围支持：重复 bash 的读取/哈希可以提炼为来源受限、跨案例参数化的 MCP 能力。它减少重新生成脚本与处理参数的工作；一次工具批处理不自动等于跳过一次模型请求，尚未证明收益。

下一步：将活动引用图和交付集合检查同样工具化；在新任务用真实 Harness 采集工具轨迹，从实际句柄/参数/输出依赖学习更长 Motif，并把选择合并进必要的语义判断。需要模型改写查询或修复未知问题时回退；简单工具脚本作为基线保留，比较学习与维护的累计成本。
