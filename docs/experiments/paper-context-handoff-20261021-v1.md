# Script Motif 上下文与完成交接修复

## 问题与范围

既有五篇/20次真实评测中，Motif少30次请求、少17,907输出Token，但多72,213冷输入Token，估费仅降1.20%，QLoRA漏检。离线追查见[原评测](paper-multipaper-eval-20261021-v1.md)：启动协议、执行结果和接管后重新解析造成上下文增长，现有证据不支持整段前缀反复失效是主因。

本轮只修复可确定的控制信息冗余与完成交接，默认关闭，不改生产、模型/工具集合、匹配阈值或执行权限。没有实现完整字段覆盖证明，不能把程序执行成功说成任务检查完成。

## 实现

- `compactContext:true`在当前语义选择中使用短ID、合并相同输入绑定，保留全部描述；由当前模型选择最小足够集合，不按论文/关键词硬编码路线。
- 通用数据修订协议不提前占据system；实际出现可绑定参数或修复时，原通知给出完整操作命令。完成后提示按用户检查项消费已有结果，仅对缺项或冲突局部核验。
- 使用DSH公开`tools/post-execute`替换模型内容；保留全部stdout、来源程序与文件版本。原始回执先完整写入私有审计；不改canonical工具值。前后版本/nonce/摘要校验、其他策略拒绝或替换均继续生效。

## 配置与复现

独立分支`codex/paper-evidence-handoff-20261021`，基于`eafeca29`。真实运行的commit、未提交diff、源码与有效配置由原runner逐次记录。私有根`.local/paper-context-handoff-20261021-v1/`保存授权、协议、认证、运行和账本。旧20次评测、原始文件与冻结库不修改。

真实任务沿用原`run-script-motif-experiment.py`及`bibliography-integrity.prompt.md`，只运行Motif，对照沿用旧Baseline和旧Motif。首先复查QLoRA、DDPM原完整BibTeX文件，各两次；属于同输入的真实局部回归，不是新的独立泛化样本。模型仍为真实DeepSeek Flash/off、输出8192、300秒期限，cap/request limit为null，reset_history:false。所有失败/重试累计；没有普通脚本缓存组，也不新跑Baseline。

最短入口同原评测，`--mode execute --script-config "$COMPACT_CONFIG"`；配置保留原12程序/1复用契约/1提示型Negative及阈值，仅显式增加`compactContext:true`。各库均须按当前代码实际重新认证，不修改原库的锁。

## 已知失败与验证

- 第一版误尝试在provider middleware替换`request.messages`，新版DSH冻结请求，4次原生任务在模型调用前失败；真实API请求/费用均0。所有任务/日志保留，不能计作通过或省费。已改用公开工具post-execute接口，并补冻结对象和其他策略优先权回归。
- 初次直接运行Node沙箱测试误用系统Python而失败；指定项目隔离Python后通过，没有放宽沙箱。全量Node还暴露既有Artifact测试的macOS临时路径别名限制；改用canonical的`TMPDIR=/private/tmp`复核，相关文件通过，未改其守卫。
- 全量Python初次1515通过/235跳过/2失败；两项PDF交付失败定位为本地隔离环境缺少matplotlib，导出引擎在构建前失败。仅向本轮私有test-libs安装测试依赖，不改Agent环境；该文件随后16通过/1跳过。未把初次全量失败改写为通过。
- 当前定向Node98通过/3平台跳过，包含真实OS沙箱、nonce/版本/篡改、冻结结果、后续策略修改、短ID重复与延迟协议。它们是免费诊断，不代表模型效果。

## 真实结果与成本

待当前版本真实任务结束后记录。启动失败与正常任务分别列出，但失败费用均计入总账。暂不宣称减少冷输入、恢复成功、稳定净降本或五篇验收完成。

## 后续边界

优先观察最小候选选择是否发生、原始stdout是否完整、接管后重复解析与QLoRA冲突是否减少。若只是冷输入少而最终漏检仍在，继续保留负面结果；字段级范围/完成验收是尚未解决的问题，不用更强提示冒充机制实现。
