# 真实论文引用阶段检查与连续接管（2026-10-10）

## 问题与范围

将上一轮预选两项输入的局部证明扩大到用户原稿的真实修订阶段：主稿活动 input 树有 34 个引用键，其中 15 条带 arXiv 标识。模型选择原始著录和查询批次，比较新来源并追加正式出版来源，输出 `triage.json` 和正文引用对应问题。不是全 Bib 库/完整论文修订/PDF 验收，也不是独立论文泛化。

结构原型继续冻结使用 `parameter-motif-proof-20261010-v1` 从五条既有正常轨迹编译的完整读取、arXiv 获取原型。目录构建和批次提交协议为手工确定的工程适配；没有声称自动学到选取策略或完整场景 DAG。Python 离线构建来源目录，TypeScript 接管已明确选定的确定性工具续接，科研版本判断留给模型。

## 实现与对照

- `scripts/paper-reference-continuation.py`：服务器入口，复用既有 Harness/预算/实验控制器，默认仅预览。
- `src/adapters/dsh_parameter_motif.ts`：首次完整读取冻结目录后，接受模型原生 write 成功提交的 `selection.json`；每项须与目录完全对应，来源与库摘要、会话、schema/工具顺序一致；每批最多 8 项。允许多轮不同计划；重复计划/条目、目录外目标和来源变化拒绝接管。
- `schemas/parameter-motif-selection.schema.json`：v2 绑定用目录字节摘要引用完整来源列表，不让模型反复复制全部来源哈希。旧固定 v1 输入协议保持兼容。
- 收集结果全部验证后才记录一次 verified skip，随后模型判断/继续。失败保留证据并回到原模型；新有效计划可继续接管。同一计划内，已由原生工具成功取得的结果不再合成重复调用；全部满足时直接交回模型，不虚报 skip。
- `scripts/check-reference-continuation.py`：检查输出集合、原始 API 用量、选定批次/验证汇合、重复网页调用及 P0 待复核标记。它不替代人工语义评审。

三组均使用同一题面、输入字节、目录、模型和原生工具集合/顺序，区别是 baseline / shadow / execute。模型可以使用终端脚本与额外正式来源查询；这些工作当前不接管。绑定与最终阶段报告的文件写入只限私人实验副本；不改上游或原稿，不写外部应用。

## 配置与复现

服务器 `/root/autodl-tmp/jjy`，加载 `.local/remote-env.sh`。模型 `deepseek-flash`、`reasoning_effort=off`，压缩关闭，单次输出 8192，无请求次数上限；已授权私人论文副本非沙箱终端。沿用此前冻结的累计 4.84521046 美元上限（含全部旧费用，不重新增加一美元），另受此前总上限 5 美元约束。

```sh
node scripts/project.mjs python scripts/paper-reference-continuation.py
node scripts/project.mjs python scripts/paper-reference-continuation.py --mode baseline --call-model
node scripts/project.mjs python scripts/paper-reference-continuation.py --mode shadow --call-model
node scripts/project.mjs python scripts/paper-reference-continuation.py --mode execute --call-model
node scripts/project.mjs python scripts/check-reference-continuation.py .local/paper-reference/paper-reference-continuation-20261010-v2
```

真实模型必须串行执行，已有运行拒绝覆盖。未结算的保守预留继续计入累计额度。私有 manifest 记录代码/来源/库/目录/题面/schema/顺序摘要、版本、模式与预算；原始材料、请求、事件、记账和交付放同名 `.local/paper-reference/` 目录。新代码尚未提交/推送，混有他人共享工作区改动，不能整体提交。

## 第一版负面证据（v1，保留不覆盖）

| 模式 | 请求数 | 代理新增 USD | 秒 | verified skip | 输出条目/目标 |
|---|---:|---:|---:|---:|---:|
| baseline | 43 | 0.064526 | 164.96 | 0 | 18/15 |
| shadow | 17 | 0.036422 | 59.30 | 0 | 15/15 |
| execute | 17 | 0.049036 | 77.77 | 4 | 19/15 |

execute 的 4 个批次共 22 次收集结果通过守卫，没有 unverified bypass；shadow 验证 9 项。三组均覆盖目标 15 条，但 baseline/execute 多列其他文献，存在范围漂移；baseline 还把正式版本更新问题标为 P0，不能视为合格交付。模型使用工具/追加来源不同，execute 与 shadow 请求数相同且费用更高，不能从 43→17 宣称因果降本。

execute 的 27 次网页获取对应 27 个不同 URL，未发生重复网页调用。现场曾仅根据工具次数误判重复，后经事件逐 URL 核对修正；新增同批去重守卫是诊断中发现的潜在边界修复，不是对已观察重复的修复。v1 第一轮 shadow/execute 代码保存在私有 `code-history/first-pass.tar.gz`；baseline 启动时尚未补入新 schema/checker 哈希，后两组已补，差异保留在 manifest。

第二版将 main 活动树、输出集合和 P0–P3/版本规则明确写入三组共同题面，同时完善同批结果观察与去重。不得将两个版本混在一组成本比较中。

## 第二版结果

| 模式 | 请求数 | 代理新增 USD | 秒 | verified skip | 最终目标覆盖 |
|---|---:|---:|---:|---:|---:|
| baseline | 50 | 0.070094 | 255.36 | 0 | 15/15，无额外条目 |
| shadow | 15 | 0.038703 | 60.54 | 0 | 15/15，无额外条目 |
| execute | 25 | 0.053869 | 96.23 | 2 | 15/15，无额外条目 |

shadow 4 批验证 30 项（15 读取/15 查询）。execute 接受 4 批：读取批次 8 项由 Runtime 接管、另 7 项原生已完成；查询批次 4 项原生已完成，后一批 7 项中 4 项原生完成、3 项由 Runtime 接管。Runtime 合计 **8 次读取 + 3 次查询**全部复核，记录 2 次整请求跳过；另 12 个目标查询来自原生路径。2026-10-10 逐批复核审计后修正此前把 11 项全写成查询的记录；原始指标和账本未改。无 unverified bypass；execute 的 37 次网页获取对应 37 个不同 URL；基线 29 次对应 28 个 URL（是否为合理重试未单独裁定）。

| 模式 | 全部输入 token | 缓存命中 | 未命中 | 输出 token |
|---|---:|---:|---:|---:|
| baseline | 3,556,192 | 3,469,312 | 86,880 | 19,345 |
| shadow | 682,579 | 613,504 | 69,075 | 11,916 |
| execute | 1,532,287 | 1,439,488 | 92,799 | 14,494 |

不能把 50→25 都归功于 Motif：Runtime 审计只证实 2 次拦截，其他差异来自模型分批、终端脚本与正式来源追加策略。execute 比 shadow 请求更多、估费更高，未命中输入也高于 baseline。单次不同轨迹的原始费用只是观察值，尚不支持等质因果降本。

人工查看三个阶段输出：范围修正后全覆盖、无 P0 标记，但发现质量差异。三组需修正条目数为 5/12/7；shadow 把可接受的作者省略等过度判为 P1；execute 对尚未独立核对的会议标题差异仍标 P1，即版本证据不足时风险等级过强。正式会议/期刊版本判断、正文实际对应内容仍需独立核验；不能据集合覆盖就宣称报告正确。原始输出不追改。本实验质量未盲评，任何结构/覆盖检查通过都不等于正式投稿验收。账单实付、人工修订时间与开发维护成本尚未知。

两版共六次新真实运行，新增代理估费约 **0.31265 美元**；含历史失败/未结算预留累计约 **4.19263**，原冻结累计封顶 4.84521046，余额上界约 **0.65258**。本地与服务器均 **172 Python / 80 Node**免费回归通过，本地无模型 smoke 18 题/83 来源通过；恢复/变更/拒绝验证属于错误注入诊断，本轮没有观察到真实工具失败后的恢复。

私有 manifest/verification-summary 已保存，本地同步排除 Harness 凭证目录；v2 定稿快照为 `code-history/final-pass.tar.gz`。v2 baseline 启动时未加载插件，随后新增重复条目守卫用于 shadow/execute；这项代码哈希差异已保留。

## 结论与边界

第一版已观察到真实阶段任务内连续四次结构续接，但没有证明合格总成本下降。第二版支持“真实阶段任务中模型选定输入后，可多轮接管并正确区分已经取得的结果”，尚不支持完整报告质量与稳定降本。下一步将逐字段证据与风险判定分离，先用独立评审锁定质量，再比较相同查询/修复条件下的成本；不继续重复跑同一原稿来冒充泛化。仍缺完整原编号 PDF、逐页视觉验收、跨论文任务、脚本节点自动编译与普通脚本/Code Mode 对照。
