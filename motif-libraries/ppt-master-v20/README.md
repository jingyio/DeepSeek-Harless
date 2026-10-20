# ppt-master-v20

基于 ppt-master-v19 的成员文件监听执行环境兼容版本。只更新已审阅的账号网关源码锁：成员后端显式接收经过校验的 Chokidar polling/interval，默认使用官方 polling，避免依赖宿主共享的 inotify 配额；不继承其他父进程环境。MCP、工具 schema、文件边界、任务权限与模型调用流程不变。原 IR、manifest、任务、工具 schema 和来源证据字节不变。旧库保留，无新训练、私有轨迹重放或模型调用，不代表质量或成本效果晋级。验证与限制见 [docs/experiments/five-user-stress-20261020.md](../../docs/experiments/five-user-stress-20261020.md)。
