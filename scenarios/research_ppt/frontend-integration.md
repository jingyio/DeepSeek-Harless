# 科研 PPT Web 对接（V17）

必需链路已实现于 `ts/web-tasks.ts`：复用 Harness 认证，流式上传、服务端回执映射、独立双路 job、预算预览/确认、后台状态、机械验收后的成品下载、费用对照。主前端原生 `/harless` 菜单选择PPT后进入 `/ppt`。显式选择科研 PPT，不使用关键词或 embedding 授权；静态 registry 不启动缺少任务 job 的 MCP。原生聊天仍走原有场景，不能仅在聊天框上传论文就假定进入 PPT。

## 启动与参数

安装根依赖与科研 PPT 渲染依赖，服务器启用环境和私有 `DEEPSEEK_API_KEY` 后：

```sh
npm run web:real -- --port 3086 --ppt-run-budget-usd 3
```

打开本次 Harness 认证地址后访问 `/ppt`。默认15页（1–30），1–8份 PDF/PPTX，每份100 MiB、总计256 MiB。说明最多10000字符；`lab/academic`，`generate/restyle`。每组60步骤、8000输出token、$1.50预算，两组合计$3；思考/压缩关闭，不在每次使用时生成新工具。原 ZIP、图件、来源、权限、版本和渲染守卫保留。

PPT使用独立启动总预算 `--ppt-run-budget-usd`，普通工作台预算不变。确认时按冻结任务预算全额预留，失败/取消也不退回未结算额度，不能通过新任务重置。同一次启动默认只够一个$3任务，额度是上限不是预计费用。任务串行、确认一次、最多1小时；取消停止进程组，保留原账本。服务重启不自动重跑付费任务，标记interrupted。

## 同伴前端调用契约

所有接口复用同一 Harness 认证；浏览器用同源cookie。当前为单一可信操作人服务，不是多用户隔离产品。

1. `POST /api/harless/ppt/upload?name=paper.pdf`：原始二进制请求体，返回 `{id,name,bytes,sha256}`。不使用base64，不允许服务器路径/tenant/命令。
2. `POST /api/harless/ppt`：`{action:"preview",receipt_ids:[id],instruction?:string,slides?:number,template?:"lab"|"academic",operation?:"generate"|"restyle",budget_usd?:number}`。缺页数默认15；只接受本启动签发的回执。返回task_id、confirmation_digest、实际参数和影响，未调用模型。
3. 同地址确认：`{action:"submit",task_id,confirmation_digest}`。绑定输入/预览SHA；重复提交拒绝。真实模型启动必须real模式。
4. `GET /api/harless/ppt?task_id=...`：轮询状态、两组accounting、机械交付和artifacts。`completed`须双方真实回执通过，非agent idle；失败可保留一侧合格成品。科研/审美显示待用户评审。
5. `POST`取消：`{action:"cancel",task_id}`。
6. `GET /api/harless/ppt/download?task_id=...&artifact_id=...`：只接受服务端回执文件白名单，每次重新核SHA，提供PPTX/PDF/PNG；不接受任意路径。

运行用 `web_bridge.py` 创建已有 `trial.prepare_trial`，随后参数数组启动现有trial/SDK/MCP。不复制模型循环，不修改上游 Harness。

## 暂缓项与边界

网页自然语言逐页修改、网页反馈评审、后台持续学习和多账号隔离暂缓。现有MCP改页、`trial.review_trial`及离线反馈/候选认证接口继续保留；需要原job、版本绑定和明确授权。资料/组件库持续保留，默认不自动晋级。普通组禁止优化组合工具，优化组由宿主选定脚本；该工程差额不能全归因RSI。

原始日志、论文、成品及凭证在私有目录，公开只保留匿名报告。HTTP检查证明接口链路；不能宣称任意可解析PDF必然生成、科学全对或费用总会下降。
