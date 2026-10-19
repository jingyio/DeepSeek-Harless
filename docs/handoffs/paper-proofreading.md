# 论文校对当前交接

- 更新时间与交接人：2026-10-19，Codex。
- 目标与本次范围：用户要求先把 Negative Motif 从重复 ID 扩展为不同错误原因自动学习，再测错误恢复与模型费用。本轮实现源码辅助的数据/控制依赖与双向反事实认证；未启动新的付费成本实验。
- 分支 / commit / 工作区：独立 `codex/negative-cause-learning`，基线 `2acb445`；本记录随实现本地提交，见 git log -1。未推送、PR 或部署，原脏工作区、生产、旧认证库和私人原件未改。
- 已完成：`negative_field_compiler.py` 通用分析静态 schema、别名、有限展开、动态列表循环、嵌套 if/else、布尔/类型/成员/集合/数量条件；保留控制开关与跨集合字段，同码多分支合并。不注册错误名/论文字段，profile 一次指向整个已审阅只读必要校验器。无法支持的控制流、动态/不透明脚本仍回退。
- 已完成：字段 IR v2 绑定 failure_code 和双向原因证据。在内存副本中，以真实对照或通用数据扰动验证修复/重新引入，并用有界 delta debugging 缩小改动；记录残余错误与是否整体通过。成功对照和依赖外干预继续要求。不是自动修稿、全局早停或通用黑盒因果证明。
- 已完成：TypeScript 有界解释带作用域变量的 IR，loader 校验错误码/证据/实现锁；原 current failure→实际请求 notice→重算条件→局部门控协议及来源/身份/目标/schema/参数/SHA 守卫保留，不扩工具表。节点 256、深度 32、数组 10000、步数 100000，未知放行。
- 已验证：npm test 完整 927 Python/887 Node 通过、199/5 跳过；局部 24 Python/19 Node 通过，无模型 smoke 与最终正负库共同装载通过。7 个不同错误标签的通用诊断跨语言、无关编辑/修复/未知状态检查通过，原生 ToolRuntime 门控保留。
- 实验结论：[paper-negative-causes-20261019-v1](../experiments/paper-negative-causes-20261019-v1.md)。原校验器静态 11 候选，真实历史认证 2 类：重复 ID 和非法 status/priority。两失败状态用于字段认证，25 个留出状态（8 枚举、17 重复）均复现原错且对应谓词 true；2 个历史成功状态两谓词 false；7 个留出状态同时有两种原因。标签/工具资格使用全轨迹，状态间相关，不是独立任务或 LLM 跳过率。
- 实验结论：真实枚举原因缩小到一个 priority，修复后原结构校验通过；重复 ID 缩小到一处改动后原错消失，但揭露枚举错误，记录 whole_validator_passed:false。不能把局部原因消除当作整个交付合格，也不将诊断值用于科研修稿。
- 配置与数据：`.local/negative-causes-20261019-v1/` 保留 field-profile/split/effective-config-final、evaluation-final/node-evaluation-final、学习计量、全部旧失败日志/库与私有复现脚本。最终负面 library-004 digest `08becf591624e9fd2a92222604e5aac6ddfe373d1cef83ea2ede53e85822895c`；正面 positive-library-002 实际重认证 7 算子，digest `111bbbd765b47f0bb4c2a8ca7d2106acab1fb5202923840254b88db427897ac8`，combined-config-final.json 装载通过。旧各轮数据/锁不改。
- 未完成与阻塞：真实认证仍仅两类，其余广度来自合成局部诊断；没有独立新任务泛化/模型行为/费用验收。控制字符、计数/编号类型分支尚不支持；不透明 Bash/Python、外部依赖和语义/科研错误未解决。草稿可读/可修复接口仍未修复，前轮服务错误与不合格报告负面证据保留。
- 接手下一步：1）先在更多受信校验器与独立资料检验原因迁移、共存错误及误拦截，未支持的条件继续安全回退，不逐错写规则。2）使草稿可读、可修复并保留原版本/验收要求，再按用户顺序做新任务 Prompt/Enforce 恢复对照。3）比较包含学习、提示、失败和恢复的全费用，稳定后用户决定 PR。
- 最短复现：项目 Python 运行 `python -m pytest -q tests/test_negative_fields.py tests/test_script_negative.py`；Node `node --experimental-strip-types --test tests/test_script_negative.mjs`。真实历史使用既有 learn-negative-motifs.py + 匹配历史 implementation-file + 新私有 field-profile/output，接口格式见 docs/interfaces.md。当前 macOS 项目环境 TMPDIR=/private/tmp、沙箱显式 SSS_LOCAL_SCRIPT_EXPERIMENT=1；服务器/Windows 未做新验收。
- 权限与预算：沿用本地真实调用无限额授权，本轮模型新增 0。旧本地 2835 请求/$4.714453692 保守估费与 1 pending 保留，V100 未核清，非账单实付。单独认证原函数调用 23/22 次，各约 0.05 秒，仅部分学习耗时，不含开发/回归/HTTP；没有后台付费任务。
- 回退与风险：关闭 negativeLibrary 恢复不使用负面逻辑，回退 2acb445 恢复上一版字段守卫。Runtime 升级须实际重编/认证，不能手改旧锁；不删除旧负面证据、私有快照或重置账本。目前不足生产发布或 PR。

前轮：[单类字段依赖](../experiments/paper-negative-fields-20261019-v1.md)、[负面提示](../experiments/paper-negative-motifs-20261019-v1.md)、[连续执行](../experiments/paper-script-frontier-20261019-v1.md)。
