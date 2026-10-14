# 论文 Motif shadow / execute：真实协议诊断

- 实验 ID：`paper-motif-shadow-execute-20261009-v1`，2026-10-09 开始、10-10 完成，Codex。
- 问题与否定条件：从真实工具轨迹编译的参数流，能否接管重复证据读取并安全跳过整次模型请求？若无实际 API 请求减少、工具结果不一致、错误/来源漂移仍计成功，就不支持该机制。本实验不判断科研质量、收益或投稿合规。
- 代码：`feature/paper-submission`，基点 `2368235f274329be6227a8393b850633cb943da4`，工作区未提交，未推送。与同目录 Web 工作并存，不修改上游或重启前端。

## 任务、编译与对照

三份不同受控 LaTeX 夹具：干净引用、缺失引用键、重复公式标签。模型分别自主调用六个只读 MCP 工具；两份挖掘，第三份留出验证。它们是不同源文件/问题的合成协议任务，不是独立人类科研决定。私人论文及其 Native/PTC 续跑不用于训练。

沿用轨迹 provenance、witnessed edge compiler、留出认证和 library exporter，得到三个 `pin_paper_{sources,build,pdf} → read_pinned_paper_{sources,build,pdf}` Motif，参数 `source_id` 来自实际工具返回。库摘要 `08ab347bd4e9ec3f3777a3d6acb0039a1c017fd6f8fba68f292fcecbb8dc564d`。冻结真实 MCP 参数 schema 摘要、版本与来源；`certification_scope=protocol_diagnostic`，普通生产插件拒绝加载。

评测是同一私人论文的**既有证据读取**：不重新编译、不修稿、无视觉、无文献真实性/会议合规判断。baseline / shadow / execute 使用相同题面、工具集合及 schema 顺序、源文件和派生产物。与先前完整 Native/PTC 工具探索的任务条件不同，不能把 85/128 次到 2 次归因于 Motif。

## 配置与复现

- 服务器 `/root/autodl-tmp/jjy`，加载 `.local/remote-env.sh`；Node 22.23.3、Python 3.10.8、Harness 0.1.5-rc.3。模型 `deepseek-flash`，`reasoning_effort=off`，输出最多 3000，不压缩、不设请求次数上限。
- 新 TypeScript 诊断适配器复用既有 JS Runtime。无 embedding；仅唯一封闭来源读取可接管。MCP 仅提供六个只读工具，禁止原生 shell/任意路径/生成代码；无需这轮启用非沙箱终端。
- 私有根 `.local/paper-motif/<实验ID>/`，每个 `runs/<运行ID>/` 保存 `manifest.json`、题面、场景/policy、逐请求、事件、代理账本、answer、metrics、Motif audit；根目录保存输入、工具契约、mining、library、manifest、verification 与独立 audit。配置快照记录实际版本、代码/输入/题面/patch 哈希、Session 和累计预算。
- 初始五份历史账本共约 0.2545546 美元、237 次请求；本实验累计上限 1 美元。新入口无默认付费；按[场景说明](../../scenarios/paper-submission/README.md)运行 `preview → prepare → collect → compile → compare`，付费阶段显式 `--call-model`。当前入口依赖既有私有账本和准备目录，不能当作通用新环境安装命令。
- `code-history/collect-runner.py` 保存训练时的控制器；其后只扩展 compile 的实际 schema 冻结，再执行评测。`compare-runner.py`、`executed-checks.py` 保存本次评测使用的版本。快照与这些代码绑定，不用事后修正版本冒充原运行。

## 已观察结果

训练采集 9 次真实模型请求，18 次 MCP，三份均读取三种视图且源未改；合计约 0.0074654 美元、31.588 秒。编译器挖掘三个 Motif 并通过受控留出验证；这不是科研质量认证。

| 私人证据评测 | 真实模型请求 | verified skip | shadow 候选 batch | 代理新增估费（美元） | 端到端秒 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 同工具 baseline | 3 | 0 | 0 | 0.003314136 | 12.019 |
| shadow | 3 | 0 | 1 | 0.003427704 | 12.490 |
| execute | 2 | 1 | 0 | 0.003438120 | 12.515 |

三个模式各执行六次 MCP；独立核对题面、完整 schema 及顺序、三类工具结果完全一致，工具失败为零，唯一授权案例且源版本不变。execute 的一个 batch 含三次 read；审计先记录 attempt，再逐项验证，最后记录一次 `model_request_skipped_verified`，随后模型继续解释证据。模型请求数来自真实代理账本，不把合成工具 stream 当模型请求。

| 模式 | 未命中输入 token | 缓存命中输入 token | 输出 token |
| --- | ---: | ---: | ---: |
| baseline | 4270 | 3456 | 1677 |
| shadow | 4150 | 3584 | 1801 |
| execute | 4286 | 1920 | 1784 |

execute 请求少 1 次，但缓存命中少、报告输出增加，估费比匹配 baseline **高约 3.7%**，耗时也未降低。当前仅单次探索，不能推断稳定经济收益。训练/开发/维护和人工成本尚未摊销；人工修订时间未测。

本实验共新增 17 次请求、约 0.0176453 美元；与前面论文实验累计 **254 次、约 0.27219994 美元**，剩余估算约 0.72780006 美元。均为代理估费；账单实付未知。

## 质量、失败与事后修正

三份回答已产出并核对主要诊断，但**质量未盲评，未判定合格**。复核发现检查器的两个问题：ACM `.bbl` 中 `\bibitem[...]%` 注释造成已渲染键全漏读；无编译步骤时 `shell_escape_disabled=false` 易被解释成未禁用，实际未知。三个模式收到同样的错误事实；“结果一致”不等于正确。

当前已修正注释解析及未知值（null），无模型复算恢复 34 个渲染键；新增回归。旧报告原样保留并在私有 audit 标记；shadow 答案把未知安全配置读成确定状态，execute 答案对字段解释更谨慎但仍继承渲染键漏读。尚未追加付费复验。检查器摘要参与版本守卫，修正后旧 task 必须失效，不能把旧认证快照直接套到新版本。

验证：修正前全量 151 Python / 48 Node 通过；修正后本机及服务器全量 153 Python / 48 Node 通过。新增源码事实/句柄漂移/越界/循环/ACM 注释回归，以及生产拒绝诊断库、shadow 不接管、工具 schema 类型变化与结果版本漂移回退。无模型 smoke 已通过 18 题/83 来源，既有首发 Motif 库重编译与 Harness baseline/shadow/execute/旧版本回退通过。模拟检查仅证明开发协议。最初本机 sandbox 的四项 loopback 测试被系统权限阻止，授权本机测试后全量通过，未删除测试。

## 结论与接手下一步

在这些条件下支持：轨迹编译的只读参数流可以经真实 Harness 跳过一次完整模型请求，并把证据交回模型。当前覆盖句柄绑定、版本核验与确定性读取；没有接管编译执行、失败修复、页面视觉或科研判断。

不支持：成本下降、质量合格、独立科研任务泛化、全场景替代模型，以及比手写 hook/脚本更好。下一步先修订质量门槛并盲评，再采集独立论文任务的编译/失败恢复轨迹；加入普通脚本对照，比较相同质量下包含训练、恢复与人工的总成本。未知分支继续交回模型，不能扩张为任意代码重放。收尾增加跨实验 ID 累计记账与全局实验锁，防止新目录重置预算；该修复在已完成运行之后，无新增付费请求。
