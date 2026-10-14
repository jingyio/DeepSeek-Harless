# 论文旧 Motif 与 PDF 生成工具复用盘点（2026-10-14）

本记录是免费静态盘点，未运行模型、未改变生产服务，也不构成新的效果实验。

## 归档体积

本地私有同步清单 `.local/paper-baseline-sync-20261014/manifest.json` 选中了跨 53 个历史实验根目录的 76 个名称含 `baseline` 的运行目录、26 个 `collect/learn/train` 目录及相关输入与元数据，共 10,212 文件、1,822,061,785 字节。目录有重跑、失败恢复和同一论文变体，**不是 102 条独立任务**，也不能与用户所说约 72 条轨迹直接等同。

按路径分类，逐请求快照占 1,269,752,327 字节（69.7%，反复包含上下文及工具内容）；工作副本占 297,060,754 字节（16.3%，含重复字体）；事件与账本类占 140,477,280 字节，Harness Session 记录占 11,075,749 字节。先前把完整实验归档体积称作“轨迹大小”不准确。V100 私有归档在 `.local/imports/paper-baseline-sync-20261014/`，逐文件 SHA-256 校验 10,212/10,212 通过；可重装依赖、profile、符号链接和疑似凭证文件未纳入。原始内容不进 Git。

## 两项旧成果的实际形态

- [论文 Shadow 三轮](paper-rsi-overnight-20261011-v3.md)：私有 `libraries/v01/library.json` 有 9 个局部图，`execution_policy=shadow_only`。最佳整组严格整请求匹配 37/114（32.5%），第三轮 45/164（27.4%）；实际 Runtime 跳过为 0，语义质量未盲评。一篇论文十种变体不是跨论文认证。
- [PDF 生成工具采用](paper-pdf-export-adoption-20261013-v3.md)：`renderer-frozen-v2` 是模型正常轨迹生成并冻结的排版程序，四个文件与 manifest SHA 均一致。20 请求/$0.021217884/61.309 秒那组通过追加当前输入与能力绑定说明采用工具；160 与 55 请求两组存在运行路径波动，第三组提示不同。它不是新增认证 Motif 图，Runtime 自动跳过为 0。

原 Shadow 库和排版包/审阅记录共 45 文件、21,064,126 字节，已复制到 V100 私有 `.local/imports/paper-legacy-reuse-20261014/`，45/45 SHA-256 校验通过，旧文件未覆盖。

## 与当前 Web 论文场景的接缝

当前 `scenarios/paper_proofreading/scenario.json` 只开放 5 个逐 Session 上传文件读取工具；旧 Shadow 库的 11 个工具名与该白名单交集为 0，9 个局部图没有可直接按现状运行的工具链。旧引用服务通过固定 `case_id`、环境变量和私有实验目录取源，不能直接给多用户 Web 使用；需要保持原工具语义、改为任务批准的 Session 输入和权限绑定，再按实际 Schema 重编译/认证。不能改旧 manifest 哈希或把未匹配图强行标为 Execute。

排版工具依赖当前 `audit.json` 的 SHA、冻结程序/字体/审阅包及只写新 PDF 的收据；Web 论文场景目前没有该报告生成链或导出授权。可复用该工具实现，但应在已有预览/确认和任务目录内登记为有副作用能力，并以真实采用轨迹学习“读取当前版本→导出→验证 PDF”的局部 Motif。模型仍负责文献判断和报告内容。

这两项适合在同一论文流程分层协作：旧库覆盖引用取证和结构检查候选，冻结工具覆盖报告排版；先完成任务级来源与工具接入，再分别做 Shadow 与受守卫保护的 Execute。两个历史表格的百分比和请求数来自不同任务、提示和质量范围，不能相加或当作合并后的收益。下一步最小验收应在独立上传论文上完成旧工具兼容、库重新认证、PDF 内容/链接与逐页检查，并对同条件 Origin 保留全部模型请求、失败与成本。

## 本轮接入与新编译（后续状态）

独立分支 `codex/harless-motif-libraries-20261014` 复用原 `PaperEvidence`、arXiv/Crossref 与冻结 PDF 脚本，在正式论文 MCP 上开放 13 个工具。引用工具只见当前任务的 `inputs/`，`case_id=current`，上传准入清单和任务 ID 变更使旧句柄无效。报告导出需菜单/任务 `allow_output=true`、当前 `audit.json` SHA 与管理员审核包版本，原稿不改，目标限新任务输出目录；收据要求逐页人工检查。文件、Session、权限及预算继续走原 Web 任务入口。

V100 隔离工作区 `/home/jingyij/jjy/.local/integration/harless-motif-20261014` 的私有 `.local/paper-composite-20261014-v3/` 已生成五文件 Runtime 包；在线 manifest 摘要 `e8fd2cc30ba6acd1ad8a75a2a5931ab1ed951941d693c81aa0ecc6383a147729`，13 工具 Schema 文件 SHA `fb4cfec6a2d5eaa1cf88173f56e0a9e80d17e795a1c9b9a9f35e590045ac7892`。两条可执行只读局部图分别为上传源码 pin/read 与引用当前稿 pin/read。旧引用图先由原契约验证，再将固定案例的起点收紧为模型实际选择 `current` 的观测锚点，重新签名并由当前契约核验；未改写旧库。原 `read_pinned_citation_records` 后继保留为普通工具，旧 Shadow 局部图留作候选，未冒称当前协议下可自动跳过。PDF 脚本与新包同场景部署，但为模型显式调用的写工具，不纳入只读 Runtime；因此两实验能力在一项任务中可配合，历史收益不合并。

免费验证：新论文工具测试 3/3；固定脚本用旧实验的当前 `audit.json` 在隔离任务目录真实生成 151,255 字节 PDF，输出 SHA `6e0418f353af842c2c6f0b62769a96cc2a43c875b7e07f86d7c17b838dbfc0be`，收据 `semantic_quality_accepted=false`。新 manifest 的在线校验及服务端包加载通过。`npm run web:scenes:check` 在 V100 无模型通过 26 个有效菜单/冻结预览、五场景实际 MCP/上传及双用户隔离；修正输出授权准入后，论文 PDF 可先预览/上传，缺 `audit.json` 在提交时明确拒绝。`npm run smoke` 18/18 题通过，付费请求 0。两名成员实际 bwrap 环境通过 10 个五场景任务预览、MCP 和跨用户拒绝，无模型。完整 `npm test`（合入最新 main 前）为 602 通过、4 个旧 literature PDF 测试失败，错误为 PDF 解析及旧句柄，当前分支未改该场景代码；仍须排查环境/回归。

真实模型验证固定 `deepseek-flash`、`reasoning_effort=off`、每任务 0.03 美元/12 请求、每启动 0.06 美元/24 请求、单请求最多 1000 输出 token，均在 V100 隔离工作区；实际账单未核。两项 Execute 分别 6 请求/1 个源码读 Verified Skip/0 工具错误（run `64349dfbc9a749f9a232d547a1639746`）与 4 请求/1 个引用诊断 Verified Skip/0 工具错误（run `52831a5caaf0493d9e0a12a599641bfb`）。第一项模型并行调用未认证的 `list_inputs`，保守 barrier 阻止引用链跳过；第二项按顺序调用后才出现真实引用跳过。相同任务说明的 Shadow（run `3cf9e652a4fc49a2bc2d9ce03fdf46cd`）为 5 请求/1 候选/0 跳过；模型先误把 `source_id` 当 `citation_id`，工具拒绝一次后纠正，错误计入。报告 PDF 基线任务（run `3e726f63ef1c43ddb3b3dff4c5845e44`）为 3 请求、2 工具、0 错误、0 跳过，模型显式调用只读报告与授权导出，得到 75,162 字节合格文件头/哈希的新 PDF，输入 SHA 未变；该报告是空白合成夹具，内容质量未评审。四项共 18 次请求、代理估费 0.010313688 美元，包含全部正常调用；没有同题同提示的 Origin 成本对照，不能宣称新的实际降本比例。PDF 逐页视觉/链接审阅、真实私人报告的独立质量对照仍待完成。
