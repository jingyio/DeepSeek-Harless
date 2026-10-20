# ppt-master-v18

基于 ppt-master-v17 的 PPT 渲染流程兼容版本。仅更新 Baseline / Motif 共用的场景提示：使用已部署 soffice 包装脚本与会话私有 profile，先核对真实字体与最终渲染路径，再以官方门禁及实际页面视觉检查验收。PDF span 包围框相交仅用于定位候选问题，不作为独立清零门禁；布局修复无进展时回查字体、测量、导出文件及坐标来源。不修改实际 PPT，不限制模型预算或步数，不降低官方要求。原 IR、manifest、任务、工具 schema 和来源证据字节不变。旧库保留，无新训练、私有轨迹重放或模型调用，不代表质量或成本效果晋级。验证与限制见 [docs/experiments/five-user-stress-20261020.md](../../docs/experiments/five-user-stress-20261020.md)。
