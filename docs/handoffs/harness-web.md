# Harness Web 当前交接

- 更新时间与交接人：2026-10-09，Codex。
- 目标与本次范围：给 SSS 增加官方 Harness Web 的服务器入口；example 与历史库匹配的 portfolio 模拟闭环、单任务权限、预算与 Motif，保留 SDK。没有开发论文工具或完整聊天前端。
- 分支 / commit / 工作区未提交改动：PR 使用独立分支 `codex/harness-web`，基准为 `2368235f274329be6227a8393b850633cb943da4`；提交与推送状态以本 PR 的 Git 历史为准，合并状态以 GitHub 为准。验收时两端为 `feature/paper-submission` 加本次未提交代码。原工作区继续保留该分支，以及既有 AGENTS、README 环境说明、main 交接、服务器免费验收记录、论文交接、本地 reference 和其他后续开发文件；不纳入本 PR。
- 已完成：`npm run web`、`web:check`、指定 run 停止脚本；`config/harness-web.json` 与 TypeScript Web 策略；场景描述复用、SDK 预算代理复用及请求数限制；官方会话/preset/tool/llm 接缝。独立 DSH_HOME、认证地址和所有运行数据在私有 `.local/web/`。
- 已验证：服务器 Ubuntu 22.04 / Node 22.23.3 / Python 3.10.8；137 项 Python、30 项 Node、18 题/83 对象 smoke、`motif:check` 均通过。`web:check` 11 组原生会话诊断通过。实际本地浏览器执行 example 的四次 MCP 调用、刷新恢复、变题拒绝，以及 portfolio baseline/shadow/execute 的三组各 13 次 MCP 调用。浏览器请求对应模拟模型次数为 5、14/14/7；execute 5 个批次实际结果验证成功。原生 HTTP 200 单独不作闭环证据。
- 实验结论：`harness-web-v1-20261009`，见 `docs/experiments/harness-web-v1-20261009.md`。仅支持工具链、结构与协议有效，不是科研决定质量或真实费用收益。固定 embedding 是运输夹具；最终 portfolio 答案只验证对象/版本。
- 配置与数据：公共入口见 README/interfaces，安装固定 DSH `0.1.5-rc.3`。每个运行保存有效配置、实际请求、schema、事件、答案、指标、代理账本及 Motif 审计；本地验收资料在 `.local/web-review/`。没有读取/输出实际模型密钥。运行先 `source .local/remote-env.sh`。
- 已补验：浏览器请求上限 1 时，一次 MCP 后显示 HTTP 429，服务端记录 budget_exhausted；最终版本再次通过 11 组原生诊断与上述全部回归。配置记录包含实际模型请求值，输出另有会话头、任务绑定及稳定的 answer.json/answer.md。
- 未完成与限制：真实模型和预算确认 UI 未开放；不支持多账号、跨启动恢复旧任务、论文流程、Windows Web 或真实语义 embedding。官方新会话拒绝主要记浏览器警告，预算耗尽显示通用 HTTP 429，没有专用提示条。Web 的已认证文件能力面向服务器操作人，不是四位同学之间的隔离边界。仍依赖 Python 启动器/预算及已有纯代码节点执行。
- 接手下一步：1. 按 README 在服务器复验 `web:check`，本地浏览器复制固定题面；验收包括真实 MCP 和对应 ledger/audit。2. 团队审阅本 PR 的公共适配改动，CI 通过后再决定是否合并；不混入私人材料和其他开发工作。3. 如要开放真实模型，另实现预算/配置预览与明确确认，验证所有路由仍受服务端限制后再进行已授权的付费试验。
- 权限与预算：本次只授权免费模拟验收；新增实际费用 0。没有实际投稿、私人论文迁移或外部应用写入；后续付费预算与授权未知。
- 回退与风险：撤回本次新增入口和小范围共享适配即可保留 SDK 基线；不修改上游包、不要删除 `.local/`。前台 Ctrl+C 或按 README 停止指定 RUN_ID；停止会保留数据。只停止本任务进程，不能扫描/终止共享服务器上的其他开发任务。
