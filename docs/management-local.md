# 本地文件管理日常使用

唯一日常入口为 `npm run management`，默认真实 DeepSeek Flash / Off。启动不产生模型请求，发送任务才计费。旧 `--real-model` 参数仍兼容；`--mock` 只做免费诊断，不生成可学习证据。不要使用历史 `/tasks` 入口来判断新版 `/management` 是否接通。

## 使用与状态

安装 `npm ci`、`npm run setup`，通过环境、项目 `.env` 或既有 `.local/deepseek.env` 配置 DeepSeek。打开启动日志所指的私有本地登录入口，创建工作区和会话，上传文件，用 `/management` 描述需求。历史访问地址可能在服务重启后需要重新登录。

`npm run management -- status` 免费查看当前管理库与凭证是否配置；`npm run management -- motifs` 免费列出每个经验档案的代数、经验类型、停用数、源码失效数与失败候选。不同源码/证书版本的经验记录不能当作不同工作流数量，也不能把兼容数当作历史学习总量。当前匹配还须通过具体任务的 schema、权限、参数及版本守卫。

日常真实库保持 `.local/rsi/daily-management-real-v3`；原生会话、任务与全局账本位于 `.local/web`，工作区任务副本位于 `.local/management-copies`。实验旧库、旧脚本、失败候选、原始轨迹和费用继续保留，勿清空 `.local`。本轮只使用个人分支，不合入 main。

## 私有备份

先正常退出本地服务，等待学习认证进程封存，再执行：

```sh
npm run management -- backup --output .local/backups/management.zip
npm run management -- verify-backup --archive .local/backups/management.zip
```

备份固定覆盖 `.local/rsi`、`.local/management-copies`、`.local/web`、`.local/runs`、`.local/file-management`、`testpdf/file-management-experiment`、`.local/file-jobs`、`.local/operation-jobs`、`.local/management-acceptance` 和 `.local/management-imports`。其中包含连续 RSI 库/配置/证书/原轨迹、任务副本、前端历史/账本、SDK 原始运行、旧文件管理实验材料与恢复数据。其它开发临时目录、工作区外原件、代码和未列出的材料需另行备份，不承诺覆盖整台电脑。

相同字节只保存一次；恢复文件使用独立副本，不用相互影响的硬链接。逐文件 SHA、空目录、原费用及预留、原源码摘要一同冻结，备份前后核对，防止复制期间发生变化。归档权限为本机私有 0600，不上传 Git。生成的 `dsh/profiles`、`web-dsh/profiles` 内 `node_modules` 不打包，恢复后重新安装；用户资料中的同名目录不排除。API 凭证及 DSH 凭证存储不属于迁移授权，恢复后沿用本机独立配置。

输出已有文件、符号链接、活动服务/worker、数据改变或损坏包会拒绝。失败回执与未完成归档保留，不删除原件。备份是本地私有归档，不能把它当作脱敏公开经验包。

## 原路径恢复

```sh
npm run management -- restore --archive .local/backups/management.zip
```

只恢复原项目绝对路径下的缺失数据根；已有数据若逐字节相同则幂等跳过，任何差异都拒绝覆盖。恢复前后校验所有文件和目录，原证书、轨迹、任务与费用字节不改写。中断恢复仍要求原源码、权限及文件版本；升级后不会强行续跑失效任务。

## 换路径冷迁移

在新检出的项目目录准备好代码和依赖后，从原目录执行：

```sh
npm run management -- migrate --archive .local/backups/management.zip --destination /absolute/path/to/new-checkout
```

目标须没有已有活动管理数据。原始备份完整复制到目标的私有 `management-imports`；用户文件提取为可打开/重新上传的副本。历史经验、证书、任务和前端历史留在原始归档中供核验，不能将旧绝对路径、旧确认或运行中任务自动转为新授权。新日常档案通过后续真实任务和独立认证形成可执行经验；原经验不删除、不重签、不自动激活。此模式不承诺原会话在新路径中无缝续跑；需要原任务时按对应源码版本在原路径恢复。

原系列已用费用、请求、尝试数及未结算上界随导入回执继承；原学习费用/预留和原生服务累计计数同时保留。重复导入同一包幂等；不同包或已有数据不能通过反复导入重置预算。导入回执或归档元数据改变会阻止后续预算使用。

## 日常目标验收

以下明确表述可在第一步文件操作前冻结完整验收条件：

- `按文件类型复制整理到 organized，保留全部原件和内容，并创建 organized/empty 空目录。完成后核验并提交报告。`
- `把 note.txt 移动到 arranged/note.txt，保留其他文件不变。完成后核验并提交报告。`
- `把 note.txt 重命名为 renamed.txt。完成后核验并提交报告。`
- `通读全部文本文件，给出完整读取覆盖清单，不修改任何文件。完成后核验并提交报告。`

按类型整理使用扩展名规则：PDF/Word→documents，Excel/CSV→tables，图像→images，TXT/Markdown/JSON→notes，其余→others；保留原相对路径。验收检查原文件覆盖、实际输出字节、预期目录/空目录、移动后的源路径和无额外影响。读取要求所选文本完整可读且未截断，不能用“调用过读取工具”代替完整阅读。

`sss-management-quality-v4` 分开记录效果完整性与目标验证。未完整解析的表述（例如“按重要性整理”）、冲突目标或未支持的语义目标显示“目标待复核”；Agent 仍可按原权限执行并报告实际结果，不把内部效果校验当作全部业务目标已经实现。新的谓词标准独立认证，旧失败和旧证书不重签。任意自然语言业务目标仍未全面自动验收。

覆盖、不可恢复删除和外部目录继续逐计划确认。副本内普通整理不额外增加授权步骤。每任务5美元/96步和请求/4000输出/2修复，系列1000、共享学习25以及更低既有限额都保留；净收益持续记录，不作为开启学习的门槛。
