# 历史论文脚本与本地引用序列接入（2026-10-15）

**问题与假设。** 完整论文审查需要反复处理 LaTeX 字面结构和 BibTeX 原文；旧正常轨迹已有 pin→检查活动引用→读取原始记录的操作序列，以及按原始条目解析和核对来源版本的脚本。假设把这段只读序列放进现有论文 MCP 后，模型能在真实任务中调用，减少工具调度，同时保留当前 Task/Session 来源守卫。若它被拒绝、没有实际调用、误称文献真实性或破坏报告/PDF 交付，假设不成立。这是工程复用，不是新增可自动跳过模型的 Motif。

**实现与训练边界。** `collect_current_local_citation_evidence()` 复用 `scenarios/paper-submission/checks.py` 中旧引用取证和 `src/adapters/paper_bibliography.py` 的原文解析，固定 `case_id=current`；只读当前任务批准的文件，返回字面诊断、原始 BibTeX、来源 SHA 和后续可用的 `citation_id`。不联网、不执行历史 shell、不写原稿，也不认定论文或正式版本。原有两条认证只读 Motif、报告生成、结构修订和 PDF 排版工具均保留在同一个场景/共享 RSI Runtime。批量工具是模型显式调用，不计 Verified Skip。旧 9 个 Shadow 候选没有因本次接线自动获得 Execute 认证。

**任务与配置。** V100 私有隔离检出 `/home/jingyij/jjy/.local/integration/harless-motif-20261014`，从 Git `340d243` 加本分支未提交代码差异运行；上传与[上一轮成功小样本](paper-generated-report-20261015-v1.md)相同的 163 字节 `main.tex` 和 79 字节 `references.bib`，无 `audit.json`，模型生成报告并请求 PDF。真实 `deepseek-flash`、`reasoning_effort=off`、Origin/RSI On；每次单任务最多 24 请求/$0.06，启动最多 32 请求/$0.08，每请求输出上限 4000 token。20 个实际 MCP Schema；私有 v2 快照 SHA-256 `ea19438c79c7afb3c8af679920ab168c735dd56d04e326144e15223ca3178e11`，认证文件 `934a820101c1b5da65f1487190e72b805fcc9ebcdfcf503058d8099a8ffad43f`，在线 manifest `e22428bb12f862c99fbec925aba2ba7e3bb7ef10b4989f0f3369bfdd84e2755a`。同一份旧 citation/uploaded 训练库重新编译出两条只读 Motif，未用本次任务训练。输入、完整有效配置、事件和估费留在私有 run，不入 Git；账单实付未知。

| 运行 | 有效配置 SHA-256 | 请求/工具/错误 | 结果 | 代理估费 |
| --- | --- | --- | --- | ---: |
| 初次，`41c1e9c0` | `b43e2b9379394d3bd116475dbf49e7b447bfbc847a4075c75c12c5675d7649a4` | 24 / 28 / 16 | 批量工具成功，但模型漏填 `references[0].evidence_files`；草稿保存后 finalize 报通用错误，重复重试，报告/PDF 均无，任务失败 | $0.021298776 |
| 修复草稿字段反馈，`97df3c1e` | `8183b25fc8a430b51e1b1e6f10a204d17c6b83a99292aa8ff9d82fd49fa1f47c` | 9 / 11 / 0 | 模型调用批量工具，生成 1 引用报告和 4 页、112,401 字节 PDF；38/38 字段字面覆盖，真实文本层，0 Motif 尝试/跳过 | $0.009274092 |

两次合计 **33 次真实请求、$0.030572868 代理估费**，失败、恢复和重复请求均计入。第一次失败的直接原因是原草稿接口接受不完整行，后续又只能追加、不能修改已保存行；MCP 统一错误遮蔽了具体缺失字段。现改为写入前返回 `staged=false`、缺失字段和原草稿 SHA，不修改草稿；成功才返回 `staged=true`。失败输入和修复回归保留在测试中。第二次工具序列含 `list_inputs → collect_current_local_citation_evidence`，之后模型仍额外读取了两个上传文件，并重复调用了一次 `read_pinned_paper_citations`；所以操作序列虽然可用，但尚未完全消除冗余读取。

**验证。** V100 项目环境中 `pytest -q tests/test_paper_proofreading_legacy.py tests/test_paper_reference_records.py` 为 22 通过，覆盖实际 stdio MCP、来源变化、跨任务句柄、缺字段拒绝与旧入口；`web:scenes:check -- --scenes paper-proofreading` 在 v2 包下通过 27 个有效冻结草稿、实际 MCP/上传、PDF 权限和双用户拒绝，0 模型；`npm run smoke`、`npm run web:controls:check` 通过，后者是模拟模型。`npm test` 为 869 Python 通过、4 个此前已记录的文献 PDF 解析用例失败，入口因此未进入 Node；单独运行构建检查和 Node 全量为 453 通过/3 条件跳过。四个文献失败与本次论文场景代码无交集，但完整测试仍不能称为全绿。

**结论与限制。** 在这个合成小样本和上述配置下，历史脚本/序列已通过真实 MCP→Harness→报告→PDF 闭环；成功轮比上一轮[未加入批量工具的小样本](paper-generated-report-20261015-v1.md)少 2 次模型请求、3 次工具调用，但代理估费从 $0.008060436 升至 $0.009274092（约 +15.1%）。成功轮未命中缓存的输入 token 从 8,699 增至 13,145，尽管总输入 token 更少；两轮 PDF 字面字段数量也从 47 变成 38。场景 Prompt/工具 Schema 和模型输出同时变化，不能据此归因请求下降，更不能称为净降本或同等质量。Shadow/Execute 对这条新批量工具尚未做真实对照，模型自主完整论文、多引用准确性、引用真实性、PDF 投稿级视觉、人类盲评和生产成员进程均未验收。PDF 收据只证明当前报告的字面字段 38/38 与基本文件结构，不证明科研质量。后续优先在独立真实论文上固定输入、工具集和输出门槛比较 Origin/Shadow/Execute，并审查多余读取的原因；只有来源、Schema、认证守卫通过的旧轨迹子图才可继续编译为自动执行库。
