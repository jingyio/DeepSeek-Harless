# 清单准备 Motif 与完整任务三组对照：inventory-motif-20261012-9af4e5f0

2026-10-12。已完成，全部原始日志/协议/策略/账本在忽略的 `.local/literature-notes/inventory-motif-20261012-9af4e5f0/`；原三篇 PDF 未改，运行期间代码未改，未提交或推送。本轮目标是学习不同工作流的重复结构，相对普通原生 MCP Harness 减少实际请求与输出；应用闭环、专家审阅、脚本与 Code Mode 优势不是启动门槛。

## 结论

**结构替代成立，完整任务收益依赖任务，组合尚不适合默认启用。** 新清单准备前沿的真实清单/导航结果与当前工具重放一致。两篇任务中双 Motif 组3/3自动门槛合格，相对 Harness 请求均值减少15.56%、输出减少9.73%，费用反而高0.52%、时间减少1.39%；样本小，不能证明稳定提速或降费。三篇任务中双 Motif 组0/3合格，输出增加18.33%；较少请求不能作为同质量收益。普通组自身也有失败。

没有将不合格样本筛掉计算漂亮均值，也没有因失败补跑替换。科学理解、引文蕴含和研究建议没有专家独立认证；“自动合格”只指本轮冻结的机械/完成门槛。已学结构不等于通用递归自改进 Agent，两个受限解释器本身是工程代码，学习的是原始轨迹所支持的参数绑定及完整覆盖前沿。

## 学习与认证

新 Motif：`list_pdfs({}) → papers[].paper_id → foreach prepare_pdf({paper_id}) → semantic handoff`。首次普通阅读、用户明确处理全部所选 PDF；不选择相关论文或阅读窗口，不做 OCR 或科研支持判断。清单来自实际工具返回对象；宿主冻结清单只用于核验。全选/绑定证据来自两个正常原生任务，实际执行顺序可有不同，在线使用清单顺序。

- 训练：`f780c803077e4bbfaeeb29d417ec945a`（三篇）、`11c8a8e02b7a4e278f0fb61866cca9f5`（两篇）。
- 认证：新普通 Harness run `2e41d77733184d0b9580ff92554115fe`，单篇 Paper2Agent /不同研究问题；12请求、输出3236、估费USD0.015132576。阅读草稿来源门槛通过，不称整任务专家验收。
- 原单篇 `c7bfc166e27f45c2959ea0a250ddbf44` 的解析器/导航/文档版本不同，拒绝复用为认证；不覆盖旧事件。首次离线编译使用旧 contract_signature，被非 replay-stable 契约正确拒绝，失败目录保留；新增独立 guarded 签名，没有放松原规则。
- 所有原模型调用/参数/成功输出逐项配对，并由当前 PDF 工具重放。仅 `cache_stats` 不参与导航一致摘要，原输出完整保留；PDF/解析器/页文本/导航/诊断全部参与。原 `replay_stable=false` 不改。
- 策略摘要 `2b9243713dcc60702c8e2486b217620de24f6ff34470c5ee5b46c89be67aa927`；旧复核入口摘要 `fa30241cbb699d1b45df22ccc47fd25f76b2218ee218e9d06dbee6dd851fb6be`。

这是三篇已知语料的开发认证与新问题评测。不同选择/问题不是新材料泛化；没有学习任意科学计划、任意代码或自动候选选择器。

## 完整任务与冻结配置

两个任务都从 PDF 开始，完整执行阅读→第一轮支持复核→必要时第二轮缺口处理→必要时综合→当前来源重放→自动交付。两篇任务的题目询问增量更新策略，本轮没有实际新增/修改 PDF 的增量操作。

- validation-boundaries：对科研 PDF Agent，这三篇论文怎样验证工具执行或研究结论？请区分作者实测、适用边界和本项目可测试的复用假设。
- reuse-and-update：这两篇论文的成本收益来自哪些复用单位，需要哪些验证条件？对科研 PDF 与笔记的增量更新提出有证据边界的方案。

每题每组三轮，共18个任务/65个原生 Harness 子运行；按轮次旋转组别顺序。三组分别是普通 Harness、仅复核入口、阅读入口加复核入口。两个 Motif 用于各自阶段的独立 Session；整体阶段协调仍为现有手写场景，不称全局控制图已自动学成。后续缺口与综合不用入口 Motif，保留旧单缺口反例。

相同模型 deepseek-flash/off、无压缩、native MCP工具/schema/顺序/提示模板/完整问题/输入/允许引用/读与提交额度。相同 warm/revalidated 解析缓存、force_refresh=true防止整任务缓存代替模型。每任务预算USD1、系列USD10；阅读max steps32/output8000，复核max steps48/output6500，completion continuation≤2；全部失败/续接费用计入。三组的模型生成草稿自然不同，不能声称逐字等价的科学质量或语义路径相同。

实验代码摘要 `1ae0523b69d75631b4a7f15381ea4b36973e382e022e2a00408a32607993afb5`，协议内容摘要 `d94b4ab9b7135b43e42ffad9477618d46cf49ef4326d4c83b53499897ae73435`。`comparison-protocol.json`、`comparison-progress.json`、`final-audit.json`、`statistics.json`保存完整配置/逐轮结果/65个run ID/真实usage和质量门槛。HEAD2368235，带本分支未提交改动；macOS arm64 /Node22.22.2 /Python3.12.13 /DSH与SDK0.1.5-rc.3，其他平台未验证。

## 全样本结果（包含不合格与失败费用）

|任务|组别|自动门槛合格|请求均值|输出 token 均值|估费均值 USD|端到端秒均值|
|---|---|---:|---:|---:|---:|---:|
|验证边界（三篇）|普通 Harness|2/3|25.33|17438.33|0.083906|110.78|
|验证边界（三篇）|复核入口 Motif|1/3|20.00|19395.33|0.083493|121.25|
|验证边界（三篇）|两个 Motif|0/3|21.67|20635.00|0.083919|125.61|
|复用与更新策略（两篇）|普通 Harness|2/3|30.00|13686.67|0.061149|99.85|
|复用与更新策略（两篇）|复核入口 Motif|1/3|26.33|12724.67|0.063791|94.44|
|复用与更新策略（两篇）|两个 Motif|3/3|25.33|12354.33|0.061468|98.46|

自动合格要求：字段/语料完整，真实提交/阶段完成，回源一致，字段缺口与数值缺口均0，没有失败复核回退。最终状态 delivered_with_gaps 不是完整合格，即使字段表暂为0缺口，也不能忽略数值问题或未完成审阅。所有组均输出可追溯交付；其中9/18满足上述完整门槛。

|任务|组别/轮次|字段缺口|数值缺口|语义复核阶段未完成|
|---|---|---:|---:|---|
|验证边界（三篇）|两个 Motif/1|0|4|是|
|验证边界（三篇）|复核入口 Motif/2|1|0|否|
|验证边界（三篇）|两个 Motif/2|1|0|否|
|验证边界（三篇）|两个 Motif/3|1|0|否|
|验证边界（三篇）|普通 Harness/3|1|0|否|
|验证边界（三篇）|复核入口 Motif/3|0|1|是|
|复用与更新策略（两篇）|复核入口 Motif/1|1|0|否|
|复用与更新策略（两篇）|普通 Harness/1|1|0|否|
|复用与更新策略（两篇）|复核入口 Motif/2|1|0|否|

两个明确阶段失败是三篇任务双 Motif第1轮、单 Motif第3轮：模型生成长文本或未完成所有pending决定，2次有界续接用尽，原始 Harness发出 `TASK_MISSING_DELIVERY_RECEIPT`。旧稿回退展示缺口且失败费用保留，没有冒充成功。其他不合格是明确撤回/未提取字段。精确行为原因尚不能归因于某一个 Motif或批次大小；两篇/三篇题目与草稿质量也不同，需要消融。

## 能直接审计的替代与不能推定的收益

普通阅读三轮/两题均有2个纯清单/准备provider请求；双 Motif均为0，实际清单和逐篇导航核源一致。普通第一轮复核三篇均3个、两篇均2个入口packet provider请求；单/双Motif均为0，实际冻结packet逐项重放一致。

所有12个复核 Motif run各2核验批次，6个阅读 Motif run各2核验批次，总36；无新入口deferred。Runtime source1+prepareN /claim15或10是真实MCP执行，不是provider付费请求。旧skip指标保持0；新entry指标与真实HTTP分别记录。训练见证拒绝 `sss-entry-*`及无真实usage的生成前沿，不能将Runtime轨迹伪装成新的模型学习成功。

可确定的是这些导航参数请求已被结构替代。全任务净差还含语义补读、提交、撤回、早停、输出截断、续接以及上下文变化；不能把所有净差都归因于减少导航请求，也不能忽略原模型消息对后续生成上下文的作用。第一轮两 Motif仅13请求却没完成复核，是最明显反例。

## 费用、错误与开销

18任务共446 HTTP200、估费USD1.313175240；25个外层工具错误、385条pending提交验证问题、9次completion续接，费用全保留。没有429。385是返回的验证问题条数，可能重复同一论断，不是385个独立科学错误。输入19,596,122 token（缓存命中16,707,840 /未命中2,888,282），输出288,703。

两篇任务双 Motif每轮均值比普通组多8,090.33未命中输入 token：按仓库固定峰值表增加USD0.002427100，缓存命中输入减少节省USD0.000509440、输出减少节省USD0.001598800，净增加USD0.000318860（0.52%）。减少请求/输出不保证费用降低；缓存/上下文路径与失败同时影响费用。这是账本分解，不能证明某插件单独导致缓存未命中增加。

本轮新增认证12请求/USD0.015132576，加完整对照合计458请求/USD1.328307816。阅读库所依赖三阶段30请求/约USD0.078250040已包含本轮认证；旧复核库依赖21请求/USD0.077256972。两个库学习/认证依赖阶段51请求/约USD0.155507012，与对照合计497请求/约USD1.468682252，不能把新增认证再次重复加入。当前代理估费未核对供应商账单；Codex/开发维护成本未计量。学习费用不能隐去，也不能用此失败混合批次估算可靠盈亏平衡点。

## 实现、检查和下一步

共享变更与 GitHub提交依据见 [inventory-prepare-motif.md](../changes/inventory-prepare-motif.md)，接口见 [interfaces.md](../interfaces.md)。保持上游Harness/旧manifest/预算/原ToolContract不变；新增受来源守卫的inventory协议/离线见证、固定插件分派、SDK全工具允许集校验。场景实验入口默认关闭，Web没有启用。

npm test：413 Python与79 Node通过，3可选Docker跳过；场景单独27 Node通过。免费真实Harness/MCP新入口4个实际调用与重放一致（mock1/API0），旧入口5个读取也一致；smoke API0、git diff --check、全部18次代码/原PDF摘要检查通过。测试不是科研质量/效率证明。

最短实验复现（需要自己的原生训练/认证轨迹和私有策略；不会随仓库分发私人PDF或原事件）：

```sh
node scripts/project.mjs python scenarios/literature-notes/learn-inventory.py --split .local/<split>.json --output .local/<library>
node scripts/project.mjs python scenarios/literature-notes/check-inventory.py --task .local/<task>.json --policy .local/<library>/entry-policy.json
mkdir -p .local/<new-experiment>
node scenarios/literature-notes/compare-frontiers.ts --experiment .local/<new-experiment> --prepare --claim-policy .local/<claim-library>/entry-policy.json --reading-policy .local/<library>/entry-policy.json
node scenarios/literature-notes/compare-frontiers.ts --experiment .local/<new-experiment> --call-model
```

split格式为 `{"training_runs":["原生三篇runID","原生两篇runID"],"certification_run":"另一任务runID"}`；数据必须当前源重放一致。场景单独开启使用 `agent.ts run --reading-entry-policy ... --claim-entry-policy ... --refresh --call-model`。

下一步优先独立的阅读-only消融与语义交接/分批提交结构诊断，保持相同质量门槛并冻结新实验，验证失败来源以及是否能减少反复序列化/无效最终报告。不能事后从两个问题拟合“≤10目标必成功”阈值，也不能继续把所有步骤都塞进入口前沿。暂不自动启用完整组合，不扩大UI或要求用户马上扩充论文；新材料和更多问题是后续泛化验收。


## 后续只读诊断：提交协议与失败层次（2026-10-12）

本次没有新增真实provider请求或改运行代码，原18轮数据不变。诊断明细`followup-diagnosis.json`。

确认一个局部接口问题：`pdf-repair-task.md`前面要求支持复核的supported/revised都带support_anchor，后面又称supported只需claim_id/verdict/reason；最终通用示例没有support_anchor且展示1–120字，支持复核实际上限80。MCP实际schema将decisions元素暴露为additionalProperties=true的通用对象，未呈现条件必填项。100/385验证问题是缺support_anchor，50为句长/理由长/引用数量限制，23为决定字段结构不合约；同一论断可多次记错，不能将这些数直接当科学错误率，也不能证明100次全部由提示矛盾引发。

当前每项_validate_decision前先增加当轮validation_attempts，格式问题也消耗3次有界次数。具体单Motif第二轮任务的UnifiedPlayers evaluation：第一轮三次分别缺anchor、anchor断在句中、字段结构不合约；后续第二轮三次则是所选引文缺数字，最终撤回。因此既有可局部修正的协议/序列化问题，也有仍需模型选择完整证据的问题，不能用“修好模板就全部成功”概括。

9个不合格任务中2个复核阶段未完成而回退旧稿，另外7个正常完成但各留1个明确字段缺口；不是9次全部文献处理失效。36个入口核验批次全成功、源重放一致，无新入口deferred；这些事实支持继续探索其他独立机械前沿。保留现有科研检查，不把缺口降格为完整合格。

原始质量差异仍需消融：三组初稿各自生成，两个题目和材料数共同变化，不能确定失败由哪个Motif、8条批次、上下文长度或材料数独立造成。支持原句/缺口的Runtime自动复制已实现，不能把再包装这一步当新Motif收益。建议优先统一提交契约，再探索增量影响清单→只准备受影响PDF、实际完整收据→结束阶段/生成状态；目录diff、既有缓存和BibTeX脚本如果已经0调用，不应虚构可省的模型请求。
