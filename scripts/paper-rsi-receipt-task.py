"""V6同工具成本对照：导出收据/简短解释是工程优化，非生成算法。"""
import importlib.util
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('receipt_effect_task',ROOT/'scripts/paper-rsi-effect-task.py')
effect=importlib.util.module_from_spec(spec);spec.loader.exec_module(effect)
task=effect.task
EXP=ROOT/'.local/paper-reference/paper-rsi-receipt-task-20261012-v6'
task.FILES.extend(['src/adapters/revision_export_receipt.ts','scripts/paper-rsi-receipt-task.py'])
original_prepare=task.prepare
def prepare(case,protocol):
    config=original_prepare(case,protocol)
    config['export_result_protocol']='revision_receipt_v2'
    return config
task.prepare=prepare
task.PROMPT+='''
输出协议revision_receipt_v2：导出成功的output只有structural_check_passed和audit_sha256，哈希对应完整产物中的同版本检查；失败仍有全部问题，必须修复或明确未合格。最终答复在150个中文字以内：只给产物名称、标识修正/去重/补缺三类实际修订依据和“未核验真实性及正式版本”限制；无需重复抄写工具计数或全部引用键，完整报告保留它们。实质冲突与未解决问题优先说明，遇此情况不受150字限制。不能省略必要判断或把待核验占位说成真实文献。'''
if __name__=='__main__':
    sys.argv.extend(['--experiment',str(EXP.relative_to(ROOT)),'--context-view','--private-export','--strict-tool-channel'])
    task.main()
