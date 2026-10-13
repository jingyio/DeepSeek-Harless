# Harless 多场景 Runtime 集成验收

- 实验 ID：`harless-scenes-runtime-20261013-v1`；开始：2026-10-13，交接完成：2026-10-14。
- 问题：原生菜单是否实际改变下一任务的 MCP/Prompt/RSI 策略，同时维持任务冻结与用户边界。若只改变显示、错用样例或跨 Session 读取输入，即否定集成通过。
- 类型：合成资料上的实际 Harness/MCP 和真实 DeepSeek 联调；不是前瞻科研任务，也不证明科研质量或降本。
- 基线：最新 `origin/main` `62ee46b`；独立分支 `codex/scene-rsi-bridge`。保留原论文目录、用户隔离协作者未提交文件及共享服务器；没有修改上游 Harness。

## 配置与复现

- V100 隔离检出：`/home/jingyij/jjy/.local/integration/scene-rsi-bridge-20261013`。Node 22.23.3、Python 3.10、DSH 0.1.5-rc.3，SDK/依赖以锁定清单及运行快照为准。Python/PPT依赖安装到本次私有环境，没有修改共享环境。
- 生产目录 `config/harless-scenes.json`；历史诊断目录 `config/harless-diagnostics.json`。配置、源码和 schema 的 SHA 保存在有效快照，不以绝对路径替代版本。用户、Session、Task、Prompt、来源/上传文件、权限、预算及模式均逐任务记录。
- 无模型新场景验收：`551b54bb87df4acc860f1ce631cdac9f`（`441ab09`）；完整 Schema 生产准入补齐后再验：`ef26d493c7514a9a966541692e15e4a8`（`99f7b2f`）。两次均0模型请求。
- 真实运行 `907266faee4d40d799eca6ae2fa2109d`，代码 `1e16147`；DeepSeek Flash、off、Shadow、无生产库，任务上限0.03美元/12请求，启动累计0.06美元/24请求，每请求最多1000输出token，压缩关闭，工具顺序固定。真实验收后新增的完整 Schema 准入只影响有库路径，按局部及全套无模型回归验证，没有为了文档重复付费。
- 原始配置/轨迹/失败日志留服务器 `.local/harless-scenes/` 与 `.local/web/runs/<run-id>/`。真实运行和报告同步本地开发工作区 `.local/integration/scene-rsi-results/`；不提交原始日志、认证URL、上传文件或控制凭证。
- 启动先加载项目私有环境。服务器文件监听额满，本次使用 `CHOKIDAR_USEPOLLING=1`，快照记录了实际值；不改变系统限额或既有进程。

```sh
# 本次 V100 隔离检出，复用项目环境入口；PPT依赖在本次私有解释器：
source /home/jingyij/jjy/.local/remote-env.sh
export SSS_PYTHON="$PWD/.local/python/bin/python" CHOKIDAR_USEPOLLING=1
npm test
npm run smoke
npm run web:controls:check
npm run web:scenes:check
npm run web:tasks:check
npm run web:check
npm test --prefix scenarios/research_ppt
# 在持续测试授权内，只读真实联调，不扩大产品预算：
npm run web:scenes:check -- --real-model
```

## 结果

- 全套 `npm test`：154 Python / 60 Node 通过。PPT Node含空job权限反例：53通过。smoke：18题/83来源通过。
- 控制协议：命令、模式、preset重组、预览冻结、继承、拒绝及三套历史MCP表面通过，模拟Provider仅用于协议诊断。
- 新生产场景无模型验收：24种菜单组合、缺后端/缺库拒绝、PPT19工具与通用2工具实际加载、指令/上传绑定、已预览任务冻结、两个用户启动实例、外来Session/Task/收据拒绝均通过。
- 旧冻结入口：11组通过，含错误工具、失败、取消、限额及失效恢复。
- 历史动态任务诊断：13组通过；portfolio baseline/shadow/execute 为14/14/7模拟请求，Execute结果验证5次，改题面回退14请求/0跳过。上述是原认证有限契约诊断，独立标记 `diagnostic:true`，不能当作生产全Schema认证或实付节省。

| 真实任务 | 任务 ID | 状态 | LLM请求 | MCP调用/错误 | verified skip | 代理估费USD | 耗时秒 |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: |
| New Scene，读取上传文本 | `4738a1e694c5459ea7b2a25d8a85db47` | completed | 3 | 2/0 | 0 | 0.001173792 | 8.281 |
| PPT，读取上传PDF与版本引用 | `726d6eede70943f88fb9ae9ad98ed2c9` | completed | 4 | 3/0 | 0 | 0.003055716 | 7.640 |

两任务均 `fallback_reason=no_certified_library`；只有对应场景工具，引用了实际文件/句柄及版本，读取事实与合成输入一致。输出权限关闭，无生成、修订或外部写入。

累计7真实请求，输入31975 token（命中23168/未命中8807），输出1207，合计33182；代理估费0.004229508美元。完整用量已结算，无重试、未决或未知用量；账单实付未核对，不能写成实付0.00423。费用上限0.06美元未重置，剩余估费空间约0.05577；本轮已停止调用。任务耗时不含环境安装和工程维护；开发/安装/人工修订成本未量化。质量未盲评，未计人工评分。

## 失败、修订与边界

- 私有新环境首次缺基础 MCP 依赖，随后出现系统监听 `ENOSPC`；都在模型启动前失败，新增API请求0。分别补齐隔离环境和测试进程轮询设置，保留失败记录。
- 现有PPT可靠Adapter拒绝无来源的空Session，新增显式Web只读初始化。默认CLI仍拒绝，空来源加输出权限也拒绝；不是用示例来源补空输入。
- 旧冻结 `outside-tool` 注入原先只作用于 portfolio selector，demo分支绕过注入，原安全断言观察4而期望5。修复统一fixture入口，保留断言及负例。真实模式仍禁止fixture，未拿模拟成功冒充真实验收。
- 论文与数据分析没有main正式后端；产品拒绝，不映射example/portfolio。PPT与通用场景没有发布生产认证库，Execute不可用；未证明这两场景的实际跳过或费用下降。
- 用户隔离验证针对两个独立Harness实例。单进程多账号/协作者gateway、跨启动恢复、浏览器真实点击、PPT生成/修订/完整PDF交付和科研内容盲评尚未验收。
- PPT原生菜单只选场景/模式，尚无页数/模板/输出授权编辑界面；这些参数通过任务API预览确认。下一步接正式论文/数据后端及用户gateway，并独立认证对应库的完整Schema、来源与任务绑定，再做小规模真实Execute对照。


## 2026-10-14：合并新主线与同范围恢复验收

交付前main刚合入多用户PR #7（`2a96552`）。合并保留账号/认证源码、预算broker、客户端Session ID、重启恢复和连续对话；冲突仅在共享任务适配/测试/交接中协调。零工具成员权限派生配置不能继承所有者MCP；通用成员对话继续工作，PPT等未挂载后端明确拒绝。旧任务读取保留批准版本与模式，当前权限仍核验；新的文件/PPT任务及场景切换用新Session。

由于Session生命周期有实际整合，追加两项只读真实回归：run `47ac1c37b74b494391bff14b56ce6b13`。新增启动封顶0.03美元/17请求，承接此前0.004229508美元/7请求，不重置本轮0.06美元/24请求总限制。其后仅测试/文档提交不影响运行时源码，完整有效快照为版本权威；不把报告完成时commit代替启动快照。

| 回归场景 | 任务ID | 真实请求 | MCP/错误 | 代理估费USD | 耗时秒 |
| --- | --- | ---: | --- | ---: | ---: |
| New Scene | `3f79ae5ff08b4daca28de9d24c30d65e` | 3 | 2/0 | 0.001005432 | 5.919 |
| PPT读取 | `b231a846c8844d1fa9bc05b6fc5604a3` | 4 | 3/0 | 0.001239780 | 7.295 |

均completed、`no_certified_library`、0 verified skip。本轮最终累计14真实请求/10MCP/0工具错误，输入63924 token（命中53120/未命中10804）、输出2429，总66353；代理估费0.00647472美元，账单未知，无重试/未决/未知用量。剩余估费空间0.05352528美元，已停止调用。追加运行属于同类合成资料的集成回归，不算独立科研效果任务，也不把缓存差异归为RSI收益。

最终V100免费回归：`npm test` 为165 Python/75 Node通过；smoke18题/83来源、控制与新场景协议、动态13组通过。PPT53 Node与冻结11组先前已通过，相关代码在主线合并中未改变。包含用户gateway/预算及重启版本冻结测试，模型费用为0。成员bubblewrap内的正式场景部署、双账号真实浏览器与模型验收仍未在本轮完成；先前主线的双账号免费结果保持原范围。
