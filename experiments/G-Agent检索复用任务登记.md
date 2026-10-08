# G-Agent 检索、组合与在线记忆：题目登记

> 2026-09-24，在本题模型调用前固定。材料是开发阶段已经阅读的 `reference/G-Agent.pdf`；该题仅用于检查新加入的“题目义务清单”守卫，不能算未见材料盲评。

## 固定任务

只依据 `reference/G-Agent.pdf` 回答：**G-Agent 在新请求中如何依次尝试完整工作流复用、Persistent TinyEdge 组合与 LLM 规划回退？成功执行后如何更新和淘汰记忆？** 每个机制要给出 PDF 页码；无法从材料确认的条件应标注不确定。

预先固定四个必答点，见 [JSON 清单](G-Agent检索复用必答点.json)。人工以 PDF pp.5–7、12–13 的方法与算法核对：完整工作流的检索阈值和当前参数实例化；组合路径的粗计划、top-k 检索、片段选择与覆盖门槛；前两路失败时的 LLMPlan；轨迹接受后的工作流/TinyEdge 更新和 LRU 淘汰时的支持度重算。需要区分论文设计与本项目已实现功能。

## 同题运行

- **普通检索脚本**：只给同一 PDF，固定人工词 `RetrieveWorkflow,RetrieveTinyEdges,theta_W,coarse plan,DistinctTinyEdges,LLMPlan,Trajectory Acceptance,LRU,RefreshTinyEdges`；1 次模型综合，按现有引文校验输出。
- **带义务守卫的结构流程**：只给同一 PDF；规划、选页、综合最多 3 次模型请求。JSON 清单在规划前核验并保存；最终每个必答点须关联至少一条来源引文可定位的结论，否则 `incomplete_answer`。本轮不做付费重试，保留缺项和总用量。
- 两组均用 `deepseek-flash`、关闭推理、同一来源。检索方式、输出格式和输出上限不同，结果仅作诊断。计入失败请求，不能把“有引文”当作“引文蕴含结论”。

若新守卫发现缺项而旧流程会误报 `answered`，算防止假完成的进展；只有四项都由人工核对充分，才能把本题算作合格答案。费用须按运行时官方价计算。
