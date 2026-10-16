# 论文校对场景当前交接

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
