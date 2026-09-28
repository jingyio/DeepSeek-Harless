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

## 2026-09-28 自发自收请求诊断

构造了一条有边界的真实 Gmail 请求：从已有的 SSS 自发自收测试邮件中搜索并读取唯一消息，核对收件地址，再准备一封**新的**研究进展邮件供本人审阅。旧邮件明确写有“无需回复”，因此任务没有要求回复它。允许的 Gmail 工具限于 `search_emails`、`read_email`、`prepare_email`、`get_prepared_email`；搜索词、可读消息 ID、唯一收件地址分别锁定在 `.local/benchmarks/research-weekly-loop/gmail-request-pilot-20260928/scope.json`。任务原文和原始轨迹仅保存在该忽略目录，不入 Git。`prepare_email` 只写本机待审队列，本次没有调用发送或打开审核页。

正常 DeepSeek Harness 运行的四轮依次是：搜索、用搜索结果的 ID 读取、依据邮件及已核实的实验事实写本地待审草稿、报告草稿状态。实际调用 Gmail MCP 3 次，DeepSeek Flash 4 次，`reasoning_effort="off"`；未命中输入 4,960 token、缓存命中输入 13,440 token、输出 810 token，用时 13.869 秒。根据逐请求 API usage 和当前计价估算费用为 **US$0.00254063**，不是与控制台对账后的账单。完整预览、模型输出、事件与预算账本分别位于上述目录的 `preview.json`、`baseline/answer.md`、`baseline/agent-events.jsonl` 和 `baseline/metrics.json`，运行入口是 `scripts/run-gmail-request-pilot.py`；本次预算门槛为 US$2。

这一轨迹说明第二轮有**潜在的整次请求跳过机会**：查询已经由第一轮选定，搜索只返回一个消息，第二轮只是把返回的消息 ID 填入 `read_email`。第三轮需要撰写正文，仍是语义工作；第四轮只做状态报告，但普通确定性 UI 也可能完成，不能直接归功于 Motif。完整基线是 4 次请求，不是零模型任务。

初次运行还发现 DSH 的 `tool/result` 丢弃 MCP `structuredContent`。桥接虽然提供结构化 ID，轨迹适配器却看不见，因此初次轨迹中的读取被标记 `missing_parameter_provenance`。修复后，桥接在保留完整原文的同时，给经过严格解析的搜索／读取元数据加固定标记；在线与离线适配器只对本试验的 scoped Gmail 工具解析该标记。一次独立的**同消息技术复跑**实际再次搜索并读取：3 次 Flash 请求、2 次 Gmail MCP 调用，未命中输入 4,525 token、缓存命中 8,320 token、输出 285 token、用时 12.476 秒，估算 US$0.00174942；轨迹适配器确认 `read_email.messageId ← search_emails.message_ids.0`，两个只读节点均合格。技术复跑不算第二项研究决定或留出任务。

这仍**不是 Motif 已经跳过了请求**。当前 Gmail 搜索结果随收件箱变化，合同标记 `replay_stable=false`，现有认证编译器不会把它当成可直接重放的来源；而且只有一条独立邮件任务，缺少跨任务认证与留出验证。可以从“模型已发起搜索，运行时观察到唯一新鲜 ID 后接管读取”这一边界设计动态来源锚点，但不能把本次重复访问同一封邮件伪装成迁移证据。下一次效果试验需用不同真实邮件决定的普通轨迹认证该边，并比较原生 Harness、Motif、直接脚本／缓存在合格交付下的请求数和总成本。
