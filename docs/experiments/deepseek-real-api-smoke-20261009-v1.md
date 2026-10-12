# DeepSeek API 最小真实调用验证

- 实验 ID：`deepseek-real-api-smoke-20261009-v1`，在调用前确定。
- 类型：真实 DeepSeek API + 真实 Harness/MCP，来源是仓库的两份公开合成笔记；科研质量未评审。
- 问题：服务器 `.env` 凭证能否经统一入口加载，完成正常模型决策、MCP 读取和有来源的回答。
- 用户授权：已明确要求本次真实调用；沿用 0.25 美元预算，不进行外部写入或实际投稿。
- 运行状态：已完成；命令退出 0，真实 API、Harness 与 MCP 基本连通和来源链路通过。

## 任务与配置

场景 `scenarios/example/scenario.json`，题面要求读取 `note:alpha`、`note:beta`，解释试验不可直接比较的原因与缺失证据，并引用 `source_id/version_sha256`。这是最小连通性与证据链检查，没有训练组、效果对照或降本结论。

服务器项目目录 `/root/autodl-tmp/jjy`，先加载 `.local/remote-env.sh`。本次使用 `deepseek-official` / `deepseek-flash`，baseline，reasoning off，预算上限 0.25 美元，每请求最多 1000 输出 token，Agent step 上限 8，压缩默认关闭。代码基于 `2368235f274329be6227a8393b850633cb943da4` 加当前未提交修改；有效配置、版本及哈希另存私有实验目录。

```sh
npm run scenario:real -- --scenario scenarios/example/scenario.json --budget-usd 0.25 --max-output 1000 --max-steps 8
```

代理固定上游 `https://api.deepseek.com`；该入口不启动模拟 Provider。`max-steps` 是 Agent step 守卫，实际 HTTP 数以代理账本为准。私有凭证不进入本记录，`.env` 的规范字段为 `DEEPSEEK_API_KEY`。

## 结果、费用与限制

| 项目 | 已观察结果 |
| --- | --- |
| 运行 / Session | `7929653e0d9d4828bf46e4ff49394abd` / `sss-105f45630d444789bccf467f3718006a` |
| 完成状态 | `done` / `completed`，退出码 0 |
| 真实模型请求 | 3 次，代理账本响应均 HTTP 200，模型 `deepseek-flash` |
| MCP 调用 | 4 次、0 错误；两次 `pin_note` 与两次 `read_pinned_note` |
| 输入 token | 2712；缓存命中 1536、缓存未命中 1176 |
| 输出 / 总 token | 1043 / 3755，reasoning token 0 |
| 端到端耗时 | 9.729 秒 |
| 费用 | 代理估值约 0.001614 美元，低于本次 0.25 美元上限；账单实付未核对 |

检查实际 `tool/call` 与 `tool/result` 的 callId 配对：两份来源 ID 和版本摘要由当前公开笔记内容重新计算一致，read 正文与来源一致，回答完整引用这两份 ID 和摘要。模型首先并行 pin 两份笔记，再读取两份来源，最后完成回答；没有使用固定模拟 Provider。源码上游、HTTP 200、真实 usage 和事件共同支持本次真实调用成立，不能只以进程退出码代替这条证据链。

首次预检发现服务器 `.env` 使用 `DEEPSEEK_APIKEY`，入口要求 `DEEPSEEK_API_KEY`，因此当时未加载凭证。已在原私有文件补齐规范变量并设为 0600；不显示或复制密钥到公共文件。再次预检加载成功后，才执行本次唯一一次真实场景；该配置修复没有发起模型请求。

有效配置及结果同时保存在两端私有 `.local/experiments/deepseek-real-api-smoke-20261009-v1/`，包含 `effective-config.json`、`verification.json`、`preview.json`、`manifest.json`、`answer.md`、`metrics.json`、`cost-ledger.jsonl`、`agent-events.jsonl`、退出码和运行日志；服务器原目录 `.local/runs/7929653e0d9d4828bf46e4ff49394abd/` 保留。逐行费用有小数舍入，公开记录统一报告约值；代理记账不是账单实付。

结论：在当前服务器与固定 SDK/Harness 版本下，凭证、真实模型决策、MCP 读取和可追溯回答能完成。来源与引用已核验，但未进行独立盲评，科研质量未评审；合成笔记不代表真实论文场景，baseline 单次成功不支持 Motif 降本。当前 3080 Web 仍为原模拟服务，没有重启或验证真实 Web；后续以 `web:real` 单独验收网页路径。
