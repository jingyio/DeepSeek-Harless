# GeneLoop 的 ppt-master 场景

网页版 `/ppt` 使用官方 ppt-master 6.6.0，原 `research_ppt` CLI、工具和库保留用于历史复现及回滚。上游为 [hugohe3/ppt-master](https://github.com/hugohe3/ppt-master)，MIT，Copyright (c) 2025–2026 Hugo He。此目录是集成适配，不是上游技能的复制品；不修改其归属文件、工作流或检查器。

`skill-lock.json` 冻结完整安装的 13,016 个文件。用已经下载的对应官方分发执行：

```sh
python scripts/install-ppt-master.py --source /path/to/ppt-master --destination /fixed/public/ppt-master-6.6.0
export GENELOOP_PPT_MASTER_ROOT=/fixed/public/ppt-master-6.6.0
```

安装器逐字节核验、不覆盖现有目录。Python 依赖按该安装的 `requirements.txt` 安装在隔离运行环境。账号网关 `memberSceneDeployment.pptMasterRoot` 指向同一安装；MCP 和 Bash 都只读挂载为 `/opt/geneloop/ppt-master`。账号网关既有 `rendererRoot`、`fontRoot` 同时提供给命令沙箱，源附件仍只读，输出仍按会话隔离。包缺失、字节变化、工具环境未就绪时明确拒绝，不回退旧生成器冒充新技能。

两种模式使用同一模型、提示、技能、普通环境准备和工具集合。模型读取入口，官方 attribution guard 成功后读取 routing，再自行按选定路由规划、编写 SVG、核对来源、检查、修复和导出。用户明确委托自主设计时使用上游 explicit delegation 分支；否则保留确认门禁。既有公共 Bash、搜索、网页读取和后台任务继续可用。

`read_skill_entry` 合并读取官方入口、运行归属检查和读取路由，并列出当前上传件，这是普通脚本优化。最初的固定技能句柄候选因“常量不能证明参数流”被编译器拒绝，没有发布。

Motif 候选只学习真实工具轨迹中可验证的 `pin_source → read_source_page`：模型选择上传 PDF 并绑定其版本，自动续接只能读取同一文件的默认首页，以核对标题和摘要。后续页、全文转换、事实判断仍由模型决定。这不是写死的制作 DAG，也不是模型权重训练。候选图、支持证据和独立认证由现有 witnessed-edge 编译器产生，未观察到符合证据的结构就不发布库。工具没有 PPT 内容或布局生成脚本。

额外 HTTP 预览服务在该命令沙箱中不可持续，按上游允许的运行环境分支关闭；保留全部真实文件渲染、检查和下载预览。会话独立的 `/tmp` 在命令间保留转换器和检查器的中间文件，不能读取其他会话或宿主临时目录。两侧共用这些普通环境优化，不把它们计为 Motif 学习收益。

```sh
python scripts/learn-ppt-master-motif.py --dataset .local/experiment/dataset.json --out .local/experiment/compiled --publish motif-libraries/ppt-master-v1
```

数据集恰好两个独立训练决定、一个独立认证决定，使用真实 GeneLoop Baseline 的原始事件、实际完整工具 schema、任务身份和逐请求费用账本。最终评测不参与编译。公开库只保存匿名证据摘要与版本锁；原始来源、轨迹、凭证和成品留在私有 `.local/`。

仅在实际拦截请求且返回值与版本核验成功后，才记 `verified_skips`。它不等同于最终成品合格或总费用下降；两侧完整用量、缓存命中/未命中、输出、重试、时间与质量需要独立比较。旧库 `ppt-web-v2-r13` 不在新工具表上执行。
