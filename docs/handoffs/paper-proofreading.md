# 论文校对当前交接

- 更新时间与交接人：2026-10-20，Codex。
- 目标与范围：自动接入真实报告状态、复用局部参数与成功产物，补回Negative Motif认证和库接入；仅实验侧启用，不扩检索、不重跑Baseline。
- 分支与同步：`codex/paper-live-recovery-state`；前轮实现`7d626d6`，本轮实现及验收`93205b4`，本地无冲突对齐main提交`22fa910`（代码树与测试版本一致）。已推送并创建[PR97](https://github.com/jingyio/GeneLoop/pull/97)供审阅；最新main=`abb9cf7`（PR96），分支已无冲突同步，保留其Web并发、额度及输出容量更新；此前PR95已合并。本次PR未合并、未部署，原脏工作区未动。
- 已完成：`reuse_mediation.ts`修复2MB来源被1MB JSON上限误拒，默认关闭的`captureCurrentReport`将实际选择的原生报告调用绑定当前任务、来源、grant、Schema和用户意图。`evidence_report.py`捕获受保护草稿，输入修复保留全部原文，再允许必要叶子修订；有界concat和语义分组选择由Runtime执行，不增加模型工具，不冒充新挖Motif。
- PR97跨平台修复：原WindowsCI因只读目标的原子替换及只读临时文件清理失败（WinError5）。现仅在Windows发布已验证当前scope时临时清除只读属性，替换前再次校验SHA，成功/失败均恢复保护并清理；不先删除旧文件。新增成功、失败回滚与过时版本拒绝检查；原失败集成用例保留。合入PR96后本地Python1319通过/213跳过、Node1181通过/5跳过，smoke和motif:check通过。当前修复提交的两平台实际结果以[PR97检查](https://github.com/jingyio/GeneLoop/pull/97/checks)为准；不等于Windows真实模型验收。日志在`.local/pr97-windows-fix-20261020/`。本轮新增付费0，旧账本不变；工具字节已变，后续真实实验须重新认证私有库，不改旧锁。
- Negative接入：显式`learn-negative-motifs.py --recertify-current-constraints --constraint-validator <受信当前文件:函数>`只迁移当前纯校验器重新双向认证通过的条件；默认旧实现拒绝仍有效，不迁移旧执行认证和prompt-only规则。新库保留旧事件及实现摘要，当前运行仍需真实失败、实际提示及当前证据。自动scope额外核对当前用户消息、工具与Schema，变化后不能重激活旧目标。
- 成功交接：实际文件、回执、配置、来源和本轮差异均核验；`initial_arguments`保留原始修复起点，成功后不重复导出。收紧总结提示只聚焦链接、变化和限制，仍不是自由文本事实校验器。
- 上一阶段已验证：定向Python13、Negative Node27、复用Node41通过；完整Python1312通过/213跳过，完整Node1171通过/5跳过；smoke18题/83来源、motif:check通过，均为免费诊断。初轮字体/Poppler环境3项失败、旧文案断言1项失败、手动Node调用系统Python导致2项失败全部留日志；使用项目Python、前轮字体、规范化TMPDIR及可用PDF后端复核，没有放宽测试。
- 真实实验：[前轮自动状态接入](../experiments/paper-live-state-20261020-v1.md)和[本轮Negative集成](../experiments/paper-negative-live-integration-20261020-v1.md)。本轮001/003/004结构恢复均2请求，输出641/715/483，估费$0.011086656/$0.011042388/$0.010934088；原参数+所选完整字段逐字一致。002/005无预置scope的自动采集恢复6/5请求、输出1300/1038，79段原文保留，估费$0.019789092/$0.017404356。五项文件字节/摘要/来源均通过，成功后无工具调用，004/005共7/5页已逐页渲染查看，无明显重叠或裁切。均为历史失败局部恢复，科学事实未重新核验。
- 真实覆盖限制：负面提示和类型化恢复在三次明确完整目标的任务中实际发生；两次自动捕获任务加载负面库，但未出现该库认证的结构错误，自动origin激活仍仅由定向回归覆盖。无不合格重试，所以本轮早停0，传统verified_skips0；不能把原生合成步骤当整请求节省，不宣称比PR95的2请求又有新降幅。
- 质量反例：001/003总结混入历史动作和不准的来源数量。收紧提示后004的范围和链接正确；005仍把合计9段说成“各9段”（实际4+5）。参数与文件正确不代表任意自由总结正确，未人工改稿遮盖。前轮完整任务报告仍有科研误判；本轮只读证实其所有非空正文在局部修复前后逐字同序，原有误判未由该补丁引入，但静态提示对更早语义路径的影响未隔离。
- 前轮完整任务：原PDF与完整原提示，无恢复scope注入；run `6f852b3ec40248ce8f11fb12fa8d8ced` / task `6e9d860c7511413893f24b49ecca5774`，81真实请求、49616输出/$0.231602928，导出6页，质量抽查未通过。比更早方法轨迹贵主要在检索10→17请求、$0.04378017→$0.12142486；其余费用$0.160423062→$0.110178068，不能作受控因果收益。全部17次检索在动态报告接管前完成，不支持认定局部恢复直接增加了检索，仍未排除静态提示影响。
- 配置与数据：本轮私有根`.local/paper-negative-live-integration-20261020-v1/`含授权、真实失败/完整目标、源码快照关联、逐项质量/breakdown、aggregate、semantic-error-origin及所有失败日志。负面库`e6c9c34642c596f84fd6d91d7052eb2b23e14c4f236eb361302ea8a6c709f66c`；最终原生库`4a54a156ffabd8c14be1785f13ea6b0635a26beb655f3c647eabc0819eeb3232`。两库均实际加载；Script库为空、无embedding/Frontier。001–003与004/005配置分别保存，没有改旧hash。
- 最短复现：沿用`run-script-motif-experiment.py --real-model --mode execute --report-evidence --source <原输入> --prompt <原恢复题面> --reuse-checkpoint <实际旧调用> --script-config <冻结配置> --budget-usd 0 --max-output-tokens 32768`；明确完整目标的结构恢复另加`--preserve-recovery-structure --resume-current-operation --recovery-goal-scope <绑定原失败的scope>`，自动采集恢复不加。凭证通过现有私有.env加载，不展示密钥；保留本地沙箱、项目Python与已验证私有字体。
- 权限与账本：本地DeepSeek Flash、reasoning off、输出32768，请求/费用不限、reset_history:false。本轮全部五项17请求/$0.070256580，累计5451请求/$9.501109584保守代理估费。无新增pending/unknown；旧pending3、V100及服务商账单仍待核，开发和人工时间未量化。全部付费任务已结束，无新Baseline。
- 接手下一步：1）审阅PR97的自动状态/局部修订边界及已保留反例，不自动合并或部署。2）审计已有17次检索的证据覆盖与重复，不凭总费用加匹配规则或降阈值。3）科研事实核验和自由总结错误另行处理，保持结构交付与科学质量分离，暂不扩场景。
- 回退与风险：关闭captureCurrentReport/repairChoices或移除实验sidecar回原生路径，移除--report-evidence回生产默认报告模块；本轮没有生产配置、私人原件或外部应用修改，所有失败和旧库保留。真实新路径仅在macOS验证，其他平台不作新验收声明。
