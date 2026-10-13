# PPT 私有库取回与 V100 同步

- 日期：2026-10-14；范围：用户开启旧服务器并明确授权下载、同步既有 PPT 库。只做文件迁移和无模型验证，不启动真实模型、改写旧证据或启用产品 Execute。
- 来源：旧部署 `/root/autodl-tmp/xjj`，代码 commit `6ced8277d7743bcb260975290665af26d105274a`。本次确认该部署的 `.local/research-ppt` 保留 12 份 `online-manifest.json`，包括 8 份早期库以及 V6 的两份、V7、V8c 各一份。该目录不包含已检查到的 V13/V14 私有运行库；那些历史记录指向另一台服务器，不把本次取回称为所有历轮数据迁移。
- 已完成：下载 12 份库及传递依赖、原工具代码、Schema、认证证据与轨迹，共 322 文件、12,374,159 字节；压缩包 5,405,830 字节。密码、凭证、`.env`、SSH 配置和 `node_modules` 未纳入备份。源文件不修改；私有副本不进入 Git。
- 私有定位：本机 `.local/imports/ppt-library-transfer-20261014/`；V100 `/home/jingyij/jjy/.local/imports/ppt-library-transfer-20261014/`。两端均有 `transfer-receipt.json`、`restore-verification.json` 和 `restored/transfer-snapshot.json`，还原文件在 `restored/snapshot/` 内保留仓库相对目录。原绝对路径仍在原始证据中，不能直接当新部署路径。
- 校验：旧服务器、本机、V100 的压缩包 SHA256 均为 `6a8f4f4fffaa05b38b3a7ffe3f56e23f46d3fe121e369d4015b222b392afdc15`。本机及 V100 对 322 文件逐项核验大小与 SHA256，通过。4 份完整证据锁及输出锁在保存的旧部署中均匹配；8 份早期库没有完整依赖锁，不能据此认定已满足当前认证要求。
- 当前 Runtime 诊断：本机 `main` 的核心及 V100 独立集成 checkout 的 `validateOnlineManifest` 各接受 10/12、拒绝 2/12；结果在私有 `current-runtime-manifest-check.json`。这是格式和内部摘要验证，未验证实际 MCP、工具权限、用户输入适用性或模型旁路。真实模型请求 0、Verified Skip 0、新增模型费用 0。
- 兼容性限制：完整证据锁与当前代码对照发现 V6 的场景工具依赖已变化；V6 witnessed、V7 和 V8c 还绑定了旧版 `online_skill_runtime.mjs`。不能改写旧哈希、忽略根路径或直接把格式通过称为产品启用。Web Scene Registry 当前仍未绑定该库。
- 接手下一步：优先用 V7 的正常独立轨迹在 V100 当前工具 Schema/Runtime 下重新编译认证，保存新派生证据并关联原库；接入每项任务当前批准输入的版本绑定；随后验证 Shadow 审计与受限 Execute，分别记录真实请求及 Verified Skip。V6 图件工具和 V8c 页面读取能力须先核验当前场景契约，不自动复用早期准入程序。
- 交付状态：取回、同步和无模型校验完成。产品库绑定、成员场景部署和真实 Execute 验收仍未完成；本记录不宣称降本或任务质量通过。迁移不覆盖 V100 的现有分支、私有配置和用户数据，费用及授权范围未扩大。
