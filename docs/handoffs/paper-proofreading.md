# 论文校对当前交接

- 更新时间与交接人：2026-10-19，Codex。
- 目标与本次范围：用户要求继续 Breakdown，先查费用瓶颈与 Runtime 未接管原因，不先大改报告接口。重分析前轮 448 次真实请求，并重放受信工具与冻结 Runtime；本轮未新增付费模型任务。
- 分支 / commit / 工作区：`codex/paper-takeover-breakdown` 基于 `d71c603`；在线仍冻结 `8fa7f23`，本次分析提交见 git log。原脏工作区、生产、旧库、原件和历史运行目录未写入；未推送、PR 或部署。
- 已完成：新增 `scripts/analyze-script-takeover.py`，复用已有费用/脚本/负面采集入口，分开 KV 命中、未命中、输出费用、辅助模型、脚本静态准入、完整请求障碍、shell 非零标记及后续请求。多个工具不重复计费，非法 JSON、未知 usage 和金额舍入保留，不推断反事实节省。
- 已验证：针对性 15 项测试通过；448/448 请求按原价格重建，与账本仅有八位小数舍入差。新副本重放 PaperOutput 暂存/定稿共 61 次，回执/SHA 一致；原 TS 库加载和 schema 摘要一致。未执行历史模型脚本，未重复全部回归或付费完整任务。
- 实验结论：[paper-takeover-breakdown-20261019-v1](../experiments/paper-takeover-breakdown-20261019-v1.md)。Baseline 脚本生成类 71.4% 费用；Positive 报告协议 40.7%+脚本类 32.6%；正负面搜索内部模型 30.2%。脚本字符串含大量当次数据/解释，类别费用不是纯代码或全可缓存费用。
- 实验结论：7 认证算子只组成一个 2 节点片段；4 个单节点不被提议，1 个网络/argv 算子只支持模型显式选择。两历史前驱被认证拒绝，且 frontier 要求相同输入契约。frontier 无 ready 就返回模型，不进入普通/embedding 匹配；两次接管后 Positive/正负面仍花约 98.8%/97.7% 费用。不是两次跳过上限导致。
- 实验结论：Positive 的 17 个结构错误都兼容冻结负面规则，但该臂未启用负面；启用臂没有这些失败。精确状态重放在“假设提示送达”下有 10 个工具拦截机会，未送达为 0，均不是实际模型跳过。工具守卫在模型生成参数之后，相关 10 请求约 $0.009301 已付；另确认单 active failure 会被其他错误替换/成功清除，旧失败条件仍成立。
- 实验结论：Bash 文本非零退出标记 11/7/5 个，均不算原生 isError；负面采集/observe 目前排除 Bash。这些是恢复诊断，文本标记不作原因认证。原三份报告仍不合格，不重评或修改成品。
- 配置与数据：`.local/paper-takeover-breakdown-20261019-v1/` 的 manifest 保存输入/代码/私有重放脚本 SHA，`*-v3.json`、summary、runtime-replay-v2、negative-state-eviction 为最终依据；初始金额容差、恢复序列化与 Node 路径诊断失败保留。原任务/题面/模型/库见 `.local/paper-negative-real-20261019-v1/`，正负库仍为 `.local/negative-causes-20261019-v1/positive-library-002` 和 `library-004`，不在线学习或改锁。
- 未完成与限制：没有新增合格净降本、成功自动恢复、真实硬早停或跨论文泛化。静态候选分析读取最终工作区，不冒充历史边界认证；重放 notice 是假设送达，不推断模型后续改变。搜索语义/科研解释、异构输入参数流、复杂 shell、写入算子均不能直接放宽守卫。
- 接手下一步：1）针对真实重复读取/取证，补当前 Evidence 参数流与跨输入的已认证关系，使模型请求前能连续接管；语义缺口批量填写，先检验一段完整循环。2）局部修复 Negative 多个并存条件的记忆，保留逐项失效和提示送达守卫；不以工具拦截数代替省请求。3）只在具体片段阻塞时修草稿/报告接口，之后真实配对检验质量、净费用及学习成本，不先扩其他场景或调 embedding。
- 最短复现：`node scripts/project.mjs python scripts/analyze-script-takeover.py --task <私有原任务> --library <冻结正面库> --negative-library <冻结负面库> --output <新私有文件>`；测试 `.venv-sss/bin/python -m pytest -q tests/test_script_takeover_breakdown.py tests/test_script_cost_breakdown.py`。重放入口与隔离副本说明见实验记录；不是生产/Windows 验收。
- 权限与预算：本地真实 API 无限额授权保留，reset_history:false。本轮新增 0 请求/$0，本地累计仍 3283/$5.307766608 保守估费，旧 pending 1、V100 未核清费用和未核账单保留；无后台付费任务。开发/审阅时间未完整计量。
- 回退与风险：本轮仅离线分析器、测试与文档，可按提交回退，不影响已认证 Runtime。后续运行时修复须重编/认证和真实效果验证，不能手改旧锁，不扩大私人原件/外部写入/投稿授权。稳定前不 PR。

前轮：[完整真实重测](../experiments/paper-negative-real-20261019-v1.md)、[原因学习](../experiments/paper-negative-causes-20261019-v1.md)、[字段依赖](../experiments/paper-negative-fields-20261019-v1.md)、[连续执行](../experiments/paper-script-frontier-20261019-v1.md)。
