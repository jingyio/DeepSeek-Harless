# GeneLoop 文件管理：原始学习 Motif v2

本包逐字节发布日常持久库第5版的4个已学习图：批量 pin/read（2节点）、inspect/pin/read（3节点）、execute/inspect/pin/read（4节点）和preview/execute/inspect/pin/read（5节点）。这些JSON来自真实普通Harness轨迹及独立认证，不是手写模板；原policy_digest/certified_digest、训练/认证指纹及文件SHA完整保留。

`catalog.json`仅发布匿名化认证摘要、原证书SHA、角色分离及实际执行次数。原证书所需的私人任务、路径、原始轨迹、账本及材料不上传；摘要不能替代这些运行准入证明，所以本公开包`default_activation=false`。日常真实入口创建或沿用自己的持久库，随后自动从正常任务学习并认证；原机器已有的库继续使用原私有证明。不能把公开参考包直接当成任意工作区写权限。

免费校验：`node scripts/check-operation-library.mjs`。原始字节、内嵌摘要、角色分离及TypeScript实际校验器均核验，源码兼容性单列报告；`--require-runtime`强制源码一致。无密钥、无云调用、无私有目录依赖。细节见`docs/changes/persistent-rsi-integration.md`和`docs/experiments/persistent-rsi-20261015.md`。

训练、建库和认证费用包含在实验记录；上传与校验不产生模型费。失败和旧版本保留。该批支持顺序有界图、重复执行与唯一字符串数组≤40，不能据此宣称任意MCP/任意循环或已证明长期净收益。
