# 新Motif、持久化任务和计划策略的在线组合

2026-10-14。状态：9个控制场景和1次最终源码新副本复验，共10次真实运行，全部满足冻结检查预期；7交付通过、3按原限制停止且保留未完成。独立审计通过。

## 问题与实验范围

验证G4真实普通轨迹学得、独立认证的15工具计划图能否在原job权限/预算/版本下执行，并在库失效、效果失败和程序验收失败后正确交回普通Harness。假设被否定的条件包括：未授权效果、版本失效仍自动执行、原计数重置、修复后重新启用Motif，或把限额/撤权失败标记为交付完成。

使用生成的新文本和路径、实际本机MCP与真实DeepSeek API；不是前瞻办公质量或H/S/M成本对照。原三PDF和54套probe/explore/certify/holdout材料不动。当前真实主实验 `fm-workflow-online-20261014-9ecabaa2`，8条件：2/4源件正常、在线模块版本失效、源范围拒绝、3请求原上限、受控缺报告验收修复、真实MCP进程中断后原授权回滚、实际授权后执行前撤权。

G4原 `fm-workflow-learning-20261014-d93e4c44` / library-lock e4a3024a…、plan policy 3da07377…保持。服务外层c1b878a1…和计划组件ae4973ce…均绑定，不冒用组件证明任意外层。首次免费开发版b37a11a9的2源件SDK检查保留；补充入口预览和权限拒绝结果断言后9ecabaa2重新冻结，付费材料只用后者。

## 有效配置与复现

branch feature/rsi-research-agent，HEAD dfe4fcc，本地未提交；Node22.22.2、Python3.12.13、Harness0.1.5-rc.3、SDK0.1.5rc1、MCP2.2.0。deepseek-official / deepseek-flash，reasoning_effort=off，不压缩，native15工具保持顺序。每题上限5USD/96请求与步骤/4000输出/2修复，限额例max_requests=3；8题批次最多40USD，计入系列原1000USD。模型实际服务端构建和账单尚未核实。

```sh
node scripts/project.mjs python scenarios/file-management/workflow_online.py
node scripts/project.mjs python scenarios/file-management/workflow_online.py --experiment .local/file-management/<冻结ID> --case normal-count4 --free-sdk
node scripts/project.mjs python scenarios/file-management/workflow_online.py --experiment .local/file-management/<冻结ID> --case normal-count2 --call-model
node scripts/project.mjs python scripts/audit-file-workflow-online.py --experiments .local/file-management/<冻结ID>
```

第一条只冻结新开发材料，不调用模型。私有protocol/frozen-source、library/binding/task/工具Schema、config、job.json.events、每segment的stdout/stderr/returncode、原native事件和HTTP usage/cost-ledger、验收每轮档案均保留。密钥沿用原受保护配置，不记录值。原失败不追改，运行轨迹不当作普通训练来源。

## 结果与质量

| 条件 / 版本 | 交付通过 | HTTP | 代理估费USD | 验证跳过 | 普通验收修复 |
| --- | --- | ---: | ---: | ---: | ---: |
| 初版正常2源件 | 是 | 7 | 0.003744722 | 2 | 0 |
| 初版正常4源件 | 是 | 8 | 0.004996825 | 2 | 0 |
| 在线模块版本失效 | 是，普通Harness | 11 | 0.005189520 | 0 | 0 |
| 未授权源预览拒绝后合法完成 | 是，普通Harness | 10 | 0.005110428 | 0 | 0 |
| 原3请求上限 | 否，limit_exhausted | 3 | 0.001057512 | 0 | 0 |
| 受控缺报告验收失败后修复 | 是，2次验收 | 9 | 0.006583261 | 2 | 1 |
| 真实MCP退出75，原token回滚 | 是 | 10 | 0.006737234 | 1 | 0 |
| 实际授权后、执行前撤权 | 否，revoked | 5 | 0.001944708 | 1 | 0 |
| 新0.01美元原预算拒绝 | 否，代理拒绝下一请求 | 1 | 0.000166452 | 0 | 0 |
| 停用持久化补强后的新4源件复验 | 是 | 7 | 0.004730401 | 2 | 0 |

主8条件9ecabaa2为6交付/2限制停止；65ac206a是另冻美元预算例（只选1个新开发模板，另7个未运行模板保留），bcb96582是最终TS门版本的免费/真实新4源件复验。9个独立条件加1次复验的检查预期均通过，但3项未完成仍按失败/停止记录，不重标交付成功。

0.01美元例只发出1个真实请求，spent=0.000166452；下一请求的保守峰值预留超过余量而被拒绝，不能把“余额仍有”解释成可以绕过代理。job仍running、没有accepted，不代表任务完成或预算已实际花完；原限额、已花费/计数和拒绝均保留，未增发预算。撤权例只自动授权，execute未发出，原字节完全不变；请求上限例也是零文件效果。

受控缺报告例首轮固定验收失败、原job.repairs=1/motif_disabled=true，再由普通Harness补交报告，round1复验通过。真实MCP中断例在故障回调后停用图，模型读取实际recovery_state并使用原plan_id/authorization_id恢复原字节，首次验收即通过；这是语义恢复，不是自动restore，也没有真实整Harness冷启动的新增证据。原SDK模拟冷启动证据另见G3记录。

收尾发现Schema/题面拒绝分支尚未持久化停用，补强TS门并改变其SHA。原9次冻结源码/绑定/轨迹/费用保持，旧绑定因此失效，bcb96582使用新源码、新绑定和新材料。新增3项会话门拒绝后冷重建不能激活检查通过；不能将旧9次当成最终代码的全部直接覆盖。最后新4源件实际执行通过，2次续接验证、7HTTP，原1工具错误保留。

## 成本、核查和失败档案

本轮10真实任务共71HTTP，10次实际验证续接、8工具错误保留；运行器累计172.653秒，不含制作材料、预检、开发、人工审阅和维护。HTTP usage为输入424300（hit370176/miss54124）、输出18169、总442469。按冻结峰值表逐HTTP重算USD0.040261056，原job纳美元向上取整合计USD0.040261063，差额0.000000007，实际账单未核对。计入所有旧学习、认证、失败与恢复后的全文件系列529尝试/5005HTTP/USD4.071946564，79未通过交付保留（本轮新增3个受控限制停止），原1000美元估费余额995.928053436。

5个初版免费实际SDK/MCP检查加最终1复验共6通过、36本地模拟HTTP、0云费用。另实际CLI/MCP预览0API且未激活job；全仓565Python/164Node通过、3可选Docker跳过，18旧smoke通过。新持久化门18项含撤权/取消/暂停/修复/费用/请求/未决/任务/源依赖/lock/绑定/外层和组件变化，以及效果失败与会话拒绝的冷重建；Node检查不是业务质量评估。

独立审计逐项重算71个真实HTTP usage/估费、原hash-chain状态和限额、0内容读取、实际自动调用身份及修复后没有自动调用、报告/字节后置与54原template/oracle/pristine及3PDF。G4原library-lock、13个15工具服务依赖及29旧库文件保持。最终审计按各轮原frozen-source识别旧TS版本；允许并单列收尾适配器版本和事后文档更新，不用新源码假装旧运行。

私有 `online-independent-audit.json`、每轮 `job.json.events` / cost-ledger / agent-events / 验收archive和失败原文保留。开发before/源码diff、测试/审计日志在workflow-online-development-20261014-aead269c。初版单测对损坏binding冷加载误用false断言，实际安全throw；审计初版把budget_denied记录当HTTP计数；均修正验证逻辑、保留原失败，未放宽权限或重跑收费结果。此前stdio辅助/空MCP描述/旧模型失败也不追改。

## 结论与限制

在生成文本、FM38 rename/move及自身日志回滚、原任务权限/预算和固定版本的这些条件下，显式认证计划Motif与持久化job能执行；版本/范围拒绝后普通Harness可完成，限制停止不产生效果，验收失败可在原限额修复并复验。计划学习/独立认证见证仍是2/3源件，在线新任务观察到2/4源件；没有重写旧认证证据。

没有同冻结H/S/M完整对照，10个验证跳过不能代替费用优势或总成本结论。缺报告/撤权/美元限额是受控负例，不代表自然业务错误率；未做人类语义盲评或真实办公前瞻，未核实账单/人工修订/维护成本。自动恢复图、其他流程与持久化任务多库组合、动态前端、并发/任意断电/元数据恢复和跨平台仍未认证。默认SDK/Web继续关闭新库，G5新留出不运行，暂不提交/推送GitHub。

[逐项共享接口](../changes/file-management-workflow-online.md)。
