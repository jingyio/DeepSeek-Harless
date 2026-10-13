# 官方真实聊天预览确认验收

- 实验 ID：`native-chat-confirm-20261009-v1`，2026-10-09，Codex。
- 问题与假设：用户在官方聊天发送消息得到 `Preview and confirm the budget in /tasks before paid execution`。此前只验证了任务工作台；原生真实聊天被直接拒绝，不能把工作台通过当作官方聊天可用。假设公开 Web 插件可接入原生提示入口并展示确认框，同时保持确认前零模型请求。
- 实现：TypeScript 将官方 `session/prompt` 登记为 `entrypoint=native_chat` 的待确认任务，保持原 Session、请求 ID 和不可变摘要；通过 `tapIndex` 在真实模式注入确认框。用户显式确认仍走原任务 API，随后才调用官方 Controller.prompt；取消不调用模型。无上游 Harness 核心修改。`/tasks?task_id=...` 可恢复同一预览，任务卡增加确认入口，预算表单读取实际服务器上限。
- 对照与范围：example 公开合成笔记，baseline，非真实论文生产任务、非收益对照。通过官方 HTTP RPC 发送和重试提示，再以任务 API 确认；确认界面单元模拟检查了题面/预算显示及重复点击幂等。浏览器自动操作被安全策略拒绝，没有完成真实浏览器点击验收。
- 配置与复现：实际服务器仍 `feature/paper-submission` / `2368235f274329be6227a8393b850633cb943da4` 加公共未提交适配，三份源码 SHA 在私有 configuration.json。固定 DSH 0.1.5-rc.3、deepseek-flash、reasoning off、1000 输出上限、24/256 次。运行 `ebd724e8f4464b72b5cbc797210da350`，3086，每任务及启动均 0.247 美元。启动命令 `npm run web:real -- --port 3086 --budget-usd 0.247 --run-budget-usd 0.247`；先加载服务器 `.local/remote-env.sh`，密钥从私有 `.env` 提供。
- 预算承接：前次运行 `9ea9d68a37a44627ad3ab1d545678c37` 的两项任务均结束，估费 0.002484720 美元，原总限额 0.25；本次新启动上限 0.247，小于剩余 0.24751528。原账本保留，不通过重启抹掉支出。
- 结果：官方原生 prompt 与相同 requestId 重试均 accepted，仅登记一个 awaiting_confirmation 任务，模型/工具调用均 0；错误摘要被 HTTP 409 拒绝，仍为 0。正确确认后任务 `46ccc0d3b7004a6dbdabe5ed2c5b62df`、Session `session-8052df01-6682-4b15-8cc4-2176dea51bcb` completed；3 次真实请求、4 次 MCP、0 工具错误，来源 ID 与完整版本哈希逐项一致。第二项未确认原生任务取消成功、0 模型请求。
- 用量与质量：prompt 3701（hit 2688 / miss 1013）、output 954、total 4655；任务统计 6.25 秒，代理估费 0.001464828 美元，账单实付未核对。连同前次两项测试累计估费 0.003949548 美元。来源核验通过，质量未独立盲评，verified skips 为 0，不支持 Motif 降本结论。
- 自动诊断：服务器 `npm test` 146 Python / 45 Node 通过；动态 HTTP/MCP 13 组通过；最终原生确认文件 8 项单元通过，前端脚本语法通过。这些诊断使用确定性夹具，模型效果证据仅来自上面的真实调用。官方 HTML 含确认脚本，root 容器独立，未发现 CSP 阻止内联脚本；这仍不等于真实浏览器点击通过。
- 证据：两端 `.local/experiments/native-chat-confirm-20261009-v1/`，含 configuration.json、verification.json、task.json、answer.md；服务器本次运行目录保留事件、账本和模型配置。认证 URL 不公开，使用更新后的私有 access-url.txt。
- 结论与边界：原生真实聊天的预览、确认、工具执行和取消链路已观察通过；负责人须使用新认证地址重新登录、新建会话，确认实际弹窗与答案展示。当前仍一 Session 一任务，后续新要求需新任务/会话；多用户、持续对话、跨启动恢复及科研交付质量不在此次验收中。
