# 论文校对当前交接

- 更新时间与交接人：2026-10-20，Codex。
- 目标与本次范围：把真实执行中的报告参数、失败字段与来源版本自动接到已有复用协议；不再由runner预置完整恢复scope。用户明确不重跑Baseline，少输出Token/少费用同样算收益。已完成局部真实恢复与一项原PDF/原提示词完整验证；未扩其他场景。
- 分支/提交：`codex/paper-live-recovery-state`，实现与实验记录本地提交`7d626d6`（基于`56beadd`）；本次未推送、未提交新PR、未合并或部署。旧[PR95](https://github.com/jingyio/GeneLoop/pull/95)仍是前轮恢复实现，未因本次改动更新；原脏检出与生产服务未动。
- 已完成：`reuse_mediation.ts`区分1MB JSON与20MiB已批准输入，修复约2MB PDF导致参数采集静默失败，并增加失败审计；正常实际报告调用启用受保护policy，`evidence_report.py`保存当前草稿与版本，先保留原文修复输入格式，再进入结构/叶子修订。显式sidecar `captureCurrentReport:true`默认关闭，无新增模型工具。
- 类型化执行：当前服务明确数组数量错误时，模型只选顺序完整分组或unknown；Runtime拼接原标题及全部段落，再经原工具重验。分组适配器是工程结构交接，不能冒充新挖Motif；原生传参契约从真实历史成功轨迹重编。新增引用concat有界且无代码求值。`initial_arguments`及摘要保留原始起点，恢复边界更新不再把结构修改记为0。
- 已验证：最终定向Node41/Python9通过；最终`npm test` Python1305通过/213跳过、Node1170通过/5跳过；无模型smoke（18题/83来源）和motif:check通过。环境为macOS、本轮实际私有字体及规范化TMPDIR；其他平台新路径未做真实模型验收。
- 实验结论：[自动状态接入、全部失败与费用](../experiments/paper-live-state-20261020-v1.md)。001/002普通patch为11/9请求，002删掉16条文献而判失败；003加内容保护后20请求、5034输出/$0.029079876。004/005/006类型化分组均4请求，输出1020/1098/971，估费$0.018611484/$0.017023560/$0.016981980，79/97/79段原文完整保留，成功后无工具调用。004/005有0变更总结错误；006修复基准后正确说明`/sections`结构变化。均为同论文历史失败局部恢复，原科研结论未重新核验，不当作独立论文/科研质量通过。
- 正常完整任务：run `6f852b3ec40248ce8f11fb12fa8d8ced`、task `6e9d860c7511413893f24b49ecca5774`，无checkpoint/scope/人工答案注入。18次当前值采集，step59明确返回段落数组输入错误，step64由Runtime执行一次字段补丁后成功导出6页；其他6节逐字段不变，所有非空正文保留，只去掉3空串，逐条表覆盖1–34。81真实请求、49,616输出/$0.231602928；成功后无工具调用，传统verified_skips仍0。报告仍有NeurIPS年份、DSPy/SARATHI误判，事实抽查未通过；不另行人工修稿冒充Agent成果。
- 成本归因：与前一次方法轨迹（非新Baseline）相比，未缓存输入196732→463668，其中检索110714→340102，解释增量85.93%。检索模型10→17请求、费用$0.04378017→$0.12142486；其余费用$0.160423062→$0.110178068。总费用上升主要来自不同搜索路径/内部上下文；不能据此否定局部机制，也不能把全部非检索下降归因Motif。首请求总输入仅+49Token；运行中通知仍非零成本，剩余37548未缓存增量未逐消息拆清。
- 配置与数据：私有根`.local/paper-live-state-20261020-v1/`含授权、真实失败参数、各版本配置/库、all-local-results/aggregate/full-breakdown/previous-method-comparison/full-quality/final-local-content-check及全部回归日志。最终`execute-native-v4.json`：native-v4摘要`57d7f8693f321a1cfabecad4448ab43a679f233f02bac3e97a04a27948053bd1`，captureCurrentReport/repairChoices均true，script库为空、无Frontier/embedding，Negative库未加载（实现锁变化须另行再认证，不能改旧hash）。全部run仍关联有效配置和逐文件source-snapshot；真实调用时为基于56beadd的未提交源码，当前实现见7d626d6。
- 最短复现：沿用`run-script-motif-experiment.py --real-model --mode execute --report-evidence --source <原PDF> --prompt <原题面或恢复题面> --script-config <当前重编配置> --budget-usd 0 --max-output-tokens 32768`。历史局部恢复另加`--reuse-checkpoint <真实旧调用>`，不加preserve/resume参数；普通完整任务完全不加checkpoint。通过Node `--env-file=.env`加载已有私有凭证，设置当前私有字体、SSS_LOCAL_SCRIPT_EXPERIMENT及隔离Python，不显示密钥。
- 权限与预算：本地DeepSeek Flash、reasoning off、输出32768，请求与费用不限、reset_history:false。本轮6项局部+1完整共133请求/$0.356092428，沿用原5301/$9.074760576后累计5434/$9.430853004保守代理估费；旧pending3、V100与服务商账单仍待核，无新增pending/unknown。开发/维护/人工时间未量化；所有付费任务已结束。
- 未完成与反例：完整科研事实质量和整任务净降本尚未证明；普通Bash未登记产物仍无法自动解释为完整草稿，捕获起点不保证原稿覆盖全部源文献。Negative自动捕获状态的兼容守卫有局部回归，新的端到端库再认证未完成。完整任务原生580.526秒与runner552.316秒不一致，保留原值，未定位时钟/口径问题，不混用为延迟因果结论。较早1页摘要与4页产物的先后判断已按原始事件纠正，见前轮记录附注。
- 接手下一步：1）按已取得一手证据审计17条检索词中的必要新增与重复，不凭总费用高就回调匹配阈值；把搜索内部输入及缓存成本单列。2）针对事实误报建立有来源的语义核验与交付检查，不能把结构成功当科学正确。3）再认证Negative当前状态接口并做真实局部留出，先保持当前基准/全文保护；暂不增加完整Baseline或扩场景。
- 回退与风险：关闭captureCurrentReport/repairChoices或移除实验sidecar回原生路径，移除--report-evidence回生产默认报告模块；本次无部署/原件/外部应用修改。完整原始日志、失败产物和旧库均保留；旧PR不应依据本轮局部结果自动合并。
