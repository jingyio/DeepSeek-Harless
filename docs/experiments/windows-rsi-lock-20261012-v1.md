# Windows RSI脚本导入与预算锁修复

阶段快照`52cb0f4`已成功推送。其[CI运行](https://github.com/jingyio/DeepSeek-Harless/actions/runs/38190783031)中Ubuntu全部通过，Windows在pytest收集阶段失败：五个测试间接导入实验脚本，而脚本顶层直接导入Unix专用fcntl。此前macOS干净验收没有覆盖这个导入差异，不能称本轮Windows通过。

新增`src/adapters/file_lock.py::exclusive_lock(path)`，Unix保留原flock，Windows使用msvcrt非阻塞独占字节锁，异常退出释放，竞争者拒绝，固定锁文件不删除。[Python官方说明](https://docs.python.org/3/library/msvcrt.html#msvcrt.locking)定义了字节范围锁及非阻塞模式。后端仅在真正取得锁时导入，因此所有17个相关脚本/学习入口的免费导入不依赖fcntl；未取消累计预算锁，也未通过跳过测试隐藏问题。

新增真实子进程竞争/异常释放、Windows后端调用/竞争拒绝和18个控制器离线导入诊断；此前两项只因fcntl而跳过的预算测试恢复跨平台执行。生成任务的代码注册加入锁模块，新实验要重新冻结快照；旧库/manifest不改。各轮旧结果仍依其归档代码复核。

本地完整385 Python/213 Node通过（免费），原snapshot的18题smoke/Motif样例验收通过；本次锁改动后尚待新Windows/Ubuntu远端CI，结果确认后追加。本轮没有真实模型请求、新增费用0，累计论文估费仍7.96362748/10美元。完整论文免费准备已编译私有副本，34个渲染条目与315个Bib记录分开，尚未开始付费长流程。

原始本地诊断在`.local/paper-reference/pre-scale-save-20261012/`，锁失败日志与完整通过日志分开保存；新代码仅提交锁入口、对应实验脚本/回归与记录。私人材料、另外两位同学场景保留本地。
