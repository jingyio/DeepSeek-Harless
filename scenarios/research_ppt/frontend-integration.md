# 科研 PPT Web 对接（V17）

单用户主聊天在显式 `--ppt-native` 时通过 `ts/native-chat.ts` 连接 `ts/web-tasks.ts` 的同一后台：官方上传回执 → 服务端预览与预算冻结 → 两路生成 → 聊天内仅返回优化稿 → 同稿后续反馈。发送后直接执行，用户无需确认预算；`/ppt` 保留备用。该桥接仅对真实 DeepSeek 的 `local-operator` 且无成员预算 broker 启用。main 的成员统一场景聊天继续使用任务级 MCP/认证读链和通用配对比较，不调用本专用学习链路。

主聊天为每个Session绑定后台task_id和当前稿件，默认15页/lab，文本中明确页数可选择1–30页；单份PPTX默认重排。`/ppt`可查看同一后台任务。主聊天和备用页的版本守卫共用；预览后若另一入口改稿，旧预览确认会拒绝。任务API的只读MCP路径仍保留，未启用主聊天桥接的用户不被改为所有者流程。

## 启动与参数

安装根依赖与科研 PPT 渲染依赖，服务器启用环境和私有 `DEEPSEEK_API_KEY` 后：

```sh
npm run web:real -- --scenario ppt --ppt-native --port 3086 --ppt-run-budget-usd 3
```

打开本次 Harness 认证地址，选择 PPT，上传 PDF/PPTX 并发送需求，后台直接执行；后续反馈继续发送，不重新上传。卡片只展示优化稿、进度、下载、预览和用户评价，不展示内部费用。`/ppt` 是备用。默认15页（1–30），1–8份PDF/PPTX，每份100 MiB、总计256 MiB。说明最多10000字符；备用页可明确`lab/academic`、`generate/restyle`。每组60步骤、8000输出token、$1.50预算，两组合计$3；思考/压缩关闭，不在每次使用时生成新工具。原 ZIP、图件、来源、权限、版本和渲染守卫保留。

## 主聊天接缝

公共`src/adapters/dsh_web_tasks.ts`仅在选定PPT且启用单用户桥接时拦截`session/prompt`，其他场景继续原生入口。文件通过官方`fileUploads.resolve`与`attachments`读取，拒绝外来回执；用户消息通过公开Session/消息API入日志，后台进度/结果使用原生`command/run`、`command/done`与插件的`conversation.chat.commandview`卡片。后台通知不伪造模型回复或额外调用模型。

`GET /api/harless/ppt/chat?session_id=...&turn_id=...` 返回当前会话的公开轮次状态和优化稿；`POST` 接受 `cancel` 或 `review`，保留兼容 `confirm`。评价绑定当前原稿和冻结试验版本，记录科学内容、图件引用、可用性、人工修改分钟及学习许可。逐次核验 Session 归属；不接受客户端指定其他 task_id。修改范围和父稿 SHA 仍由既有反馈 MCP 检查。仅提问不产生新稿。上传新资料制作另一份 PPT 需新会话。

主聊天映射保存于本次私有Web运行目录的`ppt-native-chat.json`，刷新浏览器不丢稿。Session历史位于同一DSH_HOME；保留该运行目录与Home才能恢复原聊天。统一启动器目前不支持复用已有`--run-id`：完整服务重启后`/ppt`可恢复后台任务，但不能声称新启动会自动恢复旧主聊天Session。后台状态与费用仍跨启动保留，不能因换启动目录重新付款。

PPT使用独立累计预算 `--ppt-run-budget-usd`，普通工作台预算不变。确认时按冻结任务预算全额预留；只有两路账本完整且全部请求已结算，才释放未使用额度，失败/取消的未知费用仍保守预留。私有 `.local/research-ppt/web/state.json` 跨启动保存任务、对话、版本和预算，不通过重启清零。额度是上限，不是预计费用。任务串行、确认一次、生成最多1小时、每条反馈最多30分钟；取消停止进程组，保留原账本。服务重启不自动重跑付费任务，运行中的任务或反馈标记interrupted。同一状态目录只能启动一个服务实例；已有旧运行目录需由管理员迁移，不接受浏览器指定路径。

## 同伴前端调用契约

所有接口复用同一 Harness 认证；浏览器用同源cookie。当前为单一可信操作人服务，不是多用户隔离产品。

1. `POST /api/harless/ppt/upload?name=paper.pdf`：原始二进制请求体，返回 `{id,name,bytes,sha256}`。不使用base64，不允许服务器路径/tenant/命令。
2. `POST /api/harless/ppt`：`{action:"preview",receipt_ids:[id],instruction?:string,slides?:number,template?:"lab"|"academic",operation?:"generate"|"restyle",budget_usd?:number}`。缺页数默认15；只接受本启动签发的回执。返回task_id、confirmation_digest、实际参数和影响，未调用模型。
3. 同地址确认：`{action:"submit",task_id,confirmation_digest}`。绑定输入/预览SHA；重复提交拒绝。真实模型启动必须real模式。
4. `GET /api/harless/ppt?task_id=...`：轮询状态、两组accounting、机械交付和artifacts。`completed`须双方真实回执通过，非agent idle；失败可保留一侧合格成品。科研/审美显示待用户评审。
5. `POST`取消：`{action:"cancel",task_id}`。
6. `GET /api/harless/ppt/download?task_id=...&artifact_id=...`：只接受服务端回执文件白名单，每次重新核SHA，提供PPTX/PDF/PNG；不接受任意路径。
7. 连续反馈 `POST /api/harless/ppt`：`{action:"message",task_id,message,request_id,expected_version}`。`request_id` 为8–80字符ASCII字母/数字/下划线/短横线；同ID、消息和父版本重复提交幂等，不重复付费，旧版本或同ID不同消息拒绝。`expected_version` 来自GET的 `current_version`，不是浏览器路径。普通/优化两路每条合计上限$0.50，每组24步骤/4000输出token。修改要求必须明确数字页码（如第4页、第4、5页、第4到6页）或全部页面；未明确范围则询问，不自行扩大授权。纯提问只回答，不生成新稿。回复、状态、每组费用及失败保存在 `feedback`；`current_decks` 指定各组最新版，`artifacts.version` 保留旧版，`cumulative` 计入生成与全部反馈，包括失败。费用未知保留null，不冒充零。
8. PDF/PNG 下载链接追加 `&inline=1` 可内联查看，仍须鉴权与SHA核验。历史任务通过不带task_id的GET列表恢复；重启后需用新Harness认证地址登录，旧task_id继续有效。

运行用 `web_bridge.py` 创建已有 `trial.prepare_trial`，随后参数数组启动现有trial/SDK/MCP。反馈由 `ts/feedback-runner.ts` 启动同一SDK入口，绑定原job/当前稿SHA并提供近期4轮对话及当前页面；`ts/feedback-mcp.ts` 独立限制稿件、页码、来源与新验收回执，既有后端核验非目标页OOXML及共享样式。`web_feedback_bridge.py` 仅读取同job checkpoint、独立验收和账本。不复制模型循环，不修改上游 Harness；底层每条反馈是新SDK任务，长期上下文由场景状态维护。

## 暂缓项与边界

单用户主聊天的原稿评价、后台无模型结构学习、候选试用和条件晋级已接通；目前没有本轮真实评价促成的候选或跨任务降本证据。普通组结构轨迹可以在机械交付合格且用户授权后用于发现，优化稿仍须用户认可；普通组科学/视觉质量没有独立人评，不能宣称同质量成本优势。active 有效时首版不继续训练下一代候选，成员统一场景聊天也未接入此学习器。资料/组件库持续保留；普通组禁用优化组合工具，优化组由宿主选定脚本，该工程差额不能全归因 RSI。

当前连续改页面向本场景保存完整生成计划的稿件，主聊天已接续此流程。任意外部PPTX无完整计划的保真改页、图片插入、中文数字/模糊页面名称自动定位未实现。单路失败时保留另一侧已验收新稿，明确显示未全部完成；下一条消息分别基于双方当前有效版本。未通过机械交付不把模型自述当完成，科学正确性仍需用户审阅。

原始日志、论文、成品及凭证在私有目录，公开只保留匿名报告。HTTP检查证明接口链路；不能宣称任意可解析PDF必然生成、科学全对或费用总会下降。

PPT 专用桥接与备用页面固定 DeepSeek 双路配置，不继承普通聊天的 GLM 模型、Mode 或 RSI 菜单开关；内部账本仍保留两组数据。主聊天选择 GLM 时明确拒绝此链路。需更改 PPT 模型或学习策略时应新增支持契约并重新验收。
