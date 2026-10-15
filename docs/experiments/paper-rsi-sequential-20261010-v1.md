# 论文参数 Motif 的顺序学习闭环

- 日期/执行者：2026-10-10，Codex；分支 `feature/paper-submission`，本次修改未提交、未推送。
- 问题：能否将新正常轨迹编译成可追溯的下一版库，让下一任务实际加载该版本，而不是反复测试冻结库。
- 范围：参数原型版本链和 Crossref 查询接入。没有实现完整论文修订脚本挖掘或生产认证。
- 否定条件：当前任务使用运行中更新的库、验证会话泄漏到训练、历史被覆盖、Runtime 自证，或新增原型只有数量而没有正常轨迹来源。
- 类型：五条历史原生会话的回顾性划分，加两次真实 shadow。同一论文/阶段的重复会话，不是独立论文任务流或学习收益曲线。

## 实现与版本

新增 `src/adapters/parameter_learning.py` 和 `scripts/paper-motif-learn.py`：正常 baseline/shadow 的 completed 轨迹、manifest、metrics、事件和可选版本快照逐项固定摘要；拒绝重复会话、execute 或 synthetic 调用自证。验证会话永久保留，不能在后续移入训练；验证观察不决定原型种类。父版本链、当前库与输入证据都核验，版本不可覆盖，原子更新 latest。

`parameter_motif_compiler.py` 新增显式训练/验证输入入口；旧五条输入包装器重编译结果与冻结库逐对象一致，manifest digest 仍为 `e1419f52521389a6d1e63231989af2dbbae221bbfd9b1e8cd2c422e16ec7ab5e`。新入口采用更严格的网络状态/身份守卫，旧实验不追改。

论文入口新增 `--learning-store` / `--learn-after` / `--input-zip`。当前任务固定每运行的 `library-snapshot.json`；结束后才编译下一版。输入 ZIP 限私有 `.local/`，准备器仍假定 `main.tex` / `references.bib`，不宣称通用 TeX 支持。学习库 scope 为 `parameterized_continuation_probe`，`production_activation=false`，不能默认进入 Web/生产。

私有根：`.local/paper-reference/paper-rsi-sequential-20261010-v1/`。历史 baseline-01/02 首先训练，baseline-04/05 永久验证，再追加 baseline-03；这些划分仅演示管线，没有把两条同输入会话称为独立任务认证。

| 版本 | 累计训练会话 | 永久验证会话 | 原型数量 | 本轮新增 |
|---|---:|---:|---:|---|
| round-0001 | 2 | 2 | 1 | 完整本地读取 |
| round-0002 | 3 | 2 | 6 | arXiv 获取、4 种 Crossref 查询模板 |
| round-0003 | 4 | 2 | 6 | 无新增类型，追加第一轮正常 shadow 见证 |
| round-0004 | 5 | 2 | 7 | 新正常 shadow 中一种 Crossref 模板 |

round-0002 库摘要为 `a4008d50c54e05f280fa1744b84d8b7f4f44637fbfa20f10da18fe25ce7bb3ad`；round-0003 为 `482d7102390b0fcce64b91a2d77c71e996384bd2a86bda8a04b6ee99a89604ed`；round-0004 为 `3e0d9ef7260cb321aab24fc75aaf1d066330842e021b6d9364cffe4aa5f137db`，最后一版库字节 SHA256 为 `e0bb633ae6c4e225f8a8e68ece9d7a9c8f5ceebea93cb373ecd82ec4ff68e241`。完整父摘要、新会话与代码摘要在各 `round.json`。

## 新节点及其边界

Crossref 原型从正常 `web_fetch` 的实际请求与成功结构结果提取，不手写论文查询 DAG。只允许固定 `/works` 端点、完整标题槽、rows 1–5、含 DOI/title 的已知 select 字段和原顺序。模型选择目录中的查询项；Runtime 冻结来源哈希，核对字面标题、URL、HTTP 200、JSON `status/items` 和 DOI/title 形状。空 items 是查询未命中，不证明没有正式版。候选是否对应论文、出版版本和修复等级仍由模型判断。

第四版新增 `parameter-2bacec0ead51`，有两个正常工具见证、没有验证集见证：

```json
{
  "tool": "web_fetch",
  "contract": "crossref-search-fetch-v1",
  "read_only": true,
  "arguments": {
    "url": {
      "base": "https://api.crossref.org/works",
      "query": [
        {"name": "query.bibliographic", "slot": "query"},
        {"name": "rows", "value": "5"},
        {"name": "select", "value": "DOI,title,container-title,issued,author,type"}
      ]
    }
  }
}
```

原型增加说明编译器吸收了新结构，不说明独立验证、语义正确性或收益增加。第四版读取原型有 2 训练/4 验证观察，arXiv 有 47 训练/0 验证观察，5 种 Crossref 模板都无验证观察。

对 baseline-03 的 Crossref 搜索端点诊断：23 次调用中 20 次 HTTP 200、3 次 tool error；4 次满足当时窄契约，16 次的 rows/select 等参数不受支持。其他直接 DOI 请求不包含在这个计数中。没有为了提高数字放开任意参数或取消结果守卫。

## 有效配置与复现

服务器 `/root/autodl-tmp/jjy`，加载 `.local/remote-env.sh`，Node 22.23.3、Python 3.10.8、Harness 0.1.5-rc.3、SDK 0.1.5rc1；真实 DeepSeek 官方 `deepseek-flash`，推理 off，输出 8192，无请求次数上限，压缩关闭。两轮 shadow 保留原生执行；私人副本 danger-full-access 授权沿用，原件不改、上游不改、不启动子 Agent、不重启 Web。

`manifest.json` 记录真实提示/输入/目录/schema/工具顺序、每运行库快照、配置 patch、代码 commit/dirty 和实现摘要；`round.json` 记录编译/学习代码与训练/验证证据摘要。实际代码版本以这些快照为准，不把本地未提交状态称为已同步 main。

```sh
source .local/remote-env.sh
# 已完成，不可重复使用同名 suffix 或覆盖旧运行。
node scripts/project.mjs python scripts/paper-reference-continuation.py \
  --learning-store .local/paper-reference/paper-rsi-sequential-20261010-v1 \
  --learn-after --mode shadow --suffix=-round-2-shadow --call-model
node scripts/project.mjs python scripts/paper-reference-continuation.py \
  --learning-store .local/paper-reference/paper-rsi-sequential-20261010-v1 \
  --learn-after --mode shadow --suffix=-round-3-shadow --call-model
# 不加 --train-run 时，仅查看当前库，无 API。
node scripts/project.mjs python scripts/paper-motif-learn.py \
  --store .local/paper-reference/paper-rsi-sequential-20261010-v1
```

首次训练命令及顺序验收见 `docs/paper-rsi-loop.md`。离线发布未调用模型，编译 CPU/人工开发时间未单独测量。新 Crossref 目录和协议改变了提示，不能与旧冻结库实验直接作同条件成本归因。

## 两次真实结果与失败

| 使用库 / 运行 suffix | 实际请求 | 选定结果 / 验证通过 | 完整纯工具请求机会 | 代理新增 USD | 运行秒 | 下一版 |
|---|---:|---:|---:|---:|---:|---|
| round-0002 / round-2-shadow | 25 | 38 / 30 | 3（12.0%） | 0.055552 | 98.34 | round-0003 |
| round-0003 / round-3-shadow | 34 | 23 / 1 | 0 | 0.064826 | 416.10 | round-0004 |

两轮实际跳过都是 0，反事实费用节省未知。第一轮 5 批中读取/arXiv 的 4 批结果齐全，3 次完整纯工具机会、1 次含文本需审阅；Crossref 的 8 项没有在请求边界形成候选。原因是 BibTeX 内部花括号分组被归一化成空格，将一个词拆开，原文与查询被误判不一致。修正后只接受真实 title 字段，移除分组而不拆词，含 TeX 命令的标题仍不自动解释；第一轮失败原始审计和评估保留。

第二轮使用修正后的 Runtime，Crossref 批次已通过标题守卫并在请求前形成候选，但只有一项实际调用严格对应选定标题与模板。模型后续改写查询标题、rows/select，并改用其他来源；读取条目也大量改用 bash（本轮 read 3 次、bash 16 次）。3 个选定批次的下一响应全部为混合或不同动作，故没有整请求机会。守卫没有把新意图或不同方法强行算进旧批次。当前额外 selection 文件协议与原生执行的协作不稳定，是需要改进的工程接缝；修改 Runtime 标题守卫并没有让机会率提高。

两轮 `triage.json` 的原始 key/arXiv 集合均为 15/15，无额外/重复，目录中冻结来源的最终哈希均未变化。引用问题分别记录 4/7 项，语义判断、版本关系、风险等级未盲评，人工修订时间未知；不是完整用户 PDF 检查报告。不能称为合格成本对照。

两次新增代理估费合计约 0.120378 美元；含历史失败与预留累计约 4.415383，原冻结累计封顶 4.84521046，余额上界约 0.429827。两轮均正常完成，没有通过新建任务或重置账本提高额度；账单实付仍未知。

## 诊断验证与结论

本地、服务器最终 `npm test` 均为 **195 Python / 88 Node** 通过；覆盖版本链/证据篡改、会话与验证集隔离、失败元数据、标题来源、URL 转义与跨语言一致性、网络错误及结果汇合。分析器新增 U+2028/U+2029 JSONL 检查：合法 JSON 字符不当作记录边界。服务器 `npm run smoke` 的 18 题/83 来源通过、SDK 初始化、付费请求 0；预期的未 pin 句柄拒绝保留。这些诊断不代替真实效果。

原始证据、四版库和派生分析已同步两端私有目录；归档排除 Harness 凭证目录，压缩包 SHA256 为 `f52a655d109f5bd4d1e094ec18c1a082323ed8c24011307e2e4104e10300cef8`。源数据和两轮旧评估未覆盖；共享文档只同步本次学习段落，保留两端 Web 同学的版本差异。

在这些条件下支持：参数原型可以逐批从新正常轨迹增长，任务固定当前库、完成后发布下一版的链条可运行。**不支持**：完整脚本 RSI 已实现、调用随学习下降、跨论文泛化、Crossref 独立认证或稳定达到 20%。本次 25→34 不能解释为学习收益；模板数量增长不能替代有效覆盖。

下一步优先编译正常轨迹中的受限解析/归并脚本，显式参数、输出、版本和副作用；把选择绑定合并进必要语义决策，支持模型变更查询意图时重新绑定；再在新稿/新论文上冻结新版做 shadow。质量与范围锁定后才比较 execute、原生 Harness 和合理脚本/Code Mode 的净请求与累计成本。本轮不继续付费重复同一任务以凑比例。
