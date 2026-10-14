# Harness / Code Mode / 脚本 / Motif 真实对照（2026-10-12）

## 结论

四组同一批准计划的证据包逐字一致，强基线阶段每组4轮全部交付。当前这条固定机械链，普通脚本均值最便宜、最快；Motif相对普通Harness少两次请求，但对脚本没有增量费用优势，均值贵约6.02%。Code Mode强基线平均3.5请求，比脚本4次更少，但代码生成/执行/部署及模型差异的总体开销计入后仍更慢，不能以请求数代替效率。

这是普通PDF科研Agent的**证据准备组件**，不是完整15字段科研理解/知识管理任务的质量等价结论。三篇已知论文、一个固定阅读决定，不支持全Agent降本、跨语料泛化、科学正确或统计显著性。不能据此宣称RSI有效；默认保留普通脚本/核源缓存，当前Motif继续实验性。

## 任务、来源与划分

实验主ID`harness-strong-20261012-5da6ab9f`。源为既有/testpdf三篇论文，哈希和root/文件选择在私有protocol冻结，原PDF未改。2条不同问题正常native真实轨迹训练、1条不同问题独立认证，再收集未用于学习的默认问题阅读计划；不是独立消费者/留出新语料。

- 训练1：812eb0c5c53f423790895568dd561f34，12请求/USD0.019817580。
- 训练2：807daff1d75b4c4688140ae3458def0b，11请求/USD0.018335556。
- 认证：598994c0404c49399ec6899d6ea129c2，9请求/USD0.017129796。
- 评测决定/选页：9fa9fddeab9847f3b10a6d86c2a8aea3，8请求/USD0.012848964，三窗证据计划。

实际源重放后离线编译/认证1条既有三节点参数链extract→verify→build，manifest v2 `ac8d3f33152b603b026854674d203f5e6c19dcbd59557d109361905cc192cd89`。从真实正常轨迹学习，没有手写链直接伪装为学习；但窗口选择/遍历与验证操作已存在于工具，未学习科研相关性、判断支持或全局分支。旧库/失败记录未改。

四组复用同一Harness/DeepSeek Flash/off/无压缩、同一源/问题/批准计划/底层MCP/字符预算、相同用户prompt SHA、解析缓存reuse。native组不是禁用批量的弱工具模拟；PTC组使用实际run_code、上游生成SDK和子调度，wire schema天然不同，底层MCP权限相同。只关闭不相关shell/文件写/其他Agent能力。源、工具、字段与机械质量等价通过逐窗原文/整packet/原生成功收据验证。

四轮顺序轮换：H-C-S-M / C-S-M-H / S-M-H-C / M-H-C-S。每任务32模型请求/3500输出上限，整个开发预算保护上限USD5，不等于预期费用；每次给下一任务传剩余预算。正常失败/纠正费用均计入，未整任务自动重试。Key由原宿主加载及预算代理使用，不输出、不放进容器。A100未使用。

## 强 Code Mode 对照

强阶段私有对照`frozen-evidence-20261010-b8a2c8a9`，实际2026-10-12（CLI保留旧日期前缀）。四组均给相同效率要求：能够在局部解决依赖时减少模型往返；run_code可在同程序串联登记→提取→核验→组装，只返回最终收据；没有提供代码模板，程序由真实模型生成。

| 组别 | 平均请求 | 平均代理USD | Harness秒 | 含入口秒 | 每次验证skip |
| --- | ---: | ---: | ---: | ---: | ---: |
| 普通 Harness（native MCP） | 6.25 | 0.004437882 | 10.458 | 12.196 | 0 |
| Harness Code Mode（原生PTC） | 3.50 | 0.003663846 | 11.354 | 13.100 | 0 |
| Harness + 普通脚本 | 4.00 | 0.003463803 | 7.951 | 9.696 | 0 |
| Harness + learned Motif | 4.00 | 0.003672387 | 8.086 | 10.242 | 2 |

实际请求逐轮：Harness 6/6/7/6；Code Mode 3/5/3/3；脚本4/4/4/4；Motif4/4/4/4。Code Mode各轮实际子调用分布为[2,3]、[1,1,1,2]、[2,4]、[1,4]，出现局部批量，未硬写成理论最小2请求。程序中的静态工具引用计数与真正子调用数分开存。

Motif每轮实际核对2个成功native跳过事件/对应工具结果，embedding0；脚本/Code Mode不冒充learned skip。16次最终packet完全一致，再核源成功。强阶段16独立原生run/71上游HTTP200，共USD0.060951672。源码/镜像在付费前冻结并在结尾核对，无中途变化。没有原生工具失败/坏JSON或PTC失败子调用；其中一轮多一次Harness请求及冗余动作仍保留在费用与时延里。

在这组有限条件下，脚本代理均值比普通Harness低约21.95%；Motif比脚本高约6.02%，含入口时延也更高。输入缓存不可控制、n=4，不把费用差异或小于1秒的波动声称为稳定因果收益。相对于已经更便宜的脚本，没有观察到可摊平的增量节省，因此不估算对脚本的学习回本次数。

## 保留的第一轮与反例

首阶段`frozen-evidence-20261010-d94d87e3`，16次/84请求/USD0.060794004，全部相同packet交付。虽然真实PTC启用，模型主要每段程序只执行一个工具，未充分使用批量。观察后保存amendment，修改所有组相同的用户效率说明，再新建强阶段；不是重试一个不变失败任务，也没有覆盖首阶段。

| 组别 | 平均请求 | 平均代理USD | Harness秒 | 含入口秒 | 每次验证skip |
| --- | ---: | ---: | ---: | ---: | ---: |
| 普通 Harness（native MCP） | 6.00 | 0.003937839 | 10.933 | 12.727 | 0 |
| Harness Code Mode（原生PTC） | 6.50 | 0.003474291 | 13.594 | 15.399 | 0 |
| Harness + 普通脚本 | 4.50 | 0.004144965 | 9.411 | 11.211 | 0 |
| Harness + learned Motif | 4.00 | 0.003641406 | 8.150 | 10.379 | 2 |

首阶段2个失败外层工具结果后模型恢复，坏JSON0/PTC失败子调用0，均计费。Code Mode均值6.5请求，强阶段3.5；两阶段prompt不同，不把跨阶段差异当随机对照或固定因果。首阶段额外共享Runtime源码快照在前三组结束后补录，明确记录其时间，不伪称预注册；强阶段另在付费前完整冻结。

## 普通缓存与完整费用

相同问题/批准计划/来源的显式结果缓存另跑4次。逐窗重放后同packet，新增模型/embedding/费用0；重放均值0.185秒、含入口0.456秒。这是明确同任务的普通缓存上界，不给新问题选页，不是learned RSI。不能把它并入fresh执行组来虚报Motif收益。

本轮36唯一真实run/195上游HTTP200/无429，代理总费USD0.189877572：学习认证0.055282932、独立决定选择0.012848964、首阶段0.060794004、强阶段0.060951672。包含失败与纠正；学习费单列，不抹去。累计PDF代理USD2.962426888→USD3.152304460。usage共输入1,857,487（命中1,462,912、未命中394,575）、输出52,273、总1,909,760。供应商实付未核，开发/Codex/维护/专家评估/部署时间成本未完整量化；不能宣称总成本已下降。

## 执行器、回归与复现

原有文献profile没有启用真正Code Mode，新增SDK可选--tool-presentation ptc，默认native保留。对照使用上游0.1.5-rc.3 WorkerThreadCodeRuntime，镜像Node22.22.2 `node@sha256:9f6d5975c7dca860947d3915877f85607946403fc55349f39b4bc3688448bb6e`。macOS宿主Docker28.5.2/arm64，Python3.12.13；容器内Linux不代表Linux服务器/Windows产品验收。

容器只读、无网络、非root、capabilities全去除、无新权限、256MiB/64PID/时间上限；只挂公共node_modules和执行适配脚本，挂载无论文/用户目录/Key/host Docker socket。宿主桥接当前允许的MCP。没有自制解释器，也没有以Node Permission Model冒充恶意代码隔离。实际3项Docker测试验证并行绑定、宿主假私密文件/环境不可读、挂载不可写/网络拒绝、取消与镜像拒绝；测试只用假Key。无未清理的sss-ptc容器，Desktop启动/镜像下载属于开发设置，未测部署总耗时。

PTC原生start/settled日志成对回收，分析投影附source seq/sha/type，原日志不改；投影不冒充模型决定/训练数据/成功skip，学习入口拒绝ptc轨迹。免费真实Harness原生Code Mode一次程序5个子调用/2模拟请求，同源packet完全一致，API0；不能冒充真实模型最优行为。

回归：386 Python、67共享Node通过，额外3实际Docker测试通过；Docker测试为显式可选，普通npm test默认跳过，不要求其他平台装Docker。统一效率prompt修改后46场景回归通过，并再次执行全仓测试与smoke；最终状态见交接。相关共享变化/平台边界/GitHub提交正文见[变更说明](../changes/literature-harness-comparison.md)。

```sh
npm test
npm run smoke
# 可选Code Mode需Docker Desktop运行和固定镜像；下列检查免费
# 普通native SDK/Web无需Docker
# 先 docker pull node:22.22.2-bookworm-slim
npm run code:check
node scripts/project.mjs python scripts/check-code-mode.py --evidence-run <真实批准计划run>
# 比较预览不调用模型；加--call-model才付费
node scripts/project.mjs python scenarios/literature-notes/compare-evidence.py \
  --plan-run <独立真实计划run> --manifest <当前认证manifest> \
  --include-code-mode --repeats 4 --budget-usd <剩余总预算>
```

私有protocol/amendment/split/learning/final-audit/cache与原始events/ledger保留在.local，不提交Key/论文/原始轨迹。feature/rsi-research-agent未commit/push/PR，main仍bc1ecd5。生产文献Web仍native/off/默认Motif关闭；Code Mode实验入口未自动扩大其权限，未加思考模式对照。

下一步针对资料更新/证据缺口中的可验证重复分支选候选，与已有强脚本/真正Code Mode继续同质量比较。不要将固定verify/build链搬到生产来增加开销；完整科研结论质量/动态任务泛化另验收。
