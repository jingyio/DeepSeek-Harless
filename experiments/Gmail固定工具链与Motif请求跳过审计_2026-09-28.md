# Gmail 固定工具链与 Motif 请求跳过审计

日期：2026-09-28。用户指出邮件任务中 MCP 工具选择通常稳定，要求检查这是否比反复调文献任务更适合 SSS。此文件只审计已安装工具与执行边界，不声称已经得到 Gmail 真实任务的 Motif 收益。

## 实际工具与可复用性

本机 Gmail MCP 当前列出 13 个工具：8 个只读工具，以及 `prepare_email`、`list_prepared_emails`、`get_prepared_email`、`open_email_review`、`send_email` 五个本地待审工具。只读工具包括 `search_emails(query)`、`read_email(messageId)`、`get_thread(threadId)`、`list_inbox_threads(query)`。`send_email(to, subject, body, replyToMessageId?)` **一次调用就会准备本地邮件并打开审核页**，返回 `sent:false`；实际发送由研究者在页面确认。工具清单已通过 `doctor-mcp.py --list-only` 核验；该命令的整体退出码为 1 是因为没有常驻 DSH 监听，Gmail 服务本身列出了 13 个工具。

首次真实只读查询卡在网络：shell 没有代理环境变量，直连 `gmail.googleapis.com`、Google Calendar 和 OAuth 域名均在 8 秒内未建立连接，而 macOS 系统配置的 `127.0.0.1:7890` 代理能在约 0.6–0.8 秒返回这些域名的 HTTP 状态；DeepSeek 域名可直连。Gmail 桥接现在仅在没有显式代理变量时继承 macOS 的 HTTPS 代理，并让 localhost 绕过代理；另给上游只读调用加 25 秒失败返回。修复后不注入任何手工代理变量的 `search_emails` 在约 4 秒返回非错误结果。测试未发送或修改邮件，也未把私人邮件内容写入仓库。该问题是连接路径，不能归因为 OAuth 权限或 Motif。

第二个阻碍是上游 Gmail MCP 把搜索和读取结果包成纯文本 `<untrusted-tool-output>`，没有可供 Motif 编译器读取的结构字段。桥接现在只在搜索结果严格符合上游布局时提取消息 ID，附上有序 ID 列表的 SHA-256；读取结果只从首行提取线程 ID，并把请求中的消息 ID 作为不变来源身份。原始文本完整保留给模型，正文、主题或发件人不会进入结构字段；格式异常、重复 ID 或插入额外行时不生成结构字段。3 项解析守卫测试通过；用已有自发自收测试邮件实际调用 `search_emails → read_email(headers_only)`，确认搜索恰有 1 个结构化 ID、读取 ID 与输入一致、线程 ID 可见且原文保留。没有发送或修改邮件。

邮件链中的参数关系很清楚：搜索结果的 `threadId` 可成为 `get_thread` 的输入；选定原邮件的 `messageId` 可成为 `read_email` 或 `replyToMessageId` 的输入；`prepare_email` 的审阅 `id` 可成为 `open_email_review` 的输入。这些关系有复用价值，但**参数能复制不等于能省一次模型请求**。例如模型读完邮件后还要决定正文，下一轮模型不可跳过。现有公平基线能直接调用 `send_email`，已合并准备与打开审核页；人为要求基线先 `prepare_email` 再 `open_email_review`，会制造一个本来不必存在的模型轮次。

## 下一步要找的真实机会

应从研究者真实邮件任务的普通 Harness 轨迹观察，而非先写固定 DAG。优先找搜索或收件箱结果返回**唯一**线程／消息 ID、下一轮模型只负责按该 ID 读取、其后才依据内容撰写回复的情况。先前模型选定的查询、邮件权限、消息身份与版本必须可核验；多条候选邮件、回复对象不明、附件解释或正文撰写仍由模型／人决定。若 `get_thread` 已返回全部所需内容，或普通 Harness 首轮直接读取了指定 ID，便没有可跳过的中间请求。

当前在线 Motif 清单只认证只读的 Zotero 固定来源→读取边；**没有 Gmail 真实科研任务轨迹、Gmail 参数边认证或邮件写入 Motif**。结构化 ID 只是让将来的参数来源可审计，不会自动注册 `search→read` 为 Motif。运行时要求 `read_only=true`，不会自动准备、打开或发送邮件。要声称 Gmail 收益，至少需要不同真实邮件决定的普通轨迹用于编译，再用留出任务比较：合格回复、实际 API 请求数、缓存计价费用、工具失败和人工审核时间。发送的人工确认永远不能被 Motif 计作跳过。

因此下一步是 Gmail 只读搜索／读取阶段的实际轨迹采集与参数来源审计；若它没有产生完整结构轮次，就把邮件写入作为产品功能而非 Motif 成本效果样本。日历安排和 Obsidian 状态同步也应按相同标准检查。
