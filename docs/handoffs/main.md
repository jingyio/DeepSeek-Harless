# DeepSeek Harless 主线当前交接

## 2026-10-14：斜杠场景与成员边界（当前）

- 更新时间与交接人：2026-10-14，Codex；用户授权修复、真实受限测试、部署与提交 PR，继续不代替用户合并。
- 范围/版本：PR #11 的历史续聊与原生场景引用 `0fb57ad` 已合入 main `2ad349a`。新增分支 `codex/member-workspace-hardening`，实现 `a47f76e`/`0b5955c`；后续仅文档。[PR #15](https://github.com/jingyio/DeepSeek-Harless/pull/15) 已创建，待审、未合并。
- 已完成：`harless_web_client/client.js` 原生前缀候选/蓝色引用与草稿保护；`dsh_web_tasks.ts` 工作区 ID 创建、冷会话恢复、场景锁定与同场景续聊；`dsh_member_workspace.ts`/`harless_member_file_scope.ts` 公开文件 Fetch/Lookup 边界；账号网关成员 profile 轮询、关闭浏览器连接和启动中后端。
- 已验证：最终 Linux 165 Python / 93 Node、smoke、motif:check 全通过。三组双账号各三轮真实对话，重启与隔离通过；PPT 浏览器两轮、截图对应的早期会话两轮；真实成员同名文件独立、6 类 API 越界拒绝、工作区与字节重启恢复。见 [本轮记录](../experiments/slash-member-recovery-20261014-v1.md)。
- 部署/数据：正式检出 `0b5955c`，owner 33102 / gateway 33101 保持；3080 原模型预算服务未重启。保留所有正式账号、Home、工作区、output 和迁移核验备份。原论文工作区没有覆盖；测试账户和凭证只在私有 `.local/`，结束清理测试后端，不清空历史日志。
- 权限/预算：有效 deepseek-flash、Origin、off、输出 1000；本轮 22 请求估费 0.004509264 美元。观测累计 46 请求/0.008586282 美元，上限 0.23 美元/250 请求保持，账单未核对；公共说明 `docs/harless-account-gateway.md` 与 `docs/interfaces.md` 已同步。
- 限制/下一步：未做大规模容量压测或 PPT 成品质量验收；Paper/Data 仍由部署可用性拒绝。迁入的锁定历史为文字兼容，新工具需新会话。审阅新 PR 后由用户合并；后续升级保持同 Home/output，并验证新增工具的账号文件边界。
- 回退：保留私有启动规格、policy 与访问 URL 文件；可回退 `2ad349a`，但会恢复较宽成员文件预览和旧连接退出行为。回退不删除用户文件、归属/任务索引，不重置预算，不改写私人原件。

## 2026-10-14：跨部署续聊恢复（历史，PR #11 已合并）

- 范围与版本：分支 `codex/persistent-chat-recovery` 基于 main `6ade286`；实现提交 `373eadd`（含 `5e1ecbe`），后续为文档。修复历史可见但升级后发送被拒绝，以及旧锁定 preset 无新版工具导致的二次失败。
- 接口：归属持久化至账号 `DSH_HOME`，按 Home/principal 隔离；私有 `ownership_legacy_outputs` 只导入同 Home 的明确旧目录，成员清空此配置。外部旧目录迁入的会话为文字续聊，`conversation_only:true`；附件及新版工具需新会话。正常重启不移除当前会话工具。
- 验证：Linux 全量 165 Python / 78 Node 通过；两临时账号并发各三轮真实模型对话，第三轮在网关与成员后端重启后完成，跨账号访问拒绝；实际报错旧会话两轮续聊通过；公网登录表单正常。详见 [实验记录](../experiments/chat-session-recovery-20261014-v1.md)。
- 部署与数据：正式隔离检出运行 `373eadd`；端口保持 owner 33102 / gateway 33101，原 3080 模型预算进程继续运行。保存旧启动配置与迁移前 policy；DSH Home、workspace、output 和三个生产账号保留，临时验收账号清理。原论文根工作区未重置，私有配置与日志未提交。
- 预算：有效 `deepseek-flash`、baseline、reasoning off、输出 cap 1000；本次新增 14 请求，代理估费 0.001674612 美元；当前运行累计 17 请求 / 0.002159760 美元，上限 0.23 美元 / 250 请求未重置，账单未核对。
- 后续与限制：PR 仅提交审阅，不合并。两个并发账号验证不代表容量压测；旧迁移会话为文字模式，新工具要新会话。临时 Cloudflare 隧道不在本修复范围。今后升级保留账号 Home、工作区及任务 output，回退不删除归属/任务数据、不重置预算。

## 2026-10-14：多场景前后端桥接
## 2026-10-14：Files 产品场景接入（独立 PR #14，待审）

- 本次在 `codex/harless-research-branches-20261014` 添加第五个场景 `Files`（ID `files`）；`/harless` 原生菜单从服务器 Registry 取标签与选项，任务加载 `scenarios/file-management/web-scenario.json` 的 13 工具、Prompt 和每任务文件范围。成员部署白名单只接受该固定 MCP 文件和服务器 Session 路径。共用现有 Harness Agent/RSI Runtime，不新增执行器，不改账号管理或上游 DSH。
- 默认只读盘点、读取、查重、索引与检索；用户显式开启“允许整理任务副本”并上传文件后，任务才冻结最多 6 步 `copy/move/quarantine` 授权，目标限 `organized/`、`copies/`、`quarantine/`，复用 `PlanScene` 的预览、同计划授权、执行与恢复收据。预览后上传使用任务配置摘要分离持久状态；无文件的可写任务提交拒绝。用户原件、其他 Session 和其他用户目录不在范围内。
- Files 当前没有产品认证 Motif Library。Origin 与 Shadow 使用普通 Harness；Execute On 拒绝，RSI Off 保留选择但实际 Origin。私有实验库与历史费用结果不算产品 Execute 认证或 Verified Skip。
- 已验证：V100 四项 Files 范围/权限/恢复/压缩 XML 与 Excel 元数据边界单测及 Registry 共 10 项通过；五场景免费 Harness 检查完成 30 组合、25 冻结草稿、5 个实际 MCP/上传、Files 授权草稿与空文件可写提交拒绝及双用户拒绝，0 模型请求。`npm run web:controls:check`、`npm run smoke`、`npm run motif:check` 通过，均免费诊断。真实 DeepSeek Flash Files 只读 Harness 任务完成，4 实际请求/4 MCP/0 工具错误/0 Verified Skip，预算代理估费 USD 0.001964256，实付未知、质量未人工评审。V100 两名实际 bwrap 成员各自完成五场景草稿，共 10 个，MCP/跨账号隔离通过，0 模型请求；浏览器人工点击未完成。本机缺 `mcp`，本地完整 Web 检查不能启动，V100 隔离检出补足该验证。
- 独立 V100 检出 `/home/jingyij/jjy/.local/integration/harless-research-branches-20261014` 保留了集成代码补丁与私有日志；原 V100 checkout、当前公网服务和 PR #13 未改。本次根 `npm test` 为 597 通过/4 个文献 PDF Harness 测试失败，触发点为该隔离环境的 PDF 解析，Node 阶段因 Python 失败未执行；不能写成全量通过。空环境直接调用 V100 私有 `pdfinfo` 已复现缺少 `libpoppler.so.73`，MCP 子进程传递动态库路径仍需独立核验。PR #14 最新代码提交的 Ubuntu/Windows CI 四项均通过。
- 接手顺序：1）审阅 PR #14 并在浏览器人工验证 Files 菜单与一次上传任务；2）修正/验证 V100 文献 PDF 子进程的私有工具链环境；3）用当前 PPT 代码与 Schema 重新认证运行包，再决定 PR 合并及公网切换。回退为撤销本 PR，旧四场景不受 Files 选项影响。

## 2026-10-14：科研 RSI 与 PPT 场景分支集成（待审）

- 集成基点为上线准备 PR #13 的 `77931ac`，科研 RSI 来源 `feature/rsi-research-agent@dfe4fcc` 已合并；PPT 来源 `feature/research-ppt-agent@7375185` 的场景实现与匿名 V16/V17 记录正在整合。此集成属于独立后续分支，不改变 PR #13 或当前公网服务。
- 科研分支新增 `scenarios/literature-notes/`、`scenarios/file-management/`、有界完成/验收守卫及在线 manifest v2 认证能力。冲突的旧 Web/预算/Session 入口保留 PR #13 版本；`prepare_scenario` 同时保留逐 Session 工作区和新场景守卫参数。研究场景仍为显式 CLI/实验入口，未登记为四个产品菜单场景；旧 `web:literature` 因缺任务级来源绑定明确拒绝启动，防止加载错误场景或绕过隔离。私有旧库没有默认为 Execute。
- PPT 分支新增持续知识库、显式执行策略、失败计划局部恢复、反馈及双路 Web 任务代码。双路 `native-chat` 不继承产品 Mode/RSI，故集成分支不在 `scripts/harness-web.py` 或 `dsh_web_tasks.ts` 注册这条旧入口；默认 `/harless` 仍经统一任务级配置和共享 Runtime。历轮 PDF 与私有数据未搬入 Git。
- 免费验证：科研合并后根 `npm test` 为408 Python通过/190跳过、168 Node通过/3跳过；`npm run smoke`、`npm run web:controls:check`通过。PPT TypeScript 构建及118 Node通过；本机 Python 279通过/2跳过、10个真实 LibreOffice 渲染断言因本机 PDF 的 CJK 缺字/GID0 被严格拒绝。相同集成树在 V100 固定 Noto/LibreOffice 环境复验为 PPT 291 Python通过、118 Node通过；严格字形守卫保持。`npm run web:scenes:check`、`npm run motif:check`也通过，均0云模型。
- CI 首次 Ubuntu 根测试597通过/1失败：旧文献 `run-web.py` 以已不存在的 `literature-pdf` 场景别名启动。该实验入口已改为显式拒绝并验证不启动监听；待新 CI 结果。不把缺失的文献任务绑定冒充上线能力。
- 风险：PPT代码与Prompt版本已变，PR #13 私有 `deployment-v3/runtime` 代码锁在本集成分支失效；新包必须按实际 Schema/代码重新认证和发布，未做之前生产 Execute 应拒绝。本轮未发起真实模型请求，费用新增0；保持既有任务、成员和预算隔离。

## 2026-10-14：四场景上线准备（当前）

- 更新时间与交接人：2026-10-14，Codex。
- 目标与本次范围：下一任务实际加载四场景MCP/Prompt/权限与统一RSI；补齐成员公共能力部署、PPT认证读链和机械交付，不处理另一协作者负责的旧Session bug。
- 分支 / commit：`codex/harless-launch-readiness-20261014`，整合main `6ade286`；场景/成员交付验证 `396e2cf`，Windows路径分隔符修复及根回归 `80be6a1`；文档提交见本分支最新历史。桥接PR #8及迁移文档PR #10已合并，本轮 [PR #13](https://github.com/jingyio/DeepSeek-Harless/pull/13) 已推送/未合并，公网未切换。协作者论文工作区及V100原检出保留。
- 已完成：Registry四真实后端（PPT19/论文5/数据4/通用2工具）；`session_files.py`共用准入版本守卫；PPT下一任务菜单选项；`harless_rsi_bundle.py/harless_rsi_binding.ts`可信五文件包、完整Schema/代码锁/当前上传绑定；`harless_member_scenes.mjs`只读代码/依赖/纯Runtime挂载；CPU渲染及任务内PDF/PNG/report/checkpoint。共用既有online Runtime/Agent循环，不改上游。
- 已验证：本机/V100根183Python/79Node；smoke18/83来源、controls通过；24组合中21实际冻结草稿/3无库Execute拒绝，四实际MCP/Prompt及两principal跨Task/Session/receipt拒绝。PPT53Node/212Python通过、1静态字体正例先跳过，显式指定字体后该5项组全通过。两个临时成员/8草稿四场景实际MCP及跨账号拒绝、两个成员各一份真实机械PPT/PDF/PNG通过，0模型。真实论文/数据各4HTTP，PPT成功2HTTP/1实际skip，另一次PPT预算失败1HTTP/1局部skip分列。详情 [上线记录](../experiments/harless-launch-readiness-20261014-v1.md)。
- 配置与数据：公共`config/harless-scenes.json`与四Scenario；私有`HARLESS_PPT_RUNTIME_BUNDLE/HARLESS_PPT_RENDERER_ROOT/HARLESS_PPT_FONT_ROOT`；V100独立检出`.local/integration/harless-launch-20261014`、认证部署`deployment-v3/runtime`、旧库备份`.local/imports/ppt-library-transfer-20261014`。成员配置增加`memberSceneDeployment`，账号/预算/Session接口不变。原轨迹/密钥/产物不进Git，必要私有诊断产物已同步本机。
- 未完成：公网网关切换和浏览器点击、旧Session恢复（另一协作者）、两真实成员模型并发、完整自主PPT科学/视觉质量及净降本；论文编译/外网参考真实性，数据高级推断。论文/数据/通用无生产认证库，Execute On拒绝，Origin/Shadow实际可用，不误映射样例。
- 接手下一步：1）审阅PR并在固定检出重建policy/host patch，添加私有成员部署字段，保留现有账号目录/累计账本；2）联合Session修复负责人验收两测试账号连续对话/刷新/场景切换后再切公网；3）真实研究任务独立人评与完整成本对照后决定扩库，不把机械诊断或局部skip当稳定科研收益。
- 权限与预算：先前桥接14HTTP加本轮11HTTP，累计25HTTP/代理估费0.014689896美元，实付未知；累计0.06美元限制未扩大，自设诊断次数24→25已告知。停止新增付费测试；模型质量/费用后续实验继续核对已有授权，不改公共默认额度。
- 回退与风险：现有公网进程未改；可撤新成员部署字段、RSI Off或回main `6ade286`，不删除用户文件/Session/账本。PPT工具/代码变更需新部署绑定，旧证据不改；部署共享只读能力不共享私人资料。

## 2026-10-14：多场景前后端桥接（历史）

- 更新时间与交接人：2026-10-14，Codex。
- 目标与范围：原生 `/harless` 实际选择 Scene/Mode/RSI，统一已有 Runtime；未开发缺失的论文/数据业务后端。
- 分支/版本：`codex/scene-rsi-bridge` 最初基于 main `62ee46b`，已整合最新 `2a96552`（PR #7），已推送；[PR #8](https://github.com/jingyio/DeepSeek-Harless/pull/8) 已创建，未合并；最终提交以本分支历史为准。原论文/用户隔离工作区保持。
- 已完成：`harless_scenarios.py`登记；`harless_settings.ts/dsh_web_tasks.ts`真实选择及任务冻结；`harless_task_scope.ts`独立cwd/preset/上传/job；PPT现有19工具及通用文件MCP；生产Execute完整Schema/匹配服务准入，历史诊断分列。无新Agent循环或上游改动。
- 已验证：V100合并前154 Python/60 Node；合并后165 Python/75 Node通过；PPT53 Node；18题/83来源smoke；控制与新场景/动态协议。合并前后各两项合成来源真实模型任务，累计14请求/10MCP/0工具错误/0实际跳过，见`docs/experiments/harless-scenes-runtime-20261013-v1.md`。生产有库Execute、科研质量和浏览器操作未验收。
- 配置与数据：生产`config/harless-scenes.json`；诊断`config/harless-diagnostics.json`。私有轨迹/配置/失败保留隔离验收目录，真实runs `907266faee4d40d799eca6ae2fa2109d` / `47ac1c37b74b494391bff14b56ce6b13` 已同步本地`.local/integration/scene-rsi-results/`；密钥仅由既有环境提供，未提交。
- 未完成与接口依赖：论文/数据正式Scenario尚缺，明确拒绝；PPT生产Library缺，Execute拒绝。已保留PR #7的成员预算broker、Session持久化和连续对话；零工具成员不继承所有者MCP，PPT在成员沙箱尚未部署，明确拒绝。本次没有改变账号、密码或认证模块。PPT页数/模板/输出权限暂用任务API，默认只读。
- 接手下一步：1. 审阅并合并桥接PR，安装PPT依赖后`npm run web:scenes:check`。2. 用户负责人联合验收gateway隔离；场景负责人登记正式论文/数据MCP与Prompt。3. 用独立任务认证完整Schema/库/来源绑定后，按授权做真实Execute对照。
- 权限与预算：本次真实联调累计封顶0.06美元/24请求，已用代理估费0.00647472美元/14请求，账单未知，已停止。没有借论文uncapped权限扩大Web预算，无外部写/投稿。
- 回退与风险：按本分支提交回退；旧诊断明确使用`config/harless-diagnostics.json`。不覆盖共享服务器、不修改协作者工作区、不清理`.local`；单登录实例不能当作单进程多账号。


## 2026-10-13 多用户账号网关与连续对话（[PR #7](https://github.com/jingyio/DeepSeek-Harless/pull/7) 待审）

- 范围与代码：分支 `codex/multiuser-web-gateway` 基于 `main` 的 `62ee46b`；账号网关、邀请码、账户设置、成员独立 DSH Home/工作区、账号预算路由及同一会话逐轮任务在 `scripts/harless_gateway.mjs`、`scripts/web_budget_broker.mjs`、`src/adapters/dsh_web_tasks.ts`。保留主线原生 Harless 场景/模型选择；未纳入服务器论文实验或私有配置。
- 已验证：服务器独立 Linux worktree 中 `npm test` 为 164 Python、67 Node 全部通过。免费模拟 Web 带 `--public-origin` 启动，认证 303、首页和任务/设置 API 均 200。另用两个临时测试账号同时启动隔离 DSH 后端，双方就绪与首页均 200、进程端口不同；没有真实模型调用。旧检出的 host patch 在新检出上被拒绝，改用同一检出的 patch 后通过。Windows 本机全量测试另有符号链接权限和纯代码节点环境限制，Linux 全量通过。
- 配置与部署：公共说明见 `docs/harless-account-gateway.md`，账号、邀请码、模型密钥、运行日志和私有论文继续只在 `.local/`。本 PR 未切换正在运行的公网服务；生产切换前需要以最新主线重建私有 host patch，确认 `bubblewrap` 挂载、两个测试账号实际并发和 HTTPS 隧道稳定性。服务器原论文工作区的未提交改动没有改写。
- 后续：审阅 PR 后在隔离部署上完成双账号浏览器与真实模型预算验收，再安排生产切换。PR 暂不合并；回退为停止可选账号网关并继续使用现有单用户 Web 入口。

## 2026-10-13 原生二级菜单与输入框状态（已推送，PR 待创建）

- 范围：`/harless` 原生选择器改为 Scenes、Mode、RSI 二级菜单；Scenes 新增 New Scene，使用当前服务器运行时探索。PPT、Paper Proofreading、Research Data Analysis 仍只预览且阻止误用样例工具。Mode 显示 Origin/Shadow/Execute，协议 Origin 仍为 `baseline`；RSI 默认 On，切换模式不自动改变开关，Off 的下一任务按 Origin 执行。输入框加入加粗 Harless 状态标签。
- 分支与文件：`codex/harless-picker-ui`，从 `b330bb4` 起包含原生菜单、输入框状态、模型选择与 GLM 配置；已合入最新 `origin/main`（`856c02c`），提交 `fd06213`，当前完整 HEAD 为 merge commit。对应代码、文档和回归测试已提交并推送到同名远程分支。
- 已验证：合并后 `SSS_PYTHON=/Users/apple/Desktop/SSS/.venv312/bin/python npm test` 通过 153 项 Python、56 项 Node；纯离线与模拟控制服务，模型费用为零。3094 的本机预览运行 ID 为 `9b844f86fc6f4481bb36992dad328720`，认证地址留在 `.local/web/runs/<RUN_ID>/access-url.txt`。用户确认本功能完成；真实模型任务与场景运行时仍未接入。
- 下一步：创建面向 `main` 的 PR。三个正式场景的 MCP、权限与交付仍待接入，New Scene 当前复用服务器已配置运行时。此变更不扩大付费或外部写入授权；不要提交 `.local` 或认证地址。

## 2026-10-13 原生 Harless 选择菜单（当前）

- 目标与本次范围：用户要求像 Harness 原生模型选择框一样操作，界面用英文，只显示 PPT、Paper Proofreading、Research Data Analysis，不展示样例场景。按用户确认，这三项本次仅做可选界面，运行时接入后续完成。
- 分支与改动：`codex/harless-picker-ui`；新增 `src/adapters/harless_web_client/` 双端包，使用 Harness `commandUi.decorate({kind:'popupSelect'})` 装饰裸 `/harless`；移除注入 DOM 的旧悬浮菜单及输入框观察器。后台新增 `select_preview_scene` / `clear_preview_scene`，选中尚未接通的场景后以 `scene_not_connected` 阻止任务，避免误用样例工具。
- 已验证：本机 `npm test` 151 Python、52 Node 全部通过；本机免费模拟 Web 启动成功，认证 HTML 含原生客户端插件登记且不含旧菜单注入。未操作用户浏览器，真实点击与视觉效果由用户验证；未调用模型，费用为零。
- 配置与数据：真实运行时场景仍登记在 `config/harless-scenes.json`，三个界面预览标签在 Web 适配器中；私有启动产物留在 `.local/`。V100 3094 专用预览已部署 `c147400`，服务监听 `127.0.0.1:3094`；正式 3080 与原论文工作区不变。
- 未完成与下一步：用户测试 3094 的原生菜单与英文选项；之后分别接入三个场景的 MCP、权限、输入与交付。未接通前选择这三项会拒绝任务。多人账号与文件隔离、跨启动选择恢复仍未实现。
- 回退与风险：回退本分支的原生客户端包和服务器预览选择接口；不清理 `.local`。若原生菜单未加载，保留 `/harless` 参数命令作诊断入口。

## 2026-10-13 输入框菜单与页面清理（历史）

- 最新修复：用户反馈选中 `/harless` 后页面卡住。`52d245f` 曾直接编辑原生输入框，可能与 Harness 输入框更新互相触发；本次移除此编辑，仅观察命令状态并打开设置菜单，同一段输入最多触发一次。新增重复变更回归测试；Node 语法、新测试及 11 项 Web 定向测试通过。浏览器交互按用户要求由用户测试，当前仍未验证；`/harless` 文本可能留在输入框，需根据反馈继续完善。
- 当前预览：V100 专用 3094 实例将更新到本次修复提交；正式 3080 与原论文工作区不变。本次无模型调用及费用。

- 目标与范围：保留聊天输入框旁的 Harless 场景/RSI/模式选择；移除独立 `/tasks`、`/sss`、`/harless` 页面、悬浮入口及真实模式预算确认弹窗。原生聊天发送后直接执行，服务端预算约束保留。
- 分支 / commit / 工作区：`codex/harless-picker-ui`，基于合并后的 main `b330bb4`；选择菜单 `e45338f`、页面清理 `359d0bf`、直接发送 `cb7efb2`，尚未推送。原论文工作区未改动。
- 已完成：移除两个旧 HTML 面板和命令打开旧面板的轮询；旧页面地址返回 302 跳转聊天首页。裸 `/harless` 提示使用输入框旁菜单，具体场景/模式快捷命令保留。删除真实模式预算弹窗，原生消息发送时由服务端登记、激活预算并提交；显式任务 API 的预览/提交和全部兼容路由保留。
- 已验证：Node JS/TS 语法、Python 编译、diff 检查通过；本次在本机以现有 `.venv312` 运行 `npm test`，151 项 Python 与 50 项 Node 通过。真实模式原生发送的夹具检查了直接派发、预算只激活一次、重复请求不重跑，以及页面不再注入弹窗；这是模拟控制服务，不是付费或浏览器验收。本次零模型调用。
- 实验结论：此前 `harless-controls-20261013-v1` 真实运行记录未更改；本次仅前端入口与文档调整，不新增真实 API 测试或费用。
- 配置与数据：场景登记仍在 `config/harless-scenes.json`；V100 独立副本 `.local/validation/harless-picker-cb7efb2/` 已检出本提交并通过 11 项 Web 任务 Node 定向检查。专用 tmux `harless-controls-preview` / 3094 仍运行此前版本，尚未切换；不触碰正式 3080 或私有运行数据。
- 未完成与下一步：V100 主目录为他人正在修改的论文工作区，3094 原预览副本也有未提交改动；独立副本已就绪，3094 切换暂停，不能覆盖两处工作。浏览器确认直接发送、菜单和旧页面跳转仍待完成。多人账号与文件隔离、跨启动设置恢复仍未实现。
- 权限与预算：本次删除与 UI 检查不调用模型，预计真实 API 费用为零；真实调用继续遵循项目既有授权与预算。
- 回退与风险：本次是可逆 UI 路由/面板删除；不清理 `.local`。跨用户隔离尚未实现。

## 2026-10-09 至 10-10 历史交接（当时状态）

- 2026-10-10 本机连接修复：3086 手工隧道再次消失，改为专用受限 SSH 账号与用户 LaunchAgent 自动重连，并追加本地地址代理绕过。主动断开测试约 2 秒恢复，现有认证/任务页/API 均 HTTP 200；原服务器运行、预算和 3 请求/4 MCP 统计保留，本次零模型调用。浏览器刷新待用户确认；运维配置、回退及限制见 `docs/handoffs/harness-web.md`。此记录随 PR #2 更新，原论文工作区其他修改保留；尚未合入 main。

- 2026-10-09 官方真实聊天修复：见 `docs/experiments/native-chat-confirm-20261009-v1.md`。原 `session/prompt` 直接报错已改为待确认任务与原生预算弹窗；确认前/重试/取消均 0 模型调用，确认后真实 3 请求/4 MCP/来源核验通过。当前 3086 运行 `ebd724e8f4464b72b5cbc797210da350`，每任务/启动上限 0.247 美元，承接旧支出后累计估费约 0.003950 美元、账单未核对。146 Python、45 Node、13 组协议诊断通过；真实浏览器点击仍待负责人确认。原论文分支不切换，公共修复随 PR #2 发布。

- 2026-10-09 真实 Web 恢复与 API 验收：见 `docs/experiments/web-real-recovery-20261009-v1.md`。3086 运行 `9ea9d68a37a44627ad3ab1d545678c37` 已后台恢复，baseline/execute 两项真实任务各 3 请求/4 MCP/0 错误，来源核验通过、独立 Session，execute 无库回退；合计代理估费约 0.002485 美元（总上限 0.25，账单待核对）。旧运行零调用，记录保留。真实浏览器点击仍待负责人确认；认证 URL 换行修复避免复制进终端提示符。

## 最新：普通文件任务质量修复与新留出完成（2026-10-13）

TaskScene新契约修复全局重命名、明确转换原件/产物读取，以及空文本实际读取/无写操作交付；逐项接口/Schema/前端口径已记录。最终新12条件×H/L2为24/24，首轮4失败保留；本轮48任务/513HTTP/USD0.338547576，全文件系列495/4593/USD3.836167800。独立审计每个阶段、原输入/源码/库、实际HTTP/token/费用和最终字节，原三PDF不变。最终561Python/139Node通过、3Docker跳过，18smoke及三类免费真实Harness/MCP恢复检查通过。原读取图/L2证书不改，新效果验收另记版本，没有用留出学习；L2总体费用仅−1.43%，不支持普遍收益/生产或科学质量结论。见[完整记录](../experiments/file-management-task-quality-20261013.md)、[接口变化](../changes/file-management-task-contract.md)、[场景交接](file-management.md)。分支feature/rsi-research-agent，最终同步状态以本轮提交为准；旧commit/未提交记录为历史。

## 最新：验收失败后的普通Harness修复已验证并推送（2026-10-13）

- 用户已恢复推送授权：要求原权限/预算内补最多2轮修复，真实验证后北京时间20:00前推项目分支。源码提交47d9218已于北京时间19:46推送feature/rsi-research-agent，远端SHA已核对；main未改。当前交接补记另随分支提交同步。
- 同Session TypeScript停止钩子+固定Python程序验收；每轮不可覆盖证据，原预算/96步/MCP状态不变。失败后全部Motif禁用，普通DeepSeek修复并复验；不能用重置或放宽任务通过。
- 真实两版本共8任务：6成功/2预期权限不足失败，108HTTP/USD0.098112864；15验收含9失败阶段、7修复通知及15工具拒绝全部留存。两次重命名闭环、新L2索引失败后普通模型补齐真实通过。独立审计证明修复后无自动工具、原权限不增、预算不重置；原22基准失败仍保留。
- 最终550Python/139Node通过、3可选Docker跳过；实际免费三类恢复检查、18smoke/13Web HTTP通过。文件系列447任务/4080HTTP/峰值估费USD3.497620224，实付未知。
- 前端入口docs/handoffs/frontend.md，接口与逐项改动docs/changes/acceptance-repair.md，完整结果docs/experiments/acceptance-repair-20261013.md；Web暴露修复次数，仅最终验收通过才completed。文件管理仍显式副本场景，新库默认Web不全启；2项依赖high/多用户/跨启动/科学质量限制保持。
- 密钥、私有库/PDF、原轨迹及所有费用/失败保留.local/testpdf且不推送；当前公开代码内容审查通过。以下暂停推送与旧实验记录均为历史，被本次用户授权更新。

## 最新：暂停GitHub推送，完成基础可用性核验（2026-10-13）

- 用户最新要求先确认现有功能正常使用，暂不推送；当前feature/rsi-research-agent与origin同为2368235。没有暂存/提交/推送；公开开发改动及全部私有记录保留。后续推送须等用户恢复该动作。
- 494公开文件按SHA复制到不含密钥/旧运行/私人论文的干净副本，全仓540Python/132Node通过、3可选Docker跳过；独立npm ci及Python requirements安装成功。同一macOS arm64、Node22.22.2/Python3.12.13、主机已有Poppler，未声称全新系统或新跨平台验收。
- 换用全新安装依赖后18题MCP烟测、13组真实Harness HTTP/MCP联调通过（mock模型），含预览/提交、请求幂等、附件、预算拒绝、取消和库失配回退。五类新生成文件77次实际MCP调用、7预期拒绝，检查8文件/检索4命中，5副本计划覆盖复制/移动/三类转换/归档/隔离，均幂等且逐字节恢复。文献Web两题完成及取消，15项缺口显式保留，未证明科学质量。
- 0新增真实付费API请求；已有真实模型基准22失败仍未修，新文件库默认Web关闭/只在副本CLI实验。npm audit另报2项high（@modelcontextprotocol/sdk、sharp），尚未处理，锁/运行版本保持。当前只确认限定环境内后端/工具可运行，不宣称全部任务稳定或公网可用。
- 本机核验报告.local/github-frontend-handoff-20261013/usability-verification.md/json，clean-validation日志/新生成输入/逐MCP结果/fresh-install安装与audit全部保留。下一步先修已知编号/读取验收及依赖告警，再明确前端需要的场景HTTP接入；用户确认推送后同步项目分支。

## 最新：多窗口读取学习/认证与真实对照（2026-10-13）

- 仅新文献窗口场景/实验/测试/文档及场景收集器可选参数，复用原edge compiler/sss-online-motif/批量Runtime/SDK/预算；共享核心/旧库/上游/Web默认不改。窗口四个参数用规范字符串，转换调用原PDF工具，两组相同；模型仍选择范围/解释，不称新算法。
- 两普通问题9/10参数边，第三独立6边认证，manifest1e1f378…ec14b，正式.local/window-continuation-20261012-0bc4ddc5/learned。初始39请求同会话题面认证拒绝及16步pilot M未结束都留费，不放宽检查；最后双方32SDK步完整对照。
- 两题各3轮，三篇H/M调用均10.33但M费+44.41%；两篇H12.33/M10，输出−2.88%/费−3.76%；12完整结束/来源机械合格，阅读包不同、科学支持未验。19读取批次/36结果非19净省，H68/M61净7且总体M费+17.47%。37参数类型/4发布错误保留，暂不反复小修。
- 同真实模型选定窗口组件6包严格一致：H6/6/6、M5/5/4，3读取请求实际省去，平均费−5.09%；多出1差为模型合并独立调用，不全归于Motif。全部开发26真实run/266HTTP200/$0.287990820去重含失败/学习/pilot/18对照，实付/维护未知。不默认推广，不称科学质量/Code Mode优势。
- 487Python/98Node、24专项及实际免费MCP/SDK正负通过，3Docker跳过；共享SHA/原PDF/密钥/旧工作保持、服务未停，未commit/push/PR。接口/README同步，GitHub说明docs/changes/pdf-window-continuation.md，完整证据docs/experiments/window-continuation-20261012-0bc4ddc5.md，场景HANDOFF有复现/私有数据/预算。下一步引用工作数组/资源条件分支，保持核心改动先记录。

## 最新：扩大文献任务流程探索（2026-10-12）

- 按用户优先级暂缓细小字段修补，场景workflow-discovery.md列40个消费任务/5结构候选族；新增主题检索、真实笔记引用定位、论文资源3类原生小探针，共享核心/预算/上游/正式Web不改。脚本缓存/批量工具能力单列，不称Motif新增收益。
- workflow-discovery-20261012-eec15558首轮6次+db1e78ae偏移修复2次，56HTTP200/代理USD0.063332112含所有错误/重试；首轮引用5误报为新探针绝对/相对偏移错误，修后9引用当前，旧结果保留。40任务并非全部实现/实验，0新认证库/0自动跳过/无H-M效率对照。主题/资源科学质量未验。
- 从真实原生轨迹观察13个pin→read参数链、引用/资源遍历候选；普通Harness已会批量搜索，不能略过词/资源选择。优先跨任务多窗口续接与现有foreach机制迁移；如改共享核心先列字段/生命周期/回退。当前不继续标题/长度小修、不扩UI。
- npm test477Python/98Node通过，3Docker跳过，修后14专项+三类实际免费MCP通过/API0。场景入口explore-workflows.py预览再--call-model，用户API使用已授权。完整结果docs/experiments/workflow-discovery-20261012-eec15558.md；私有全部.local，场景HANDOFF有命令/版本/预算；feature/2368235未commit/push/PR，原服务/PDF/密钥/改动保留。

## 最新：目录日期/作者修补与重认证（2026-10-12）

- 只改变目录场景：日期候选类型/选择（行政日期拒作出版年、唯一年份程序投影）、author_coverage候选词元覆盖及真实partial缺口、submission/投影来源；共享核心/预算/上游不改。候选有限，完整作者/身份不认证，旧catalog/策略失效，新原生重认证，旧实验保留。实施前docs/changes/catalog-metadata-guards.md。
- catalog-guards-20261012-066ad241训练/认证15请求/$0.01665555，新policy f1b912390ce4e1dac61f66bf3403652e704348badaf7256d9ab287a3f78efe8c。12真实对照所有作者名单/日期与已查原文一致，但一次M标题缺口。新增1篇M费+11.31%/输出+16.18%；新增2篇费−13.00%/输出−19.83%，不证明普遍降本，默认不全启。
- 原生前沿12请求→0，12核验批次；后语义15→18，全任务27→18净少9，不能按批次数报净收益。全部源/保留记录及配对plan/packet一致。所有60HTTP200/代理USD0.06146788含学习与45评测/重试，实付维护未知；463Python/98Node/34专项通过，3可选Docker跳过，实际MCP/SDK mock正负/未变0API。结果docs/experiments/catalog-guards-20261012-066ad241.md。
- 原PDF/Key/旧脏工作保留，feature/2368235未commit/push/PR；服务未停，无新服务器/跨平台/思考模式验证。下一步原文区间/句柄减少逐字重抄（两组共有，不算Motif），再另一个真实任务前沿，避免扩人工审阅/UI。CLI已完成，Web未接目录任务；其他接口见场景HANDOFF。


## 最新：文献目录任务与工作清单 Motif（2026-10-12）

- 新普通PDF目录创建/增量更新场景：read_catalog_plan→work成员首页读取→原Harness元数据判断→类型/原文/版本/完整集合核验→私有JSON/Markdown/BibTeX。新增CLI/学习/检查及19回归，本轮无共享核心/预算/上游变化；复用原incremental IR/TS插件，旧库不改，独立工具重新认证。
- catalog-work-20261012-f44dece1：3/2文件普通训练+第三1文件认证，12请求/$0.01215073。新policy08cc0f802a36d3eb0238a9e72cc865ee42e8f6877269468dec6a0ae2c8a0594b仅私有实验、默认关闭/Web未接；实施前docs/changes/pdf-catalog-motif.md、结果docs/experiments/catalog-work-20261012-f44dece1.md。
- 12对照全任务H28/M19请求；新增1篇费−25.36%但M作者缺口1；新增2篇费−14.32%，必填均3/3但有Accepted日期当出版年问题。H真实前沿12请求/915输出→M0，累计12核验批次；后语义H16/M19，不能把批次数/全差当因果收益。所有源/保留字段重放一致，完整质量不等价。
- 本轮91HTTP200/代理USD0.10926764含32失败/.05574344、12学习/.01215073、47评测/.04137347；0模型环境阻止/免费检查错误保留。末轮448Python/98Node、3Docker跳过、真实SDK/MCP mock正负API0、未变普通程序0API、diff check。密钥/PDF/旧脏工作保留，feature/2368235未commit/push/PR，服务8765/3080未停，无新服务器/思考模式验证。
- 下一步有界日期类型/可见作者缺口自动处理，变化后新认证并保留负面；再扩任务或新来源，默认不全启，不扩人工审阅/UI。其他接口与权限见场景HANDOFF。


## 最新：文献收据后终止 Motif（2026-10-12）

- 新terminal_compiler/terminal_receipt_policy认证正常收据→最后模型文字/stop关系，固定dsh_entry_motif/SDK新配对terminal参数与独立计数，原预算/上游/entry不改。状态模板手写受限复制，不称自动学任意总结或优于脚本。当前claim-repair/preview，needs_review未认证回模型。
- 私有terminal-receipt-20261012-34cfce1d库db7c1941f3d149369124d975549a9d93432272de1b67d79d992ea89c7f650db3；1/2目标训练+第三1目标原生认证，15请求/.01749130，源/引用/Schema回放一致。12留出方法组请求4→2.67/估费−32.08%，两组3/3无机械缺口；评测组M更多请求/估费+0.56%且2缺口，只有1末尾触发。共4跳过，全任务差异不可都归因末尾，科学质量未验。
- 所有15新产物/未选字段/引用/范围机械核源一致；本轮63HTTP200/代理估费USD0.09794229包含全部学习/48评测/重试，实付维护未知。429Python/98Node+场景29通过，3可选Docker跳过；免费实际SDK/MCP正负/API0、烟测与diff check通过。篡改产物旧SHA0跳过、SDK error，免费错误断言记录保留。
- repair-pdf --terminal-policy、agent.ts --claim-terminal-policy第一support_audit显式可用，默认SDK/Web关闭，HTTP拒路径、组合旧库拒绝。入口/agent改变使旧缓存正常按workflow失效，不改旧索引。共享实施前/GitHub记录docs/changes/terminal-receipt-motif.md、结果docs/experiments/terminal-receipt-20261012-34cfce1d.md。
- 本地feature/2368235未commit/push/PR，旧脏工作/PDF/Key保持，服务8765/3080未停；无新跨平台/思考模式/服务器验证。下一步另一文献任务的更大结构前沿（建索引/引用目录），已有缓存/脚本0调用不计新Motif；needs_review分支先独立训练/认证，不手扩状态。


## 上轮：文献增量工作清单 Motif（2026-10-12）

- 已最小修复支持复核题面/条件必填Schema，证据/版本/科学支持规则保留。真实单事实3请求/0工具错误/首提交带anchor成功，不代表所有论文理解问题已解决。
- 第三Motif独立协议sss-entry-incremental-v1：当前完整update-plan→work数组参数绑定→只prepare受影响PDF→语义交接。改动entry_compiler/inventory_entry_policy/entry_read_policy及PROVENANCE；旧协议保持，原固定插件/SDK/预算/上游不改。实施前接口与GitHub正文docs/changes/incremental-work-motif.md。
- 首版51请求/$0.10004980两个混合prepare/list前沿被拒，原事件/费用保留。两组共同明确纯准备阶段后，新训练/独立认证45请求/$0.08795057，实际源与导航逐项回放一致。派生基线来自已有模型事实，机械源绑定而非科学审批；0模型创建，不计Motif收益。
- 12次真实新增1/2篇对照：一篇M请求−29.41%/输出−18.83%/估费−5.17%，两组3/3收据且无机械缺口；两篇M输出+29.55%/估费+12.79%且缺口更多。总体请求H90/M78但总费用M+7.95%。支持局部结构/一个已知任务效率，不支持默认全启或科学质量等价。6M共12入口核验批次，失败/重试计入；详见docs/experiments/incremental-work-motif-20261012-a55cdbd9.md。
- 本轮267HTTP/$0.55989722含全部探索/学习/评测/3请求公共契约probe，实付/维护未知。419Python/84Node+场景28通过，3可选Docker跳过，末轮48相关Python、SDK真实MCP/mock/fixture smoke API0。原PDF未改/Key未写/.local不提交。
- 新run-incremental --entry-policy与agent.ts --incremental-entry-policy显式CLI，HTTP不接策略路径、默认关闭；旧claim库须新认证，不自动组合。HEAD2368235/feature分支脏工作保留，未commit/push/PR，服务8765/3080未停。
- 下一步成功收据→状态/结束结构及其他文献流程的更大前沿；提交引用与无收据早停保留为窄修补，尚未加增量completion_guard，不扩质量框架。当前仅已知三PDF，本机macOS，无泛化/思考模式/新服务器验收。


## 上轮：文献清单准备 Motif 与完整任务对照（2026-10-12）

- 后续只读诊断（无新模型费用）：36入口批次与绑定正常；9个不合格中2个阶段失败、7个仅1字段缺口。确认pdf-repair-task前面要求supported带support_anchor，后面/例子却给不含anchor的三字段简写，80/120字示例也混用；实际submit schema元素是宽泛dict。385重复验证问题中缺anchor100/字段限制50/字段结构23，格式错误同样消耗当轮3次额度。此缺陷影响全部组，不能独自解释Motif质量差异。细目见原实验追加章节及.local/.../followup-diagnosis.json。
- 用户询问是否可继续其他任务流程。建议最小统一提交协议，保持科研支持/版本检查；优先增量受影响论文准备、已验证收据后的纯状态结束。现有0调用缓存/目录diff/支持原句复制不应再计Motif省调用；修完不能改写旧实验，也不声称模板能解决所有证据缺口。


- feature/rsi-research-agent/HEAD2368235，未commit/push/PR，原工作区改动保留。第二入口Motif学习原生PDF清单→全部选中文件准备；3/2训练、1篇不同问题认证，实际源重放一致，仅cache_stats排除导航摘要。新guarded协议不放松旧replay契约，公共接口先列明后实施，见`docs/changes/inventory-prepare-motif.md`与`docs/interfaces.md`。
- 新`sss-entry-inventory-v1`在线TypeScript/离线Python，复用旧固定Harness插件/预算/认证库；SDK全工具允许集校验。run-pdf/agent程序与CLI显式开启，Web/HTTP默认不启用并拒绝客户端策略路径；不改上游/旧manifest/依赖/前端。
- 18完整任务/65native子运行/446HTTP200/$1.313175240；加新认证共458/$1.328307816。两篇题目双Motif3/3自动合格、请求30→25.33、输出−9.73%、费+0.52%；三篇题目双0/3合格、输出更多。H各2/3、单各1/3；不支持整Agent稳定降本或默认启用。失败/续接保留，36入口核验批次不是36净省请求，专家质量未认证。原始资料.local，公开实验`docs/experiments/inventory-motif-20261012-9af4e5f0.md`。
- 413Python/79Node+场景27Node通过，3可选Docker跳过，免费Harness与smoke API0，原PDF与18run代码未改。8765/3080服务保留。下一步阅读-only消融和语义交接/分批提交结构诊断，不继续盲目堆入口Motif或扩大UI。

## 最新：多任务入口读取 Motif（2026-10-12）

- 用户当前以相对普通Harness减少调用/输出为主，不要求先胜过脚本；应用闭环降优先级。已有原生84消息中选出冻结目标数组的入口读取前沿，15/10目标学习、5目标独立任务认证；只接管调度，保留语义模型。
- 共享变化先写docs/changes/task-entry-motif.md：新的离线entry_compiler、TypeScript entry_read_policy及公开dsh_entry_motif插件；SDK --entry-policy/--entry-task、prepare_scenario可选entry_motif，默认关闭。现有manifest版本、计价、上游Harness、Web默认不改；接口同步docs/interfaces.md。
- 18真实run/89请求/USD0.145160004，两种已有证据复核观察到节省：H7.33→M3.67和H6→M2.67；单缺口H4→M6且M一次未填出，所有费用/反例保留。不是全Agent同质量/泛化或所有Harness模式结论。学习复用既有21请求/USD0.077256972，本轮新学习API0。
- 所有原文包相同、非目标字段不变、9个真实入口批次已核验；402Python/71Node、免费真实Harness/MCP检查及smoke通过，3可选Docker跳过。原PDF未变，不要求人工审批，无embedding/A100。
- 当前分支/HEAD不变，未commit/push/PR，原服务和工作区保留。公开结果docs/experiments/multitask-motif-20261012-4ba53478.md，完整场景交接scenarios/literature-notes/HANDOFF.md；新策略仍为显式CLI实验，不默认接管生产任务。

## 最新：文献 Agent 第一阶段三任务（2026-10-12）

- 场景内完成首次三篇比较、受控单字段缺口修复、两篇新增第三篇及无变化控制，复用既有 Harness/MCP/预算，新增私有来源反馈与指定字段复核 CLI；没有共享 Runtime/Motif/预算或上游接口变化。
- 初轮68请求/USD0.186649992；原文核对发现自动复核漏检，两次有界定向修订16/USD0.017195688保留负面结果。完整84HTTP200/USD0.203845680，5工具错误/2坏JSON恢复费均保留，0 learned Motif/embedding。原PDF不变，无人工审批；来源核对非专家真值/完整语义质量证明。
- 实际自动依赖图保留旧10字段、处理新5字段并更新综合；初轮及最终修订后无变化控制0模型/0费用。此前全复核说明属于遗留图或旧描述，已修正文档并保留原实验冻结版本。
- 全仓392Python+67共享Node，额外26场景Node/81相关Python通过；3可选Docker跳过。当前分支/HEAD仍feature/rsi-research-agent/2368235，未commit/push/PR，main bc1ecd5及已有服务/工作区保留。
- 公开实验与提交说明：`docs/experiments/phase-one-20261012-8a865a78.md`、`docs/changes/literature-phase-one.md`；完整场景交接见 `scenarios/literature-notes/HANDOFF.md`。下一步先建立缺口执行分支的强基线，再学习/认证Motif，不能按跳过计数宣称收益。

## 最新：Harness / 真正Code Mode / 脚本 / Motif对照（2026-10-12）

- 用户明确要包含Harness；发现此前文献入口没有原生Code Mode，补SDK可选native/ptc、相同MCP权限守卫、Docker部署的上游WorkerThreadCodeRuntime、原生PTC收据分析投影；未改上游/计价/原PDF，生产Web仍native/off。共享变化先登记docs/changes/literature-harness-comparison.md。
- 真实harness-strong-20261012-5da6ab9f：2train+1certify32请求/USD0.055282932，独立评测选页8/USD0.012848964，真实正常native学习1条3节点链，manifest ac8d3f33…。known三论文/一个冻结三窗决定，非整Agent科学或跨语料验收。
- 对照：首阶段d94d87e3四组16次/84请求/0.060794004全部packet相同，但CodeMode逐工具生成程序；记录amendment后全部组同加局部批量说明，强阶段b8a2c8a9四组16次/71请求/0.060951672，包/plan/prompt/source一致。实际请求均值H6.25/C3.5/S4/M4，USD均值0.004437882/0.003663846/0.003463803/0.003672387，Harness秒10.458/11.354/7.951/8.086，Motif每次skip2/embedding0。脚本最便宜/最快，Motif对脚本+6.02%，没有增量收益，不凭skip证明RSI。
- 完整开发36run/195HTTP200/$0.189877572，含首阶段2外层工具失败后纠正、无429/坏JSON/PTC失败子调用；累计PDF代理$3.152304460，实付/维护未知。显式同问题/计划/源缓存4次0模型/0费用，重放0.185秒/含入口0.456，不是learned RSI。私有protocol/amendment/source冻结/final-audit/cache及所有原事件/账本保留，未抹去负面结果。
- 回归：386 Python+67共享Node通过；额外3真实Docker绑定/隔离/取消测试通过。免费真实Harness PTC5子调用/2模拟请求、packet相同。最后统一prompt46相关测试并全仓/smoke复核。仅macOS arm64与Docker内Node22.22.2验收，服务器/Windows未新增验证，无A100使用。
- 接手：默认保留已有批量脚本/核源缓存，固定verify/build Motif仍实验性；先从资料变更/证据缺口的原生轨迹找有可验证前提的分支，再比强脚本/实际CodeMode。新Web全语义质量对照/思考模式/CodeMode+Motif组合仍未做；PTC分析不作原始模型训练见证。
- Git/运行：feature/rsi-research-agent/HEAD2368235，未commit/push/PR，main仍bc1ecd5同origin。Docker为显式PTC可选，普通SDK/Web无需；--tool-presentation ptc或npm run code:check需Desktop和固定镜像，无unsafe宿主回退。最新3080文献Web与8765保留，Docker无sss-ptc残留容器。公开结果docs/experiments/harness-strong-20261012-5da6ab9f.md，完整接口提交说明见上。


## 最新：文献官方Web逐Session接入（2026-10-12）

- 已完成：npm run web:literature，固定服务端PDF目录与独立任务preset/MCP；同Session阅读→自动claim复核最多两轮→完整表综合→真实收据交付。原生聊天/任意路径/通用附件拒绝，预算/记录/单槽仍原Web；原SDK/8765/自研最终前端路线保留。
- 修复：第二轮传原始证据历史及拒绝原因，复核阶段不能通过普通读取绕claim额度；启动包装器转发退出信号，防端口残留。共享变更先登记在docs/changes/literature-web-binding.md，无上游/Motif核心/原PDF修改。
- 验收：378 Python+66共享Node，免费最终51ad10a4两个任务各43模拟请求/15显式缺口，加取消0请求；真实aaf962ec两题各15字段0程序缺口/17和16引文，22/21请求，0.100008924/0.076882584美元。首版8d701dd9的4/1缺口及49请求费用、启动6b82834e失败0请求保留；开发合计92请求/USD0.358430952，累计PDF代理USD2.962426888，实付/维护未知。0程序缺口不是科学认证，本轮verified skip0/没有新learned Motif。
- 数据：私有web-binding-20261012-*/protocol/real-audit/outcome与.local/web/runs；公开docs/experiments/literature-web-binding-20261012.md，后续公平对照协议literature-web-comparison-protocol.md待运行。界面仅预览/取消0付费，问题和论文显示替代内部提示词。最终共享UI元信息修正后免费/回归核验，不重跑付费。
- 限制/下一步：Web仍off，旧工作台缓存/增量更新未迁入；无大PDF浏览器上传、任意子集或跨启动HTTP历史加载。每任务独立preset的长期内存未测。先冻结质量和强脚本基线，从真实轨迹选独立认证候选，再运行相同质量成本对照；不能强用旧web未认证库或宣称现已降本。
- Git/回退：feature/rsi-research-agent/HEAD2368235保留既有未提交工作，main与origin/main仍bc1ecd5，未merge/commit/push/PR。回退到SDK/8765或通用Web profile，不删除历史/PDF/Key。最新文献Web真实服务3080，通过私有access-url认证；8765旧工作台未停。


## 最新场景与main同步：完成收据/单引用（2026-10-12）

本地main已建立、跟踪origin/main并同为bc1ecd5；当前开发工作目录仍feature/rsi-research-agent/HEAD2368235，main Web入口/预算文件按来源合入开发目录，保留场景未提交修改，未完整Git merge/commit/push。SDK入口保留、npm run web通用官方Web动态任务可用。共享新接口completion_guard及固定TypeScript插件使用公开停止钩子，最多2次同Session续接、仍同预算、产物SHA收据才算完成；文献单citation_id解析保留旧格式/权限，不称learned Motif。

371 Python+64 Node、SDK/Web模拟故障诊断通过；真实2380b87f…15字段/18引文/0程序缺口，28HTTP200/0.075927552美元，含全部纠正（6工具失败、3坏JSON、19复核拒绝诊断），未实际触发续接。333ac7f2…同配置缓存0请求，原PDF/Key保持。代理累计2.603995936，未核账单。GitHub记录docs/changes/literature-receipt-guard.md、实验docs/experiments/receipt-fix-20261012-9c6d79d9.md。最终自研前端、暂用官方Web；论文目录/问题与官方/tasks逐Session绑定未接完，SDK/Web固定off、思考模式对照未做，下一步先接绑定再比较。科学正确/净降本未认证，原生记录留私有区。

## 最新场景：阅读归一化与决策记录（2026-10-11）

文献场景完成按实际页尾/重叠范围计预算、保持已选原文的确定性执行；引用权限、失败额度、低文本与源版本守卫保留。新增场景TypeScript决策诊断绑定原生事件/费用，自动交付无Human审批。不修改共享Harness/Motif/预算接口，也不把缓存/批量算RSI。351 Python+44共享Node通过，场景Node23包含在Python包装；日志时间戳小修后23场景Node再通过。

真实开发任务最终15字段/24引文/0程序缺口，同配置核源缓存0请求。包含首次3缺口/未完成续修、新语义补3缺口及开发者复核轮次选错引发全量任务：10唯一run、65HTTP200、USD0.177344580，失败和误触发费用完整保留。原12字段在补证据中不变，原3PDF未改，科学理解/净降本未认证。旧实际超限3例仍拒绝，默认脚本/缓存不变；更新的Evidence执行版本需重新认证旧库。记录docs/experiments/plan-efficiency-20261011-4ebe9910.md，GitHub接口/回退说明docs/changes/literature-plan-efficiency.md，详细当前交接scenarios/literature-notes/HANDOFF.md。下一步优先引用ID选择与未提交便结束，基于原生轨迹再决定有条件Motif；未commit/push/PR。

## 上轮场景：Motif重新学习与脚本强基线（2026-10-11）

新增场景免费机械review CLI/两个原生测试，复用现有Harness/MCP/预算、Python学习认证、v2 manifest和TypeScript在线规则；无本轮新增共享接口。当前profile3下两真实训练/一不同问题认证得到1个既有三节点机械Motif，新默认问题选计划后做同包三轮9任务。6/4/4请求，Motif各2成功原生验证skip，源/参数/许可及callId配对通过；只认证证据准备，既有15字段科研稿和原PDF未改。

结果：Motif平均费用比脚本高1.68%，含启动10.809/10.870秒几乎相同，学习USD0.04752未摊平；同输入缓存0调用。保留显式实验库，工作台默认批量/缓存/模型支持审查路线不切换。没有完整科研质量等价、稳定费用/时延或泛化证明。三次正常计划超12000字符拒后恢复，费用计入，候选不跨失败。

本轮82真实请求/13唯一run/USD0.104601444，HTTP200逐账本核对；累计PDF代理估费USD2.350723804未核账单。344 Python+44共享Node通过（内含21场景Node），实际PDF/新库免费模拟协议另列；Key/原稿/论文不变，本地未提交/推送/PR。当前服务PID50879/8765不需重启。

[完整实验与反例](../experiments/motif-renew-20261011-14c3fc42.md)、[本轮无共享变更的提交说明](../changes/literature-evidence-renewal.md)、[唯一场景交接](../../scenarios/literature-notes/HANDOFF.md)。下一步聚焦本次发现的选窗预算、重复补读和来源变化恢复，先对普通脚本/缓存验收增量价值，不继续包装同一固定链。

## 最新场景：批量读计划与最终引用支持（2026-10-11）

已新增来源前后守卫的普通批量读、同论断额度/凭证隔离、最终连续原文anchor/真实句末检查、保守双栏修复及bbox异常保留普通文本。继续复用Harness/MCP/预算，无Human审批。唯一本轮新增共享入口是官方Pro模型ID/旧别名归一与requested_model预览；Flash默认、共享价格/预算/Harness/Motif核心不改，此前共享续接修改保留。

三原论文最终真实修复job39d912a2-f6f0-49a3-8805-3b1888b18782直接交付15字段/19引文/0技术缺口，逐源重放通过；先前0缺口仍有否定截断，最终实际补完整引文。开发源比对不等于专家盲评/科研真值/泛化。相同来源显式同配置重放0新增调用。原PDF/Key未改，原失败稿/费用保留。

真实模型已选同一5窗的四轮暖机MCP对照：普通并行10调用8.994ms、批量1调用3.322ms，上下文完全一样；首版批量更慢反例保留。没有新增learned Motif或verified skip，不能当整Agent收益。本轮252请求/42唯一原生run/USD0.705697132含失败与修复，HTTP200账本核对；累计PDF代理估费USD2.246122360未核账单。342 Python+44共享Node通过（内含21场景Node），工作区未commit/push/PR。

[场景交接](../../scenarios/literature-notes/HANDOFF.md)、[GitHub接口/逐项变更](../changes/literature-read-plan.md)、[实验/质量反例/全部费用](../experiments/read-plan-20261011.md)。下一步固定当前门槛，学习并独立认证新候选Motif，与普通脚本和缓存强基线比较同质量全成本。

## 最新场景：实际PDF来源变化对照（2026-10-11）

普通PDF在独立私有版本中真实新增、同名替换、删除，复用既有Harness/MCP/预算和场景Runtime；无新增共享核心修改。补齐增量超长参数的字段/实际长度诊断，保持120字符上限；删除0变化字段时也重新读取整份当前表做全局综合。场景对照入口默认预览，不另建模型循环。

两协议235实际请求/USD0.391720872含首轮32步失败与重新建库；累计PDF代理估费USD1.540425228未核账单。第二协议新增full/inc 21/39请求、78.901/88.969秒、0/2缺口；替换26/31、95.392/83.698秒、均1缺口；删除17/8、60.334/23.808秒、均0技术缺口。增/换仅处理5字段并原样保留15，删除保留15且重做综合；旧句柄隔离/源重放通过。同源普通缓存0调用，不计新Motif收益。

新增增量更慢且有缺口；独立开发检查仍发现陈述超出选中引文/综合扩大事实，未证明同质量降本或科研质量可靠。接手优先论断覆盖/条件/栏位，再优化新论文读取计划与脚本/Code Mode/Motif对照。全仓329 Python+44共享Node通过，原PDF/Key不改。服务PID8104/8765，当前浏览器显示删除增量8请求；最新缓存job3bb6eed9-f09e-41ca-9b35-9ad0c637c391。

工作区未提交/推送；此前共享接口改动保留在下节，不能当成本輪新增。[唯一场景交接](../../scenarios/literature-notes/HANDOFF.md)、[本轮GitHub说明](../changes/literature-source-changes.md)、[实验与反例/完整费用](../experiments/source-changes-20261011.md)。

## 历史场景：普通PDF局部续修与自动依赖更新（2026-10-10）

已把4项技术/引用缺口逐项补读修复；续修只处理缺口，局部更新后自动重写全组综合假设，字段原样保留。自动稿无需Human审批建立Runtime来源绑定图，改/增PDF只重做对应字段，删除重综合，问题/版本/提示变化失效；旧人工图兼容。手写图和普通缓存不称learned Motif，科学质量未认证。

本輪17请求/USD0.017576004，含全局综合收据回收错误；累计PDF代理估费USD1.148704356。全局收据由真实原生工具提交0新请求回收，原成本保留。最终job2caa0f22-44bc-4b32-be27-8145811bd963直接交付15字段/0结构缺口，无变化更新0模型请求/$0；剩余11项未完整独立语义验收，不是净收益或泛化证明。

本次只改场景/测试/文档，没有新增共享核心接口、预算或上游修改，未提交/推送；此前共享变更在下一节单列。[唯一场景交接](../../scenarios/literature-notes/HANDOFF.md)、[本次接口/提交说明](../changes/literature-auto-incremental.md)、[实验含失败与费用](../experiments/targeted-repair-20261010.md)。下一步在私有副本做真实变化更新，再比较Harness、脚本、缓存与学习/认证后的Motif总成本。

## feature/rsi-research-agent 的共享接口更新（2026-10-10，本地未提交）

- 用户明确授权修改共享接口并详细记录。新增批准计划续接契约、训练/留出许可检查、manifest v2 与 TypeScript 在线许可守卫；保留上游 Harness、预算算法及 v1 无许可行为。逐文件/GitHub正文见 [变更记录](../changes/approved-plan-continuation.md)，协议见 [interfaces](../interfaces.md)。本段不表示已经合入或推送 main。
- 实验 `approved-continuation-20261010-94934aab`：正常真实模型两训练/一留出重新认证，新问题实测6次真实请求、2次原生验证跳过、0 embedding，3窗原文包逐字重放通过。本轮37请求、代理估费$0.047486532，含一次计划超限恢复；原始轨迹/凭证及PDF保留。科学质量、跨语料和超越普通脚本的净费用未验证，详见 [实验](../experiments/approved-continuation-20261010-94934aab.md)。
- 后续同计划真实三轮 `frozen-evidence-20261010-997d9e47` 完成：每组6/4/4请求，相同包；Motif每次跳过2、embedding0，均值6.636秒/脚本7.803秒，费用均值较脚本仅低1.8%且第三轮反向。42真实请求/$0.031742316，累计PDF代理估费$0.885055476；学习与未知人工成本单列，不支持稳定净收益。[新记录](../experiments/frozen-evidence-20261010-997d9e47.md)。
- 最新全仓284 Python+44 Node通过；实际MCP/Harness固定批准计划免费三组6/4/4模拟请求，包一致。新增场景内固定计划对照与结果缓存入口，未再修改共享核心/schema；完全相同显式请求缓存核验0模型请求。TypeScript生成桥接一致性纳入测试，不新增TS运行loader。新功能本机macOS/Node22已验证，其他平台待CI。
- 场景当前交接保持在 [既有 HANDOFF](../../scenarios/literature-notes/HANDOFF.md)，未再复制第二份。接口之外的其余科研场景工作仍在该分支工作区；`.local/`及`testpdf/`均忽略，不能提交私人PDF/凭证。本轮没有commit/push/PR，后续需审阅工作区并提交允许范围。
- 下一步：按 [分层验收方案](../experiments/literature-evaluation-protocol.md) 留出新论文/研究问题，先验收科学支持与失效回退，再对照缓存/脚本/Harness/Motif的同质量总成本。三篇已知论文及同计划重复仅是机制证据；优先现有有效结果缓存，不靠请求跳过数宣称RSI净收益。

## 此前 main 的交接（历史同步状态）

- **更新时间与交接人**：2026-10-09，Codex 根据项目负责人的要求整理；后续主线负责人由课题组确定。
- **目标与本次范围**：提供四人共用的 Motif / DeepSeek Harness / 自定义 MCP 底座；用户兼任项目负责人及论文生成/投稿场景负责人。当前补齐前后端动态任务、三模式与独立统计，产品统一名为 DeepSeek Harless，保留已分发历史库和 SDK 入口；不替代论文场景开发。
- **当前分支与版本**：公共改动位于 `feature/web-task-api`，基于已合入冻结 Web 的 `origin/main`（`bdf934f`）；在线代码提交 `8168f83` 已推送，[PR #2](https://github.com/jingyio/DeepSeek-Harless/pull/2) 已创建，按负责人授权转为待审，尚未合入 main。后续交接提交以该分支 Git 历史为准。原本地与服务器的 `feature/paper-submission` 工作目录和未提交论文材料保留；实验发生时的旧 commit/dirty 配置仍以各实验快照为准。
- **公共 Web 当前新增状态**：默认 `npm run web` 动态入口，`--frozen` 兼容旧固定题面回归；产品页面 `/tasks`、API `/api/harless/tasks`，旧地址兼容。后端接收文字、JSON instruction/content/user messages、图片、官方文件 receipt 和服务器 resource_id；三模式逐任务固定，无有效认证库或输入不适配时回到普通 Harness。一个启动连续多任务，一任务一 Session、单活跃，记录独立。免费一键代码完成，真实模式仍预算预览与确认；goal/队列编辑不能绕过任务绑定。详见 `docs/handoffs/harness-web.md` 与 `docs/interfaces.md`。
- **公共 Web 最新验证与边界**：服务器 Node 22.23.3 / Python 3.10.8 通过 146 Python、44 Node、冻结 11 组、动态 HTTP/MCP 13 组、smoke 18 题/83 来源及 Motif 闭环，这些诊断无真实 API 费用。正式动态 3080 运行 `f91a53c78a524bbaa3fb935fd68c8b4f` 保持运行，浏览器认证进入 `/tasks`，产品标题/免费一键/三模式可见；同一运行无重启提交两项不同题面 `2057d2c5580d466d8efea9c385ad491a`、`ae83a4b3ad104fc7a4d0bf5760198de5`，各 completed/5 模拟请求/4 真实只读 MCP/实付 0、独立 Session、无额度表单或再次确认，刷新保留。私有截图 `.local/web-review/browser-live-multi-tasks.jpg`。同版本 3084 另已验证文字 baseline、JSON messages execute 缺库普通回退及另一聊天任务，截图 `.local/web-review/browser-free-one-click.jpg`；诊断 3084 与旧冻结 3080 均精确停止、资料保留。记录 `docs/experiments/dynamic-web-tasks-20261009-v1.md`；真实 Web、科研质量、费用收益、Windows Web 和多用户隔离未验证，预算/纯代码仍 Python。
- **后续测试执行与权限**：用户现已持续授权测试目的真实 DeepSeek API；涉及模型行为的端到端、场景和效果/成本验收默认使用服务器 `npm run web:real` / `npm run scenario:real`，不再用固定回复替代。单元、错误注入和无模型 smoke 仍为确定性诊断。运行前说明有效预算，先沿用既有 0.25 美元任务/整启动限额及实际请求上限做最小测试；超额、外部写操作和投稿另确认，不通过重启循环绕过限额。私有密钥不展示。正式 3080 仍是 mock，真实 SDK 结果不能当作真实 Web 验收。
- **真实 SDK/API/MCP 已验证**：`web:real` / `scenario:real` 显式入口已完成；服务器原变量为 `DEEPSEEK_APIKEY`，已在项目根私有 `.env` 补规范 `DEEPSEEK_API_KEY` 并设权限 `600`，未展示值。`scenario:real` 的 example/baseline、`reasoning_effort="off"`、0.25 美元上限、单请求输出 1000 token、8 步运行退出 0，耗时 9.729 秒；运行 `7929653e0d9d4828bf46e4ff49394abd`，Session `sss-105f45630d444789bccf467f3718006a`。3 次真实上游请求均 HTTP 200，4 次真实 MCP（2 pin/2 read）、0 工具错误；两个来源的 ID、SHA、读取正文和回答引用逐项一致。prompt 2712 token（缓存命中 1536/未命中 1176）、output 1043、total 3755，代理估费约 0.001614 美元，账单实付未核对。记录见 `docs/experiments/deepseek-real-api-smoke-20261009-v1.md`；原目录 `.local/runs/7929653e0d9d4828bf46e4ff49394abd/`，原始轨迹、答案与 `verification.json` 已同步两端 `.local/experiments/deepseek-real-api-smoke-20261009-v1/`。支持基本连通，任务仍用合成来源，质量未盲评，无收益结论；既有 3080 未重启。
- **当前接手优先级**：1. 项目负责人审阅公共改动，按可验收范围提交/PR，不混入私人材料和他人工作，再让同学同步。2. 各场景在服务器用真实 API 联调入口接自己的 MCP、真实输入；论文场景在独立 PR 推进，其交接不纳入本公共 PR。3. 固定质量标准、任务与配置，在已授权预算内执行最小真实验收并记录用量/人工修订；预算扩展另确认。不要再把模拟结果作为新增模型行为验收。

## 已有基础与历史验证

以下保留主线整理、分发、平台与服务器安装的历史依据；其中旧分支、测试数量、未实现前端等描述按发生时记录，当前状态以上述新增状态及 Web/论文交接为准。

- **已完成**：通用场景入口 `scripts/run-scenario.py`、场景配置适配 `src/adapters/scenario.py`、SDK 启动边界 `src/adapters/harness_runtime.py`、工具白名单与在线 Motif 插件；保留 Motif 核心及许可来源、18 项冻结科研夹具。入口见 `README.md`，协议见 `docs/interfaces.md`，合作方式见 `docs/collaboration.md`。
- **已验证**：此前在 macOS 及不含历史 `.local` 数据的临时目录执行 `npm test`，通过 133 项 Python、24 项 Node 测试；`npm run smoke` 通过 18 题、读取 83 个来源对象。另有本机模拟 Provider 的真实 SDK/MCP/预算代理闭环。以上属于离线协议与回归检查。本次纯文档修改检查 diff 和路径一致性，未重复运行模型或整套测试。
- **最近复核（2026-10-09）**：回答项目结构与连通性问题时，在当前本机重新执行 `npm test` 和 `npm run smoke`，仍通过 133 项 Python、24 项 Node 及全部 18 题工具检查；包含真实 Harness 对本机模拟 Provider 的三次请求、两次 MCP 调用。没有付费云调用或新的科研效果结论。当前在线路径为场景配置 → Python SDK → Node Harness → 可选 JS Motif 插件 → MCP；Python controller 为独立结构执行路径。新场景接入 Harness 后，要另行收集轨迹、编译认证 library 并配置任务/embedding 才能启用 Motif。现有 `docs/collaboration.md` 未提交修改属于用户工作，本次保留。
- **后续技术路线（2026-10-09，用户明确）**：Python 负责离线学习、编译和科研实验；新增 Harness 在线逻辑用 TypeScript，逐步迁移现有 JS 插件。生产在线 Runtime 以 TS 为权威，Python controller 用于参考/离线验证；不实施之前讨论的 Python 在线桥接方案。SSS 已通过 npm 安装并启动本地 Harness，已有原生插件，但独立插件分发、共享 Schema/类型及无额外 Python 的已有 library 执行尚未完成。当前纯代码节点和实验预算代理仍依赖 Python。本次仅核对代码和更新文档，没有重构、重跑付费实验或重复全套测试；用户在协作文档和 `dsh_client.py` 中的未提交修改保留。
- **首发历史库（2026-10-09）**：新增 `examples/motif-library/research-portfolio-v1/`，保留历史 4 个算子的认证摘要和 library 摘要。出处是真实 DeepSeek 调用、合成科研来源；两项训练/一项独立认证，共 26 次历史请求。公开 46 次工具证据均经 MCP 重放一致，未公开原日志；历史目录叫 v2，但题面哈希匹配 v1，已如实记录。新增 `npm run motif:check` 与 `motif:rebuild`，无须旧私有数据，重编译到 `.local/`，不修改在线核心或通用私有轨迹约束。136 项 Python、29 项 Node 通过，本机真实 Harness 四组协议验收通过：baseline/shadow/execute/旧版本请求为 14/14/7/14，四组工具调用均 13，取得相同对象/版本；结果验证跳过批次仅 execute 为 5。模拟 Provider 和固定 embedding 仅用于诊断，不是科研质量/成本结论；见 `docs/experiments/distributed-motif-example-v1.md`。库开发阶段保留用户的两份未提交文件；后续按用户的提交推送要求处理，范围见下文。
- **实验结论**：离线检查支持当前工具链和所覆盖的安全守卫可运行；没有本次真实研究交付的盲评或付费同题对照，不能据此宣称 Motif 降本或科研质量提升。清理与验证依据见 `docs/main-cleanup.md`；后续实验按 `AGENTS.md` 记录在 `docs/experiments/`。
- **配置与数据**：公开场景在 `scenarios/`，通用配置在 `config/`，依赖在 `package.json`、`package-lock.json` 和 `requirements.txt`。新入口默认 baseline、预览、`reasoning_effort="off"`，预算上限 0.25 美元、16 步、单请求输出上限 3000 token；实际实验以预览和配置快照为准。密钥使用本机 `DEEPSEEK_API_KEY` 或 Harness 凭证存储；MCP 认证用场景的 `from_env`。私人资料与历史原始记录在各自本机 `.local/`，不随 Git 分发。未在本记录中读取或记录任何密钥值。
- **未完成与限制**：Ubuntu/Windows 原生离线 CI 已通过（测试、18 题 MCP、Motif 本机模拟闭环）；真实 HTTP MCP 服务及外部应用场景尚未联调。三个实际场景及负责人尚未在仓库冻结。在线 JS runtime 是 Python 结构执行的子集，不是完整移植；embedding 和具体 MCP 服务的平台适配仍需场景验证。仓库定价表也需在付费实验前核对。
- **接手下一步**：
  1. 主线负责人确认团队共享仓库及同步范围，将需要的本地提交推送；验收是同学能取得相同版本并运行基础检查。
  2. 三位同学各开场景分支，复制 `scenarios/example/`，实现最小只读 MCP 链路；验收包括正常调用、版本/权限拒绝检查及各自场景交接记录。
  3. 选定真实独立研究决定，冻结任务、来源、基线、配置和质量标准；先预览预算，获得对应调用权限后再做付费对照。
- **干净分发复核与提交范围**：在临时干净副本（没有旧 `.local`，复用已安装依赖）通过完整 `motif:check`；重编译和场景 shadow 预览均通过。此前未提交的三位同学姓名分工按用户的“推送当前最新代码”要求纳入；语义客户端待提交改动绕过跨平台适配，推送前修正回 `create_harness` 统一边界，`reasoning_effort="off"` 仍由该边界设置。没有修改 SDK 上游核心。
- **历史阶段权限与预算**：此前授权涵盖本地备份、主线整理、样例库开发及最新 main 提交和推送，整理与模拟验收无新增付费支出，当时没有新增真实实验授权。当前测试目的真实 API 持续授权以顶部新约定为准；发送邮件、外部写操作、实际投稿及超额支出仍需另确认。
- **Windows CI 修复（2026-10-09）**：用户提供首次 Windows CI 的 8 个失败，已定位为 LF/CRLF 原始字节哈希、cp1252 解码中文和不适用的 Unix 模式位断言；前两份哈希差已由换行转换精确复现。新增 `.gitattributes`、入口 UTF-8 配置、显式文本读写及平台限定的模式位检查；保留冻结哈希与所有非模式位安全验收。本机仍通过 136 项 Python、29 项 Node。推送后以对应平台 CI 为准；细节见 `docs/experiments/windows-ci-compatibility.md`。未调用付费模型。
- **回退与风险**：文档可按对应提交单独回退；完整历史可从两个归档分支查阅。不要直接把全部 archive 合回 main，也不要删除 `.local/`。通用入口的 `--call-model` 会启用付费调用；有副作用的 MCP 还需服务端权限、预览和确认。

- **Windows CI 验证结果**：修复提交 `c05127f` 的 [运行 37888988141](https://github.com/jingyio/DeepSeek-Harless/actions/runs/37888988141) 中，Ubuntu 与 Windows 均完成并通过 `npm ci`、环境安装、`npm test`、`npm run smoke`、`npm run motif:check`。本地 `core.autocrlf=true` 干净检出额外验证了 79 个冻结文件的原始哈希。当前已验证离线及模拟闭环，不能扩大为所有真实应用/MCP 或付费云实验的支持结论。
- **远程开发源码同步（2026-10-09）**：按用户授权，将 `main` 的 `2368235f274329be6227a8393b850633cb943da4` 及完整主线 Git 历史恢复到指定服务器 `/root/autodl-tmp/jjy`，`origin` 指向原 GitHub 仓库；本条交接更新尚未提交，也随源码同步。未传输本机 `.local/`、密钥、虚拟环境、`node_modules` 或缓存；归档分支未单独迁移。远端为 Linux x86_64，现有 Conda Python 为 3.10.8，未找到 Node.js；开发依赖尚未安装，未运行远端测试或付费任务。接手先准备 Node.js 20+ 与 Python 3.12，再按 `README.md` 执行 `npm ci`、`npm run setup` 和免费检查。此次只授权源码同步，没有新增模型支出；SSH 凭证不写入仓库。
- **后续执行约定（2026-10-09，用户明确）**：用户负责论文生成与投稿场景，本地操作与审阅，后续 Agent 计算在服务器执行；运行前同步代码和输入，运行后同步交付与必要结果。已简短写入 `AGENTS.md`；本次仅更新文档，不安装环境或运行实验，文档改动未提交、未推送。
- **环境要求修正（2026-10-09）**：Python 3.12 是已有 CI/本机验收版本，不能据此推断 3.10 不兼容。`src/`、`scripts/`、`tests/` 通过 3.10 语法解析；已安装固定直接依赖的元数据允许 3.10。远端 Ubuntu 22.04、x86_64、内核 5.4、glibc 2.35 满足 Node.js 22 官方 Linux 二进制平台条件；尚未安装 Node 或完成 Python 3.10 依赖安装及运行回归；远端依赖 dry-run 解析未完成后已停止，不构成不兼容证据。已修正 `README.md`，下一步优先核验现有 Python 3.10 与 Node 22 的免费闭环。最终展示采用本地浏览器访问服务器任务接口；该前端/API 尚未实现。本次没有付费调用。
- **服务器免费闭环已完成（2026-10-09）**：更新上一条待验证状态。用户授权后在服务器安装项目隔离的 Node 22.23.3 / npm 10.9.9，沿用 Conda Python 3.10.8 创建 `.venv-sss`；依赖一致性检查、136 项 Python 与 29 项 Node 测试、18 题 / 83 对象 MCP smoke、4 个 Motif 重编译与 Harness baseline/shadow/execute/旧版本回退均通过，场景入口保持预览。没有为适配 3.10 修改源码；付费 API 请求为 0。记录见 `docs/experiments/server-python310-free-loop-20261009-v1.md`；配置与原始日志在两端 `.local/experiments/server-python310-free-loop-20261009-v1/`，启动先 `source .local/remote-env.sh`。安装中的慢速下载中止与缓存恢复已记录，不是功能失败。当前文档及验收记录未提交、未推送；用户 `reference/` 文件保留。下一步可在此环境接论文生成与投稿的最小 MCP 场景；尚未安装论文编译工具、联调真实论文或实现前端/API，付费任务及实际投稿仍需授权。
