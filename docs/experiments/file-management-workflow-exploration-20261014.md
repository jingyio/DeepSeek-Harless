# 首批六流程的普通 Harness 真实探索

G3普通探索和轨迹汇集已完成。六流程各两个条件均已有机器验收合格轨迹；共14次真实尝试，12通过、2失败。两次失败来自第一版恢复服务的读取权限缺口，修复后使用两份新文本材料通过，原失败不追改。两版本共206次真实HTTP请求，代理峰值估费USD0.123931013；当前没有新Motif库、认证或留出对照，业务质量尚未人工盲评。

## 任务和版本

本轮验证普通DeepSeek能否在相同文件权限和固定验收门槛内完成下载整理、目录合并、版本比较、字节备份与恢复演练、ZIP交付、重命名中断恢复。材料为生成文本、路径和规则，复用已知Office/图片模板及三篇PDF副本；这种探索不能代表真实办公材料泛化。所有操作仅在有标记的testpdf实验副本内，私人oracle不交给模型。

| 实验 | 范围 | 通过 / 尝试 | HTTP | 代理估费 USD | CLI累计执行秒数 |
| --- | --- | ---: | ---: | ---: | ---: |
| fm-workflow-explore-20261014-03260edc | 六流程×正常/边界条件 | 10 / 12 | 177 | 0.104709232 | 357.546 |
| fm-workflow-explore-20261014-bbefcf67 | 新版本FM38两条件、新文本字节 | 2 / 2 | 29 | 0.019221781 | 70.690 |
| 合计 | 包含失败及工具纠正 | 12 / 14 | 206 | 0.123931013 | 428.236 |

最终12个条件的合格轨迹分属两版本，不能称同一冻结版本下的完整基准12/12。原免费协议fm-workflow-free-20261013-de2f6604的54份pristine、题面和oracle保持不变，包括6份独立认证与18份留出；本轮只使用explore副本，修复版另生成三文件的两套文本字节。原三PDF及旧七份工具/契约实现SHA不变。

## 配置和权限

沿用既有DeepSeek配置，model=deepseek-flash、reasoning_effort=off、native baseline，关闭压缩及全部Motif策略，无embedding调用。前五流程14工具，恢复15工具；各任务保存实际schema及顺序、输入/源码/配置SHA、原事件、逐HTTP账本、实际目录、报告收据和验收轮次。源码为dfe4fcc公开基线加本地未提交版本，精确运行源码在各实验frozen-source内。

环境为macOS26.4.1 arm64、Node22.22.2、Python3.12.13、Harness0.1.5-rc.3、Python SDK0.1.5rc1、MCP2.2.0、Pillow12.3.0。每任务预算USD5、96请求/步骤、4000输出token、最多2次验收修复，最多一次由固定验收识别的冷启动续接。第一版批次预览上限USD60，第二版USD10，均计入原系列USD1000；恢复始终复用原任务、授权、预算和计数。

2026-10-14核对[DeepSeek官方价格页](https://api-docs.deepseek.com/quick_start/pricing/)，既有Flash峰值价格表保持缓存命中0.006、未命中0.30、输出1.20美元/百万token。计费依据为代理的真实响应usage；未知usage保留预留。本轮完整206份usage：输入1,704,716，其中命中1,559,168、未命中145,548，输出59,093，总token1,763,809。实际账单尚未核实；开发、免费检查和人工审阅时间未折算收费成本，表中时间只包含CLI运行。

## 失败和恢复证据

第一版FM38-N和E分别14/18请求、USD0.006727694/0.009457946，文件最终字节正确，但均实际读取了allowed_reads为空的三个原文件。RecoveryScene继承的pin_file缺少WorkflowScene范围守卫；固定验收拒绝这一不可逆历史违规，两个job终态failed、修复次数0。未扩大读取权限，也未重置旧job或重标失败。

修复版在pin_file生成句柄前拒绝未授权路径，read_task明确仅用目录/哈希元数据。新FM38-N/E均0份内容读取，job终态completed、验收各1轮、修复各0次。E在第一个目标发布后真实退出MCP进程75；Harness的MCP客户端重新连接，模型再次read_task取得持久化partial_failure和原授权标识，再restore_plan恢复初始字节。只有一次execute和一次restore，无部分计划重放，全部范围外文件不变。此真实任务观察到MCP重连，未触发外层CLI冷启动。

真实N任务只调用一次execute，未证明模型主动重复执行或整Harness冷启动；幂等重启由免费实际MCP探针另验。免费实际Harness的冷启动检查使用本地模拟Provider，在中断后换新传输Session、复用同一持久化任务，12次模拟HTTP、1修复/2验收通过，0云费用。早期尝试复用原SDK传输Session被“session already exists”拒绝，原免费失败日志保留；上游核心没有修改。

两真实版本共59次工具错误全部保留、计费。原备份任务的未授权读取尝试已在工具侧拒绝；修复版另观察到未读集合collect拒绝、报告超过2000字符拒绝、MCP重连后未read_task的盘点拒绝，模型随后纠正。不能用最终成功抹去这些调用和成本。

## 审计和学习材料

独立离线审计加载各自归档源码重新计算执行版本并重跑原验收，核对源文件、题面、oracle、工具schema、配置、报告、实际字节、逐HTTP/token/估费和持久化job；第一版仍10通过/2失败，第二版2通过。原始失败、免费SDK失败、审计第一次误读usage字段导致token显示0的日志和修正记录保留，实际HTTP账本未变。

统一数据集workflow-observations-20261014-2f267505含14张观测图、343工具节点；12份成功普通轨迹可供后续核验，2份失败保留但不训练，0个Runtime自动节点。按实际执行版本和schema分为14工具的10份、15工具的2份合格组；免费/模拟/认证/留出轨迹均未混入。

scalar观察器提取出pin→read、preview→execute、preview→authorize等重复参数传递候选，尚未编译或认证。嵌套动作、集合完整性、授权token和恢复分支需要更完整的见证；观察顺序或重复频率不能授权效果执行。当前没有H/S/M对照，因此没有新流程的Motif节省或相对普通脚本优势结论。

## 复现和下一阶段

本机私有指针workflow-explore-current.json指向修复版，workflow-observations-current.json指向统一数据集。各实验含protocol、frozen-source、tasks/attempts、summary、independent-audit、unified-observed-graphs、analysis-source；原SDK事件和HTTP账本在.local/runs，逐轮验收在.local/task-acceptance，开发/免费失败/源码差异在.local/workflow-exploration-development-20261014。不提交这些原始数据、凭证、PDF或私有库。

```sh
# 新实验默认仅准备/免费预览；已有结果禁止覆盖。
node scripts/project.mjs python scenarios/file-management/workflow_study.py
node scripts/project.mjs python scenarios/file-management/workflow_study.py --workflows FM38
node scripts/project.mjs python scenarios/file-management/workflow_study.py --experiment <NEW_EXPERIMENT>
# 已授权范围内显式调用模型；须先完成源码和权限冻结。
node scripts/project.mjs python scenarios/file-management/workflow_study.py --experiment <NEW_EXPERIMENT> --call-model
# 离线审核归档源码，不调用模型。
node scripts/project.mjs python scripts/audit-workflow-exploration.py --experiment <EXPERIMENT>
node scripts/project.mjs python scripts/audit-workflow-exploration.py --pool <EXPERIMENT_1> <EXPERIMENT_2>
```

最终npm test为565Python/146Node通过、3可选Docker跳过；修复后33项真实MCP免费探针和18项旧烟测通过。接口改动见[逐项记录](../changes/file-management-workflow-runtime.md)。全文件系列累计509次尝试、4799请求、代理估费USD3.960098813，76个模型任务失败保留，估费预算余额USD996.039901187；实际账单未知。

下一步G4按14/15工具的实际依赖版本分别学习并独立认证，未获证书的效果/恢复候选继续普通Harness；随后G5新留出H/S/M三组对照，包含学习、认证、失败、恢复和人工质量成本。动态前端、完整格式恢复、并发和跨平台恢复不在本轮验证范围。当前只本地开发，未提交或推送GitHub。
