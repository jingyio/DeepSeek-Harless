# paper-web-v22

基于 paper-web-v21 的历史父会话冷恢复兼容版本。只更新已审阅的 dsh_web_tasks.ts 代码锁：没有普通任务记录的旧对照父会话，恢复时核验实际挂载能力；能力缺失则沿既有历史只读路径关闭旧工具，保留旧 preset 字节与账号权限，后续请求在新私有 scope 使用当前能力。当前兼容 preset 不降级；原 IR、manifest、任务、工具 schema 和来源证据字节不变。旧库保留，无新训练、私有轨迹重放或模型调用，不代表科研质量或成本效果晋级。验证与限制见 [docs/experiments/five-user-stress-20261020.md](../../docs/experiments/five-user-stress-20261020.md)。
