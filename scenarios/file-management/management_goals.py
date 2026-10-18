"""Bounded, independently computed goal checks. Unknown wording remains reviewable."""
import copy,re
from pathlib import PurePosixPath
from common import digest

VERSION='sss-management-goal-v1'
FOLDERS={'.pdf':'documents','.doc': 'documents','.docx':'documents','.xls':'tables','.xlsx':'tables','.csv':'tables',
         '.png':'images','.jpg':'images','.jpeg':'images','.webp':'images','.gif':'images','.txt':'notes','.md':'notes','.json':'notes'}
PATH=r'[\w./-]+'
TAIL=r'(?:[，。]?完成后核验并提交报告)?[。.!]?'
def path(value):
    value=value.rstrip('/')
    if not value or len(value)>180 or '\\' in value or PurePosixPath(value).is_absolute() or any(p in ('','.','..') or p.startswith('.sss-management-') or p.endswith('.') for p in value.split('/')):raise ValueError('goal path needs clarification')
    if value.split('/')[0] in ('.experiment-copy','.management-copy'):raise ValueError('reserved goal path')
    return value
def compile_goal(objective,initial,explicit=None):
    goal={'format':VERSION,'objective_sha256':digest(objective),'state':'review_required','source':'bounded_language',
          'scope':'workspace','requirements':[],'reason':'目标表述未被完整解析；仅核验实际操作完整性，目标完成情况需复核。'}
    if explicit is not None:
        return {**goal,'source':'explicit_frozen_checks','state':'frozen' if explicit else 'review_required',
                'requirements':copy.deepcopy(explicit),'reason':None if explicit else goal['reason']}
    text=objective.strip().replace(',','，');expected=copy.deepcopy(initial);requirements=[];checks=[];known=False
    files={n:h for n,h in initial['files'].items() if n not in ('.experiment-copy','.management-copy')}
    def publish(source,destination,move=False):
        source=path(source);destination=path(destination)
        if source not in files:raise ValueError('source is absent from the original snapshot')
        if destination in expected['files'] and expected['files'][destination]==files[source] and not move:
            requirements.append({'kind':'file','source':source,'path':destination});return
        if destination in expected['files'] or destination in expected['directories']:raise ValueError('existing target requires a separately reviewed goal')
        expected['files'][destination]=files[source]
        requirements.append({'kind':'file','source':source,'path':destination})
        if move:expected['files'].pop(source);requirements.append({'kind':'missing','path':source})
        p=PurePosixPath(destination).parent
        expected['directories']=sorted(set(expected['directories'])|{str(q) for q in (p,*p.parents) if str(q)!='.'})
    try:
        m=re.fullmatch(r'按(?:文件)?类型(?P<op>复制|移动)整理到\s*(?P<dest>'+PATH+r')(?:，保留(?:全部)?原件(?:和内容)?)?(?:，并?创建\s*(?P<empty>'+PATH+r')\s*空目录)?'+TAIL,text)
        if m:
            if m['op']=='移动' and '保留' in text:raise ValueError('move and preserve originals conflict')
            dest=path(m['dest']);selected=[n for n in files if not n.startswith(dest+'/')]
            for n in selected:
                target=dest+'/'+FOLDERS.get(PurePosixPath(n).suffix.lower(),'others')+'/'+n
                publish(n,target,m['op']=='移动')
            if m['empty']:
                empty=path(m['empty'])
                if empty in expected['files']:raise ValueError('empty directory conflicts with a file')
                if any(n.startswith(empty+'/') for n in [*expected['files'],*expected['directories']]):raise ValueError('requested empty directory is not empty')
                expected['directories']=sorted(set(expected['directories'])|{empty,*[str(p) for p in PurePosixPath(empty).parents if str(p)!='.']})
                requirements.append({'kind':'empty_directory','path':empty})
            checks=['extension classification','all original input files','source byte preservation','no extra file/directory effects'];known=True
        else:
            m=re.fullmatch(r'(?:把|将)?\s*(?P<src>'+PATH+r')\s*(?P<op>复制到|移动到|重命名为)\s*(?P<dest>'+PATH+r')(?:，保留其[他它]文件不变)?'+TAIL,text)
            if m:
                dest=m['dest']
                if m['op']=='重命名为' and '/' not in dest:dest=str(PurePosixPath(m['src']).parent/dest)
                publish(m['src'],dest,m['op']!='复制到');checks=['requested source/destination','byte preservation','no unrelated effects'];known=True
            elif re.fullmatch(r'通读全部文本文件，给出完整读取覆盖清单，不修改任何文件'+TAIL,text):
                selected=[n for n in files if PurePosixPath(n).suffix.lower() in ('.txt','.md','.csv','.json')]
                requirements=[{'kind':'read','path':n} for n in selected];checks=['all selected text files readable without truncation','no filesystem changes'];known=True
        if known:return {**goal,'state':'frozen','reason':None,'requirements':requirements,'expected_tree':expected,'checks':checks}
    except ValueError as e:goal['reason']=str(e)
    return goal

