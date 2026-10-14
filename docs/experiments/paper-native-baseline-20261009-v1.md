# 论文原生基线与基础环境验收

- 实验 ID：`paper-native-baseline-20261009-v1`；时间：2026-10-09；状态：基础编译环境已验证；首次原生基线受沙箱阻塞，用户授权非沙箱恢复后生成 PDF，最终报告因累计请求上限未完成。
- 问题与假设：先观察 DeepSeek Harness 用原生工具检查编译、引用、排版的路径，再决定专用 MCP 与结构复用入口。若不能完成检查或没有可追溯证据，则不支持交付质量或降本主张。
- 任务与对照：真实私人论文 ZIP 的只读工作副本；本轮只跑 native baseline，无 MCP/Motif 组，不检查会议合规。未预置检查 DAG 或答案。来源 SHA-256 `7aafe2468ac50d69c23c3dab719213b47406b2c33efe55dc911c361f25360027`，正文、文件名称和原始日志不公开。

## 配置与复现

代码基点 `2368235f274329be6227a8393b850633cb943da4`，工作区含未提交开发变更；私有 `effective-config.json` 记录启动接缝、预算代理和控制脚本摘要。Ubuntu 22.04 容器、宿主内核 5.4；Node 22.23.3、Python 3.10.8、DSH 0.1.5-rc.3、固定 Python SDK 0.1.5rc1。

原生 SDK profile，`deepseek-flash`，`reasoning_effort="off"`（实际请求 `thinking.type="disabled"`），预算 1 美元、24 次请求、每次 3000 输出 token。保留原生 Agent 循环、native function calling 与通用工具；不加载场景守卫、专用 MCP 或 Motif。关闭自动压缩、标题模型、自动重试、外部遥测和额外付费 `web_search`，保留 `web_fetch`。限制 `workspace-write`，审批策略 `never` 会拒绝需要提升权限的调用，权限预设与此一致。这是受控原生基线，不能称为完全未配置的官方 Web 默认行为。

24 个模型可见工具及顺序在私有逐请求快照中保存；4 次请求的 schema 摘要均为 `0e4ce701e493768e606a1647bf4252b0270120f4c6b953932c35aa070b720d8e`。私有原始逐决策请求和事件同步两端 `.local/experiments/paper-native-baseline-20261009-v1/`，不进入 Git。`started.lock` 阻止直接重跑重置预算；恢复必须累计已有费用和请求次数；后续已按此约束执行。

公共环境复验（不调用模型）：

```sh
source .local/remote-env.sh
node scripts/project.mjs python scripts/check-paper-env.py
```

真实输入和控制脚本仅在服务器私有目录；原始启动命令为：

```sh
node scripts/project.mjs python .local/experiments/paper-native-baseline-20261009-v1/run.py --run
```

它已执行，不能直接再次运行。私人材料不能通过公共仓库复现；需负责人提供相同授权输入并核对哈希。

## 结果与负面证据

- 公共 ACM 夹具三引擎（pdfLaTeX、XeLaTeX、LuaLaTeX）全部编译成功；BibTeX、交叉引用、PDF 元数据和字体嵌入检查通过。成功环境运行 `20261009T131136Z-b7b4bc44`，摘要保存在两端 `.local/paper-env/runs/<ID>/summary.json`。TeX Live 2021、latexmk 4.76、Poppler 22.02.0、chktex 1.7.6；安装清单见场景环境 README。
- 先前环境失败也保留：`20261009T130213Z-ae69f963` 缺 `acmart.cls`，增加 `texlive-publishers`；`20261009T130533Z-b1b7d68a` 缺 `binhex.tex`，增加 `texlive-plain-generic`。均为无模型诊断，不是论文检查。
- 首次原生启动权限预设冲突，在发出请求前失败，0 请求/0 费用；记录保存在私有 `startup-failed-001/`。修复预设后才发出真实请求。
- 真实 Session `paper-native-e6644b536eb54cd7a78e7d36b94c4ff7`（以私有有效配置为准）；4 次上游请求均 HTTP 200。实际工具为 `bash` ×4、`glob` ×1、`read` ×1；只有目录文件名列举成功。4 次 shell 均 `SANDBOX_UNAVAILABLE`，读取 ZIP 则 `FS_NOT_TEXT`。
- 安装 bubblewrap 后无模型探测仍失败：`Creating new namespace failed: Operation not permitted`。容器禁止所需 namespace，内核 5.4 没有 Landlock 后备能力。首次阶段没有自行绕过边界；后续取得用户明确授权才修改本次私有实验权限。
- Harness 返回 `finish_reason=completed`，只是模型结束回复；任务验收仍为失败。该首次阶段未解压/编译，答案是阻塞说明，质量未盲评。后续恢复结果独立追加如下。

## 成本、耗时与结论

有效预算上限 1 美元；已用 4 次真实请求，prompt 30,532 token（缓存命中 22,656 / 未命中 7,876），output 1,350，total 31,882，推理 token 0。代理按峰值表估费约 0.00411874 美元，账单实付尚未核对；不能将估费写成实付。模型基线耗时 9.956 秒，环境安装、调试和人工审阅时间未完整计时，不能据此报告端到端效率或总成本收益。

已观察：模型确实选择了原生终端、文件列举与读取工具，失败时未声称论文已检查。只支持 API/原生工具派发可达；不支持论文校验质量、Motif 可复用性或模型调用节省。公共夹具编译通过不代表 Harness 沙箱里的编译可用。

最初的接手计划是修复环境或申请本次非沙箱权限后累计恢复。用户随后已明确授权本次 `danger-full-access`；实际恢复与新限制见下。实际投稿、原件修改和写外部应用仍不在授权范围内。


## 用户授权后的恢复与最终状态

用户明确允许仅本次论文实验使用非沙箱终端，未改变项目通用沙箱默认配置。固定 SDK 的 `session/prompt` 在进程重启后会尝试创建 Session，不能直接打开原有身份；尝试原身份时零新增请求失败。此前一次权限预设名称不匹配同样零新增请求失败。两项失败分别保存在私有 `startup-failed-002/003/`，没有删除负面证据或额外收费。

恢复阶段使用原 Session ID 加 `-recovery`，同一实验、同一私人输入、相同 24 个 native 工具和原账本。代理启动时恢复先前 4 次计数和已用费用，剩余请求 20 次，费用上限仍为总计 1 美元。权限变更和 Session 关联保存在 `effective-config-resume.json`；不宣称跨进程会话无缝恢复或稳定前缀完全不变。

- 已观察的实际路径：解压 → 读取主文件/辅助文件 → grep 引用与标签 → 复制独立 build → latexmk/BibTeX → pdfinfo/日志分析 → 临时参考文献解析及修补。源码搜索包含旧文件和注释，不能将所有 grep 候选都当作活动文稿问题。
- 论文 PDF 已生成：14 页、1,908,077 字节，latexmk 退出 0；存在未定义引用、重复标签与排版警告。引用真实性、会议要求及科研内容均未核验。公共记录不公开私人问题位置和内容；详见私有 `codex-audit.md`。
- 原 ZIP 哈希保持一致；Codex 对 src 与 build 两份来自 ZIP 的 34 个文件逐项比对，均未改动。编译产物同步至本地私有 `work/build/main.pdf`。
- 未完成 `artifacts/report.md`、字体嵌入和视觉排版核验。恢复阶段 20 次请求后遇到 `NativeBudgetExceeded`，任务仍不合格。累计原生工具 bash×34/read×5/glob×1。
- 临时 `.bbl` 解析发生多次修补，最终结构化条目键仍错误；shell 中 Python 退出非零时外层 `isError` 仍可能为 false。该轨迹不能直接认证为成功 Motif，应由可靠工具输出/退出码守卫补齐。
- 模型编译命令没有显式 `-no-shell-escape`；日志为 `restricted write18 enabled`，未满足声明的完全禁用条件。这是流程偏差，后续编译工具必须固定参数，不能只依赖提示词。

最终累计：24 次上游请求全部 HTTP 200；prompt 406,497 token（缓存命中 378,880 / 未命中 27,617），output 7,281，total 413,778，推理 token 0。代理累计估费约 0.0193 美元（账本逐行四舍五入总和与内存累计值有微小差异），账单未核对。首次模型运行 9.956 秒、恢复 45.602 秒，模型运行相加约 55.558 秒；不含环境安装、启动配置调试、文件传输与人工核对，不能当作端到端总耗时。

本轮支持：真实原生 Agent 能选择基础工具并完成论文编译。尚不支持完整校验交付、Motif 收益或可靠的 RSI 工具生成。下一步以编译参数、活动来源解析、诊断输出和真实退出码为最小可靠 MCP 契约候选；先完成工具质量与报告闭环，再对成功正常轨迹挖掘并认证。暂不扩大调用或重置已达到的 24 次上限。
