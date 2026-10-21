# paper-web-v31

从 paper-web-v30 重导出的原生能力兼容版本。相同 IR、online manifest、task、完整 MCP schema 与来源证据逐字节保留；旧库保留。

公共原生 read/read_image、文件搜索、skill/todo/present、提问和同任务受控子 Agent 是运行环境能力，未加入本库认证的 MCP 子集，也没有被本次学习。PPT 新增的 read_image 页面视觉检查属于两侧共同的真实图像通道，原来源固定与转换结构不变。上下文压力、重试计量与用户界面接线通过代码锁绑定，不是新的结构认证。

本次零新训练任务、零原始轨迹重放、零模型调用；不声称合格净降本。entry/report 原有 new_training=true 描述原始训练来源，不是本次重导出发生训练。当前质量、费用和压力效果需独立真实实验；未测结果不能写为通过。

验证记录：docs/experiments/dsh-native-capabilities-20261021.md。
