# 论文校对场景当前交接

## 2026-10-17：四档思考强度代码兼容

- 当前产品默认 `paper-web-v2` 为四档任务准入代码的免费兼容重编；原 `paper-web-v1` 包、两训练/一留出决定、图、完整 24 工具 Schema、来源证据保持。无新采集或质量/成本晋级；默认仍为 Execute。
- 模型选择和校对判断不变，off/low/high/max 由本轮冻结，两侧同档。新界面与实际请求验证见[滑杆验收](../experiments/geneloop-reasoning-strength-slider-20261017-v1.md)。

## 2026-10-17：普通文档读取 Execute

- `codex/all-scene-motif-execute` 基于已合并 `30b5a37`。产品默认库切换为 `motif-libraries/paper-web-v1`；旧 `paper/` Shadow 及私有论文/参考文献 Execute 路线保留，不把旧证书改成新授权。
- 新库经两独立 Baseline 训练与一留出认证，只续接模型已固定来源的默认第一页读取；完整 24 工具和后续校对/导出不变。来源版本、默认参数、实际 Schema、代码锁、独立题目和账本均校验，失败回到模型。
- 当前网页 Off / On 是模型 API 的 disabled / enabled+high，不是校对流程轮数；Motif 的 Execute 与此独立。采集、失败成本、质量限制与发布状态见[本轮记录](../experiments/all-scene-motif-execute-20261017-v1.md)。下方保留 PR #42 历史整合证据，不能替代本次验收。

- 更新时间与交接人：2026-10-16，Codex。
- 目标与本次范围：基于最新 main `c793937`（含 PR #40–#54） 整理 PR #19 的论文参考文献与 RSI 能力，保留 main 的多格式读取、来源表格摘要、最小修改规则与 PDF/Markdown 普通报告。
- 分支 / commit / 工作区：`codex/main-paper-rsi-integration`，替代旧 PR #19；最终 main 兼容复核通过，已推送并创建 [PR #42](https://github.com/jingyio/DeepSeek-Harless/pull/42)，用户已授权在 CI 通过后尝试合并。旧 PR 分支与所有历史实验保留，不把历史机制验收当作本次整合验收。
- 已完成：同一 paper_checks/paper_trace_rsi 共 24 工具；安全 ZIP、只读引用取证、BibTeX 判断批量写入、任务草稿/定稿、受审阅脚本 PDF 导出均复用旧实现。共享 Runtime 保留 Shadow 不跳过及受守卫的 Execute。
- main 兼容：普通报告不被强制转为参考文献报告；已启动的引用报告接受当前任务普通报告或历史排版工具的有效交付。默认 `motif-libraries/paper` 保留，管理员可显式指定私有库；无私有排版包不阻断普通报告。无效私有库拒绝激活，不静默换库。
- 已验证：完整 Python 987/Node 722 通过、3 跳过；smoke/motif/controls/scenes 通过；实际两成员/10 草稿通过。真实 Shadow 4 请求/1 候选/0 跳过，Execute 3 请求/2 验证跳过，均 0 工具错误；整合 PR #40 后专项 Python 62、全量 Node 731 通过/3 跳过，真实新 Execute 5 请求/1 验证跳过/0 错误。见[整合记录](../experiments/paper-main-integration-20261016-v1.md)。
- 实验结论：旧 [RSI 机制闭环](../experiments/paper-rsi-loop-mechanism-20261016-v1.md)有真实窄链见证，非本次代码版本的收益结论；学习/发布仍显式离线触发，不宣称 Web 全自动学习。更多正负历史证据保留在 [PR #19](https://github.com/jingyio/DeepSeek-Harless/pull/19)。
- 配置与数据：Registry 在 `config/harless-scenes.json`；私有包用 `HARLESS_PAPER_RUNTIME_BUNDLE`，历史排版包用 `HARLESS_PAPER_RENDERER_ROOT`。旧 23 工具包不适配当前 24 工具，须用实际 MCP Schema 和最终代码重新编译。材料、凭证、轨迹和结果仅留 `.local/`。
- 本次修复：补齐根 PDF 依赖、统一 Windows JSON 路径，保留原生图片；普通报告恢复与参考文献交付按条件分发，阻止重复导出。`4179775` 的双平台 CI/V100 全量通过；最新主线整合本机 Node 762/3 跳过、PPT 全30页实际完整 Schema 通过，最终 V100 最终 Python 1011/Node 762 通过、3 跳过，smoke/motif/controls 通过；最终 CI/合并见 PR 回执。
- 未完成与阻塞：24 工具已按最终执行代码重编，真实最后一轮 2 请求/1 验证跳过/0 工具错误；[PR #42](https://github.com/jingyio/DeepSeek-Harless/pull/42) 已发布待审，最终 controls/scenes 均通过；完整论文真实性、跨论文泛化及稳定费用收益未验收。
- 接手下一步：审阅替代 PR（含停止钩子按场景分发）；私有最终包为 `.local/integration-check/compiled-main54/runtime`；合并后按独立发布流程部署、复核 owner/member，不直接切线上服务。
- 权限与预算：延续当前论文实验授权，公共产品额度、用户隔离及既有累计账本不变；本轮五次真实运行合计 17 请求/$0.044873460 代理估费，含三轮全部调用；实付未知。
- 回退与风险：未更改生产服务。回退到整合前 main `c793937`；回退不删除旧库、轨迹、用户数据或账本。
