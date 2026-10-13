# Harless 四场景上线准备（2026-10-14）

## 问题、范围与配置

验证原生菜单的下一任务是否加载真实场景、冻结正确策略，以及成员是否共享同一公共能力而仍隔离资料。错误的工具/Prompt、跨账号访问、确认后参数漂移或未认证跳过都否定这一闭环。不是科研质量或同质量降本实验。

分支 `codex/harless-launch-readiness-20261014`，基于桥接 PR #8，整合 main `6ade286`（PR #9/#10）；功能/协议最终验证代码 `396e2cf`。不修改上游 Harness、账号密码或 Session 归属恢复；原论文工作区不覆盖。新配置引用路径均由服务器登记，不接收前端主机路径/命令。

环境为 V100 Ubuntu 18.04.6，Node22.23.3、Python3.10.21、DSH0.1.5-rc.3、SDK0.1.5rc1；Python虚拟环境继承既有隔离依赖。服务器新独立检出私有 ID `harless-launch-20261014`，本机也使用独立 worktree。固定 DeepSeek Flash、reasoning off、压缩关闭、单次输出1000；旧失败、重试、请求与估费持续累计，不借论文不限额授权扩张公共Web预算。GLM及公网浏览器本轮未验收。

真实运行有效配置、逐次请求/用量、原始审计与结果在该检出的 `.local/web/runs/<RUN_ID>/`；菜单/场景诊断在 `.local/harless-scenes/`。它们不进Git。四场景公共配置在 `config/harless-scenes.json`，工具顺序、Schema/Prompt/Scope及代码摘要写入每任务 `effective-config.json`。账单实付、人工修改时间和维护成本未测量，不填零。

## 实际接通与认证边界

| 场景 | 实际能力 | 当前 RSI 范围 |
| --- | --- | --- |
| PPT | 既有19工具、批准PDF/PPTX、读取、原生PPT生成/修订新副本、真实PDF/PNG验收；菜单页数/模板/输出权限 | 迁移认证库仅接管闭合pin/read；生成/科学选择仍交模型 |
| Paper Proofreading | 5只读工具、PDF/文本、平铺LaTeX引用/标签/浮动体及已有日志检查 | 无生产认证库；Execute On拒绝 |
| Research Data Analysis | 4只读工具、UTF-8 CSV/TSV描述统计/空白缺失/完整对Pearson相关 | 无生产认证库；Execute On拒绝 |
| New Scene | 本Session批准文本的list/read和普通Harness | 无生产认证库；Execute On拒绝 |

论文静态检查函数逐项复用 `feature/paper-submission@9479edf`，没有修改该协作者工作区；本轮不编译LaTeX、不核实外网参考文献、不改原稿。数据分析不执行任意代码、不插补、不作显著性/因果推断。成员沿用已有bwrap/预算broker，仅部署只读公共代码和依赖；输入/Session/配置/轨迹/输出仍分别归属账号。

旧PPT库取回详情在 [迁移记录](ppt-library-transfer-20261014-v1.md)。从原始独立正常轨迹2训练/1留出与真实完整19工具Schema，使用既有Python编译器得一个结构Motif；不修改旧证据。私有 `.local/ppt-rsi-migration-20261014/derived-v1/compilation/` 留存证据。工具/来源ID只从当前任务实际pin绑定，task_id/session_id/批准SHA逐任务冻结，无旧题面/句柄复用。

当前 `deployment-v3/runtime` 五文件用于成员只读加载。IR摘要 `e6d44bca71238206bead4056f2c704de6be4218de233a23efe43f8d45f8cf518`；完整有序Schema SHA `4ce03ae6722ffc63e3a9fa6de48ca1075615abae2813ca12b52da7951f5f93c5`；认证文件 SHA `565b931c51e144e6eb8578e7a1242b70ab91cfcd6462e4926b4ff9cb2c0a45aa`。认证为 `independent_trace_structure/structural_only/ppt_uploaded_sources_v1`，`quality_cost_promoted=false`。部署v2/v3在服务及checkpoint修改后由未变化的有效认证IR生成新代码绑定，旧包保留；没有重新签署旧实验结果。语义排名明确禁用并回退LLM，未用固定向量冒充embedding。

## 真实模型运行（合成输入，不是研究前瞻）

| Run / Task | 状态 | HTTP请求 / MCP / 错误 | 实际Verified Skip | 代理估费美元 / 耗时 |
| --- | --- | --- | --- | --- |
| `f835652d0b244a559a63aff471546de8` / `0015d069f5df4520b87ff8e790f8b2b5`（论文） | completed | 4 / 3 / 0 | 0 | 0.002039520 / 9.682秒 |
| 同Run / `f6b56a1ce0fa4bcdbcd4921571afe140`（数据） | completed | 4 / 3 / 0 | 0 | 0.001370352 / 6.246秒 |
| `91614ee307ed434f99973ca9bd3f55bf` / `63ab7d5354684979bc6db9e6ec1f366f`（PPT Execute） | budget_exhausted，空最终回答 | 1 / 3 / 0 | 1，失败任务的局部批次 | 0.002117100 / 1.984秒 |
| `000ff19ad5e644c8a1824222fba20b01` / `3d6f196b7c0e4117bad1df2616b2fd7b`（PPT Execute） | completed | 2 / 3 / 0 | 1 | 0.002688204 / 4.136秒 |

论文/数据代码 `a40d178`，Shadow无库、每任务/启动0.03美元与10请求。输入分别为语法错误合成文本、四行含空白CSV。输入/回答未作独立质量盲评。

PPT真实代码 `a7d3a44`、部署v1、只读一页合成PDF；每任务/启动2请求，首次0.01美元cap导致下一请求的保守预留被拒绝（实际已花金额低于cap不代表足够预留下一请求），失败费用继续计入。第二次显式诊断cap0.02美元，3模型决策中1结构接管、2实际HTTP。没有降低预算守卫、固定Provider回复或假命中。最终v3的实际工具/共享Runtime协议另用零云调用诊断验证，未把它记成再次真实模型验收。

本轮新增11真实请求、代理估费0.008215176美元；加上先前桥接14请求/0.006474720美元，**累计25请求/0.014689896美元**，账单实付未知。诊断次数的自设上限从24调整到25已告知用户，累计0.06美元额度未扩大。首次私有.env未挂载的启动失败为0请求，保留失败日志。完成任务的1次实际skip与失败任务的1次局部skip分列，不能把它们当作两个成功任务、固定比例节省或稳定降本。

## 免费诊断、实际产物与失败修复

- `npm test`：本机与V100分别183 Python/79 Node通过，含SDK、预算、网关、版本/来源/Schema守卫与模式回归；无付费模型。
- `npm run smoke`：18诊断题/83来源、SDK初始化/MCP通过，0付费。
- `npm run web:controls:check`：原生菜单协议、既有example/portfolio历史诊断通过；模拟Provider，不是科研/费用效果。
- `npm run web:scenes:check`：最终Run `61954210661e45ac8f2791f121cc2704`，四场景×三模式×RSI开关24组合；21组合实际创建冻结草稿并在同场景切模式后核对原摘要不变，3无库Execute On明确拒绝。另核对四真实MCP/Prompt/上传、连续不同场景及两principal对Task/Session/receipt拒绝，0模型。
- `npm --prefix scenarios/research_ppt test`：构建及53 Node通过；场景Python全量212通过/1跳过/1警告（207.76秒）。跳过项是未配置测试变量的静态Noto正例；指定已安装 `SSS_TEST_CJK_FONT` 后 `test_rendered_glyphs.py` 5项均通过，保留原全量结果。
- `check-harless-members.py --render-ppt`：Run `3ad0d379585c402cbec776567413dd8f`，两临时账号/8四场景草稿、实际bwrap/MCP、跨账号Task/Session拒绝；在各自实际挂载内独立生成一页PPTX/PDF/PNG，两个交付均通过且退出后文件存在。0云模型，显式合成计划，不是模型自主生成或科学质量验收。诊断不使用生产账号库。
- `check-ppt-runtime.mjs`：实际pin/read，Shadow只审计/继续原LLM入口，Execute实际MCP结果核验后确认一个结构批次；机械生成中文PPT/PDF/PNG通过，预览已目视检查文字完整/无明显溢出，仅一页合成例，不作审美认证。

LibreOffice首次在V100启用OpenCL后退出134，保留失败报告；相同PPT的CPU转换成功。最终转换子进程限定 `SAL_DISABLE_OPENCL=1/SAL_USE_VCLPLUGIN=svp`，不更改全局环境。该开关存在于 [LibreOffice7.6源码](https://github.com/LibreOffice/core/blob/libreoffice-7.6.7.2/opencl/source/openclwrapper.cxx)。随后发现新任务内验收目录被旧checkpoint全局路径守卫拒绝，修复为当前job或历史CLI根；真实回归仍拒绝其他任务与软链接越界，完整工具交付重新通过。

固定私有安装为 [LibreOffice官方7.6.7.2](https://downloadarchive.documentfoundation.org/libreoffice/old/7.6.7.2/deb/x86_64/LibreOffice_7.6.7.2_Linux_x86-64_deb.tar.gz)（归档SHA `5fbd379bd9cedb037fa00b6e7e830619bff503a9451bc321e2b4e8d646081920`）及 [Noto CJK Sans2.004](https://github.com/notofonts/noto-cjk/releases/tag/Sans2.004) 固定简体OTF（SHA `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b`）。旧Ubuntu22系统安装没有直接复制到V100；新安装/字体只部署私有依赖目录并只读挂载，不改系统包。

## 复现、交付与限制

加载既有服务器隔离环境及 `.env`，安装根/场景固定依赖并构建，配置三个 `HARLESS_PPT_*` 环境变量；运行上列免费入口和 `npm run web:scenes:check`。真实入口为 `npm run web:scenes:check -- --real-model --scenes paper-proofreading research-data-analysis` 或 `--scenes ppt --mode execute`，再次运行必须先核对累计预算，不能将每次启动新cap当新增授权。

配置与协议见 [控制文档](../harless-controls.md)、[接口](../interfaces.md)、[成员部署](../harless-account-gateway.md)。当前是独立检出的测试与PR交付，**未切换公网生产网关**；旧Session问题由另一协作者处理。本轮未做全任务PPT模型生成、论文编译投稿、GLM行为、浏览器点击或两真实成员模型并发验收。未做配对baseline，不支持稳定净费用收益；结构认证也不是科研正确性认证。上线后先用真实研究任务独立人评，再扩展库。

回退保留既有公网进程、私有账户库与累计账本；可撤回新部署字段恢复明确chat-only，或RSI Off回Origin。不能为了回退清空用户tasks/Session/.local。代码/工具/来源变化要新配置/新部署包，失效旧包不能改哈希绕过。私有旧库及本轮PPT交付/检查日志均已保留服务器和本机备份。
