# 结果收据到结束的 Motif（实施前接口记录，2026-10-12）

用户授权继续上一轮下一步。当前只做文献论断复核的末尾前沿：原生成功submit_claim_repair收据→下一次模型请求只返回最终文字、结束。学习的是结束控制关系，状态JSON的字段复制程序由开发者限定；不声称自动学习任意总结、论文推理或优于手写停止规则。用户需要的笔记仍是工具产物，保留原collector逐引文重放，不以最后消息代替结果。

## 所需共享接口（先记录，再改）

1. 新Python离线terminal_compiler：配对真实模型原始提交/成功收据/紧随的一次真实最终模型消息和stop事件；拒绝Runtime、投影、混合提交批次、后续工具/用户输入。两个不同目标集合/工作量的原生任务训练，第三任务认证；Schema/只读非stable契约不变，源产物与原输入仍可逐项重放。原entry编译器/协议不改。
2. 新TypeScript terminal_receipt_policy：只解释receipt_then_finish/claim-repair-v1；现Session中实际工具回调发出、最后单一工具结果、对应模型原始提交、相同冻结任务/提示/Schema、私有产物/审计SHA、任务与修复范围、当前PDF/输入/执行文件摘要全部符合才产生有Runtime标记的状态JSON和stop。失败、pending、未学习status、混合批次、源变化、用户续问回到原模型；不生成科研事实，不申请新工具或写用户文件。
3. 复用固定dsh_entry_motif插件，在该插件加入独立terminal env/controller；保持旧entry行为。run-scenario新增配对--terminal-policy/--terminal-task，私有路径/场景白名单/本次Session与实际prompt绑定，当前与entry/旧manifest/PTC互斥；普通baseline清空新env。新增terminal_model_requests_bypassed_verified单独记账，实际预算与HTTP账本不变；不修改上游Harness/共享费用代理。

## 场景接口与实验边界

repair-pdf新增--terminal-policy，构建绑定当前输入、源PDF/代码与本次输出目录的task；原题面/工具/语义判断/collector和收据守卫不变。策略默认关闭，暂不改Web或将旧库组合使用。新增场景learner/helper，产物在.local不提交。改repair入口会使自动缓存workflow变化，旧缓存应正常失效，历史索引/实验不改写。

训练/认证与评测均用当前已知PDF的已有模型草稿及不同复核目标；正常语义过程仍实际由模型完成。至少三轮H/M串行交错同任务/Schema/提示/源/限制。比较每次收据后的请求与全任务费用，原失败/恢复/显式缺口都保留。结构末尾预计只能跳1请求，不预测全任务大幅提速。科学支持与泛化未认证；普通规则也可实现同一停机条件。

修改共享代码后npm test/相关实际SDK+MCP免费正负检查；真实API继续使用已授权Key与每任务USD1保护上限，无外部发送、用户PDF修改、提交或推送。

应用层补充（实施前）：agent.ts增加claim_terminal_policy/CLI --claim-terminal-policy，只用于第一轮claim_support_audit；缺口续修/综合仍原Harness，HTTP拒绝策略路径。当前拒绝与任何旧入口/manifest组合，新库默认关闭。任务记录新增terminal_verified_batches，实际model_requests仍取上游账本，不混入entry/旧skip。只影响场景协调和观测，不修改共享预算或核心LLM循环。

已实现：新SDK参数复用prepare_scenario的固定插件装载开关，不新增场景JSON字段；共享预算/上游不改。scripts/project.mjs把新增Node回归加入npm test。状态渲染器是手写有界字段复制，离线编译学习的只是收据后终止关系和已见status；不把格式化模板称作模型自动生成程序。本轮三个正常轨迹只见preview，因此策略不会自动结束needs_review，仍交原模型。

免费SDK检查曾对SDK错误结果返回方式做了错误假设（假设抛异常，实际返回finish_reason=error），断言失败0付费。审计已确认篡改产物被拒、0跳过、5模拟调用及错误结束；检查改为验证拒绝/不产生Runtime完成答复，失败目录与账本保留，没有改生产守卫。

## 已验证与GitHub提交正文

文献复核已由工具写出笔记后，原Harness仍调用模型生成结束文字。本次从两个不同复核目标集合与第三独立任务认证该末尾关系；实际收据/来源/范围/版本符合时，复用公开llm/stream与tools/result接口，输出有Runtime标记的状态JSON并结束。正文、科学判断、工具权限、收据守卫与实际预算保持原路径。

主要共享变动：新增src/motif_core/offline/terminal_compiler.py、src/motif_core/terminal_receipt_policy.ts；固定src/adapters/dsh_entry_motif.ts独立末尾控制器、scripts/run-scenario.py配对terminal参数/私有绑定/账本计数、scripts/project.mjs新增Node回归入口；PROVENANCE记录本项目扩展。无上游、费用代理、旧entry编译/协议变更。场景terminal_entry/learn-terminal/check-terminal、repair CLI及agent选项同步。

状态渲染是手写受限程序，学习的是收据后结束条件，不称自动发现任意流程或优于脚本。库仅preview；needs_review两次实测回退且缺口保留。12真实对照方法组估费−32.08%但评测设计组+0.56%且缺口更多，不能全面启用。4实际末尾跳过，最终发布物/未选字段/源重放一致；63HTTP/代理估费USD0.09794229含全部学习/重试，账单实付未知。

429 Python/98 Node+场景29通过（3可选Docker跳过），免费实际SDK/MCP正负和smoke通过。篡改产物0跳过，返回SDK error；免费检查一次错误异常假设已修，原记录保留。详见[实验结果与限制](../experiments/terminal-receipt-20261012-34cfce1d.md)。

默认关闭、HTTP不加载客户端策略，组合旧策略未认证直接拒绝。移除--terminal-policy/--claim-terminal-policy回退；旧自动缓存按新版workflow失效，私人原结果不删不改。当前本机macOS验收，未新增跨平台/思考模式/整体产品验收；未commit/push/PR。
