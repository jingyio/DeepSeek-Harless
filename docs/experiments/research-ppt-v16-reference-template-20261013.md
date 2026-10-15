# V16 私有科研参考稿与模板后端验证

状态：工程验证完成；默认 Agent 尚未接入参考 PPTX 模板，不构成生成质量或 RSI 降本结论。属于 V16 的独立零模型支线，主设计见同目录 `research-ppt-v16-persistent-learning-20261013-plan.md`。私人稿件、派生产物及日志只在 `.local/` 与服务器 `test-logs/` 保存。

## 问题、来源与方案

用户提供六份科研 PPT 作为风格参考。不是授权执行文件中的指令，也不自动授权公开分发内容/标识。服务器真实解析并渲染全部141页（23/23/18/27/27/23），全部16:9，1个母版、1至11个layout。本机下载557份来源/结构/预览并逐文件核SHA/size；不修改原件。版式不是科学事实来源。

逐稿总览及精选单页检查支持优先复用“方法流程”“完整原图＋分层解释”“比较表”“实验条件＋结果＋限制”页型。不能仅提取颜色、增加卡片或强制结论标题；图件细节与文字容量应决定版式。匿名ref-04作为朴素组会参考，ref-02的原图/原生结果表作补充。选择清单与shape坐标保持私有。

比较两条后端路线：固定旧PPTAgent的解析保存，与在原PPTX副本上替换明确shape槽位。都是零模型兼容测试，没有新论文自动规划。失败也保留；不以“API成功保存”代替对象/来源保留验收。

## PPTAgent 固定版本与真实结果

- 最新main固定 `833cda553b343be0e486a93b0b57cac962cdd566`：HTML Skill，与早期PPTX参考引擎不同。本次只静态阅读，不证明其新稿质量。
- 旧 `v0.2.0` 固定 `d53296bc0ddd73e81d51c523d20dd711c7f233f3`（MIT）；python-pptx fork固定 `219513d7d81a61961fc541578c1857d08b43aa2a`，实际模块 `1.0.4+PPTAgent`。使用私有依赖环境，主环境仍为1.0.2，不导入上游Agent/内部模型循环，不运行eval编辑。
- 实验 `pptagent-zero-model-roundtrip-ref02-20261013`：`Presentation.from_file → save`，23页输入SHA `5c019c5bbdef2edf3f124509d19acf83e08108adaa8bb1edd4c750568458066d`，解析 `error_history=[]`。

| 检查 | 原稿 | 旧引擎副本 |
|---|---:|---:|
| 页数 |23|23|
| 原生表格 |9|0|
| 原生图表 |5|0|
| 嵌入Excel |5|0|
| 有notes页面 |23|0|
| 图片对象 |27|41|
| master/layout数量 |1/6|1/6|

表格和图表实际变为绿色占位图，非准确截图；来源备注全部丢失。原有5份媒体内容哈希均保留，新增占位图且文件名重排，不能说原图片字节丢失。两稿实际LibreOffice输出均23页PDF，逐页PNG有7页完全一致、16页变化，其中12页MAE>1；差值只是变化诊断，不是审美评分。直接看第3/4页确认占位损失。单稿未覆盖多母版、动画、分组、SmartArt等。

证据目录 `.local/research-ppt/reference-ppt-20261013/pptagent-roundtrip-01/result-03/`；复现 `roundtrip_ref02.py`，失败依赖安装和前两次阻断日志均保留。服务器成功日志 `test-logs/research-ppt-v16-persistent-learning-20261013/pptagent-roundtrip-03.log`。本机下载另保留服务器相对路径，因此解包下有嵌套 `.local`。模型请求/token/费用0；计算与维护费用未知。此结果不否定最新版HTML生成能力。

## 原包明确槽位替换

实验 `ref04-page17-slots-02`：输入27页SHA `ed5db40ed9885b65e84ffa0d0c582116ef71b297bf43318461069d8ff661ac0b`，只修改第17页标题、解释、来源和图片。新图来自用户RSI论文PDF p.8完整Figure3，来源字节与真实caption/geometry绑定；不使用他人科学内容当新任务答案。

首次验证发现原图片裁切参数，按安全规则停止并保留。第二次明确清除该替换图片旧srcRect，按原形状尺寸contain完整原图，新增独立媒体，不覆写其他图片。137个未变原ZIP成员payload逐字节相同；只改slide17.xml及关系、新增1个PNG。原母版/layout/theme/media/notes均保持，shape ID和几何不变，实际文字可编辑，LibreOffice仍输出27页。

新PPTX SHA `99be2069b1b0080079f729b0e14cb3cdff4080b5f6c31329e0989bd14e55e44f`，12份原manifest产物下载逐文件核SHA/size。执行10.252秒，模型请求/token/费用0，人工分钟与计算费用未知。原notes部件文本为空，新notes尚未生成；另外26页仍是原作者内容。因此只展示修改页PNG，整27页副本不作为新论文交付。大图半栏的细图例偏小，实际应用应有宽图页型，不强制一种布局。

证据目录 `.local/research-ppt/reference-ppt-20261013/slot-validation/ref04-page17-slots-02/`，含audit、figure-evidence、manifest、PNG及后补 `audit-review-boundary.json`。服务器日志 `reference-slots-01.log`、`reference-slots-02.log`、`reference-slots-notes-supplement-01.log`；旧失败及原文件不改。

## 决定与下一步

本稿证据不支持直接把旧PPTAgent整稿重建作为默认后端。优先在原包副本上实现受限模板绑定，并保留来源/权限/版本和真实渲染验收；清理身份、旧正文与notes，检查原生表格/图表关系和可读性后，才进入新稿生成。

最小拟议接口为模板检查、填槽预览、显式执行。模板源SHA、固定shape/类型/位置、允许字段与图片尺寸、租户、notes/标识清理均需验证；输出新副本，字体/溢出/图内文字独立检查。此接口尚未发布。模板复用是普通工程能力；未来从真实轨迹学得选择/绑定、独立认证且被新任务调用，才谈RSI增量收益。

私有参考证据已另包下载至本机v16-evidence-backups/reference-20261013t0724z-02/：1952文件在ZIP内及成功解包files-02/后逐SHA/size一致，ZIP183,808,716字节，SHA5bf32ef22fc6d6d4519bcb998ea91f094065fc19cf327c4ef8c29fb06903f9ff，侧车manifest/log亦已校验。可重建backend-venv原件保留，包内只保存pip metadata/环境和原安装log定位，不当完整依赖锁。首次软链接安全拒绝及Windows长路径解包失败留证，第二份归档/长路径解包成功；不覆盖或删除旧结果。
