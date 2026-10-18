# GeneLoop：本地文件管理与持续 RSI

当前使用 `feature/rsi-research-agent`。本分支的 `/management` 已接入原生 GeneLoop；本页是本地单用户入口，历史入口和实验结论保存在[原 README](docs/history/readme-before-local-entry-20261018.md)。本任务不合入 main。

## 安装与启动

需要 Node 22.18+、Python 3.10+ 和现有 DeepSeek 配置。

```sh
npm ci
npm run setup
npm run management
```

入口默认真实 DeepSeek Flash / Off。凭证读取环境变量、项目 `.env` 或已有私有 `.local/deepseek.env`，不打印密钥。启动时不会调用模型；在本地登录地址打开前端，新建工作区、会话，上传文件并用 `/management` 说明需求。`--real-model` 旧写法继续兼容；仅免费诊断使用 `npm run management -- --mock`，模拟轨迹不能学习。

工作区任务副本内默认允许复制、移动、重命名、建目录和可恢复隔离；覆盖、永久删除及外部目录逐计划确认。凭证、私人资料、轨迹和恢复数据均不上传 Git。

## 状态、经验与恢复

```sh
npm run management -- status
npm run management -- motifs
npm run management -- backup --output .local/backups/management.zip
npm run management -- verify-backup --archive .local/backups/management.zip
```

日常沿用 `daily-management-real-v3` 同一持久化库；旧库、失效项、停用项和失败候选继续保留。`motifs` 区分历史版本记录与当前源码兼容数量，任务执行仍核验实际 schema、权限、文件状态和证据。

每任务最高 USD5、96 步与请求、4000 输出、2 次验收修复；原系列 USD1000、共享学习 USD25，不因重启或新建库清零。每轮真实任务封存后自动发现、学习、独立认证并激活合格候选，后续任务自动匹配；失效或验收失败回到普通 Harness。净收益只持续记录，不作学习门槛。

[本地使用与备份迁移](docs/management-local.md)记录持久化目录、备份范围、恢复和换路径迁移边界。[文件管理交接](docs/handoffs/file-management.md)及[本轮实验](docs/experiments/management-local-20261018.md)保留验证与失败；[共享接口](docs/changes/management-local.md)说明权限、迁移和认证约束，原生集成历史见[此前实验](docs/experiments/management-native-20261015.md)。

普通聊天、`/data`、`/ppt`、`/paper` 及其它入口仍保留，见历史 README 和各场景文档。其它 MCP 的持续学习需独立登记材料、权限和验收。多账号部署适配后置；本地单用户闭环不依赖账号网关。
