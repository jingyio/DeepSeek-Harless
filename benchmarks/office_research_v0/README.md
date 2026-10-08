# Office Research v0：机制回归小基准

这是 SSS 自建的**合成**任务，专测科研资料整理和增量更新中的去重、版本替换、来源绑定与旧判断失效。它不能代表真实研究质量，也不用于宣称产品胜过公开 benchmark。报告正文仍须人工评审。

## 两阶段任务

**阶段 A（首次整理）**：输入 `inputs/stage_a/` 的五份文件。建立归档清单，按同一实验集合比较可比的方法，标记重复文件和来源不明的笔记，输出引用来源的简报。不要把不同实验集合的数字直接排名。

**阶段 B（增量更新）**：在阶段 A 的基础上加入 `inputs/stage_b_delta/`。`MF-24` 的正式更正版替代旧版，同时出现一个新方法。更新归档和简报；已验证且不受影响的 `GP-25` 与 `TR-25` 资料可以复用，旧版 `MF-24` 的数字必须失效。保留改动记录，说明哪些结论被替换及原因。

程序化输出用 JSON：

```json
{
  "stage": "A",
  "archive": [{"file": "motif_2024.md", "record_id": "MF-24", "status": "canonical"}],
  "facts": [{"id": "mf_success", "value": "32/40", "source_file": "motif_2024.md", "support_quote": "32 of 40 tasks passed"}],
  "report": "面向组会的简报正文，附来源 ID。"
}
```

`status` 只能是 `canonical`、`duplicate`、`superseded` 或 `needs_review`。阶段 B 的输入应为阶段 A 全部文件加 `stage_b_delta/` 两份文件。程序评分检查归档、关键事实与引文原文是否存在；另设人工评分看比较是否合理、冲突是否交代、简报是否可用。阶段 B 还应记录运行时 trace 中的复用与失效，但不能仅凭 trace 声称报告质量提高。

数据是虚构的，文件内均明确标记。黄金答案在 `gold.json`；评测时只把 `inputs/` 复制给被测 Agent。测试脚本只读评分，不发起模型调用：

```bash
python3 scripts/office_research_benchmark.py prepare --stage A --out .local/benchmarks/office_research_a
python3 scripts/office_research_benchmark.py prepare --stage B --out .local/benchmarks/office_research_b
python3 scripts/office_research_benchmark.py grade --prediction /absolute/path/to/prediction.json
```

迁移后的 MotifAgent 内核可实际运行两阶段任务，需 Python 3.10+。先用上面的 `prepare` 命令创建两份输入目录，再运行：

```bash
.venv312/bin/python scripts/run-motif-office.py --stage A --input .local/benchmarks/office_research_a --out .local/motif-office-a
.venv312/bin/python scripts/run-motif-office.py --stage B --input .local/benchmarks/office_research_b --resume-state .local/motif-office-a/state.json --out .local/motif-office-b
.venv312/bin/python scripts/office_research_benchmark.py grade --prediction .local/motif-office-b/prediction.json --events .local/motif-office-b/events.jsonl
```

运行时保存 `prediction.json`、`state.json`、`events.jsonl`。`--events` 会核对实际读取／复用／失效事件与预测 trace 是否一致；评分仍只证明这个合成题的结构条件和引文原文存在，不判断引文是否充分支持整句结论。适配器只解析本题结构化记录，报告使用固定模板，模型请求为零，不能据此推断 DeepSeek、Jev 或真实调研任务的质量和成本。

## 与公开基准的关系

外部质量对照优先用 [DR³-Eval](https://github.com/NJU-LINK/DR3-Eval) 的中文研究报告任务，尤其任务 `zh/003`；它有固定多文件资料库和报告质量维度。本小基准补其未直接提供的增量更新和归档状态。正式实验要报告两者，不以此合成小基准的高分替代真实任务成绩。
