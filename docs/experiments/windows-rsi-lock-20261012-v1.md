# Windows RSI脚本导入与预算锁修复

阶段快照`52cb0f4`已成功推送。其[CI运行](https://github.com/jingyio/DeepSeek-Harless/actions/runs/38190783031)中Ubuntu全部通过，Windows在pytest收集阶段失败：五个测试间接导入实验脚本，而脚本顶层直接导入Unix专用fcntl。此前macOS干净验收没有覆盖这个导入差异，不能称本轮Windows通过。

新增`src/adapters/file_lock.py::exclusive_lock(path)`，Unix保留原flock，Windows使用msvcrt非阻塞独占字节锁，异常退出释放，竞争者拒绝，固定锁文件不删除。[Python官方说明](https://docs.python.org/3/library/msvcrt.html#msvcrt.locking)定义了字节范围锁及非阻塞模式。后端仅在真正取得锁时导入，因此所有17个相关脚本/学习入口的免费导入不依赖fcntl；未取消累计预算锁，也未通过跳过测试隐藏问题。

新增真实子进程竞争/异常释放、Windows后端调用/竞争拒绝和18个控制器离线导入诊断；此前两项只因fcntl而跳过的预算测试恢复跨平台执行。生成任务的代码注册加入锁模块，新实验要重新冻结快照；旧库/manifest不改。各轮旧结果仍依其归档代码复核。

本地完整385 Python/213 Node通过（免费），原snapshot的18题smoke/Motif样例验收通过；本次锁改动后尚待新Windows/Ubuntu远端CI，结果确认后追加。本轮没有真实模型请求、新增费用0，累计论文估费仍7.96362748/10美元。完整论文免费准备已编译私有副本，34个渲染条目与315个Bib记录分开，尚未开始付费长流程。

原始本地诊断在`.local/paper-reference/pre-scale-save-20261012/`，锁失败日志与完整通过日志分开保存；新代码仅提交锁入口、对应实验脚本/回归与记录。私人材料、另外两位同学场景保留本地。

## 第二轮：轨迹路径与本机路径混用

修复`a18660a`的[运行](https://github.com/jingyio/DeepSeek-Harless/actions/runs/38191821895)中Ubuntu仍通过，Windows不再收集失败，但有5项断言失败、380项通过。用户提供的完整错误显示：当前读取路径用反斜杠，而编译器手工拼接斜杠前缀；POSIX轨迹在Windows又被本机Path解释；预算记录的相对路径未采用协议表示。结果是读取见证未匹配、Motif缺失和预算路径格式不一致。

新增`trace_paths.py`按记录自身的POSIX/Windows风格做词法相对路径判断，而不依赖编译机操作系统。只有显式根目录下的路径能绑定；外部盘符、相似前缀、上级跳转与盘符相对路径拒绝，捕获版本仍必须匹配。native/parameter编译器统一依赖键为正斜杠；预算记录只用as_posix序列化，不改变真实文件、授权或历史记录。保持现有Motif数量断言，不将缺失候选改成预期结果。原生Bash编译仍是受限Unix命令子集，不能称已支持任意Windows终端程序。

补充不同平台的记录风格、大小写、相似路径前缀与外部读取拒绝检查；本机CI模式400 Python/213 Node通过。新运行记录注册锁/路径模块hash，旧manifest未改。因公开GitHub完整日志接口需登录，CI额外生成Python/Node JUnit并将失败摘要转成检查注释：不更改失败退出码、不断言通过、不隐藏日志；换行与百分号转义，避免日志内容注入工作流命令。新远端Windows/Ubuntu结果仍待确认，不能仅以本机通过替代。

## 第三轮：Windows Node目录绑定及导出保护

`dd89ce4`的[运行](https://github.com/jingyio/DeepSeek-Harless/actions/runs/38193122575)中Windows已通过Python阶段，Node为177通过/36失败。公开注释与用户补充完整日志显示：共享catalog绑定使用了POSIX斜杠后缀，在Windows路径下使多条Shadow/execute测试共同失败；此外Windows没有O_NOFOLLOW，旧导出会跟随已有符号链接，安全测试正确拒绝该行为。

目录绑定改用平台basename并保持目录文件SHA与来源映射检查。导出先lstat拒绝符号链接/硬链接/非普通文件，再独占创建当前私有工作区的随机临时文件，写完核验报告版本后rename至固定revision-report.md，最终清理临时文件。rename替换目标路径自身，不写链接指向文件；目标在检查后被换成链接也不会改写其指向的原件。新增重复导出覆盖/摘要一致/临时文件清理验证，旧链接拒绝断言不变。模型、算法、执行effect范围和费用授权不扩大，新代码须新快照，旧实验不追改。

本机400 Python/213 Node完整通过，包含全部原安全检查；新远端CI待确认。诊断注释增加合并失败索引，公开接口一次能看到失败名称集合，而非只得到前几条独立异常。另一会话修改的AGENTS/README远程部署说明未纳入本修复，不覆盖其工作。累计预算仍未新增模型支出。

## 远端验证完成

修复提交`62b6658790fc03d583c5bd4e09a97066c53fa716`已推送至`origin/feature/paper-submission`。[CI运行38194682416](https://github.com/jingyio/DeepSeek-Harless/actions/runs/38194682416)的Windows与Ubuntu两项任务均为success；逐项核对`npm test`、`npm run smoke`、`npm run motif:check`全部通过。Windows任务于2026-10-12 10:12（Asia/Shanghai）完成。以上是实际远端结果，不是本机推断；前三轮失败记录保留。

本轮确认的是跨平台免费开发回归及样例闭环，不代表Windows真实模型、任意终端命令或完整论文验收已完成。此次修复没有新付费请求，累计预算与完整论文长流程准备状态不变。主线和场景交接正在由另一会话更新，因此本次仅追加这份修复记录，避免同时修改其交接内容。
