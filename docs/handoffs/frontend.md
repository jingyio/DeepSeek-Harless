# 前端接入当前科研Agent分支

2026-10-13。代码分支：`feature/rsi-research-agent`，仓库 `jingyio/DeepSeek-Harless`。这是开发联调版本；源码提交 `47d9218` 已于北京时间19:46推送，下面安装命令从当前分支取得它。

## 安装与免费联调

推荐Node22.18+、Python3.12；PDF能力另需Poppler的 `pdfinfo` / `pdftotext`。依赖按锁文件安装。私人PDF、凭证、轨迹、库及实验文件不随Git分发。

```sh
git fetch origin
git switch feature/rsi-research-agent
git pull --ff-only origin feature/rsi-research-agent
npm ci
npm run setup
npm run smoke
npm run web:tasks:check
npm run web
```

`npm run web`默认模拟模型，监听127.0.0.1:3080。使用本次启动的认证地址建立Cookie后，以同源方式访问 `/tasks` 和API。认证地址写在私有 `.local/web/runs/<RUN_ID>/access-url.txt`；不要硬编码或提交令牌。密钥通过私有 `.env` 的 `DEEPSEEK_API_KEY` 配置。显式 `npm run web:real` 开启真实连接，任务仍须预览并确认预算。

## 已有HTTP契约

主路由 `/api/harless/tasks`，兼容 `/api/sss/tasks`。请求保留原用户输入，服务端负责能力、文件、版本和预算约束。前端不要构造任意工具或插件路径。

| 操作 | 请求 |
| --- | --- |
| 列表 | `GET /api/harless/tasks`，返回tasks和aggregate |
| 详情 | `GET /api/harless/tasks?task_id=<ID>` |
| 预览 | POST `{ "action":"preview", "request": { "instruction":"用户任务", "request_id":"唯一请求ID", "mode":"baseline", "budget_usd":0.25 } }` |
| 执行 | POST `{ "action":"submit", "task_id":"预览ID", "confirmation_digest":"预览原值" }` |
| 取消 | POST `{ "action":"cancel", "task_id":"ID" }` |
| 附件 | POST `{ "action":"upload", "task_id":"未执行ID", "name":"文件名", "data":"规范base64" }`；256KiB上限，上传会更新预览摘要 |

调用使用 `credentials:'same-origin'`、JSON请求头。`request_id`相同且内容不变保持幂等；同ID内容变化返回409。预览摘要变化必须重新展示并使用新 `confirmation_digest`。服务目前单活跃任务；其他任务执行中返回 `task_busy`。

状态：`awaiting_confirmation` → `running` → `completed` / `failed` / `cancelled` / `budget_exhausted`。显示 `failure`、`fallback_reason`、`provider_mode`、`paid_calls_enabled`；真实实付未知时不要用估费冒充账单。详情中的 `answer` / `delivery` 是用户结果；`artifacts`只是记录名称，没有通用任意文件下载接口。

`mode`为baseline/shadow/execute，execute缺少可用认证库时仍回普通Harness。它不自动开启最新文件管理L2库；这两套显式入口不能互相混用。

## 新增有界验收修复

服务端文件管理场景可显式设置：

```json
"acceptance_guard": { "kind": "file_management", "max_repairs": 2 }
```

该配置通过公共SDK适配器及普通Web preset加载同一TypeScript停止钩子。FM_TASK_FILE、FM_OUTPUT由服务端原场景配置提供，客户端不能提交这些路径。固定Python验收器核对原任务、真实收据和文件结果。失败现场先保留，再在同Session交普通DeepSeek修复；Motif保持关闭，共用原预算、步数和MCP授权。最多2轮；取消、预算耗尽、任务版本改变、不可逆历史范围违规和次数耗尽不能继续。

启用此守卫的Web任务，仅最后一次程序验收通过才显示completed；验收失败或缺少验收记录显示failed。`stats.acceptance_repairs`、`stats.acceptance_checks`、`stats.acceptance_passed`可用于显示修复次数和最终结果。CLI还返回 `acceptance_trace_dir`，这是私有证据定位，不能直接作为前端下载路径。

```sh
# 免费真实Harness/MCP修复闭环、次数耗尽、预算耗尽
node scripts/project.mjs python scripts/check-acceptance-repair.py --case pass
node scripts/project.mjs python scripts/check-acceptance-repair.py --case exhaustion
node scripts/project.mjs python scripts/check-acceptance-repair.py --case budget
```

普通文件管理目前通过指定实验副本和CLI运行，不是一个可任意选择用户真实目录的成品HTTP服务。复制、移动、转换、隔离和恢复均须遵循现有工具权限；前端不能通过选择execute或修复按钮扩大授权。实现细节见[接口变更](../changes/acceptance-repair.md)、[场景入口](../../scenarios/file-management/README.md)。新克隆缺少本机私有库时先用普通Harness或公开Motif样例，不复制别人实验库或构造认证摘要。

## 文献入口与限制

`npm run web:literature -- --papers-dir <服务端PDF目录>`将文献任务绑定到上面的官方任务API；`--real-model`才使用真实连接。另有独立本机工作台 `node scenarios/literature-notes/agent.ts serve --port 8765`，其 `/api/jobs`、`/api/run`属于另一套场景协议，不能与 `/api/harless/tasks`混用。该工作台写请求还要求同源及页面会话许可。

新闭环的程序验收不认证科研理解，也不能抹掉此前22项基准失败。依赖审计仍有2项high告警（MCP TypeScript SDK、sharp）；本分支适合限定输入的内部联调，公网发布前须解决并回归。多用户隔离、跨启动恢复和真实文件管理产品入口仍待验收。
