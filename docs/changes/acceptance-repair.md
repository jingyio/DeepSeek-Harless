# 验收失败后的普通Harness修复闭环

2026-10-13，用户授权在原权限和预算内补有界修复，用真实模型验证后于北京时间20:00前推送既有 `feature/rsi-research-agent` 分支。本记录在实施前建立，结果完成后追加。

采用显式场景配置 `acceptance_guard`，由TypeScript监听公开Harness停止生命周期；固定Python文件验收器只核对原任务、实际报告/读取/文件结果。验收不通过时先保存不可覆盖的每轮现场，再在同一Session发送结构化失败诊断，关闭该会话Motif续接，交普通DeepSeek修复并重新验收。最多2轮修复，共用原预算代理、步数上限、MCP进程与授权，不能重启/重置预算或放宽验收来通过。

源码修改范围：场景配置适配器、停止/修复插件、Motif回退守卫、固定验收脚本及运行指标；原文件工具、报告契约、旧库和旧基准结果保持。新配置替代原缺收据续写门，避免双重重试。无法修复的历史范围违规、外部版本变化、权限不足、预算或次数耗尽应保留失败并停止。原始DeepSeek费用、失败、事件和每轮副本均留私有区。

本闭环是普通程序修复策略，不能当作新学得Motif或整体任务质量保证。新验证独立记录，不追改此前22项失败。分支推送不等于正式上线，现有2项依赖high告警和文件管理Web产品入口限制继续披露。

## 实施与验证完成

新增src/adapters/dsh_acceptance_guard.ts、固定scripts/validate-file-delivery.py，scenario.py新增受限配置，dsh_entry_motif/dsh_online_motif在后端验收修复来源下禁用自动执行，run-scenario新增验收指标。普通Web共享preset并校验最终记录，失败不显示completed，统计修复数；允许工具/schema/原文件工具/预算价格/旧库保持。公开免费诊断、离线审计与新recovery_study保留原失败；源变化/前后patch在私有开发归档。

550Python/139Node通过，3Docker跳过；免费三类实际Harness/MCP及18烟测/13普通Web HTTP通过。真实8次6成功+2预期权限失败，108HTTP/USD0.098112864，15验收含9失败阶段全部保留；新L2首段5批后关闭自动调用，由普通模型补齐索引，审计证明修复后0自动工具。总体系列447运行/4080请求/USD3.497620224，实付未知；原22基准失败未追改。完整逐项证据与限制见../experiments/acceptance-repair-20261013.md，前端见../handoffs/frontend.md。
