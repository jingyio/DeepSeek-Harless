# 论文校对当前交接

- 更新时间与交接人：2026-10-20，Codex。
- 目标与范围：沿用已有Baseline，先审计真实费用，再改善当前恢复接管；复杂恢复增益未稳定，不扩场景、不调Embedding、不更换挖掘算法。用户最新授权验证后提交并合并PR，覆盖此前只审阅不合并；不包含部署。
- 分支/提交：`codex/paper-recovery-evidence`，本轮实现`a0074e2`；基于aff4d86，已包含main5e545b4，原脏工作区未动。PR94已更新代码，最终CI/合并状态收尾记录。
- 已完成：`reuse_mediation.ts`根据受保护的显式当前执行义务，核验task/grant/来源/参数/Schema后，在首次模型请求前执行一次；失败交回语义修订，成功核验文件并交回总结。runner新增`--resume-current-operation`，非默认、非历史相似性授权。拒绝复合shell时给静态计划的精确修正建议，不执行原命令。成功通知说明Bash目录边界、附实际字段差异；不能保证模型因果解释正确。
- 跨平台修复：原PR94 Windows失败是测试LF/CRLF与边界路径问题；实际字节摘要不放宽，Python读UTF-8原字节并统一POSIX见证，LF/CRLF均测试。旧Linux证据不追改。
- 已验证：本轮正常恢复003/005均1个真实模型请求（仅总结），1次Runtime原生执行，完整参数逐字段未变，0工具错误/成功后额外工具。页数恢复004为18请求，37条详细记录及来源未变；最终修改说明仍有不准确处。006为43请求，7次导出、三次同字段长度失败，最终报告改写逐条表/来源且总结有错误，不能算无损成功。
- 测试：义务接管后的npm test Python1297/Node1149通过（213/5跳过）；增加差异交接后定向Node29通过；无模型smoke通过。最终GitHub Ubuntu/Windows结果收尾补录，未取得结果前不称跨平台通过。
- 实验结论：[本轮Breakdown与全部六次真实运行](../experiments/paper-recovery-control-20261020-v2.md)。只支持显式当前操作的窄接管机制；001/002没有该义务，9/67请求，后者脚本及搜索额外成本全部保留。短协议、实际差异提示均不足以保证复杂修订稳定降本或总结正确。
- 配置与数据：`.local/paper-recovery-control-20261020-v2/`含authorization、aggregate、逐运行quality/native/breakdown、全部测试日志；execute-final.json指向native-003。native-only的2原生契约/1诊断契约，无脚本库或embedding调用。完整代码和有效配置在各run快照，不改旧hash。
- 最短复现：本轮实验记录引用前轮统一runner命令，增加`--resume-current-operation`；需execute、reuse-checkpoint、preserve-recovery-structure、SSS_LOCAL_SCRIPT_EXPERIMENT=1及已核验HARLESS_REPORT_FONT。当前操作义务来自显式选择，不能仅由相似轨迹设置；代码锁变化需重编库。
- 权限与预算：本地DeepSeek Flash、reasoning off、输出32768、请求/费用不限，reset_history:false。本轮139请求/$0.200397576代理估费；本地累计4972/$8.312584668。无新pending；旧pending2、V100/账单待核保留，非账单实付。全部六项运行已结束，无生产修改。
- 未完成/下一步：1）对同一长度约束连续失败，研究从当前可信约束生成有类型的修订缺口，避免改无关字段；不能将相关性当根因。2）真实核验复杂修订是否保留科研信息、最终总结是否与证据相符。3）局部增益稳定后再考虑独立论文、其他场景和高效挖掘。通用自然语言到当前义务尚未自动化，持续RSI增长未证实。
- 回退：关闭实验sidecar、report-evidence及resume-current-operation回原路径；不碰生产/原件/公共认证库。代码合入与部署分开，不能直接重启正式服务。

前轮：[恢复与成功复用](../experiments/paper-recovery-evidence-20261020-v1.md)、[边界证据](../experiments/paper-evidence-slice-20261019-v1.md)、[统一复用](../experiments/paper-unified-reuse-20261019-v1.md)。
