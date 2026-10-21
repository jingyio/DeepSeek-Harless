# ppt-master-v16

基于 ppt-master-v15 的 Linux 只读沙箱挂载准备兼容版本。只更新已审阅的 geneloop_shell.ts 代码锁：固定会话 scratch 内预建 inputs/outputs 挂载点，拒绝符号链接和非目录；输入、scratch 只读以及网络隔离守卫保持。原 IR、manifest、任务、工具 schema 与来源证据字节不变；旧库保留，无新训练、原始轨迹重放或模型请求，不代表科研质量或成本效果晋级。验证与限制见 [docs/experiments/five-user-stress-20261020.md](../../docs/experiments/five-user-stress-20261020.md)。
