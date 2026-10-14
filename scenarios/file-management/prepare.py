"""Freeze 24 exploration, 12 certification and 24 untouched evaluation tasks."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
from uuid import uuid4
from common import ROOT,HERE,DATA,save,sha,snapshot,digest,source_code,PREFIX

TOOLS=('read_task','list_files','pin_file','read_file','hash_files','build_index','search_index',
       'compare_snapshot','preview_actions','execute_plan','restore_plan','submit_report')
FAMILIES={
 'inventory':('盘点所有文件，读取检查其格式与可读性，明确指出损坏文件和仅可读取属性的图片。不要修改文件。',[]),
 'index':('读取所有文件并建立内容索引；不可读文件和图片的状态保留，不声称 OCR。',[]),
 'attribute_search':('找出所有 Word 和 Excel 文件，读取并核对它们；报告有效文件及损坏文件。',[]),
 'content_search':('建立可用索引，找出包含 workflow 或 graph 的研究材料，引用实际来源；单独指出没有文本的文件。',[]),
 'rule_classify':('把 inbox 中所有文件按扩展名移动到 organized/<扩展名去掉点>/原文件名；包括损坏文件。保留其余目录。',['move']),
 'content_classify':('读取 inbox 中的 Word、文本和 Markdown，按内容分为 research 或 administration，移动到 categories/<类别>/原文件名。空内容、图片、表格和 PDF 留原位。',['move']),
 'rename':('把 inbox 中所有文件改名为 normalized/<扩展名去点>/item_01.<扩展名>、item_02.<扩展名>等，按原路径字典序编号，保留其他目录。',['move']),
 'deduplicate':('计算全部文件内容摘要，完全重复文件保留字典序最小路径，将其他副本移到 quarantine/<原路径>；不同内容同名文件均保留。',['quarantine']),
 'conflict':('比较 left/brief.txt 与 right/brief.txt 的内容。若不同，分别复制到 resolved/brief_left.txt 与 resolved/brief_right.txt；不要覆盖。',['copy']),
 'convert':('将 inbox/brief.docx 转为 converted/brief.txt、inbox/ledger.xlsx 转为 converted/ledger.csv、inbox/poster.png 转为 converted/poster.jpg，验证产物。',['convert']),
 'incremental':('比较此前目录快照，只读取新增和修改的文件并建立这些文件的索引，报告删除项和未变化项；不要重读未变化文件。',[]),
 'archive_restore':('将 inbox 中全部文件打包为 exports/inbox.zip，核验完整清单，然后恢复这个操作并确认目录恢复到执行前状态。',['archive']),
}

def prepare(assets):
    if not assets.is_dir(): raise ValueError('author fixture assets first')
    DATA.mkdir(parents=True,exist_ok=True)
    exp=DATA/('fm-20261013-'+uuid4().hex[:8]); exp.mkdir(mode=0o700)
    private=ROOT/'.local/file-management'/exp.name; private.mkdir(parents=True,mode=0o700)
    originals=sorted((ROOT/'testpdf').glob('*.pdf'))
    if len(originals)!=3: raise ValueError('expected original three PDF inputs')
    manifests=[]
    for i,v in enumerate(('a','b','c','d','e')):
        dataset=exp/'datasets'/v; dataset.mkdir(parents=True)
        for name in ('brief.docx','ledger.xlsx','poster.png','minutes.txt','invoice.txt','notes.md','empty.txt'):
            dest=dataset/'inbox'/name; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(assets/v/name,dest)
        pdf_source=originals[i] if i<3 else assets/v/'paper.pdf'
        shutil.copyfile(pdf_source,dataset/'inbox/paper.pdf')
        (dataset/'copies').mkdir(); shutil.copyfile(dataset/'inbox/minutes.txt',dataset/'copies/minutes.txt')
        for side,value in [('left',f'{v} research project briefing\n'),('right',f'{v} administrative expenses\n')]:
            (dataset/side).mkdir(); (dataset/side/'brief.txt').write_text(value)
        (dataset/'bad').mkdir(); (dataset/'bad/broken.docx').write_bytes(b'not a ZIP document')
        (dataset/'bad/disguised.pdf').write_text('This text is not a PDF file.\n')
        manifests.append({'variant':v,'snapshot':snapshot(dataset),'pdf':{'anonymous_id':f'P{i+1}',
                           'sha256':sha(pdf_source),'origin':'real' if i<3 else 'generated'},'generated_other_files':True})
    tasks=[]
    for role,variants in [('explore',('a','b')),('certify',('c',)),('evaluate',('d','e'))]:
        for variant in variants:
            for family,(objective,operations) in FAMILIES.items():
                tid=f'{role}-{variant}-{family}'; work=exp/'tasks'/tid/'workspace'
                shutil.copytree(exp/'datasets'/variant,work)
                (work/'.experiment-copy').write_text(tid)
                previous=snapshot(work)
                if family=='incremental':
                    (work/'inbox/minutes.txt').write_text((work/'inbox/minutes.txt').read_text()+'New graph meeting action.\n')
                    (work/'inbox/new.txt').write_text(f'{variant} new research workflow notes\n')
                    (work/'inbox/empty.txt').unlink()
                spec={'schema_version':1,'task_id':tid,'role':role,'family':family,'variant':variant,
                      'objective':objective,'rules':{'scope':'experimental copy','preserve_unselected':True},
                      'allowed_operations':operations,'workspace':str(work),'initial_snapshot':snapshot(work),
                      'previous_snapshot':previous,'material_origin':'real PDF plus generated fixtures'}
                taskdir=private/'tasks'/tid; save(taskdir/'input.json',spec)
                (taskdir/'prompt.md').write_text((HERE/'prompt.md').read_text()+f'\n本次任务 {tid}\n{objective}\n',encoding='utf-8')
                config={'schema_version':1,'name':'file_management','prompt':str(taskdir/'prompt.md'),
                        'servers':[{'server_name':'file_management','transport':'stdio','command':'${PYTHON}',
                         'args':['${PROJECT_ROOT}/scenarios/file-management/file_tools.py'],'cwd':'${PROJECT_ROOT}',
                         'env':{'FM_TASK_FILE':{'from_env':'FM_TASK_FILE'},'FM_OUTPUT':{'from_env':'FM_OUTPUT'}}}],
                        'allowed_tools':[PREFIX+n for n in TOOLS],
                        'completion_guard':{'tool':PREFIX+'submit_report','statuses':['delivered','delivered_with_gaps'],
                                            'max_continuations':2}}
                save(taskdir/'scenario.json',config)
                tasks.append({'task_id':tid,'role':role,'family':family,'variant':variant,
                              'input_sha256':digest(spec),'task_dir':str(taskdir)})
    protocol={'experiment_id':exp.name,'data_directory':str(exp),'private_directory':str(private),
              'model':'deepseek-flash','reasoning_effort':'off','compression_enabled':False,
              'mode':'baseline','total_cap_usd':1000,'per_task_cap_usd':5,'max_steps':48,'max_output':4000,
              'tasks':tasks,'datasets':manifests,'source_code':source_code(),'shared_core_changes':False,
              'limitations':['generated file fixtures','three real PDFs','held-out PDFs are generated; no real-world corpus generalization claim'],
              'pricing_checked_url':'https://api-docs.deepseek.com/quick_start/pricing/',
              'accounting':'existing proxy peak-rate conservative estimate; actual bill not verified'}
    save(private/'protocol.json',protocol); save(exp/'task-catalog.json',{'tasks':[{k:v for k,v in t.items() if k!='task_dir'} for t in tasks]})
    save(ROOT/'.local/file-management/current.json',{'experiment':str(private)})
    print(json.dumps({'experiment':str(private),'data':str(exp),'explore':24,'certify':12,'evaluate':24,'call_model':False}))
    return private

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);a=p.parse_args();prepare(a.assets)
