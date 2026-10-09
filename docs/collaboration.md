# 三个场景、两天工期的协作方式

继续在这个仓库开发，每人一个场景分支。main 是大家共享、经过检查的起点；archive 是历史备份，不作为日常开发分支。

| 人员 | 主要负责 | 变更边界 |
| --- | --- | --- |
| 你 | Motif / Harness 公共接口、集成、合并与演示 | `src/`、通用脚本和配置 |
| 同学 刘沛林 | 场景 A 的 MCP、任务、契约与测试 | `scenarios/scene_a/`、自己的测试 |
| 同学 杨夏泽 | 场景 B 的 MCP、任务、契约与测试 | `scenarios/scene_b/`、自己的测试 |
| 同学 夏俊杰 | 场景 C 的 MCP、任务、契约与测试 | `scenarios/scene_c/`、自己的测试 |

第一天开头，大家先 `npm test` 和 `npm run smoke` 跑通底座，再各复制 example。第一天中午前，每个场景至少提交一个 MCP 可调用的最小链路。第一天结束前集成一次；第二天优先修复联调和真实任务问题，下午冻结演示版本。小步合并比等完整场景做完才同步更适合两天工期。

## 同学第一次开始

把下面的 scene_a 换成自己的名字；已有本地修改时先提交，不要覆盖。

```sh
git switch main
git pull --ff-only origin main
git switch -c codex/scene-a
npm ci
npm run setup
npm test
```

先确认管理员已经把整理后的 main 推到共享仓库。复制 `scenarios/example/` 后，只修改自己的目录与测试。每个场景至少有：题面、MCP 配置、工具契约、一个正常调用和一个版本/权限失效检查。模型负责科研判断；工具负责授权读取与确定性计算。

## 提交并同步

```sh
git add scenarios/scene_a tests/test_scene_a.py
git commit -m "Add scene A MCP read flow"
git push -u origin codex/scene-a
```

发 PR，注明一个可复现命令、任务预览、模型预算、尚未支持的功能。你检查后合入 main。不要让每位同学都改公共依赖、README、同一启动器或核心运行时；遇到共同需求先由你做公共改动。

别人合并后，先提交自己的工作，再同步：

```sh
git fetch origin
git merge origin/main
npm test
```

只有两个分支改了同一段代码时才通常需要解决冲突。出现冲突先暂停 AI 批量改写，与该文件负责人确认；两天工期使用普通 merge 即可，不必学复杂 rebase 或强制推送。

## 给编码 Agent 的任务边界

明确告诉它：场景目录、真实 MCP 工具、输入输出契约、验收命令、预算，以及需要人判断的研究问题。要求先复用公共接口、解释真实依赖，不要生成另一套 Agent 循环、手写整题 DAG，或为绕开失败去删安全测试。密钥放本机环境，实验输出只进 `.local/`。
