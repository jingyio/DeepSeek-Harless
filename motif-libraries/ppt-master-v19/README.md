# ppt-master-v19

基于 ppt-master-v18 的自产预览能力边界兼容版本。仅更新 Baseline / Motif 共用的场景提示：当前工具不能将自产 PNG 像素返回模型，不得把路径、base64、ASCII 或几何统计冒充已看过页面；交付完整预览及实际检查结果，并如实注明逐页视觉复核尚未完成，留给用户或人工审阅。保持来源 MCP 的上传审批边界，保留 soffice 包装脚本、字体校准及防重复 bbox 微调流程。不增加工具或能力，不修改实际 PPT，不限制预算或步数，不降低官方要求。原 IR、manifest、任务、工具 schema 和来源证据字节不变。旧库保留，无新训练、私有轨迹重放或模型调用，不代表质量或成本效果晋级。验证与限制见 [docs/experiments/five-user-stress-20261020.md](../../docs/experiments/five-user-stress-20261020.md)。
