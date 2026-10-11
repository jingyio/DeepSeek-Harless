# 服务器 Python 3.10 免费运行验收

- 实验 ID：`server-python310-free-loop-20261009-v1`；日期：2026-10-09；执行人：Codex，用户授权准备服务器环境并运行免费闭环。
- 问题与假设：现有 Python 3.10.8 能否支持 SSS 开发底座，而无需先升级到 3.12。固定依赖安装失败、测试失败或 Harness/MCP/Motif 链路失败均不能算验收通过。
- 类型与对照：离线协议检查、公开合成科研夹具与脚本模拟 Provider；不是前瞻科研任务，也不是同题费用或 Python 版本效果对照。已有 library 的训练/认证划分与来源不变，见 `examples/motif-library/research-portfolio-v1/provenance.json`。

## 配置与复现

- 代码：`main`，`2368235f274329be6227a8393b850633cb943da4`；运行前有 `AGENTS.md`、`README.md`、`docs/handoffs/main.md` 三份文档改动，未提交。195 个受控文件与本地 SHA-256 一致；没有改动运行源码或上游 Harness。
- 系统：Ubuntu 22.04.1 LTS，Linux 5.4 x86_64，glibc 2.35；Node 22.23.3，npm 10.9.9，Python 3.10.8。
- 安装：Node 官方归档经 SHA-256 校验，位于 `.local/toolchains/`；Python 在 `.venv-sss/`。`npm ci --no-audit --no-fund` 安装锁定依赖；Python 按 `requirements.txt` 安装，`pip check` 通过。SDK 0.1.5rc1、MCP 2.2.0、Pydantic 2.13.5、pytest 8.4.2；全部传递依赖的实际版本保存在配置快照，本次没有新增公共传递依赖锁。
- 私有记录：两端 `.local/experiments/server-python310-free-loop-20261009-v1/`，含 `configuration.json`、`results.json`、源码哈希清单、安装及检查日志。SSH 密码与模型密钥未写入记录或仓库。
- 配置快照 SHA-256：`c42f28c9cb2a08b1d878b4bebf54bef0b1120a8bb850ce4f23898c7d41d61459`；结果 SHA-256：`cbb19c206258a039825d3e2404d3b0cb918e32ba0558c65293ae10fe0665416c`。后续文档更新不追改运行前快照。
- 场景、题面、来源、契约、工具顺序及 library/manifest 哈希由快照记录；模型名为 `deepseek-flash`，请求实际指向服务器回环脚本。`reasoning_effort="off"`，固定向量 embedding，阈值 0.8/0.1，每组 Provider 最多 24 次请求，输出上限 1000 token，无显式 Agent 步数参数。通用场景预览预算为 0.25 美元、16 步、3000 token，但 `model_call_enabled=false`，未执行付费入口。

在已配置服务器的项目目录复现：

```sh
source .local/remote-env.sh
npm test
npm run smoke
npm run motif:check
npm run scenario
```

环境入口由本次部署生成，只用于已配置服务器；新机器仍需安装 Node 和 Python 依赖。以上不读取真实论文、不执行实际投稿，也不调用云模型。

## 结果与质量

| 检查 | 结果 | 服务器耗时 |
| --- | --- | --- |
| `npm test` | 136 项 Python、29 项 Node 通过 | 20.813 秒 |
| `npm run smoke` | 18 题、83 来源对象通过，SDK 初始化成功 | 30.493 秒 |
| `npm run motif:check` | 4 个 Motif 重编译一致，46 次公开工具证据重放通过，四组 Harness 验收通过 | 20.235 秒 |
| `npm run scenario` | 预览成功，模型调用关闭 | 0.568 秒 |

Smoke 中未知 `source_id` 的拒绝消息属于预期安全检查，最终退出码为 0。

| 模拟组别 | 回环 Provider 请求 | 工具调用 | 结果验证的跳过批次 | embedding 请求 |
| --- | --- | --- | --- | --- |
| baseline | 14 | 13 | 0 | 0 |
| shadow | 14 | 13 | 0 | 9 |
| execute | 7 | 13 | 5 | 5 |
| execute，旧版本 | 14 | 13 | 0 | 0 |

四组返回相同来源对象和版本清单；旧版本拒绝复用并恢复语义路径。以上是结构及协议验收，不是语义匹配质量评测。真实论文交付质量未评审；没有人工盲评或论文修订时间数据。

## 成本、恢复与边界

- 付费云 API 请求为 0，新增模型费用为 0；回环请求不可当作云模型费用或降本结果。真实云缓存命中/未命中 token、输出 token、账单实付不适用；测试中模拟用量不是账单。
- 四项检查累计 72.109 秒，不含安装与文件传输；安装全过程未单独计时。服务器租用成本与人工/维护工时未量化。
- 官方 PyPI 与阿里云镜像的 81MB SDK 运行包下载曾因低速主动中止。随后从官方 PyPI 下载 Linux 包作为传输缓存，校验并上传；SHA-256 为 `ad877237382baff4628969a9ebdbfe38486d971b7987c032d0e29775759b5229`。安装该同版本包后，通过阿里云 HTTPS 镜像补齐其余依赖；安装日志与来源校验保留，不将中止记作兼容性失败。
- 在这些版本与夹具条件下，支持 Python 3.10.8 完成 SSS 免费运行闭环；无需源码适配。不能据此宣称所有后续依赖、真实 MCP 或论文投稿流程均兼容，也不能宣称科研质量或成本收益。
- 接手下一步：复用已配置服务器，实现论文场景的最小 MCP 链路；另行准备论文编译依赖和授权输入，审阅交付后再接前端。当前没有真实论文编译、外部应用联调、云调用或实际投稿授权。
