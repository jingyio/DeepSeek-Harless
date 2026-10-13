# V17发布准备：参数统一与main差异核验

## 问题与范围

用户要求停止付费参数实验，按本地V17及已有经验提高交付余量，清理PPT分支，保留必需代码、历轮报告和证据。此次只做发布整理与免费开发诊断，不新增模型效果样本，不把参数放宽称为已证实的稳定性提升。

## 配置与复现

- 实验/检查ID：`research-ppt-v17-release-preparation-20261013`，类型为服务器免费回归与真实无模型MCP诊断。
- 发布基点：main `856c02cf29ca0be630dd4fec7f2ab6deecbf27a8`；no-commit合入远端feature `34ca217`。V17来源为本地`research-ppt-reports-v14`树`e452983`加未提交增量；原两工作区保留。
- 服务器：独立发布核验副本，不覆盖既有V17任务、checkpoint或证书；激活原项目私有环境。实际解释器/依赖与源码SHA清单保存在私有检查日志。
- PPT单路默认$1.50/60步/每请求8000输出；双路总$3；PDF/PPTX每份100 MiB、1–8份、1–30页。外层MCP300秒、内层240秒；ZIP/图件/权限/来源守卫保持。思考/压缩off，无模型执行、API支出0。
- main通用Web配置、场景registry、公共适配器、锁文件和其它场景未修改。没有把不受支持的PPT字段加入通用请求。

最短免费验证命令（在服务器激活环境并安装依赖后）：

```sh
npm test
npm --prefix scenarios/research_ppt test
python -m pytest scenarios/research_ppt/tests -q
npm run smoke
python -m scenarios.research_ppt.delivery_smoke --out .local/research-ppt/release-check-delivery
python -m scenarios.research_ppt.recovery_smoke --out .local/research-ppt/release-check-recovery
```

两份诊断输出目录须为新目录；不要覆盖旧记录。`test-logs/<检查ID>/`保留每项命令日志、退出码、起止UTC时间及源码SHA/size核验。没有新模型请求或实际账单核对；无需付费预算。

## 改动与清理

1. 移植V16受控交付、持久资料/组件接口与V17局部草稿恢复/回执校正；不改上游Harness，也不造新Agent循环。
2. 原来文档/资料库100 MiB、解析摘要30 MiB不一致；统一100 MiB并分块摘要，增加边界/增长拒绝回归。PPTX展开150 MiB、单图8 MiB等安全限额保留。
3. 单路CLI默认与双路统一到60步/8000/$1.50，提高PPT工具超时；冻结任务仍不能在运行时换参数。已有实验的40步等历史快照不追改。
4. main已清理的8个旧矩阵/报告入口不重新引入，维护所需安全、费用、修订及真实MCP回归保留。按用户要求保留20份PDF及V1–V17文字报告；报告SHA原样，失败/勘误不删除。原始日志留私有区，公开报告保留匿名运行摘要。
5. 七个前端对接点与待新增代码见`scenarios/research_ppt/frontend-integration.md`。当前未写任务级Web桥接、流式上传、下载/完成判断或反馈UI，不能宣称网页已可用；高频脚本在已有Agent入口由宿主控制。

## 验证结果

| 检查 | 最终结果 | 边界 |
| --- | --- | --- |
| 根`npm test` | 151 Python、53 Node通过 | 公共协议/权限/前端回归；含确定性夹具，不是云模型验收 |
| 场景构建/Node | 94通过 | TypeScript编译、执行策略、草稿恢复及运行时约束 |
| 场景Python | 286通过、1跳过 | 初次独立副本没有测试默认位置的静态Noto字体；不放宽字形oracle |
| 字体单项补验 | 5通过、0跳过 | 显式使用原服务器已有`SSS_TEST_CJK_FONT`重跑字形文件；只补缺失环境条件，不重复整套 |
| 根smoke | 两套各9例通过，0付费 | 底座无模型诊断 |
| 真实交付smoke | 第二次全部通过，63.254秒 | 实际图件/可编辑PPTX/PDF/PNG、修订、非目标页保持、两次MCP重启、权限与版本拒绝 |
| 真实局部恢复smoke | 通过，0模型 | 失败草稿、局部修补、真实渲染、陈旧版本及普通组拒绝 |

首次交付smoke在`new_tools_read_only_annotations`检查失败，尚未生成交付。旧诊断用数组位置`i>=2`推断只读，V17新增`repair_pending_plan`会写入却落在该范围；实际MCP注解正确。改为按明确工具集合逐项核验，保留写操作false要求。原失败summary/log继续留存，修复后用新目录`release-check-delivery-02`通过，不覆盖失败证据。这是诊断代码修复，不是隐藏或放宽生产守卫。

服务器初始466个公共源文件逐项SHA/size一致；最终371个运行时/测试/锁及运行提示文件再次与本机核对一致（不含报告和纯说明文档）。日志与三份诊断目录的28个证据文件下载到本机并核SHA/size；包身份和逐文件结果位于私有`transfer-verification.json`。20份既有报告PDF与原manifest的SHA/size一致，未重新生成或修改历史结果。

全部检查在新服务器副本完成，原运行目录不覆盖；API支出0。节点模块类型提示和重复ZIP路径负例的warning保留。这些检查不证明科学或审美质量，也没有验收浏览器完整PPT链路。

## 结论与交付边界

当前仅支持“发布内容已准备、参数已在Agent入口生效”。前端仍需任务级适配、流式上传与回执映射、交付状态/鉴权下载、反馈与双路展示，复用现有JSON/MCP/DSH引擎。多用户身份必须由可信后端贯穿。

V17历史双路15页结果、质量待评审和成本归因限制见`research-ppt-v17-local-recovery-20261013.md`；本次免费检查没有新增请求/token降幅，也不能证明任意PDF必然交付。参数提高可能增加最坏费用与资源占用，预算预览和有界失败必须保留。

本次尚未commit/push，无PR。按用户此前要求，用户查看完整真实V17成品并通知后再告知中文commit范围、提交和推送；本次分支整理不绕过该条件。清理细节见`docs/research-ppt-release-cleanup.md`。
