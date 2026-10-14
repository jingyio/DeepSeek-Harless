# 前端接入当前科研Agent分支

库提交 `02bcc21` 已推送到 `feature/rsi-research-agent`，GitHub分支引用和全部18个分发文件的blob哈希已核对；其余本地开发改动仍未提交。

## 最新 Motif 库可下载 2026年10月14日

- 用户恢复了本次库分发推送授权，目标 `feature/rsi-research-agent`。公开 [file-management-v1/catalog.json](../../examples/motif-library/file-management-v1/catalog.json) 提供9个已学习库/策略、3个manifest及来源/认证摘要，格式 `sss-public-file-management-library-v1`。
- 本次没有发布尚未提交的G4运行服务/持久化任务接入。索引是静态库清单，不是自动选择/执行接口；`default_activation=false`。前端下载库后须校验来源兼容，再通过当前任务权限与预算入口接入，不可沿用历史指纹授权。
- 原SDK/Web默认与HTTP任务接口未改，固定脚本库另存；私人 `.local`、费用和失败完整保留。免费发布检查6项通过，云费用0。[分发说明](../../examples/motif-library/file-management-v1/README.md)。

## 最新文件任务契约（2026-10-13）

重命名/转换/空文本的新TaskScene最终24次新留出均通过机器验收。使用既有分支更新后的`scenarios/file-management/task_tools.py`作为MCP入口，保持原14工具、stdio配置及`FM_TASK_FILE`/`FM_OUTPUT`变量；场景继续显式`acceptance_guard={"kind":"file_management","max_repairs":2}`。旧服务和旧任务不会自动升级口径。

在原本私有任务JSON（含workspace、initial_snapshot、objective、rules、allowed_operations等）增加如下字段；这里只展示新增部分，不是可独立执行的完整任务。工作目录仍必须是授权testpdf实验副本并有标记，任务JSON与交付目录在.local。

```json
{
  "family": "rename",
  "report_contract": {"version": "sss-file-report-v3", "kind": "task_result"},
  "task_contract": {
    "version": "sss-file-task-v1", "kind": "rename",
    "source_prefix": "inbox/", "destination_prefix": "normalized/",
    "allow_optional_original_reads": true
  }
}
```

转换使用`kind/family=convert`与`conversions=[{source,destination,format}]`（format=text/csv/jpeg），按需求设置`allow_output_verification_reads`、`require_output_verification_reads`。分类用`kind/family=content_classify`、`source_prefix`与`routes=[{literal,destination_prefix}]`，按首个不区分大小写的字面命中选择，保留相对路径；仅docx/txt/md必读，空白实际读后原位，全部为空则无需操作计划。

前端显示`read_task.reading_contract`中的必读原件、可选读取和允许/必读产物，以及正确编号/完整候选路径。只有当前程序验收通过才显示完成；不要把`submit_report.status=delivered`单独当任务成功。最终task_result的file_ids须包含所有当前身份。结构预校验可用[JSON Schema](../schemas/file-task-contract.schema.json)，服务端继续执行跨字段/相对路径/版本/权限校验。

新TaskScene继承原认证读取图，私有L2需明确policy/scope才启用；新效果契约不代表整个Agent已经认证或Web可任意选择用户目录。[逐项接口变化](../changes/file-management-task-contract.md)、[两版质量/费用/失败](../experiments/file-management-task-quality-20261013.md)。

2026-10-13。代码分支：`feature/rsi-research-agent`，仓库 `jingyio/DeepSeek-Harless`。这是开发联调版本；首个源码包`47d9218`已于北京时间19:46推送，本轮任务契约修订继续同步到该分支，下面安装命令取得最新HEAD。

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
# 新任务契约走同一闭环
node scripts/project.mjs python scripts/check-acceptance-repair.py --task-contract --case pass
```

普通文件管理目前通过指定实验副本和CLI运行，不是一个可任意选择用户真实目录的成品HTTP服务。复制、移动、转换、隔离和恢复均须遵循现有工具权限；前端不能通过选择execute或修复按钮扩大授权。实现细节见[接口变更](../changes/acceptance-repair.md)、[场景入口](../../scenarios/file-management/README.md)。新克隆缺少本机私有库时先用普通Harness或公开Motif样例，不复制别人实验库或构造认证摘要。

## 文献入口与限制

`npm run web:literature -- --papers-dir <服务端PDF目录>`将文献任务绑定到上面的官方任务API；`--real-model`才使用真实连接。另有独立本机工作台 `node scenarios/literature-notes/agent.ts serve --port 8765`，其 `/api/jobs`、`/api/run`属于另一套场景协议，不能与 `/api/harless/tasks`混用。该工作台写请求还要求同源及页面会话许可。

新闭环的程序验收不认证科研理解，也不能抹掉此前22项基准失败。依赖审计仍有2项high告警（MCP TypeScript SDK、sharp）；本分支适合限定输入的内部联调，公网发布前须解决并回归。多用户隔离、跨启动恢复和真实文件管理产品入口仍待验收。

CI补记：首次Ubuntu/Windows失败来自一个实际调用Poppler的文献测试漏标外部依赖。已补依赖条件；Linux CI安装poppler-utils以执行全部PDF检查，Windows无Poppler时明确跳过相关PDF测试，不当作Windows PDF能力认证。本机保留完整检查。首次失败日志留私有开发归档，没有删除断言。
