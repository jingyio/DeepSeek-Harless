# 科研 PPT 当前交接

- 更新时间与交接人：2026-10-13，Codex。
- 目标与本次范围：以本地V17整理待发布分支，按已有经验统一稳定运行参数；保留main前端/公共内核、必要PPT代码、维护回归和历轮报告。不新增付费实验，不宣称网页已接通。
- 分支 / commit / 工作区：独立准备树 research-ppt-v17-release，HEAD为main 856c02cf29ca0be630dd4fec7f2ab6deecbf27a8，已no-commit合入远端feature/research-ppt-agent 34ca217；尚未commit/push，无PR。V17来自research-ppt-reports-v14树e452983加未提交改动；两原工作区不覆盖。
- 已完成：V16受控baseline_steps/host_delivery、持久资料/组件库、反馈绑定与独立候选接口；V17 ts/pending-plan.ts/plan-recovery.ts局部草稿恢复，严格运行时校验与最终adapter/host/文件三层交付取证。脚本/缓存/局部恢复属于普通工程，不算新RSI。
- 参数：1–8份PDF/PPTX，每份100 MiB、1–30页、说明10000字符；单路60步骤/8000输出/$1.50上限，双路总$3。思考/压缩off，默认不生成新工具；host最多8patch/6恢复渲染。MCP外层300秒/内层240秒；ZIP150 MiB展开、单图8 MiB及原权限/来源/版本检查保留。main通用Web参数未改。
- 最短入口：安装按根README与scenarios/research_ppt/deploy-ubuntu18.md，激活服务器环境后构建。npm run ppt -- --input .local/inputs/paper.pdf --slides 15 --template lab --allow-output 默认仅预览；确认后 npm run ppt -- --trial <实际trial.json> --call-model。已有JSON/MCP接口，无新HTTP服务。
- 清理：沿用main已移除的8个旧矩阵/报告脚本，不重新引入。必要真实MCP smoke、安全失败、版本失效、恢复与费用回归保留。20份历史PDF及V1–V17计划/报告/失败/匿名摘要保留；私人论文/成品/原始日志留.local和server test-logs，未清空或公开。清理说明见docs/research-ppt-release-cleanup.md。
- 已验证（历史）：服务器V17真实trial-20261013T133803Z-706a7c89，两份同源15页机械交付，普通32请求/1,799,740token/$0.0880055，host28请求/1,283,476token/$0.0418032；质量未人评，不支持合格端到端降本或RSI收益。allow_rsi=false，verified旁路0。回执校正55项服务器回归通过；旧失败/原账本不覆盖。
- 本次验证：独立服务器副本根151Python/53Node、场景94Node及286Python通过，1字体夹具缺失跳过后显式用已有字体补验5项全过；根smoke两套各9例、真实MCP/LibreOffice交付/修订/重启及局部恢复通过。首交付诊断位置推断只读误报，逐项集合核验修复后新目录通过，旧失败保留。371运行文件与本机SHA/size一致，28证据文件下载核验；记录docs/experiments/research-ppt-v17-release-preparation-20261013.md。未复跑付费模型、改旧快照或重签证书。
- 实验结论：V16科学失败、优化成本上升等负面结果仍保留；V17观察到普通工程恢复的请求/token/代理费下降，质量待评审。报告索引docs/experiments/research-ppt-reports/README.md；代理估费不是账单实付，真人修订/维护/计算未知。
- 配置与数据：公共schema/配置/锁在scenarios/research_ppt/；DEEPSEEK_API_KEY/DEEPSEEK_BASE_URL私有不展示。资料库默认保留、解析缓存off，可信后端提供身份。V17成品本机H:/DeepSeekHarness/.local/research-ppt/research-ppt-v17-local-recovery-20261013/review/{baseline,optimized}/。准备manifest和日志在本机.local/research-ppt/v17-release-preparation-20261013/。
- 未完成与阻塞：main网页仍缺任务级job/流式上传回执映射、PPT参数契约、真实交付完成/鉴权下载、反馈与paired展示。不能只登记静态PPT场景：SSS_PPT_JOB是每任务独立的必需输入。多用户认证、任意外部PPT无损精细修改、Windows完整渲染未验收；无本轮新候选晋级。
- 接手下一步：1）前端同伴按frontend-integration.md接TypeScript任务生命周期，复用trial/固定MCP及预算代理；2）上传/下载贯穿真实身份并核SHA，补契约/权限/取消失败回归；3）用户查看V17两份结果并通知后，先告知中文commit范围，再推feature/research-ppt-agent，不开PR。
- 权限与预算：整理、可逆修改和免费检查已授权；本次付费API支出0。既有真实API授权不代替上传条件：用户明确要求看完完整真实测试成品并通知后才能提交/推送，本次尚未收到放行。
- 回退与风险：发布树为main加V17独立副本，两原工作区与所有私有证据保留。参数/代码摘要改变只用于新job；不能恢复旧证书/旧checkpoint后当作同版本。解析成功不保证规划或渲染成功；机械交付不认证科学/审美。
