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
- File 模型为真实 `deepseek-flash`、`reasoning_effort=off`，本轮未显式启用压缩，SDK 压缩默认值未单独采集；新增实验封套 1 美元，每任务 0.05 美元、48 步、3000 输出、0 修复。私有 `rsi` 配置、源码冻结、题面、输入、schema、认证回执及逐请求费用由原 runner 保存。旧 PR84 费用记录继续保留，本次费用另列并关联，不重置旧账本。
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
- 首次全量在 v6 生成前开始，1408 Python 通过/3 跳过，3 项因新库尚不存在失败；生成后同版本最终全量另行保存。PR92 接入后再定向通过 71 Python/112 Node，覆盖主线阅读索引、图片原始身份、多轮/取消、PPT 学习与 File 当前种子。最终 CI 与全量结果完成后补录。
- 不声称任意自然语言目标、完整 PPT 制作或科学质量无损，不以合成认证或局部 skip 推导实际业务净收益。上线账号/浏览器/完整独立业务任务尚未在本集成版本重新验收。正式发布仍须通过统一 `npm run service` 入口，本次不部署或清空旧数据。


## 公开种子消费者补充（2026-10-20）

- 第二项为预先限定的单文件读取诊断，未指定工具路线，沿用第一项的同一账号 registry/pool 与费用，只给新任务追加独立测试副本根；原任务、配置与结果不改。没有私有学习记录、auto_worker 关闭、learning_eligible=false，不能把它计入训练。
- 单文件任务真实 5 请求，3 次 verified skip，严格交付/生命周期/用量完整均通过，0修复、无 deferred，估费0.003739633美元。三文件的0skip反例仍保留，不能用新成功替换旧分母。
- 认证12项 + 消费者2项，共14个真实任务、82个实际请求，新增代理估费合计0.057137782美元，未核对供应商账单；全部初始失败/恢复及未结算状态仍保留。人工/开发/CPU/维护时间未计价，不支持净收益结论。
- 认证与消费者在 PR92 之前完成，PR92 合入后逐项核验 File 的全部42个运行源码原始字节未变，因此本证据仍限定于这些相同 File 执行代码；主线附件阅读新能力另由其本轮回归验证，不混称为新的付费附件验收。


## 最终 Linux 全量与用量（2026-10-20）

- PR92 主线 `31c7309` 共同集成后的源码 `6603d7d`，使用前述隔离 Python/Node 和已安装 OCR/PDF 资源执行 `npm test`：**1415 Python 通过/3 跳过；1073 Node 通过/3 跳过，0失败**。其中 Node 共1076项；跳过项按现有平台/环境条件保留，不能视为功能通过。PR92 之前集成版为1411 Python/1067 Node通过，各3跳过；不把两次套件数量相加作为覆盖收益。
- 原始供应商用量回执共82次 HTTP200、0 provider_retry；输入556733 token，其中缓存命中480512、未命中76221，输出26157，总582890，reasoningTokens=0。代理估费0.057137782美元，供应商实付仍未知；14项任务的 elapsed_seconds 总和393.239秒，这是任务耗时相加，不是整个开发/维护端到端耗时。
- 同一最终隔离副本的 `npm run smoke`、`npm run motif:check` 均通过；`npm test` 内的 continuation 构建产物核对通过，以上均无付费模型请求。
- 三个最终库的全部源码锁均匹配。与 main PR92 对比，`harless_attachment_context.ts`、`harless_attachment_reading.ts`、服务生命周期及其原生图片回归文件保持不变；main 已发布的 v16/v11 和 PR84 的 v5 字节保留。
- 私有元数据及正反消费者摘要已回传本地 worktree `.local/pr84-88-integration-results/`，包括 `effective-snapshot-reviewed.json`、`accounting-summary.json`、认证摘要与两份消费者摘要；原始任务/轨迹/费用账本留在服务器原私有目录，不上传凭证或 SDK 凭证存储。
- 验证提交 `3c3636085236288b645170796bf9dffa57b32369` 的 push/PR 两组 Ubuntu/Windows 四项 CI 均通过：[push运行](https://github.com/jingyio/GeneLoop/actions/runs/39288942171)、[PR运行](https://github.com/jingyio/GeneLoop/actions/runs/39288950689)。本条仅补文档，执行源码/配置/库/测试与验证提交一致；之后的最新 head 检查仍以 PR93 为准。未合并、未部署；合并前须核对最新主线，不把离线 CI 扩大为 Windows/Linux 真实账号浏览器验收。
