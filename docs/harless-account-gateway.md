# Harless 账号网关（Linux）

`scripts/harless_gateway.mjs` 是部署在官方 Harness Web 前面的可选入口。浏览器访问公网 HTTPS 地址时，网关显示与 Harness 风格一致的登录页；同学凭一次性邀请码注册账号。密码用 scrypt 加盐保存，登录 cookie 为 HttpOnly、SameSite=Lax 的浏览器会话 cookie；关闭浏览器后通常需要重新登录（浏览器若恢复会话仍可能保留 cookie）。所有者可以在账户页修改名称、用户名、密码并生成邀请码，成员可以修改自己的资料和密码。

网关为每个成员启动独立的 DSH 进程与受限的 `bubblewrap` 文件系统，分别挂载 `membersDir/<user-id>/workspace` 和 `membersDir/<user-id>/dsh`。账号数据、会话、工作区均写在服务器私有目录；不得提交到 Git。成员使用独立的任务 ID 前缀、预算路由和模型授权。一个成员的任务不会映射到另一个成员的预算或会话；同一成员的后续消息在上一轮结束后获得新任务预算。实际可同时启动的成员数取决于服务器 CPU、内存与模型额度；当前代码只限制同时**启动**的后端不超过 8 个，不保证任何固定在线容量。

部署需要 Linux、`/usr/bin/bwrap`、Node 22.18+、项目依赖和一个已有的真实模型预算代理。先用 `HARLESS_GATEWAY_ENABLED=1 npm run web:real -- --public-origin https://YOUR_HOST` 启动所有者 Harness Web，使账号入口显示在设置菜单。`--public-origin` 只设置 DSH 的可信主机和生成私有访问 URL，**不会**自动创建网关、账户或隧道。账号网关配置 JSON 放在 `.local/`，权限只给服务账号。其字段包括 `port`、`publicOrigin`、`dataDir`、`membersDir`、`accountHtml`、`ownerPort`、`ownerTokenFile`、`adminToken`、`scopedBudgetPort`、`upstreamControlPort`、`upstreamBrokerPort`、`memberPolicy`、`memberPatch`、`nodeRoot`、`nodeModules`、`sourceDir`。`memberPolicy` 来自服务器验证过的 Web policy，成员的工具和私有资料应按实际授权另行限定；`memberPatch` 必须从**同一代码检出**的本次 host patch 生成，旧检出的插件绝对路径会使网关在启动时拒绝配置。`sourceDir` 指向仓库 `src` 目录，`nodeModules` 指向仓库 `node_modules`，`nodeRoot` 指向 Node 安装根目录。这些路径及令牌只能放私有配置。部署前核对所有挂载路径与预算端口；不得把所有者的私有资料或配置复制进成员挂载目录。

通过 `node scripts/harless_gateway.mjs .local/PRIVATE-GATEWAY-CONFIG.json` 启动网关，它只监听 `127.0.0.1`。使用反向代理或 Cloudflare Tunnel 将 HTTPS 公网地址指向网关端口；在反向代理中转发 WebSocket，并限制只有网关可访问内部预算和控制端口。网关初次部署用 `node scripts/harless_gateway.mjs .local/PRIVATE-GATEWAY-CONFIG.json claim` 生成一次性所有者激活码；所有者登录后从账户页生成成员邀请码。不要在日志、PR 或聊天记录中公开激活码、邀请码、DSH token 或私有配置。临时 `trycloudflare.com` 隧道和手工 `tmux` 进程可能中断、重启或换地址；生产用途应由持久化服务管理器监控入口与后端。

升级代码时保留每个账号的 `DSH_HOME`、工作区及任务 `output` 目录，不把持久化数据放进随代码版本删除的检出目录。会话归属现在保存在对应 `DSH_HOME` 中的 `harless-web-ownership-*.json`，因此前端进程重启不会丢失续聊权限。首次升级自动导入当前 `output` 的旧归属记录；如果所有者以前已更换过 `output`，可以在其私有 policy 中设置 `ownership_legacy_outputs`（旧目录的绝对路径列表）。只会导入与当前 DSH Home 匹配的归属文件，不能据聊天标题或浏览器传入的 ID 认领历史。成员后端清除此迁移列表，只访问自身挂载目录。迁移归属不会恢复旧任务额度或移动文件；场景的工作区、生成 preset 和任务记录仍须保留。没有逐轮预算 broker 的入口继续拒绝重用已绑定任务。

从其他旧 `output` 导入的已开始会话按文字对话恢复：保留上下文，每轮继续经过当前预算代理，但不把新版场景工具强行装进已锁定的旧 Harness preset。设置接口的 `conversation_only` 会标记这种兼容会话；需要文件或新版场景工具时新建会话。当前目录内正常重启的会话保留原有能力。

更早于归属记录功能的会话需要管理员核验当前所属 DSH Home、持久头部、创建时间和来源，再将明确批准的 ID 写入私有、匹配该 Home scope 的迁移记录；不要自动认领 Home 内全部历史，也不要通过标题猜归属。归属核验、批准记录和备份只保存在私有部署目录。

原生工作区选择只向 Harness 传递账号本地注册表中的 `workspaceId`；其 API 不接受 ID 与 `cwd` 同时出现。没有工作区参数时自动登记服务器分配的工作区，使直接创建和场景切换得到的会话也能在界面使用。场景文件、输入摘要和 PPT job 仍按 Session 独立保存。场景标识与切换规则见 [Harless 控制协议](harless-controls.md)。

回归检查运行 `npm test`，其中包含账号并发注册、登录持久化、跨账号预算拒绝、Web 连续对话及预算路由测试。部署后还需用两个**测试账号**验证：同时登录、各自创建工作区和会话、互相不能访问文件、连续发送两轮、刷新与关闭浏览器后的登录行为，并确认真实 API 成本落在服务器预算内。单元测试不证明公网隧道、服务器资源或真实模型质量可用。
