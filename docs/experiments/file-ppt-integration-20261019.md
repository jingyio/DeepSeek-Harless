# PR84 / PR88 与 PR91 主线能力保留集成

- 实验 ID：`file-ppt-integration-20261019`；2026-10-19 启动，2026-10-20 继续集成。类型为代码集成、确定性回归及合成材料上的真实模型兼容认证，不是独立真实业务质量或净收益实验。
- 基线：最初 main `806e1ae62c96774f3dfe6db213d84d98dcd3ebec`（含 PR89/90/91），最终再接入 PR92 main `31c73098699fceba7afa1b532695bfbb1bb00cb9`，PR84 `5dbac290c10f27c08efb071eb7b9c1659326464a`，PR88 `0110d14179e6f1abb39bb72a187886deb2c68966`。保留两分支提交历史，独立分支 `codex/integrate-file-ppt-rsi`；未合并或部署。
- 问题与否证：PR84 可文本合并，但 `file-v5` 对主线公共 PDF 代码失配；PR88 的宿主、注册表及同名认证库冲突。任一原图丢失、旧权限扩大、附件上下文退回污染用户消息、学习/恢复失效或新证书不可加载，均不满足集成验收。
- 更正前次审查：主线注册的是 `paper-web-v15` / `ppt-master-v10`；v14/v9 对新版源码的拒绝属于历史版本守卫，不能据此声称当前主线库失效。本次以实际注册表和加载结果为准。

## 合并决定与证据边界

- 保留 main 的附件身份/版本、私有上下文、真实用户输入、异步准备进度、取消与迟到输入隔离，以及统一服务生命周期修复。PPT 学习接线叠加到该宿主，不覆盖回 PR88 的旧上下文实现。
- 保留 `/file`、账号私有经验库、高风险逐计划确认、交付下载、同一原任务恢复；其他场景请求由文件扩展交回原宿主。文件入口仍有 PR84 自身的 DeepSeek/Off、每任务 5 美元/96 步/4000 输出等边界，本次没有扩权。
- 所有已经发布的库目录保持原始字节。PR88 同名 v9/v14 的不同元数据不覆盖 main；该分支原证据继续从其 Git 提交和实验记录追溯。
- Paper/PPT 最初以 main v15/v10 生成候选 v16/v11；推进期间 PR92 先发布了同名库，因此最终完整保留 PR92 的 v16/v11，改以它们为来源发布 v17/v12。早期候选字节通过集成提交 `e058f6f` 保留，不覆盖主线已发布版本。`scripts/reexport-ppt-learning-compat.py` 默认只读审查，精确限定 Paper 三项、PPT 五项源码差异，公共 exporter 必须重导出相同 IR、完整 schema 和契约；原图、来源证据、任务及 manifest 原始字节不变。新增学习模块纳入源码锁。这是接线兼容，不是新训练、原始轨迹回放或质量/成本晋级。
- File 历史公开证明只作为重认证的图来源。新增 `validate_historical_certificate` 不用于在线准入；当前 `validate_certificate` 继续核对当前全部源码及工具目录。复用已有 recertifier，要求新原生见证和两次独立实际执行、无修复的严格交付及完整费用，之后才能发布新的 `file-v6`。没有只改旧 manifest 或旧证书哈希。

## 环境、配置与复现

- 本地独立 worktree 编辑和审阅；计算在已配置 Linux 服务器的隔离副本执行。私有定位为原项目 `.local/pr84-88-integration-20261019/code`，不覆盖旧源码、正式服务、账号、数据或累计账本。私有原始日志在该副本 `.local/logs/`。
- Node 22.23.3、Python 3.10.21；从既有解释器复制项目隔离环境后按 `requirements.txt` 补齐，Pillow 12.3.0，`pip check` 通过。71 请求的 File 重认证先在原共享 Pillow 12.0.0 环境完成；冷消费者与最终定向检查使用新隔离环境，这两个环境不混称。旧共享 Python 的 Pillow 12.0.0 与依赖要求不一致，未修改共享环境。
- File 模型为真实 `deepseek-flash`、`reasoning_effort=off`，不压缩；新增实验封套 1 美元，每任务 0.05 美元、48 步、3000 输出、0 修复。私有 `rsi` 配置、源码冻结、题面、输入、schema、认证回执及逐请求费用由原 runner 保存。旧 PR84 费用记录继续保留，本次费用另列并关联，不重置旧账本。
- 初次两轮在模型调用前分别被修复次数不一致、candidate registry 不在本状态根拒绝；保留旧模板/锁/错误，本次这两轮模型请求为 0。后续沿用 v2 配置和预算，将新认证 job 放入其原状态根执行。
- 首轮阅读诊断 5 项失败；补既有 OCR 数据路径后剩余 3 项 PDF CLI 失败。原因是解析子进程主动清理环境，缺少旧 Poppler 的动态库路径；只在隔离诊断目录创建动态库包装，6 项阅读检查通过。未降低读取或覆盖标准。
- 首轮 Node 定向 110 通过/1 个真实图片归一化等待超时；同项独立复核通过。初步改为 30 秒墙钟有界等待；PR92 随后已提供相同等待窗口和安全诊断，最终直接保留 PR92 的整份回归文件，未留下另一套修改。仍要求实际终态、像素与身份断言；产品超时和取消逻辑未改。

```sh
# 项目依赖和已安装 PDF/OCR 资源由服务器私有环境提供。
source .local/remote-env.sh
node scripts/project.mjs python scripts/recertify-file-seeds.py \
  --experiment .local/file-ppt-integration-seeds-20261019-v2
# 显式 --call-model 才执行；同一路径恢复原认证、原费用，不重新购买已封存见证。
node scripts/project.mjs python scripts/recertify-file-seeds.py \
  --experiment .local/file-ppt-integration-seeds-20261019-v2 --call-model
npm test
npm run smoke
npm run motif:check
```

## 当前验证与限制

- 已通过：62 项 Paper/PPT/历史重认证定向 Python 检查、6 项完整阅读/PDF/OCR 检查、PPT 后台学习认证/后续任务晋级/重启/负反馈否决/完整性守卫，以及真实附件存储图片身份定向诊断。后者使用真实存储和合成像素，不调用云模型。
- File 四类原图全部通过当前代码下的独立原生见证和两次独立实际复用，发布 `file-v6`，42 项运行源码锁全部匹配；相对 v5 保留相同四组 nodes/bindings。认证合计 71 请求、代理估费 0.048023997 美元，实付未知。PR92 未改变这 42 项 File 源码，因此不重复购买相同认证。
- 冷消费者一：没有历史私有经验的账号仅从公开 v6 安装 4 项。三文本任务严格交付/生命周期/完整用量通过，6 请求、代理估费 0.005374152 美元，实际 skip=0。模型在 pin_files 后插入 select_files，使已启动的两节点读取链按 changed_or_failed_operation_result 拒绝并回到普通 Harness；这是保留的真实不命中反例，不是发布证明失效，也不算节省。
- 最初冷档案配置的非日常 profile 不符合现有 enabled() 的准入条件，在线经验未启用，断言在模型调用前拒绝；随后使用真实账号产品相同的 daily-management-real-v3 profile，保留原错误/空池。没有修改 enabled() 或放宽在线守卫。
- 首次全量在 v6 生成前开始，1408 Python 通过/3 跳过，3 项因新库尚不存在失败；生成后同版本最终全量另行保存。PR92 接入后再定向通过 71 Python/112 Node，覆盖主线阅读索引、图片原始身份、多轮/取消、PPT 学习与 File 当前种子。最终 CI 和进一步消费者结果完成后补录。
- 不声称任意自然语言目标、完整 PPT 制作或科学质量无损，不以合成认证或局部 skip 推导实际业务净收益。上线账号/浏览器/完整独立业务任务尚未在本集成版本重新验收。正式发布仍须通过统一 `npm run service` 入口，本次不部署或清空旧数据。
