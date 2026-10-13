# 当前版本证据链重新认证：GitHub提交说明

解析与引用规则更新后，旧证据包/认证不能强制继承。本轮从当前版本的两条真实普通轨迹重新学习已有“提取→核验→组包”候选，以不同研究问题认证，再用新模型批准的同一计划比较Harness、普通脚本和Motif。原始科研判断仍由模型承担，工作台无需Human审批。

## 代码和接口范围

- 新增`scenarios/literature-notes/review-evidence.py --run .local/runs/<真实baseline>`：免费来源/原生许可/参数核对CLI，复用实际共享run、已有源重放与轨迹适配器；只接受真实模型普通baseline。确认连续三个成功节点、相同许可、实际前驱参数和精确最终包，无歧义才保存绑定packet/events/contracts/版本的机械review；已有不同记录拒绝覆盖。不授予相关性、论断或科研质量认证。
- 新增`tests/test_literature_evidence_review.py`：实际本地Harness事件检验错误参数、插入步骤及伪收据拒绝；模拟Provider不能提升为真实模型训练。测试使用自有临时夹具，0付费请求。
- 复用现有`learn-evidence.py`、`run-evidence.py`、`compare-evidence.py`、`reuse-evidence.py`和共享Python编译/认证及TypeScript在线许可规则，无新Agent模型循环或在线执行规则。
- **本轮新增共享接口变化：无。** MCP schema、manifest v2、预算、价格、Harness/SDK和工作台默认执行路线不改。此前共享续接/模型别名改动保留，不能当成本轮新增。新库仅对应literature_evidence命名空间，不能混用literature_pdf库。

## 验证、结果与回退

全仓344 Python+44共享Node通过；21场景Node已包含在Python包装。真实模型两训练/一独立问题认证，编译1个三节点Motif并通过权威Node Runtime校验。当前PDF/新库免费原生协议6/4/4、同包、2skip、0embedding通过；另核旧真实baseline版本拒绝、execute训练拒绝和新问题缓存拒绝。没有修改原论文、Key或原始失败稿。

真实三轮9次对照均为同一六窗证据包：Harness/script/Motif每次6/4/4请求，Motif每次2个成功原生验证skip；平均代理USD0.004726544/0.004346424/0.004419348。**Motif比脚本贵约1.68%**，含启动均值12.483/10.870/10.809秒，后两者几乎相同；学习/认证USD0.04752尚未摊平。同输入普通缓存0请求，不算Motif收益。当前不默认启用这条Motif。

完整准备、学习、认证和比较共82真实请求/USD0.104601444，原生账本逐项核对，旧失败和历史成本保留；科研质量等价、跨语料及净收益未建立。[完整配置、运行ID、全部费用与边界](../experiments/motif-renew-20261011-14c3fc42.md)。

回退只移除本轮新增机械review入口/测试与对应文档，不影响正常工作台或已有共享许可功能；显式选择普通baseline/script即可退出可选Motif。私有新库、轨迹、源和费用不删除、不入Git。本地feature/rsi-research-agent，未commit/push/PR。
