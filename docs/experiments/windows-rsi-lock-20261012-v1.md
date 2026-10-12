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
