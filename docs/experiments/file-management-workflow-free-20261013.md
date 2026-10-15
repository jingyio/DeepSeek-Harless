# 首批六流程副本、验收与免费恢复检查

本轮完成六流程的新副本和固定验收，免费MCP检查33/33通过；真实Harness接本地脚本Provider完成一次验收失败后的普通修复与再次验收。没有调用DeepSeek云端，未运行新Motif学习、认证或付费留出。

实验ID：`fm-workflow-free-20261013-de2f6604`。分支`feature/rsi-research-agent`，公开基线`dfe4fcc`；运行代码和交接只留本地，未提交/推送。

## 问题与任务

检验首批下载整理、目录合并、版本比较、字节备份与恢复演练、ZIP交付和任务中断恢复，能否在原授权副本内形成真实效果与独立验收。恢复必须保留原版本、权限、预算和修复上限；模型语义质量和Motif收益尚未检验。

准备54模板：probe18、explore12、certify6、holdout18。每份有独立文本/路径/规则/初始字节和私有oracle。有效Word/Excel/图片沿用现有容器模板，PDF复制三篇已知真实原件；不能作为全新办公语料泛化。实际检查只用probe复制出的新工作区，全部pristine和留出均未变。

## 免费检查结果

| 范围 | 数量 | 结果 |
| --- | ---: | --- |
| 六流程正常、边界、状态变化 | 18 | 探针18通过；业务后置验收12通过，外部变化6项按设计停止且保留失败 |
| 预算、取消、撤销、输入、修复、请求、版本守卫 | 7 | 全部拒绝越过原限制，实际副本无额外写入 |
| 集合0/1/8/9/32-33、动作40-41、ZIP30-31、计划6-7 | 8 | 有效边界接受，超界拒绝；容量探针不修改源件 |
| 真实Harness/MCP与持久化HTTP代理 | 1链路 | 9次本地模拟HTTP，1次普通修复、2轮验收，最后完成 |
| 全仓回归 | 565Python / 145Node | 全通过，3可选Docker检查跳过 |
| 最后执行版本核验定向回归 | 26 | 全通过 |
| 原18题MCP烟测 | 18 | 全通过，0付费模型请求 |

上述33项是开发探针通过数，不是33项业务完成；六个外部变化任务保持未完成。8/9检验集合成员读取和完整汇集，本轮未加载Motif，不能据此声称自动调度批次或新图已认证。

FM38在真实MCP子进程退出75后启动新进程，识别“目标已发布、原件仍存在”的已记录中间状态，用原authorization_id恢复；重复部分计划执行被拒绝。重启前后保留非零requests=1、steps=1、repairs=1，以及USD0.0054189的合成未决预留。最终回滚字节正确，再次验收后checks=2；未决预留仍保留。这里的预约是专门检验账本持久性的合成数据，真实上游请求0、实付0。

另一个SDK链路由真实Harness使用15工具、原权限制定并执行计划；本地Provider第一次停止时不交报告，固定验收失败，TS守卫分配一轮普通修复，刷新当前身份后实际submit_report并复验。持久化代理计9次本地请求、模拟峰值计价USD0.000486；这不是真实模型费用。重建代理后完成任务仍拒绝新请求，计数不重置。

## 失败与修订

首轮全仓回归559通过、2失败：普通旧场景的acceptance_guard为None，新增入口误调用get，旧CLI模型别名预览报AttributeError。已修复，22项定向后通过，全仓再跑565/145通过；原失败日志保留，不涉及云调用。

真实进程退出、6个外部变化停止、一次SDK无报告验收失败和各工具拒绝均原样保存。恢复演练先验收失败再修复成功，不删除最初部分效果/失败轮次。早期4489e154的25项、b6ed55c8和9008726a的33项免费记录仍保留；最终新增版本核验和frozen-source后使用de2f6604，不把旧记录冒充最终版本。

## 配置与复现

Node22.22.2、Python3.12.13、macOS本机；使用既有DSH0.1.5-rc.3/MCP依赖。场景native、reasoning_effort=off、压缩关闭。任务上限USD5、96请求/步骤、输出4000token、2轮修复；请求耗尽另以2次合成上限做负例，零预算以USD0做负例。未做Windows/Linux恢复实测。

```sh
# 只准备新版本，不调用模型。需要本地已有有效容器模板，可显式--assets。
node scripts/project.mjs python scenarios/file-management/workflow_prepare.py
node scripts/project.mjs python scripts/check-file-workflows.py --experiment <PRIVATE_EXPERIMENT>
node scripts/project.mjs python scripts/check-file-workflow-sdk.py --experiment <PRIVATE_EXPERIMENT>
npm test
npm run smoke
```

每次检查新建工作区/attempt，禁止覆盖旧结果。prepare把实现、共享适配器、配置/锁/依赖清单冻结到frozen-source；文档后来更新会使整目录哈希变化，重现使用归档实现或prepare新版本。MCP子进程不传模型凭证；本地SDK明确使用mock-no-key和loopback代理/Provider，不访问云端。

## 成本、版本与下一步

本轮新增真实API0、真实模型估费USD0；系列仍495次付费实验尝试/4593HTTP/代理估费USD3.836167800，原74次任务验收失败保留，实际账单未知。免费合成预约和模拟Provider计价单列，不混入该系列费用。原三篇PDF与原七个文件工具/契约源码SHA保持。

共享接口逐项见[变更记录](../changes/file-management-workflow-runtime.md)和[接口总表](../interfaces.md)。当前只实现受限重命名/自身计划回滚的任务状态整合；普通Web动态目录选择、任意格式恢复、并发或任意断电恢复均未验证。

下一步在冻结新协议和系列预算内运行普通Harness探索，再汇集其原始轨迹学习/独立认证，最后新留出H/S/M。免费脚本选择及模拟轨迹不参与Motif学习；留出未用于调试与学习。本轮没有真实模型语义评审、总收益结论或新组合证书。
