# GeneLoop 统一启动与发布流程

所有开发者和 AI 使用仓库中的同一个服务入口。正式网页托管需要 Linux；Windows/macOS 本地开发仍使用 `npm run web`，真实独立联调用 `npm run web:real`。本入口管理已准备好的 owner 与账号网关，并提供显式、独立的 Cloudflare Quick Tunnel 恢复流程；不自动安装依赖、生成场景证书或创建模型预算服务。

## 唯一的服务命令

服务器先加载已配置的私有环境，并设置私有启动计划路径：

现有服务器的私有环境已设置 `GENELOOP_SERVICE_HOME` 和 `GENELOOP_SERVICE_CONFIG`。加载该环境后，可先执行 `cd "$GENELOOP_SERVICE_HOME"` 再运行下面的服务命令；其他包含本入口的 main 检出也可运行。入口检出与正在运行的应用代码检出可以不同，不要因此覆盖旧版本源码。

```sh
export GENELOOP_SERVICE_CONFIG=/ABSOLUTE/PRIVATE/service.json
npm run service -- status
npm run service -- start
npm run service -- check
```

`start` 检查并接管与启动计划完全匹配的现有进程；健康时重复执行不会重启。缺少进程时，只启动缺少的部分。执行顺序固定：检查私有配置/数据路径 → 启动 owner → 从本次独立日志提取令牌 → 验证 303、内部 cookie、认证首页 200 → 原子同步令牌 → 启动网关 → 验证登录页 → 保存私有进程身份与回执。失败清理只针对本次启动的子进程，不杀未知端口进程、不打印启动环境或凭证。

Linux 的端口与 PID 快照在进程刚启动时可能暂不完整。只有本次入口启动的已知子进程，在原有 60 秒启动期限内可重读这种快照；明确看到其他 PID 时立即拒绝。检查既有服务和停止进程仍要求唯一、完整的归属与进程身份，不能用此等待逻辑接管未知进程。

生产私有计划的 owner 与 gateway 显式环境建议都设置 `CHOKIDAR_USEPOLLING=1`、`CHOKIDAR_INTERVAL=1000`。这是已安装 Chokidar 的官方环境入口：以定期检查文件替代 `fs.watch`，不分配对应的 inotify watch；间隔单位为毫秒。inotify 配额由同一系统用户的进程共享，其他编辑器的监听也可能令服务启动报 `ENOSPC`，这不等于磁盘空间不足。无需为此停止其他开发工具或修改系统配额。

显式使用原生监听时，统一入口在停止健康旧版本前会实际申请并释放一个临时只读 watch；无法申请就拒绝发布，避免已知资源耗尽后仍停服务。该探测不能保证探测后配额不会被其他进程占用；生产仍建议使用上述 polling 配置。

成员后端采用显式环境白名单，不能假设网关环境会自动全部继承。网关只把上述两个经过校验的设置传给成员，缺省为 `1` / `1000`；polling 只接受 `true`、`false`、`1`、`0`，interval 必须是有效计时器范围内的正整数。显式关闭 polling 会重新使用系统原生监听配额。polling 保留设置和配置变化的发现能力，但存在所配置间隔的发现延迟；它不更改 MCP、模型预算、文件权限或来源边界。

维护窗口内的同版本重启：

```sh
npm run service -- restart
```

出现正在执行或状态未知的任务、对照或对照分支时拒绝重启；检查覆盖所有持久成员任务根。独立 File SDK 的 state.json 也纳入检查：成员从持久 output 读取，所有者从已核验的当前运行源码目录读取，不能用新候选目录掩盖旧任务。File 的 completed/failed/cancelled/interrupted 是可保留的终态，未知或损坏状态拒绝发布。仅用当前管理记录的 PID、启动时间、命令摘要和 cwd 校验后发送 SIGTERM，不按进程名称批量杀进程，也不强制 SIGKILL。

这是有维护窗口的重启，不是零停机发布。多个用户可能短暂断线；管理员仍需安排维护窗口，避免新请求与重启竞争。命令不承诺续跑被外部中断的任务，也不是进程崩溃后自动拉起的守护服务。

## 修改代码后的标准发布

1. 阅读 `AGENTS.md`、本文件、相关场景交接；同步 main，在独立版本检出完成代码、`npm test`、smoke 及涉及场景的验证。
2. 准备新版本的依赖、同检出 host patch/policy、场景 preset 和认证库。现有生成/认证入口继续使用，不能伪造证书或修改库哈希绕过检查。输出到新的私有候选目录，不能覆盖正在运行版本的启动配置、代码、库或 preset。
3. 以 `config/service.example.json` 为字段示例生成新的私有计划。owner/gateway 命令、cwd、env 来自核验过的启动配方；沿用原 owner Home、工作区、账号、成员、任务输出、预算端口与累计账本。新计划与原计划使用同一 `state_dir`。敏感值只留服务器私有文件。
4. 安排维护窗口，执行 `npm run service -- restart --config /ABSOLUTE/PRIVATE/CANDIDATE-service.json`。不得再为某项修复另写 Popen/nohup/kill 启动流程。配置生成脚本可以保留，实际启动/切换必须调用本入口。
5. 执行 `npm run service -- check --config /ABSOLUTE/PRIVATE/CANDIDATE-service.json`，再验公网入口、管理员和测试成员的实际页面与相关场景。内部健康检查不替代公网、注册、模型任务或交付质量验收。
6. 发布成功后，将私有 `GENELOOP_SERVICE_CONFIG` 指向候选计划；记录 commit、回执、验证与回退方式。按负责人要求提交 PR 并合并 main。

服务入口会复制并保留私有 gateway config、owner policy、host patch 与启动计划。运行中的管理配置内容发生原地变化时拒绝操作，要求恢复原配置并准备独立候选计划。外部场景资源、preset、依赖和代码检出也必须按版本保留；入口不备份、迁移或重建这些外部资源。

发布启动失败会通过同一启动路径尝试恢复上一份冻结计划，并记录回退是否成功。上一个成功版本可显式回退：

```sh
npm run service -- rollback
npm run service -- check
```

回退同样检查活跃任务、进程身份和内部认证。资源已被外部删除/原地修改时，回退仍可能失败；不能删除旧检出后再依赖这条命令。账号/任务/预算存储位置的变更会被拒绝，应作为单独的数据迁移审查。自动回退失败返回非零退出码，检查私有回执后恢复依赖，不能继续宣布发布成功。

若候选启动与自动回退都失败，且管理记录中的 owner/gateway 均已退出，可准备独立修复候选后，通过同一入口执行 `npm run service -- start --config /ABSOLUTE/PRIVATE/RECOVERY-service.json` 恢复。入口必须核验原受管进程均未存活、已知端口没有其他监听者、持久数据位置一致，并继续对原计划执行完整活跃/未知任务检查。任一原进程仍存活、端口归属未知、存在活跃或未知任务时拒绝跨版本 `start`；应解决实际状态，不能清除管理记录、修改任务终态或杀未知进程来绕过。恢复成功仍需执行 `check` 及公网和成员验收，并保留上一份冻结计划的回退记录。

## 私有计划与运行记录

字段示例在 `config/service.example.json`，不是可直接用于生产的配置。`version=1`；`gateway_config`、`owner_output`、`state_dir`、两个进程的 `argv/cwd/env` 均为实际绝对路径和有效值。计划、gateway config、owner policy、host patch 采用 600，管理目录 700。env 是显式传入的环境，不执行 shell、不自动展开变量，也不从历史日志猜配置。

可选 `runtime_pointer` 指向已有私有运行记录；成功后仅合并更新 owner/gateway PID 和服务管理信息，保留预算等其他字段。可选 `source_sha` 填本次实际代码 commit，不填虚构哈希。

`state_dir/current.json` 保存已核验的进程身份和计划；`previous.json` 指向上一份可回退计划；每次启动的日志、配置快照与回执也在这个私有目录中。不要提交或公开这些文件。生产启动计划路径保存在服务器私有部署目录，公共交接只引用环境变量名。

## 公网入口恢复：保留正在运行的任务

`check` 验证本机后端，不能证明 Cloudflare 公网入口正常。发布和故障恢复还须运行 `public-check`。本机登录页正常、公网出现 530/1016/1033 时，先核验 Cloudflare/隧道链路，不要为此重启健康的 owner/gateway。

公网配置是独立、600 权限的私有 JSON，通过 `--public-config` 或 `GENELOOP_PUBLIC_CONFIG` 指定；不要原地给受管后台计划增加字段。其必需字段如下：

- `version: 1`、`public_origin`（原 workers.dev 地址）、`previous_origin`（实际旧 trycloudflare 地址）。
- `previous_process`：由原正式收据及 `/proc` 同时核验的 `pid`、`start_ticks`、`argv_sha256`、`cwd`，不能按进程名猜测或选择别的端口的隧道。
- `tunnel`：显式的 `argv`、`cwd`、`env`、`binary_sha256`。当前受支持的 argv 严格为：已核验绝对二进制路径、`tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:GATEWAY_PORT --http-host-header ORIGINAL_PUBLIC_HOST`。网关端口、Host 和二进制摘要不符即拒绝。
- 可选 `https_proxy`：明确的本机 HTTP CONNECT 代理，例如 `http://127.0.0.1:4180`。代理也必须允许实际需要的域名；域名策略返回 403 不能记录成隧道验证成功。

默认不需要 Cloudflare API token，采用两段式操作：

```sh
npm run service -- public-check --public-config /PRIVATE/public.json
npm run service -- public-prepare --public-config /PRIVATE/public.json
# 由已获授权、已登录 Cloudflare 的维护者核验候选地址，
# 在原 Worker 中仅修改原 plain_text UPSTREAM_ORIGIN，再读回确认。
npm run service -- public-confirm --public-config /PRIVATE/public.json \
  --route-evidence /PRIVATE/route-evidence.json
```

`public-prepare` 复用统一生命周期锁，核验受管后台身份与本机登录/Logo，保存原公网错误和旧隧道身份，再由入口启动唯一候选隧道。候选目录、日志、配置及回执均为独立私有文件。返回 `awaiting_route_update` 只表示候选已注册，不能作为公网恢复成功；直接域名无法从当前网络验证时，会明确返回 `candidate_direct_verified: false` 并保留原观察。重复准备在已有待确认候选时拒绝，不再启动第二个候选。

维护者实际读回后的私有 `route-evidence.json` 须包含：

```json
{
  "version": 1,
  "method": "cloudflare-dashboard",
  "public_origin": "https://app.EXISTING-SUBDOMAIN.workers.dev",
  "worker_name": "app",
  "binding_name": "UPSTREAM_ORIGIN",
  "binding_type": "plain_text",
  "upstream_origin": "https://ACTUAL-CANDIDATE.trycloudflare.com",
  "worker_code_unchanged": true,
  "other_bindings_unchanged": true
}
```

可以补充实际观察时间和私有截图定位。该文件是授权维护者的人工读回声明，回执明确标记 `manual-dashboard-attestation`，不冒充自动 API 校验。不要为恢复临时新建宽权限 token。`public-confirm` 还必须独立确认候选 PID/启动代次/命令、后台代次，以及公网 `/login` 和 Logo 的实际字节 SHA 与当前本机应用一致；任何一项失败都不能登记成功。

有现成、已授权的 API token 时，可在独立配置增加 `cloudflare`：`account_id`、`script_name`、`api_token_file`（600 原始 token 文件）、`expected_deployment_id`、`expected_settings_sha256`。设置摘要使用 UTF-8 的排序 JSON、紧凑分隔符 `(',', ':')`。`public-recover` 会检查当前部署和设置，验证候选，然后通过固定的 Cloudflare [Worker settings API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/) 仅更换当前已核验的单一 `plain_text UPSTREAM_ORIGIN`。出现其他绑定类型/额外绑定或并发配置变化时拒绝，不能重部署 Worker 代码或吞掉未知秘密。PATCH 响应丢失时只读回确认，不盲目重复写入。无 `cloudflare` 配置时，`public-recover` 等价于准备阶段，仍须人工更新及 `public-confirm`。

公网维护不调用后台重启或活跃任务终止逻辑，不修改账号、任务、预算指针或累计账本。旧隧道及旧端点始终保留；失败清理仅允许对本次尚未发布的候选子进程做精确身份核验后的正常退出。上游变更可能已生效但无法读回时保留候选和失败证据，不能杀掉可能已成为正式入口的进程。成功记录单独写入 `state_dir/public-current.json`，原后台 `current.json` 和回退链保持。每次新恢复均准备匹配实际旧端点、进程与路由状态的新私有配置，保留旧记录。

此流程提供受管、可核验的人工恢复；Quick Tunnel 仍可能被注销，不承诺长期稳定域名或自动守护。持久化 named tunnel 需要实际域名及现成授权配置，不能用此修复假称已经部署。

## AI 开发约定

仓库 `AGENTS.md` 与 README 明确指定这个入口。后续 AI 必须先读规范，使用 `npm run service`；需要更改启动规则时，修改本入口、增加回归并更新本文件。历史 `.local/deploy*.py` 仅作证据和配置准备参考，其旧启动段不再是发布入口。

规范约束不能阻止一个忽略指令、直接操作服务器的工具。项目通过统一可执行命令、私有进程身份记录、认证检查、失败回退和自动化回归降低误用风险；不能声称所有 AI 都会被技术上强制遵守。
