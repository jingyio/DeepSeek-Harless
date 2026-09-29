# 科研工具 MCP 接入

## 任务范围内的来源句柄（实验性）

针对真实科研任务，`src.mcp.scoped_obsidian_read_server` 可在 `SSS_SCOPED_HANDLE_MODE=1` 时只暴露 `pin_scoped_source → read_pinned_note/text/pdf_pages` 等受限读取工具；另有独立的 `src.mcp.scoped_zotero_read_server`，暴露 `pin_scoped_zotero_source → read_pinned_zotero_item/annotation`，并可用 `lookup_scoped_zotero_item(identifier)` 将明确的 DOI／arXiv ID 匹配到**任务已批准**且版本未变的唯一条目。未命中不扩大搜索范围，多项匹配则拒绝自动选择。两者以 `.local` 中的任务 scope 圈定确切来源和 SHA／Zotero 版本，读取时重新核验授权与版本，返回不透明 `source_id`。工具契约分别在 `config/scoped-research-handle-contracts.json` 和 `config/scoped-zotero-handle-contracts.json`，轨迹审计可重复传入 `--contracts` 合并。Zotero 受限服务是**另一个可选的只读 MCP**，未加入下面默认工具目录，也不替代现有 Zotero 桥接；未批准的私人摘录不会被暴露。`read_pinned_approved_note_excerpt(source_id)` 可直接读取 scope 已批准的笔记行段（最多 120 行），无需模型猜行号；没有明确行段、版本变化或权限变化时拒绝读取。

这些接口已通过本地伪来源的版本／授权失效测试；Model RSI 真实批准来源的 Obsidian pin→read 已在无模型 MCP 客户端调用中验证。Zotero pin→read 尚未对用户私人条目开放模型试验，且目前没有两个应用的真实 DSH 参数链。因此，接口可用不等于已挖到跨任务 Motif。

受限 PDF 来源另提供 `locate_pinned_pdf_quote(source_id, quote)` 和 `read_pinned_pdf_match(match_id)`：前者只扫描本任务批准的文件页，按精确引文匹配；仅有一个匹配页时生成带来源及 scope 版本的 `match_id`，后者据此读取该页。多页命中或未命中只返回候选／缺口，不自动决定科学相关性；PDF 是扫描件、抽取文字失真、引文改写或跨页断句时可能找不到。`match_id` 可在实际工具轨迹中为后续读取提供可核验的参数边，但还没有据此认证新的跨任务 Motif。2026-09-27 无模型检查中，P1 已批准的六条 Zotero 高亮分别在批准 PDF 页内唯一定位；MCP 客户端完成一次 pin→locate→read，未向模型发请求。本工具只加入可选的受限来源服务，当时的默认 87 工具清单不变。

`npm run dev` 会按本机准备情况连接多个 MCP 服务，工具在 DeepSeek Harness 中分别以 `mcp__local_research_tools__`、`mcp__literature_discovery__`、`mcp__zotero__`、`mcp__obsidian__`、`mcp__google_calendar__` 和 `mcp__google_gmail__` 为前缀。`local_research_tools` 只是 Python、文件与 Quarto 的适配层，不是 SSS 核心运行时；编程环境本身也不依赖 MCP。早期调研 MCP 原型已删除；MotifAgent 主控内核仍在迁移。跨服务的逐步骤工具切换尚未实现。

一个 MCP 服务可暴露多个工具。当前代码的默认清单为 **90 个**：Zotero 21、Obsidian 19、Gmail 13、Google 日历 13、本地 Python／Quarto／结构化核查 13、文献发现 11；配置第三方 Google Scholar 接入后为 91 个。新工具要重启 Harness 才会出现在新会话；旧会话的工具清单不变。Zotero 上游虽列出 41 个工具，但本机 Zotero 9 不支持本地写入，桥接层仅暴露 21 个读／能力检查工具。Gmail `send_email` 和日历 `create-event` 都只准备本机待审项，实际写入必须由人在浏览器页面确认。清单数量不是已验证能完成任务的能力数量；后续评测应记录每个工具的实际调用成功率和任务贡献。

| 服务 | 当前能力 | 启用条件 |
| --- | --- | --- |
| Python + Quarto + 结构化核查 | 13 个本地编程、文件、渲染及有版本的只读数据工具 | 本机 macOS `sandbox-exec`、Quarto；常用分析库用 `npm run connectors:setup` 安装 |
| 文献发现 | arXiv 主题与编号检索及限页 PDF 正文读取、OpenAlex 检索与被引、Crossref 核对、Europe PMC 开放全文，默认 10 个只读工具 | 公网可用；默认无需 API key；Google Scholar 第三方接入需独立凭据与预算 |
| Zotero | [zotero-mcp-server 0.13.1](https://github.com/54yyyu/zotero-mcp) 的本地 MCP，经读工具桥接 | Zotero 正在运行且本地 API 可访问；`npm run connectors:setup` |
| Obsidian | [Local REST API 插件](https://github.com/coddingtonbear/obsidian-local-rest-api)自带的 MCP | 在所用 vault 安装并启用插件，然后 `npm run obsidian:connect` |
| Google 日历 | [@cocal/google-calendar-mcp 2.6.3](https://github.com/nspady/google-calendar-mcp) 读取 + 本机待审事件队列 | 保存 OAuth 桌面客户端凭据并完成 `npm run calendar:auth` |
| Gmail | [@klodr/gmail-mcp 1.2.0](https://github.com/klodr/gmail-mcp) 读取 + 本地待审邮件队列 | 启用 Gmail API，保存 OAuth 桌面客户端凭据并完成 `npm run gmail:auth`；发送另需独立授权 |

## 本机安装

```text
npm install
npm run structure:setup
npm run connectors:setup
npm run dev
```

另开终端运行 `npm run connectors:doctor` 可逐一连接六个 MCP、核对工具数量并执行一次代表性的**只读**调用；`npm run connectors:doctor -- --list-only` 只检查工具清单。检查结果只输出服务状态、数量和成功／失败，不打印邮箱、笔记、文献内容或令牌。它检查的是当前连接器进程；DeepSeek Harness 是否正在监听也会单独显示。该检查不会调用付费模型，不会发送邮件或创建事件。

Zotero 连接使用其本地 API，不配置云端 Zotero 密钥，也不启用外部嵌入模型。本机 Zotero 9.0.6 的本地写入 API 不受支持；上游 `zotero_write_capabilities` 已实际返回 `mode: none`，默认桥接层隐藏上游不可用的写工具。Zotero 官方说明 [10 起可在用户授权后本地写入](https://www.zotero.org/support/dev/web_api/v3/local_api)；升级用户资料库前应先备份和单独验收，当前不把写入计入已完成能力。

## 文献发现

常规入口是 `search_arxiv`（主题、题名、作者或摘要词）、`get_arxiv_paper`（arXiv 编号）、`read_arxiv_pdf_pages`（指定 PDF 版本的有限页正文），以及 OpenAlex 的 `search_works`（普通关键词）。当 arXiv 检索或 OpenAlex 不可用时，`search_crossref_works` 可按题名或书目信息查找有 DOI 的候选，再用 `verify_doi_metadata` 核对选中的 DOI；后者保留 Crossref 的预印本／期刊版关系、`asserted_by` 与归一化的 `assertion_source_doi`。Crossref 会自动在另一条 DOI 记录显示反向关系；两边都有关系字段不等于两家出版方各自断言，也不证明正文版本差异。Crossref 的结果不能覆盖没有 DOI 的预印本，也不提供论文正文。研究者无需先知道 DOI；它只在可用时帮助核对元数据、合并重复记录、连接 Zotero 与开放全文。arXiv 预印本可以没有 DOI。arXiv 题录结果缓存一天；PDF 按版本缓存在 `.local/`，最多下载 20 MB，每次最多读取 3 页并返回内容哈希与页码。PDF 文本抽取可能漏图表，关键图需视觉复核。检索按 [arXiv 官方接口建议](https://info.arxiv.org/help/api/user-manual.html)控制连续请求间隔。

另有 OpenAlex 的 `get_work`、`get_citing_works`，Crossref 的 `verify_doi_metadata`，以及 Europe PMC 的 `find_europe_pmc_fulltext`、`list_europe_pmc_sections`、`read_europe_pmc_section`。后三者目前仍按 DOI 找到开放全文候选，再按 PMCID 实际验证、列章节、读取最多 8000 字符的片段；这是全文定位能力的限制，不是研究者发现论文的前置要求。结果带原始接口 URL、检索时间、内容哈希和缓存命中状态。全文 XML 限制为 6 MB，缓存只写入 `.local/literature-cache/`，7 天内复用、过期后重新抓取；不能把元数据或片段自动当作已核验的科学结论。[Europe PMC 官方接口](https://europepmc.org/RestfulWebService)只为其开放获取子集提供全文 XML。默认无账号、无付费 API key；公共接口可能限流，遇到 `429` 会报告错误，不自动无限重试。查询词、DOI 和 PMCID 会发给公开服务，私人笔记及 PDF 不会由此 MCP 上传。若未来提供 `OPENALEX_API_KEY`，必须先核对账户预算。

Google Scholar 没有面向本项目的官方检索 API；其[官方帮助](https://scholar.google.com/intl/en/scholar/help.html)要求自动访问遵守 robots 规则，也不提供批量记录访问。为避免不稳定的网页抓取，`search_google_scholar` 仅通过[第三方 SerpAPI](https://serpapi.com/google-scholar-api)提供。默认不暴露这个工具。需要自备 SerpAPI 账号，把 API key 写入 `.local/serpapi-api-key`、每月最多可调用次数写入 `.local/serpapi-monthly-search-budget`（正整数），文件仅当前用户可读，然后重启 `npm run dev`。本机账本 `.local/literature-cache/scholar/usage.json` 先预留调用额度再请求；失败或结果不明也计一次，以免超额自动重试。第三方的实际套餐、费用和剩余额度仍须在账号页面确认，本机上限不等于供应商计费上限。此接入尚无用户凭据，因此只完成模拟测试，未做真实 Google Scholar 查询。

Python 代码和 Quarto 输出位于 `.local/python-workspace/`。两者的子进程在本机 macOS 沙盒里运行，不能使用网络，不能写入该目录以外的位置；可读本机普通文件，但明确阻止读取本项目的 Obsidian、Google 日历、Gmail 和 Harness 凭据目录，以及常见的本机密钥目录。分析数据建议先放在明确的任务目录，生成内容由人复核后再保存到正式交付位置。此运行方式尚未支持 Windows/Linux。

同一服务现有七个通用只读数据工具：`list_research_sources` 列出限定目录内的文件名与大小；`pin_source` 固定允许目录中研究文件的 SHA-256 并返回 `source_id`；`inspect_records` 读取 JSON 记录数组或 CSV/TSV 的字段与记录数并返回 `dataset_id`；`aggregate_records` 按 Agent 指定的分组、过滤和统计式返回 `result_id`，包括 Pearson 与带平均秩并列处理的 Spearman 相关系数；`rank_grouped_result` 对已保存统计按明确的分层与类别核对排名；`compare_sources` 检查两份文件是否逐字节相同；`compare_results` 比较两份同口径聚合。输入文件仅允许在 `.local/benchmarks/`、`.local/python-workspace/`、`reference/`、`experiments/`，每份最多 48 MB；旧编号每次使用前都重新哈希，来源变化会停止调用。编号映射只保存在受保护的 `.local/structured-research/`，不进入 Git。它们不选择科研问题、不推断因果、也不替 Agent 决定哪些论文或数据可比。工具契约见 `config/structured-research-tool-contracts.json`；轨迹适配器可从结果编号到下次参数的精确相等与事件顺序推断参数来源，缺少可验证来源的链不能编译。三类真实核查轨迹与局限见 [实验记录](../../experiments/结构化MCP三类真实数据核查记录.md)。

若 JSON 顶层有多个记录数组且调用未指定 `records_path`，`inspect_records` 的 MCP 错误会列出有界的候选路径、记录数和字段名。Motif 运行时可将同一情况转换为有类型的单选语义交接；模型只能在候选路径中选择，返回列表或陌生路径会被拒绝，来源改变也会阻断恢复。

## Obsidian

在目标笔记库的“第三方插件”中安装并启用 `Local REST API`。插件提供 `https://127.0.0.1:27124/mcp/`；所需 API key 在插件设置中。运行 `npm run obsidian:connect`，在本机提示符输入 key。脚本验证接口并把 key 和插件证书存入 `.local/`，权限设为仅当前用户可读；重启 Harness 后才会出现 `mcp__obsidian__*` 工具。无需在仓库中提交 key，也不需要启用明文 HTTP 端口。

插件需要安装到**具体 vault**；仅启动 Obsidian 应用并不会自动提供 MCP 服务。如果有多个 vault，先在预期的 vault 中安装和启用插件。

## Google 日历

在 Google Cloud 中启用 Calendar API，创建 **Desktop app** 类型的 OAuth 客户端，并把自己的账号加入测试用户。将下载的 JSON 放在 `.local/google-calendar/oauth-client.json`，然后运行 `npm run calendar:auth` 完成本机浏览器授权。令牌保存在 `.local/google-calendar/tokens.json`，重启 `npm run dev` 后日历工具才会出现。OAuth 文件和令牌都被 `.gitignore` 排除。macOS 上若已配置系统 HTTPS 代理，授权和 DSH 启动脚本会自动沿用；其他系统需自行设置 `HTTPS_PROXY`、`HTTP_PROXY` 和 Node 的 `--use-env-proxy`。

本机桥接向 Agent 暴露 9 个读取／计算工具与 4 个本机待审事件工具。新增的 `find-available-slots` 会即时读取 Google 忙闲并计算指定窗口、时长内的最早连续空档；`validate-slot` 会重新读取忙闲，分别报告候选是否满足时长、窗口和无冲突，以及是否最早。它们只针对一个明确的日历 ID，返回来源哈希和查询时间，不创建事件，也不代替研究者判断会议对象或排期偏好。待审工具为 `prepare-event`、`list-prepared-events`、`open-event-review`、`create-event`。后者只准备事件并打开临时浏览器审核页，返回 `created: false`；研究者核对日历、时间、参与者和说明，并输入 `CREATE <完整审阅编号>` 后，才调用 Google Calendar API。审核页 2 小时后失效，待审事件可用原编号重新打开。参与者非空时 Google 可能发送邀请，审核页会明确列出参与者。结果不明时状态为 `uncertain`，禁止自动重试。第三方 MCP 即使启用内置工具白名单仍会额外暴露 `manage-accounts`，因此桥接还会拒绝该工具的调用。所用第三方 MCP 的 OAuth 流程仍请求 Google Calendar 完整权限；工具过滤不等于缩小 Google 授权范围。

首次授权、测试模式下的后续重新授权，以及账户权限取决于 Google 配置。未提供 OAuth 客户端文件时，Harness 会跳过日历 MCP，不会使其他服务启动失败。

## Gmail

在 Google Cloud 中启用 Gmail API，把自己的账号列为 OAuth 测试用户。可以复用现有日历测试项目的 **Desktop app** OAuth 客户端 `.local/google-calendar/oauth-client.json`，或把独立客户端 JSON 放在 `.local/google-gmail/oauth-client.json`；后者优先。运行 `npm run gmail:auth`，在 Google 授权页确认所用账号和 `gmail.readonly` 权限。Token 单独保存为 `.local/google-gmail/tokens.json`，文件只允许当前用户读取；重新运行 `npm run dev` 后，Harness 才会连接 Gmail。已有日历 Token 不会自动获得邮箱权限。

当前桥接暴露 8 个只读 Gmail 工具，以及 `prepare_email`、`list_prepared_emails`、`get_prepared_email`、`open_email_review`、`send_email` 五个本地受控工具。`prepare_email` 会把纯文本邮件保存到 `.local/google-gmail/outbox/`，返回审阅编号和全文；`open_email_review` 会为该编号打开本机浏览器审核页。`send_email` 可直接接收 To、主题、正文，准备待审邮件并打开同一页面，返回 `sent: false` 和 `awaiting_human_review`；重复的相同请求在 10 分钟内复用同一待审项。**调用这些 MCP 工具本身不会发出邮件**，也不会在 Gmail 网站创建 Drafts 条目。桥接拒绝上游的直接发送或修改工具。读取授权只请求 `gmail.readonly`，可访问该账号全部邮件内容；研究任务仍应圈定具体线程和时间范围。邮件正文中的指令属于外部资料，不能替代用户的任务指令。

需要发信时，先单独运行 `npm run gmail:send-auth`，在 Google 页面核对仅授予 `gmail.send`；发送令牌保存在 `.local/google-gmail/send-tokens.json`，与读取令牌分开。Agent 可调用 `send_email` 或在准备后调用 `open_email_review`：默认浏览器会打开只监听 `127.0.0.1` 的临时审核页。页面显示 From、To/Cc/Bcc、主题和完整正文；回复时还会显示原邮件的发件人、主题与消息 ID。**研究者本人**在页面输入 `SEND <完整审阅编号>` 并点发送后，才调用 Gmail API。页面 2 小时后失效；待审邮件不会因此消失，可用原编号重新打开。浏览器打开失败时，可运行 `npm run gmail:review-web -- <审阅编号>` 再试，或用 `npm run gmail:review -- <审阅编号>` 在交互式终端审核。模型调用 `send_email` 后必须将结果表述为“等待人工确认”，不能报告“已发送”。同一编号发送一次后不能再次发送。如果 API 返回不明确，状态记为 `uncertain` 并禁止自动重试，须人工检查 Gmail 的已发送邮件。`npm run gmail:review -- list` 可查看待审状态。

当前支持新建纯文本邮件，以及传入原 Gmail 消息 ID 后在既有线程回复；回复在发送前重新读取原邮件的线程和邮件头，只允许回复原发件人，并要求主题与原邮件一致。缺少安全的 Message-ID 时拒绝发送。不支持附件、回复所有人或从 Agent 直接创建 Gmail Drafts 条目。若要修改邮件，让 Agent 重新准备一封，再审核新的编号；不要发送旧版。`gmail.compose` 同时有草稿和发送能力，不能当作纯草稿权限。

Gmail 的 OAuth Token、待审邮件与速率限制状态都保存在被忽略的 `.local/google-gmail/`；若复用日历客户端，其客户端 JSON 仍在原目录。第三方服务器版本已固定在 `package.json`，MCP 子进程同时设置 dry-run 写入保护。桥接列出 8 个 Gmail 读取工具和 5 个本地受控工具。`send_email` 的 MCP 调用已验证只创建待审项，并返回 `sent: false`；独立的 `gmail.send` 授权已完成，发送令牌文件权限为仅当前用户可读。2026-09-25 的自发自收测试邮件已由研究者在审核页确认发送，本地状态为 `sent`，保存了 Gmail API 返回的消息 ID；随后通过只读 MCP 按 ID 成功读取邮件头。此验收不代表其他收件地址或附件已测试。

## 验证与限制

已验证：Zotero 上游列出 41 个工具，默认桥接实际列出 21 个；`zotero_get_recent` 成功，写入能力检查确认本机不可写。Obsidian HTTPS MCP 列出 19 个工具，`vault_list` 成功，并已通过 MCP 创建、读取、永久删除一篇专用临时测试笔记。日历桥接当时列出 11 个工具，`list-calendars` 成功，待审事件本地测试验证重复提交拦截；新增空档计算和校验后现列出 13 个工具，并已在真实测试日历上完成两种桥的只读调用验收；实际事件仍需在审核页由人确认。Gmail 桥接列出 13 个工具，真实标签读取、人工审核发送、自发自收邮件的只读回查成功。Python 的 pandas 分析与 Quarto HTML 渲染成功。文献发现 MCP 原有 OpenAlex／Crossref 4 项及 Europe PMC 3 项已实际调用，新增 arXiv 两项已用公开论文检索和编号查询验证；Google Scholar 可选适配只做了模拟测试。2026-09-25 的健康检查对六个服务全部完成工具清单与代表性只读调用，默认合计 79 个工具；尚未逐个执行全部工具，也未完成 Motif 主控或 DSH Web 模型驱动的完整科研链。本轮健康检查不调用付费模型。

2026-09-26 再次运行 `doctor-mcp.py --json`：六个服务均列出预期工具并通过代表性只读探针，现为 13 + 10 + 21 + 11 + 13 + 19 = **87 个默认工具**；DeepSeek Harness 重新启动后在 `127.0.0.1:8765` 监听。`tests.test_workflow_mcp` 的本机 Python 沙盒执行、工作区外写入拒绝、Quarto HTML 渲染及 MCP 客户端连通四项均通过；另用私有临时 `.qmd` 成功输出一份 Word `.docx`。探针证明的是当前连接和代表性操作可用，不代表 87 个工具都已逐个验收，也不代表科研任务的质量或成本已达标。

本机 Obsidian 插件从项目的 [GitHub 5.2.0 发布包](https://github.com/coddingtonbear/obsidian-local-rest-api/releases/tag/5.2.0)安装到当前 vault，并在 Obsidian 中启用；该库的安全模式已按用户确认关闭。安装资产的 SHA-256：`main.js` 为 `703fbd0c9367772b31166f8980d87f707165180ea67cb3aa985991f4676cbfd3`，`manifest.json` 为 `f028748fca85a1950b9e22e3d1e3f07b0e2c6ace75987fc368731d303baec3a0`，`styles.css` 为 `19956deaf4d14142381f81fdf92cae8241fd0aa08a1a3a5464b0d007bae1924d`。插件与用户笔记均未复制到 SSS 仓库。

`scripts/build-mcp-patch.py` 在启动时生成 `.local/dsh/active-mcp.patch.yml`，只为已准备好的账号服务添加连接项；文献发现和本地分析服务始终连接。此文件不包含凭据明文；本机敏感配置和运行输出都留在 `.local/`。本轮没有实现跨服务的逐步骤工具裁剪。
