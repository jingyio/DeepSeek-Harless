# 普通 Harness 与 Code Mode 强基线（2026-10-12）

用户要求实际比较并明确包含Harness。现有文献入口只开放MCP，未启用原生Code Mode；先前普通Harness结果仍有效，但不代表Code Mode能力。第一轮比较范围是可精确重放的证据准备中间流程，不宣称整Agent科研质量或成本提升。

修改前列出所需共享接口：

- `prepare_scenario`/SDK入口新增可选native/ptc呈现方式，默认native保持原路径；ptc只为明确的实验启用。底层MCP权限相同，外层只允许原生run_code，子调用继续原工具守卫。Motif执行仍采用其已认证的native路径，不把PTC嵌套执行当成功skip。
- 新TypeScript CodeRuntime部署适配器复用上游WorkerThreadCodeRuntime实际执行模型程序，放在无网络、只读、无Key/论文/用户目录挂载的Docker容器内；宿主只桥接当前已批准MCP绑定。它改变部署隔离，不替换上游PTC调度/代码生成，也不新增Agent循环或自制解释器。
- 如原生PTC只记录ptc-dispatch，则回收读取其原始start/settled事件、验证配对并保存来源摘要；不伪造原始tool事件或修改旧日志。训练和认证继续来自正常native真实轨迹。
- 三主组为普通Harness、普通脚本、learned Motif；Harness另外报告真实Code Mode强基线。固定同一批准计划、语料/解析版本、模型/off/质量/预算，允许程序化批量和并行能力，训练/恢复/隔离启动费用分列。

Docker本机已有，启动已有Desktop后再检查；镜像固定Node22.22.2并记录实际digest。源码/环境/日志保留旧版本，apikey始终留宿主原加载与预算代理。Node Permission Model不是恶意代码的安全边界，不能以它代替隔离（[Node官方说明](https://nodejs.org/api/permissions.html)）；上游CodeRuntime包的containment限制见本机固定依赖README及[上游](https://github.com/deepseek-ai/deepseek-harness)。

新Web的literature_web库尚无认证，不能改旧库工具名称来凑全任务Motif组。第一轮不改其生产profile，不改原PDF/上游/计价；后续能否更省由对照决定，脚本或Code Mode获胜就如实采用。

## 实际接口与验收

- `prepare_scenario(path, case='', tool_presentation='native')`只接受native/ptc，HTTP/场景JSON未新增任意代码或路径参数。SDK `run-scenario.py --tool-presentation ptc`显式选择原生tools mode=ptc，替换部署CodeRuntime为隔离适配器，仍同一Agent循环。ptc与Motif shadow/execute同时请求会拒绝；不是当前库支持的组合。
- `dsh_scenario_guard.mjs`仍只登记MCP白名单，ptc仅在实际tools.modeFor(scope)为ptc时允许外层run_code。所有子调用走原MCP守卫，无bash/fs/subagent权限。默认native行为保持。
- `dsh_code_container.ts`实现公开CodeRuntime.run；容器内`dsh_code_container_runner.mjs`实例化固定上游WorkerThreadCodeRuntime。模型实际代码、顶层await/return/日志/异常及ToolError仍由上游处理；透明RPC仅桥接当前绑定，不自制解释器或编译模型程序为手写脚本。Docker无网络/只读/无私人数据挂载，取消/超时关闭该次容器；不可用时显式失败，无不隔离执行回退。
- `project_ptc_dispatches(events)`是有来源标记的分析视图，检查原始run_code root、唯一start/settled、参数/工具/parent一致；未结算、篡改、重复拒绝。原始日志不改，投影不冒充原始tool事件或模型决定。仅PTC收据回收使用；learn-evidence拒绝PTC训练轨迹。
- 场景run-evidence记录native/ptc；compare-evidence新增--include-code-mode，四组四轮顺序轮换。同一批准计划、底层工具和用户prompt，Code Mode wire schema与native天然不同且显式记录。单窗口机械来源重放/完整packet相等才accepted；学习/选择/失败成本单列。
- 首阶段模型逐工具生成程序，保留全部16轮。随后记录amendment并对全部组统一鼓励局部连续执行，新强阶段16輪，未提供代码模板。最新真实结论见[实验记录](../experiments/harness-strong-20261012-5da6ab9f.md)：脚本均值最便宜/最快，Motif较脚本贵约6.02%，没有增量优势。Code Mode平均请求较少但端到端更慢；不能以skip或请求数宣称收益。
- 共195真实请求/USD0.189877572含学习/独立选择/两阶段纠正，全部HTTP200、原PDF哈希未变；最终源码/镜像重核，无APIKey传入容器。386 Python+67共享Node回归通过，另3实际Docker隔离/绑定/取消测试通过；最后效率prompt修改后相关回归和全仓再验收。免费真实Harness PTC五子调用、二模拟请求，packet一致，不冒充真实模型最优表现。

## 使用、兼容与回退

Code Mode是可选实验依赖：Docker Desktop须运行，先pull固定node:22.22.2-bookworm-slim；真实比较记录镜像digest。`npm run code:check`免费实际PTC；`SSS_TEST_CONTAINER=1 node --test tests/test_code_container.mjs`才运行额外Docker测试，普通npm test默认跳过。SDK默认native和生产Web不需要Docker，Web文献profile未打开PTC、未强加旧库。

macOS arm64/Node22.22.2/Python3.12.13/DSH0.1.5-rc.3/Docker28.5.2本轮已验收；容器内部Linux/Node22不代表Linux服务器、Windows或多租户完整部署已验证。未使用A100。镜像/原始日志/论文/Key都不提交，只提交适配器/配置接口/测试/公开记录。

回退使用默认native、去掉--include-code-mode；不删除.local历史/旧库/论文，Docker失败不能回退到宿主无隔离执行。整个新共享改动在feature/rsi-research-agent/HEAD2368235、未commit/push/PR；main与origin/main仍bc1ecd5。强阶段冻结后只修改测试入口/文档，未追改原模型输出或实验费用。下一步聚焦动态可验证分支，当前固定链不迁到Web增加开销。
