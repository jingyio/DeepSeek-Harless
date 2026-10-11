# 邮件与日程管理 Agent 当前交接

- 更新时间与交接人：2026-10-11，Codex。
- 目标与本次范围：首批8个任务版本验收设计已接受。本次按用户授权选择性恢复archive工具、固定依赖、接只读/本地预览场景并推送，不替代真实Demo或MGGA效果验收。
- 分支 / commit / 工作区未提交改动：`codex/email-calendar-demo`，基于远端main `bc1ecd5`；验收集`964d244`、工具恢复`bb1720d`均已推送，当前交接随后续提交同步。未创建PR、未合并main。实现位于此分支独立检出，原`feature/paper-submission`/`2368235`工作区未切换，其论文/Web改动不纳入。
- 已完成：从archive `810edf46872e190019667239cb4e5b6b85df8f99`恢复13个公共工具/授权脚本及4个旧测试，新增4项MCP合同诊断。Gmail搜索/消息/线程/批量读取、本地草稿；Calendar查询/忙闲/空档与候选复核、本地新建预览。新增`scenario.json`、真实账户只读`prompt.md`、来源清单与安装说明；18个工具不含发送/建会/打开确认页面。
- 已验证：macOS、Node22.22.3/npm10.9.8、Python3.12.14；`npm test`通过146项Python+67项Node，`npm run mail-calendar:check`通过22项（包含在67项内，不另加），`npm run smoke`通过18题/83来源且SDK初始化成功。场景预览通过，依赖/锁文件、来源摘要、工具名、链接、格式和提交差异检查通过。MCP合同诊断使用InMemoryTransport与固定工具替身，未验证真实Google账户或模型行为；Windows授权未验证。
- 实验结论：无新增真实效果结论。恢复后工具在诊断边界可调用，不等于第一批任务质量合格、可组合Motif已认证或真实请求/费用下降。测试不运行付费模型，未用模拟Provider替代行为验收；自动execute测试仍暂停。
- 配置与数据：入口`scenarios/mail-calendar-collaboration/scenario.json`，SHA-256 `efed3b755e2ec0c0612ffbe46f5f34109c16cf11f2d8b249fd483ece1868498f`；工具/依赖/授权说明`tool-readiness.md`，原始来源摘要`archive-source.json`，任务摘要`review/checksums.json`。私有诊断快照`.local/mail-calendar-tool-recovery-20261011-v1/config-snapshot.json`与预览，不推送。OAuth路径变量为GMAIL_OAUTH_PATH、GMAIL_CREDENTIALS_PATH、GOOGLE_OAUTH_CREDENTIALS、GOOGLE_CALENDAR_MCP_TOKEN_PATH；授权/token留在操作者服务器私有目录。
- 未完成与阻塞：本次未连接账户或圈定访问范围，不能直接宣称真实Demo通过。旧prepare-event只支持新建预览，既有提醒更新/取消仍需待审差异说明或补专用工具；真实偏好/事项状态、分页、线程完整性与新鲜性合同待验证。原人工发送/建会代码保留但默认场景不开放。每日调度、真实推送、独立认证库和通用组合未完成。
- 接手下一步：①协作者拉取分支后npm ci、npm run setup、npm run mail-calendar:check，再用npm run scenario -- --scenario scenarios/mail-calendar-collaboration/scenario.json --budget-usd 1仅预览；②服务器加载.local/remote-env.sh，按tool-readiness.md放私有客户端、授权并设置4个路径变量，圈定真实来源，首批题面实例化后用原生Harness验收质量；③正常轨迹有可认证结构再编译并冻结shadow评测，C01/C03后置组合，R组只压力诊断，不增加步骤凑比例。
- 权限与预算：用户授权本次工具恢复与Git推送；新增模型费用0、Google请求0、外部邮件/日历写入0。真实模型测试持续授权但运行前固定有效累计预算与输出/步数限制；此分支SDK默认0.25美元，文档显式示例1美元，未更改公共默认，不挪用论文8美元额度。账户内容范围、发送/建会/修改/推送未在本次执行。
- 回退与风险：恢复前分支`c9b84d3`，可按Git选择回退工具提交。完整archive与本地v2备份未上传；公开仅恢复审查后的工具/合成测试，凭证和原始日志不进入Git。Gmail保留scoped_gmail_request命名与历史元数据，但消息ID不能证明线程无新回复；旧成功轨迹不授权新任务接管或外部写入。
