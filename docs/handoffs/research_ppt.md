# 科研 PPT 当前交接

- 更新时间与交接人：2026-10-14，Codex。
- 目标与本次范围：将科研 PPT 接入官方 Harness 主聊天，保留 `/ppt` 备用入口；主聊天接收上传和需求，后台执行双路交付，成品与后续同稿反馈返回同一聊天。
- 分支 / commit / 工作区：本次工作区为 `C:/Users/Xia/.codex/worktrees/research-ppt-main-sync/DeepSeekHarness`，基于 `origin/main` `6ade286` 与 `feature/research-ppt-agent` 已发布内容整理；提交后推送到 `feature/research-ppt-agent`，不创建 PR。H 盘旧工作区不覆盖。
- 分支核对：`origin/main` 已包含 broker session ID 修复和 PPT 私有库同步；`origin/codex/persistent-chat-recovery` 的 3 个会话持久化提交已纳入本次同步。邮件/日历、投稿、其他 RSI 分支与 PPT 主聊天无直接依赖，未混入。
- 已完成：新增 `scenarios/research_ppt/ts/native-chat.ts`，连接官方上传回执、Session 消息、预算预览、双路后台、进度/成品卡片、下载和同稿反馈；`src/adapters/dsh_web_tasks.ts` 仅在显式选择 PPT 且满足单用户准入时接管，其他场景仍走原生 Harness。`/ppt` 与主聊天共用后台、版本守卫和下载白名单。
- 交互契约：主聊天选择 PPT 后上传 PDF/PPTX、发送说明，收到预算卡片后确认；默认 15 页，支持 1–30 页，1–8 份输入。生成双路总上限 `$3`，每组 60 步/8000 输出 token；反馈双路每轮 `$0.50`，每组 24 步/4000 输出 token。思考与压缩关闭，运行中不生成新工具。纯提问只回答；改页必须给出明确页码或全部页面，按父稿版本生成新副本并保留历史稿。
- 身份与安全：主聊天桥接只启用 `local-operator` 且无成员 budget broker 的单用户服务；Session、上传回执、预览摘要、父稿 SHA、request ID 和版本逐项核验。用户不能提交任意 cwd、路径、租户或任务 ID。费用账本、来源、运行日志和私有文件只保留 `.local/` 与服务器受保护目录。
- 已验证（免费）：`npm run smoke` 通过；PPT TypeScript 构建通过；PPT 场景 117/118 通过，唯一失败是 Windows 未启用创建符号链接权限；主聊天、会话恢复、选择器、网关和预算定向 Node 测试 56/56 通过；仓库 `npm test` 164 项通过，剩余 1 项为 Windows 符号链接权限环境问题。`web:controls:check` 通过；本机 `web:tasks:check` 与 `web:scenes:check` 因本地 runtime/PPT Python 依赖未安装失败，服务器真实验收已另行记录。新增回归覆盖预览无付费、重复确认、回执归属、文字确认、同稿版本传递、取消/失败与持久映射。
- 已验证（真实）：实验 `research-ppt-native-chat-20261014` 使用 Attention Is All You Need，在官方浏览器主聊天上传、确认并生成两份 15 页可编辑 PPTX/PDF/逐页 PNG；34 个下载文件均通过鉴权和 SHA 校验，刷新后同一聊天状态恢复，第 4 页反馈完成版本与非目标页保持校验。优化结果优先返回用户，普通 DSH 仅作后台统计。
- 成本观察：普通 19 请求/707922 token/$0.03116531，优化 16/410206/$0.01853018；本次两路合计 `$0.04969549`，优化组相对普通组请求少 15.8%、token 少 42.1%、代理估费少 40.5%。这是固定宿主交付路径的单次观察，`verifiedskip=0`，未归因新增 RSI；人工审美/科学质量盲评和账单实付仍未知。
- 实验与报告：V1–V17 报告和负例在 `docs/experiments/research-ppt-reports/`；本轮记录为 `docs/experiments/research-ppt-native-chat-20261014.md`。本轮不覆盖旧轨迹、不重签历史证书。
- 未完成与边界：多账号 PPT 后端、图片插入、无完整计划的任意外部 PPTX 保真改页、模糊/中文数字页码定位、网页反馈自动晋级暂缓。不能宣称任意可解析 PDF 必然生成、科学内容必然正确或每条消息必然降本。统一启动器暂不自动复用旧 run 的主聊天映射；保留原 DSH_HOME 后 `/ppt` 可恢复后台任务。
- 接手下一步：同伴前端复用 `frontend-integration.md` 的上传、预览/确认、状态、下载和反馈接口；部署前用最新 commit 重建服务并验证 Harness 认证、单用户状态目录和私有 API key。若要跨完整重启恢复主聊天，需增加 run-id/DSH_HOME 复用契约并单独验收。
- 回退与风险：回退到推送前 `feature/research-ppt-agent` 的 `82e1376`；不清理 `.local`，不触碰服务器其他运行目录。当前是可信单用户开发入口，机械交付通过不等于科研质量审阅通过。
