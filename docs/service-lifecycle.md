# GeneLoop 统一启动与发布流程

所有开发者和 AI 使用仓库中的同一个服务入口。正式网页托管需要 Linux；Windows/macOS 本地开发仍使用 `npm run web`，真实独立联调用 `npm run web:real`。本入口管理已准备好的 owner 与账号网关，不自动安装依赖、生成场景证书、建立 Cloudflare 隧道或创建模型预算服务。

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

维护窗口内的同版本重启：

```sh
npm run service -- restart
```

出现正在执行或状态未知的任务、对照或对照分支时拒绝重启；检查覆盖所有持久成员任务根。仅用当前管理记录的 PID、启动时间、命令摘要和 cwd 校验后发送 SIGTERM，不按进程名称批量杀进程，也不强制 SIGKILL。

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

## 私有计划与运行记录

字段示例在 `config/service.example.json`，不是可直接用于生产的配置。`version=1`；`gateway_config`、`owner_output`、`state_dir`、两个进程的 `argv/cwd/env` 均为实际绝对路径和有效值。计划、gateway config、owner policy、host patch 采用 600，管理目录 700。env 是显式传入的环境，不执行 shell、不自动展开变量，也不从历史日志猜配置。

可选 `runtime_pointer` 指向已有私有运行记录；成功后仅合并更新 owner/gateway PID 和服务管理信息，保留预算等其他字段。可选 `source_sha` 填本次实际代码 commit，不填虚构哈希。

`state_dir/current.json` 保存已核验的进程身份和计划；`previous.json` 指向上一份可回退计划；每次启动的日志、配置快照与回执也在这个私有目录中。不要提交或公开这些文件。生产启动计划路径保存在服务器私有部署目录，公共交接只引用环境变量名。

## AI 开发约定

仓库 `AGENTS.md` 与 README 明确指定这个入口。后续 AI 必须先读规范，使用 `npm run service`；需要更改启动规则时，修改本入口、增加回归并更新本文件。历史 `.local/deploy*.py` 仅作证据和配置准备参考，其旧启动段不再是发布入口。

规范约束不能阻止一个忽略指令、直接操作服务器的工具。项目通过统一可执行命令、私有进程身份记录、认证检查、失败回退和自动化回归降低误用风险；不能声称所有 AI 都会被技术上强制遵守。
