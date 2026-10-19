# Harless 账号网关（Linux）

每个成员账号首次访问时按需启动一个独立后端进程树，同账号的多个工作区和对话复用该后端；管理员连接预先启动的 owner 后端。各账号共享服务器计算资源、模型服务及预算代理，按账号凭证、任务前缀和 Session 绑定校验归属。当前没有代码级空闲自动回收、总在线人数限制或 CPU/内存配额；退出登录只撤销登录会话。成员进程退出后，下次访问重新启动，持久化资料保留。最多 8 个同时启动是启动阶段保护，不是可保证的在线容量。

同一轮 DeepSeek 场景对照允许 Baseline 与 Motif 同时执行，各侧独立 Session、工具范围和预算路由；仍按账号逐轮调度，不允许新任务抢用另一对照的并行槽。无 Session 请求头的旧 GLM 适配器继续串行，避免模糊的费用归属。

`scripts/harless_gateway.mjs` 是部署在官方 Harness Web 前面的可选入口。浏览器访问公网 HTTPS 地址时，网关显示与 Harness 风格一致的登录页；同学凭一次性邀请码注册账号。密码用 scrypt 加盐保存，登录 cookie 为 HttpOnly、SameSite=Lax 的浏览器会话 cookie；关闭浏览器后通常需要重新登录（浏览器若恢复会话仍可能保留 cookie）。所有者可以在账户页修改名称、用户名、密码并生成邀请码，成员可以修改自己的资料和密码。

网关为每个成员启动独立的 DSH 进程与受限的 `bubblewrap` 文件系统，分别挂载 `membersDir/<user-id>/workspace` 和 `membersDir/<user-id>/dsh`。账号数据、会话、工作区均写在服务器私有目录；不得提交到 Git。成员使用独立的任务 ID 前缀、预算路由和模型授权。一个成员的任务不会映射到另一个成员的预算或会话；同一成员的后续消息在上一轮结束后获得新任务预算。实际可同时启动的成员数取决于服务器 CPU、内存与模型额度；当前代码只限制同时**启动**的后端不超过 8 个，不保证任何固定在线容量。

部署需要 Linux、`/usr/bin/bwrap`、Node 22.18+、项目依赖和一个已有的真实模型预算代理。先用 `HARLESS_GATEWAY_ENABLED=1 npm run web:real -- --public-origin https://YOUR_HOST` 启动所有者 Harness Web，使账号入口显示在设置菜单。`--public-origin` 只设置 DSH 的可信主机和生成私有访问 URL，**不会**自动创建网关、账户或隧道。账号网关配置 JSON 放在 `.local/`，权限只给服务账号。其字段包括 `port`、`publicOrigin`、`dataDir`、`membersDir`、`accountHtml`、`ownerPort`、`ownerTokenFile`、`adminToken`、`scopedBudgetPort`、`upstreamControlPort`、`upstreamBrokerPort`、`memberPolicy`、`memberPatch`、`nodeRoot`、`nodeModules`、`sourceDir`。`memberPolicy` 来自服务器验证过的 Web policy，成员的工具和私有资料应按实际授权另行限定；`memberPatch` 必须从**同一代码检出**的本次 host patch 生成，旧检出的插件绝对路径会使网关在启动时拒绝配置。`sourceDir` 指向仓库 `src` 目录，`nodeModules` 指向仓库 `node_modules`，`nodeRoot` 指向 Node 安装根目录。这些路径及令牌只能放私有配置。部署前核对所有挂载路径与预算端口；不得把所有者的私有资料或配置复制进成员挂载目录。

成员文件预览额外经过 `dsh_member_workspace.ts` 的公开 Fetch 路由检查：只允许会话工作区内的文件，解析符号链接后仍须位于该目录；拒绝 `../config`、`/proc` 等越界读取。工作区创建和目录选择只允许账号的 workspace 与 sessions 目录。`workspaceFileScope` 公开 Lookup 同时限制 HTTP 和 WebSocket changes feed 的会话根；原生 changes feed 继续按工作区过滤。上游桌面文件预览默认允许读取工作区之外，不能把独立 Home 或桌面默认行为视为此成员边界。所有者仍按其管理员权限使用原生文件 API。

成员后端对小型配置/profile 树启用 Chokidar 轮询（`CHOKIDAR_USEPOLLING=1`，文本检查间隔 1000 ms），减少多人同时启动时对共享服务器 inotify 额度的依赖。它不改变原生工作区文件事件协议；轮询会增加少量文件检查，不能替代 CPU/内存容量监控。停止后端继续由 bubblewrap 的 PID 隔离与 `--die-with-parent` 结束子进程。

网关关闭时结束已就绪与启动中的成员后端，并断开空闲 HTTP 和已升级的浏览器连接；WebSocket 上下游任一侧关闭时同时释放另一侧。正常升级使用 SIGTERM，保留账号/会话/文件目录。任务仍在运行时应等待完成再切换；此关闭操作不会自动续跑未完成的任务。

通过 `node scripts/harless_gateway.mjs .local/PRIVATE-GATEWAY-CONFIG.json` 启动网关，它只监听 `127.0.0.1`。使用反向代理或 Cloudflare Tunnel 将 HTTPS 公网地址指向网关端口；在反向代理中转发 WebSocket，并限制只有网关可访问内部预算和控制端口。网关初次部署用 `node scripts/harless_gateway.mjs .local/PRIVATE-GATEWAY-CONFIG.json claim` 生成一次性所有者激活码；所有者登录后从账户页生成成员邀请码。不要在日志、PR 或聊天记录中公开激活码、邀请码、DSH token 或私有配置。临时 `trycloudflare.com` 隧道和手工 `tmux` 进程可能中断、重启或换地址；生产用途应由持久化服务管理器监控入口与后端。

所有者后端每次启动都会生成新的内部 launch token，网关的 `ownerTokenFile` 必须同步；它不是账号密码或模型 API Key。使用直接启动 DSH 的自定义发布/回退脚本时，必须在启动网关前执行以下检查，失败则停止发布。追加日志需要在启动进程前记录字节偏移并传入 `--log-offset`，或每次使用独立日志；不能从混合多次启动的日志猜测令牌。

```sh
python scripts/harless_owner_access.py --config .local/PRIVATE-GATEWAY-CONFIG.json \
  --startup-log .local/PRIVATE-CURRENT-OWNER-STARTUP.log
python scripts/harless_owner_access.py --config .local/PRIVATE-GATEWAY-CONFIG.json --check
```

该工具只向配置端口的 `127.0.0.1` 发送认证请求，要求 303、内部 cookie 和携带 cookie 的首页 200 全部成功后，才以私有权限原子更新令牌文件，不输出凭证、不调用模型。网关会在下次请求重新读取该文件，正常同步无需重启网关。只检查 TCP 监听、未认证的首页或公开登录页无法证明管理员工作区可用；部署验收应分别检查管理员与测试成员账号。成员的内部凭证在各自后端启动时采集，不读取 `ownerTokenFile`，因此所有者令牌陈旧不等于所有新用户不可用。

升级代码时保留每个账号的 `DSH_HOME`、工作区及任务 `output` 目录，不把持久化数据放进随代码版本删除的检出目录。会话归属现在保存在对应 `DSH_HOME` 中的 `harless-web-ownership-*.json`，因此前端进程重启不会丢失续聊权限。首次升级自动导入当前 `output` 的旧归属记录；如果所有者以前已更换过 `output`，可以在其私有 policy 中设置 `ownership_legacy_outputs`（旧目录的绝对路径列表）。只会导入与当前 DSH Home 匹配的归属文件，不能据聊天标题或浏览器传入的 ID 认领历史。成员后端清除此迁移列表，只访问自身挂载目录。迁移归属不会恢复旧任务额度或移动文件；场景的工作区、生成 preset 和任务记录仍须保留。没有逐轮预算 broker 的入口继续拒绝重用已绑定任务。

从其他旧 `output` 导入的已开始会话按文字对话恢复：保留上下文，每轮继续经过当前预算代理，但不把新版场景工具强行装进已锁定的旧 Harness preset。设置接口的 `conversation_only` 会标记这种兼容会话；需要文件或新版场景工具时新建会话。当前目录内正常重启的会话保留原有能力。

更早于归属记录功能的会话需要管理员核验当前所属 DSH Home、持久头部、创建时间和来源，再将明确批准的 ID 写入私有、匹配该 Home scope 的迁移记录；不要自动认领 Home 内全部历史，也不要通过标题猜归属。归属核验、批准记录和备份只保存在私有部署目录。

原生工作区选择只向 Harness 传递账号本地注册表中的 `workspaceId`；其 API 不接受 ID 与 `cwd` 同时出现。没有工作区参数时自动登记服务器分配的工作区，使直接创建和场景切换得到的会话也能在界面使用。场景文件、输入摘要和 PPT job 仍按 Session 独立保存。场景标识与切换规则见 [Harless 控制协议](harless-controls.md)。
四场景部署在同一私有配置增加 `memberSceneDeployment`。`projectRoot` 是本次代码检出，`pythonExecutable` 是场景依赖解释器，`pythonRoots` 只列解释器/venv的安装根（include-system-site-packages也列实际base及继承环境），不能填写用户家目录或整个项目。可选 `libraryRoot` 只包含认证Runtime五文件，`rendererRoot` 是含program/share的LibreOffice安装，`fontRoot` 只含固定中文字体、字体配置及许可证。只读挂载服务代码和依赖不共享用户资料；输出映射到每成员自己的tasks目录。未配置时保留旧chat-only部署。每次代码或渲染版本更新必须重建同检出host patch/policy及有效库部署绑定；不要复制旧证书哈希绕过守卫。安装示例与边界见 [控制协议](harless-controls.md)。

在隔离检出运行 `node scripts/project.mjs python scripts/check-harless-members.py --render-ppt` 可生成两个临时诊断账号，实际启动bwrap/MCP、检查四场景与跨账号拒绝，再在各自实际挂载内生成一页合成PPT/PDF/PNG。需先配置上述库/渲染依赖；不调用云模型，不证明浏览器、公网或模型自主生成质量，不使用生产账户数据库。

数据报告使用可嵌入的中文字体。部署时从 Ubuntu 官方仓库下载 `fonts-wqy-microhei` 版本 `0.2.0-beta-3`，将包内的 `wqy-microhei.ttc` 与 `copyright` 分别复制为既有私有 `fontRoot` 中的 `wqy-microhei.ttc`、`WQY-COPYRIGHT.txt`；无需修改系统字体或用户资料。该版本包 SHA-256 为 `e7827bca16475a02f29dd7a59208c1790992037a43d64896320572362d1bd79d`，字体 SHA-256 为 `2420e8078af796b19a3f6ef13de527a1a91c1e7171eea115926c614ced1009b3`。字体和安装收据不提交到仓库。生成 policy 时设置 `HARLESS_PPT_FONT_ROOT`，会为数据报告注入固定路径 `HARLESS_REPORT_FONT` 和实际字体 SHA；成员沙箱核验路径、文件及 SHA 后只读挂载。报告引擎校验中文字符覆盖并嵌入字体子集，避免依赖阅读器的中文 CID 字体回退。升级后重建同检出的 policy；旧下载文件保持不变，新排版使用新的引擎版本目录。

回归检查运行 `npm test`，其中包含账号并发注册、登录持久化、跨账号预算拒绝、Web 连续对话及预算路由测试。部署后还需用两个**测试账号**验证：同时登录、各自创建工作区和会话、互相不能访问文件、连续发送两轮、刷新与关闭浏览器后的登录行为，并确认真实 API 成本落在服务器预算内。单元测试不证明公网隧道、服务器资源或真实模型质量可用。
