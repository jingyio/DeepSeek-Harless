# 论文校对当前交接

- 更新时间与交接人：2026-10-17，Codex。
- 目标与本次范围：复用已有 `/paper`、原生任务轨迹、Python 编译器及 Shared RSI Runtime，自动连接“任务完成→编译认证→私有版本→下一任务”。不增加 Agent 循环、认证管理或第二套轨迹存储。
- 分支 / commit / 工作区：`codex/web-paper-auto-learning`，基于 main `547be11`；最终提交与 PR 见 Git/PR 回执。用户桌面协作者分支未改，生产服务未动。
- 已完成：`dsh_web_tasks.ts` 完成通知/冻结版本，`harless_paper_learning.ts` 后台协调与版本准入，`learn-web-paper-tasks.py` 重用已有编译器；`web_task_budget.py` 只投影当前路由的结算回执，不重置累计用量。任务事件起点排除历史对话；不可变 round、固定留出、去重和失败状态按现有隔离目录保存。其他场景自动学习不在范围。
- 已完成：保留 main 四档思考、六项通用能力、24 个论文工具、三模式与 RSI Off。Paper v3 / PPT r10 免费重编原证据兼容当前锁；原 v2/r9、历史 Paper Shadow 库和所有私人材料保留。修复已有“不生成 PDF”否定识别与 Prompt 冲突、后台写日志关闭异常。
- 已验证：最终 V100 全量 `npm test` Python 1,032/Node 797 通过，Node 3 跳过。两个真实成员 bubblewrap、10 草稿跨用户拒绝及各自私有学习编译/加载通过（合成事件、零模型）。`smoke`、`motif:check`、`web:controls:check`、`web:scenes:check` 均通过，后者含 30 种选择组合与 28 项有效冻结预览。
- 实验结论：[自动学习验收](../experiments/web-paper-auto-learning-20261017-v1.md)。真实论文原书目四份摘录，三次 Baseline 后自动发布，后续 Execute 冻结 round-0001、1 次验证跳过、0 工具错误。首轮两个导出错误完整保留；两轮共 55 请求/$0.051121236 代理估费。质量未独立审阅，不能宣称完整论文或持续降本通过。
- 配置与数据：Registry `config/harless-scenes.json`；静态 `HARLESS_PAPER_RUNTIME_BUNDLE`、历史排版 `HARLESS_PAPER_RENDERER_ROOT` 沿用。实际候选在 V100 `.local/integration/web-paper-auto-learning-20261017`，原题/结果 `.local/auto-paper-real-20261017{,-v2}`；材料、密钥、原始事件不入 Git。私有版本位于本账号当前运行 `output/learning/<user+scope hash>/round-NNNN`。
- 未完成与阻塞：仅支持固定来源后默认第一页读取，重复问题/源任务不计独立证据，至少两训练/一留出；生成新版本不代表覆盖增长或降本。换新运行目录不迁移旧私有版本，其他场景没有自动学习；前端新增状态面板未做。正式共享预算服务需同步回执接口，本次没有重启。
- 接手下一步：1）审阅 PR 与双平台 CI；2）如批准部署，同步代码/回执接口和 owner/member 配置，保护原账本与用户文件；3）小流量真实业务记录新任务/覆盖/费用及失败，不扩大到任意脚本执行。
- 权限与预算：沿用真实论文实验持续无限额授权，仍逐请求记账；不扩大外部写、私人原件或投稿权限。新 PR 目前无生产部署/合并动作。
- 回退与风险：回退本分支代码和 Registry 至 `547be11`；保留所有私有 round、任务、费用及失败证据。原库旧代码锁会随代码变化拒绝，不能只改哈希假认证；按现有真实证据重新编译或回退匹配代码。
