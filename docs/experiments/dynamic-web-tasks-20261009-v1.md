# DeepSeek Harless 动态任务接口免费验收

- 类型：真实 Harness/Web/MCP 协议诊断，模型与 embedding 使用本地夹具；科研质量未评审。
- ID：`dynamic-web-tasks-20261009-v1`，实现后补记；开始前未单独固定实验 ID，各次启动始终有独立 RUN_ID。
- 代码：`feature/paper-submission`，基于 `2368235f274329be6227a8393b850633cb943da4` 加未提交修改；尚未提交/推送。原 Web 首版与其他场景工作保留。

## 问题与条件

验证同一个官方 Web 进程能否处理前端的新题面、结构化消息、资料引用与附件，保持三模式和逐任务统计，不串用旧 Session/预算/Motif 授权。模拟 Provider 不理解任意科研请求；成功只支持接缝可运行。

环境为服务器 `/root/autodl-tmp/jjy`，Ubuntu 22.04、Node 22.23.3、Python 3.10.8，固定 DSH `0.1.5-rc.3`。运行前 `source .local/remote-env.sh`。默认 DeepSeek Flash、reasoning off、输出 cap 1000、压缩关闭。公共配置见 `config/harness-web.json`；每次实际配置及文件摘要在私有运行目录的 `effective-config.json`。

## 复验与已观察结果

```sh
npm test
npm run smoke
npm run motif:check
npm run web:check
npm run web:tasks:check
```

| 检查 | 结果 | 边界 |
| --- | --- | --- |
| Python / Node | 146 / 44 项通过 | 单元与协议回归 |
| smoke | 18 题、83 来源对象，通过 | 不调用真实云模型 |
| Motif 样例 | 重编译及四组 Harness 检查通过 | 历史结构，合成来源 |
| 冻结 Web | 11 组通过 | `--frozen`，保留旧守卫 |
| 动态 Web | 13 组通过 | 同进程连续任务、真实 HTTP/MCP、本地模拟模型 |

动态组覆盖：自由文本、user 消息、三模式、幂等、摘要篡改拒绝、未知能力/来源拒绝、同 Session 文件 receipt、图片受控拒绝、零预算、原生聊天新会话、变化题面回退与取消。Example 每个合格诊断任务独立为 5 次代理请求和 4 次只读工具；之前的记录不会被后续任务覆盖。Portfolio baseline/shadow/execute 为 14/14/7 次请求，三组各 13 次工具，execute 结果核验后计 5 次跳过；变题回到 14 次，不复用旧绑定。

当前模型 metadata 不支持图片：图片进入正式 admission 后明确失败，模型请求数为零。这是正确拒绝的证据，不是图片理解成绩。普通文件确认了真实上传 receipt 与同会话绑定，未评估 PDF/论文附件内容理解。

所有终态关闭对应预算路由；队列编辑与 Goal continuation 无法悄悄改变已绑定任务。费用、token 和缓存字段来自模拟 usage；真实云费用为 0，不支持降本结论。真实模式的确认拒绝已用合同测试验证，未调用真实 DeepSeek API。

## 失败及修正

首次多任务复验到累计第 25 次请求时，模拟 Provider 的旧全局 24 次上限返回 HTTP 500。失败任务/ledger 保留在私有 `.local/web/`，没有删除证据或改为通过。夹具现在允许由启动器传入全启动次数上限，原样例默认仍为 24；后端每任务与全启动上限分别保留。更名版重新通过 13 组。

原始报告与日志为 `.local/web/tasks-protocol-check.json`、`protocol-check.json`、`harless-*-check.log` 与各 RUN_ID 的私有目录；均不入 Git。免费浏览器验收单独记录在 Web 交接中，不能仅以 HTTP 200 代替。

## 最终免费一键与正式入口浏览器验收

主 Agent 用本地浏览器访问服务器同版本 3084 运行 `b94e903d4a7c434dad86ee3b0e04be03`：免费模式没有额度表单，“开始免费联调”自动执行规范化/预览、必要上传与提交，不要求第二次确认。

| 输入与模式 | Task / Session | 结果 |
| --- | --- | --- |
| 文字，baseline | `6c16010fedb04f4aa3dd4ad5c15394be` / `session-cee09b6c-8793-422a-9c2e-73d93abf57df` | completed，5 次代理请求、4 次 MCP，真实费用 0 |
| JSON user messages，execute | `c8eacea8a8e146f486fb340541602f1c` / `session-99a8032c-44b8-4977-935c-f67aa28bde21` | completed，5 次代理请求、4 次 MCP，真实费用 0；`no_certified_library` 明确回到普通 Harness |
| 另一个聊天的浏览器，同一运行 | `9ecedf8ae3a146d88cbf0a627f27b622` | completed，5 次代理请求、4 次 MCP，真实费用 0 |

刷新后历史与独立任务仍保留，私有截图为 `.local/web-review/browser-free-one-click.jpg`；前期两项文本连续任务的截图 `.local/web-review/browser-multiple-tasks.jpg` 保留。上述支持动态输入、一键交互、独立追踪及缺库回退；模拟模型不证明任意科研输入被理解，免费模式简化也不开放真实模型免确认。

正式端口已切换并完成任务验收：新动态 3080 运行 `f91a53c78a524bbaa3fb935fd68c8b4f` 保持运行，本地浏览器认证进入 `/tasks`，看到 DeepSeek Harless 标题、免费一键和三模式；同一运行无重启完成两项不同题面，无预算输入、无需第二次确认：

| 正式 3080 Task / Session | 结果 |
| --- | --- |
| `2057d2c5580d466d8efea9c385ad491a` / `session-76fe9ec7-a112-45e4-b472-992f1f537c01` | completed，5 次模拟模型请求、4 次真实只读 MCP，实付 0 |
| `ae83a4b3ad104fc7a4d0bf5760198de5` / `session-d53cd760-75e9-4540-830f-fd65a71c9e59` | completed，5 次模拟模型请求、4 次真实只读 MCP，实付 0 |

刷新后两项历史保留，私有截图 `.local/web-review/browser-live-multi-tasks.jpg`。以上正式入口两任务为最终浏览器闭环证据；前述 3084 为同版本补充诊断，运行、任务和 Session 不混用。旧冻结 3080 运行 `b1bce3882e5f470eb6f8ccc088e7a505` 与诊断 3084 `b94e903d4a7c434dad86ee3b0e04be03` 已按身份停止，原资料保留。当前代码和记录仍未提交/推送。

## 下一步与限制

免费一键及正式入口切换已完成上述浏览器验收，真实模型仍预览确认。需要用户在服务器私有 `.env` 填密钥并明确授权真实任务，才能验证真实 API、答案质量及费用。当前一个启动注册一个能力配置、一次一个活动任务、一任务一 Session；没有多账号、跨启动恢复、任意大文件或论文生产工具闭环。后续场景需提供自己的 MCP 能力与认证 library。

## 公共 PR 发布复核

代码整理为 `feature/web-task-api` 的 `dcdfdc9`，基于已合入旧冻结入口的 `bdf934f`，已推送并创建 Draft [PR #2](https://github.com/jingyio/DeepSeek-Harless/pull/2)，尚未合入 main。原实验发生时的分支/dirty 快照保持原记录，不能追改为本次提交。服务器独立工作树再次通过 146 Python、44 Node、18 题/83 来源 smoke、动态 13 组及冻结 11 组；本次是提交完整性与协议诊断，没有新增真实模型请求或质量/降本证据。私有复核结果在 `.local/pr-validation/web-task-api-dcdfdc9/.local/validation/`；原论文工作区和 3080 服务保留。
