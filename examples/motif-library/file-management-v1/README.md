# 已学习的文件管理 Motif 库

本目录发布此前被 `.local/` 忽略的真实学习产物。9 个库/策略文件、3 个在线 manifest 和3份认证/冻结摘要均逐字节复制，保留原始 SHA-256、`certified_digest`、`library_digest`、`policy_digest` 和训练/独立认证任务指纹。没有手写图替代学习结果，也没有重签旧证书。

| 目录 | 产物 | 状态 |
| --- | --- | --- |
| `read-edge-v1` | 初版 pin→read 库及两个 manifest 版本 | 历史版本 |
| `collection-v1` | 模型选集合后 foreach pin/read→gather | 历史版本 |
| `authorized-plan-v1` | preview→authorize→execute | 历史版本 |
| `collection-reentry-v2` | 验证前一集合完成后，模型选择新的集合并复用读取图 | 历史第二版 |
| `report-quality-v1/L1`、`L2` | 修订报告契约后的两版集合/重入策略 | 历史质量修订版 |
| `workflow-v1/workflow14` | 新流程独立认证的读取边、集合读取 | 最新已认证来源版本 |
| `workflow-v1/recovery15` | 新流程独立认证的授权计划 | 最新已认证来源版本 |

`catalog.json` 是公开索引：每项记录原实验 ID、原文件相对位置、文件哈希、格式/版本、重复副本来源及 manifest 对应库。`files.lock.json` 锁定目录全部公开内容。`workflow-v1/library-lock.json` 与 `result.json` 原样保留独立认证摘要，包括未认证的恢复分支、排除原因以及未做人类语义盲评的限制。

在安装仓库依赖、使用 Node 22.18+ 后，从仓库根目录运行免费检查：

```sh
node scripts/check-file-management-library.mjs
```

检查原始文件字节、内嵌摘要、训练/认证指纹分离、在线 manifest 与原库绑定，并使用现有 TypeScript Runtime 的真实策略校验器加载这些 JSON。它不访问 `.local`、不使用密钥、不请求模型。检查输出另外报告当前源码是否符合 G4 认证锁；如需强制要求一致，可运行：

```sh
node scripts/check-file-management-library.mjs --require-group workflow14
node scripts/check-file-management-library.mjs --require-group recovery15
```

本次授权发布范围是库及索引。G4 的部分 MCP/持久化任务源码仍在本地工作区，尚未随此次提交发布；索引明确记录缺失/不同的来源文件。下载者可以取得并检查库，但当前分支不能仅凭这些 JSON 执行 G4 新流程。接入时须发布并核对认证源码，创建当前任务/来源/权限/预算绑定，再通过正常验收；不能用历史 witness 的任务指纹充当新任务授权。默认 SDK/Web 不自动激活本目录，也没有新增自动 RSI 控制器。

训练来自 `deepseek-flash` 的原生工具轨迹；本目录的免费检查是产物完整性和 Runtime 加载检查，不是重做真实模型学习、质量评测或费用证明。原轨迹、HTTP、账单代理记录、失败、私人论文及任务副本继续留在被忽略的 `.local/`；公开摘要不包含正文。仅靠公开摘要不能独立重做原历史认证。固定脚本复用库属于另一实验组，此目录不包含它。

所有历史版本保留供追溯；“最新已认证”指对应冻结来源版本，不等于当前任意目录、规则或服务升级后仍适用。系列既有实验观察到 Motif 完整 API 成本高于预写脚本的情况，不能从库上传或免费检查推断成本优势。上传本身无模型调用、费用为 0。
