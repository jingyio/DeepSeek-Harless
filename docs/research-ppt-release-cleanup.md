# 科研 PPT 试用发布清理

本次发布以最新 main `b143bccb0167261bd9a7b8c3269710ef726bdf5f` 为整合基点，保留 main 的 Web 入口、按会话预算、请求上限和场景 API。科研 PPT 使用公共场景服务与已有 TypeScript 渲染器；本次只收敛稳定使用入口，不新增实验矩阵。

## 从发布运行树移出的历史脚本

以下八个文件在删除前逐文件复制并核验 SHA256 与字节数。删除仅发生在发布 worktree，每项均核验解析后的绝对路径位于该 worktree 内；使用逐文件删除，没有递归删除目录。开发 worktree、服务器历史实验目录与原始运行记录保留。

| 文件 | 原用途 |
| --- | --- |
| `scenarios/research_ppt/experiment.py` | 历史逐步、组合、Motif 对照矩阵 |
| `scenarios/research_ppt/experiment_v5.py` | 第五轮设计与布局对照 |
| `scenarios/research_ppt/experiment_v6.py` | 第六轮生成工具对照 |
| `scenarios/research_ppt/experiment_v9.py` | 第九轮正常轨迹采集与修订运行 |
| `scenarios/research_ppt/experiment_v10.py` | 第十轮明确修订与产品入口对照 |
| `scenarios/research_ppt/experiment_v11.py` | 第十一轮科研页型生成对照 |
| `scenarios/research_ppt/report.py` | 历史摘要转 PDF 的独立报告脚本 |
| `scenarios/research_ppt/tests/test_experiment_v9.py` | 随旧轮次模块组织的运行记账测试 |

私有备份位于操作者本机主项目 `H:/DeepSeekHarness` 的 `.local/research-ppt/release-archive-20261013/`，不在发布 worktree 的 `.local`。其中 `manifest.json` 包含原相对路径、发布 worktree 的源路径、SHA256 和字节数；`removal-receipt.json` 记录逐文件移除范围。八份备份均与删除前源文件字节一致。备份 manifest 的 SHA256 为 `3d4492c6c89582b058ae29b4938e1ca2faacb2a88febdf8e929dea17b21c8971`。这些私有文件不进入版本控制。

## 保留的通用能力与边界

- 公共记账函数已独立到 `scenarios/research_ppt/accounting.py`，包括缓存命中／未命中输入、输出、失败请求、未知费用和全部尝试汇总；代理估费仍不等于实付。
- 运行依赖快照已独立到 `runtime_snapshot.py`，记录实际 Node、字体与依赖版本；历史兼容证据由调用者显式选择，默认不依赖旧实验日期目录。
- 有价值的记账、失败、修订和解释器快照回归迁移到 `tests/test_run_records.py`。清理没有删除有效安全检查；服务器测试结果由发布交接与对应实验记录提供。
- 工具学习、布局学习、条件认证、真实 MCP smoke、checkpoint、版本与权限守卫保留。`tool_learning.py` 已改用公共记账模块。移除前的代码扫描未发现其他场景 Python 模块仍导入这些历史实验入口；这项静态检查不代替运行测试。
- 成熟模板库的五套／28 个页型及原生填充原型，不属于本次默认稳定入口。相关代码、许可和历史证据按可选扩展或历史版本保留，不把素材文件存在表述为用户入口已经接入。

## 历史报告与复现

历史实验设计、报告、失败结论及勘误继续保留，清理运行入口不改变既有实验结论。旧报告中的轮次 CLI 是当时版本的复现说明，不是当前试用版命令。

需要复现旧实验时，使用报告记录的代码 commit、有效配置与私有数据。上述历史脚本可从 `4008d2d1c7794cbdb5882cf6d3222bab1f067b5e` 或相应更早的报告 commit 找回；不能在最新发布树中重新拼接脚本，然后声称与历史实验环境相同。旧证书、来源或依赖版本发生变化时，应按原有守卫拒绝，不重新签署旧结果。
