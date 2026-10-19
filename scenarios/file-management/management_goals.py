"""Bounded, independently computed goal checks. Unknown wording remains reviewable."""
import copy,re
from pathlib import PurePosixPath
from common import digest

VERSION='sss-management-goal-v3'
FOLDERS={'.pdf':'documents','.doc': 'documents','.docx':'documents','.xls':'tables','.xlsx':'tables','.csv':'tables',
         '.png':'images','.jpg':'images','.jpeg':'images','.webp':'images','.gif':'images','.txt':'notes','.md':'notes','.json':'notes'}
PATH=r'[\w./-]+'
TAIL=r'(?:[，。]?完成后核验并提交报告)?[。.!]?'
def path(value):
    value=value.rstrip('/')
    if not value or len(value)>180 or '\\' in value or PurePosixPath(value).is_absolute() or any(p in ('','.','..') or p.startswith('.sss-management-') or p.endswith('.') for p in value.split('/')):raise ValueError('goal path needs clarification')
    if value.split('/')[0] in ('.experiment-copy','.management-copy'):raise ValueError('reserved goal path')
    return value
def explicit_tree(initial_roots,requirements):
    """Closed final footprint; checks are frozen before any file operation."""
    expected=copy.deepcopy(initial_roots)
    origins={root+'/'+n:root+'/'+n for root,t in initial_roots.items() for n in t['files']}
    for r in requirements:
        root=r.get('root_id','workspace');name=path(r['path']);kind=r['kind']
        if root not in expected or kind not in ('file','missing','unchanged','read','directory','empty_directory'):raise ValueError('unsupported frozen predicate')
        t=expected[root]
        if kind=='missing':
            for n in list(t['files']):
                if n==name or n.startswith(name+'/'):t['files'].pop(n);origins.pop(root+'/'+n,None)
            t['directories']=[n for n in t['directories'] if n!=name and not n.startswith(name+'/')]
        elif kind=='file':
            source_root=r.get('source_root','workspace');source=path(r['source'])
            value=initial_roots[source_root]['files'][source]
            if name in t['directories']:raise ValueError('frozen file conflicts with directory')
            t['files'][name]=value
            if initial_roots[root]['files'].get(name)!=value:origins[root+'/'+name]=source_root+'/'+source
        elif kind in ('directory','empty_directory'):
            if name in t['files']:raise ValueError('frozen directory conflicts with file')
            t['directories']=sorted(set(t['directories'])|{name})
    for root,t in expected.items():
        reads=[r['path'] for r in requirements if r['kind']=='read' and r.get('root_id','workspace')==root and r.get('source')]
        parents={str(p) for n in [*t['files'],*t['directories'],*reads] for p in PurePosixPath(n).parents if str(p)!='.'}
        if parents.intersection(t['files']):raise ValueError('frozen parent conflicts with file')
        t['directories']=sorted(set(t['directories'])|parents)
    for r in requirements:
        root=r.get('root_id','workspace');t=expected[root];n=r['path']
        if r['kind']=='unchanged' and t['files'].get(n)!=initial_roots[root]['files'].get(n):raise ValueError('conflicting frozen unchanged predicate')
        if r['kind']=='missing' and (n in t['files'] or n in t['directories']):raise ValueError('conflicting frozen missing predicate')
        if r['kind']=='empty_directory' and any(p.startswith(n+'/') for p in [*t['files'],*t['directories']]):raise ValueError('conflicting frozen empty directory')
    return expected,origins


def intermediate_sources(initial_roots,expected,requirements):
    return {r.get('root_id','workspace')+'/'+path(r['path']):{'origin':r.get('source_root','workspace')+'/'+path(r['source']),
            'sha256':initial_roots[r.get('source_root','workspace')]['files'][r['source']]}
            for r in requirements if r['kind']=='read' and r.get('source') and r['path'] not in expected[r.get('root_id','workspace')]['files']}


def _compile_file_goal(objective,initial,explicit=None,*,initial_roots=None):
    goal={'format':VERSION,'objective_sha256':digest(objective),'state':'review_required','source':'bounded_language',
          'scope':'workspace','requirements':[],'reason':'目标表述未被完整解析；仅核验实际操作完整性，目标完成情况需复核。'}
    if explicit is not None:
        result={**goal,'source':'explicit_frozen_checks','state':'frozen' if explicit else 'review_required',
                'requirements':copy.deepcopy(explicit),'reason':None if explicit else goal['reason']}
        if explicit:
            expected,origins=explicit_tree(initial_roots or {'workspace':initial},explicit)
            result.update(expected_tree=expected['workspace'],expected_roots=expected,expected_origins=origins,
                          intermediate_sources=intermediate_sources(initial_roots or {'workspace':initial},expected,explicit),
                          checks=['complete final file/directory footprint','actual original source lineage','frozen predicates'])
        return result
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
            m=re.fullmatch(r'(?:把|将)?\s*(?P<src>'+PATH+r')\s*复制到\s*(?P<temp>'+PATH+r')\s*，完整读取该副本，再重命名为\s*(?P<dest>'+PATH+r')\s*，保留原件'+TAIL,text)
            if m:
                temp=path(m['temp']);source=path(m['src']);dest=path(m['dest'])
                if temp in initial['files'] or temp in initial['directories'] or temp in (source,dest):raise ValueError('intermediate read needs a distinct new path')
                publish(source,dest);requirements.append({'kind':'read','source':source,'path':temp})
                checks=['complete intermediate read with original source lineage','final rename without extra copy','all original files preserved'];known=True
        if not known:
            m=re.fullmatch(r'(?:把|将)?\s*(?P<src>'+PATH+r')\s*(?P<op>复制到|移动到|重命名为)\s*(?P<dest>'+PATH+r')(?:，保留其[他它]文件不变)?'+TAIL,text)
            if m:
                dest=m['dest']
                if m['op']=='重命名为' and '/' not in dest:dest=str(PurePosixPath(m['src']).parent/dest)
                publish(m['src'],dest,m['op']!='复制到');checks=['requested source/destination','byte preservation','no unrelated effects'];known=True
            elif re.fullmatch(r'通读全部文本文件，给出完整读取覆盖清单，不修改任何文件'+TAIL,text):
                selected=[n for n in files if PurePosixPath(n).suffix.lower() in ('.txt','.md','.csv','.json')]
                requirements=[{'kind':'read','path':n} for n in selected];checks=['all selected text files readable without truncation','no filesystem changes'];known=True
        if known:
            roots,origins=explicit_tree(initial_roots or {'workspace':initial},requirements);expected=roots['workspace']
            return {**goal,'state':'frozen','reason':None,'requirements':requirements,'expected_tree':expected,
                    'expected_roots':roots,'expected_origins':origins,
                    'intermediate_sources':intermediate_sources(initial_roots or {'workspace':initial},roots,requirements),'checks':checks}
    except ValueError as e:goal['reason']=str(e)
    return goal



def compile_goal(objective,initial,explicit=None,*,initial_roots=None):
    from management_temporal import compile_temporal
    timing=compile_temporal(objective,initial,explicit)
    checks=None if explicit is None else [r for r in explicit if r.get('kind')!='temporal']
    result=_compile_file_goal(objective,initial,checks,initial_roots=initial_roots)
    if explicit is None and result['state']!='frozen' and timing['state']=='frozen':
        remaining=objective
        for clause in timing['source_clauses']:
            remaining=remaining.replace('时序要求：'+clause,'').replace('时序要求:'+clause,'').replace(clause,'')
        remaining=re.sub(r'[。！!\s，,；;：:]','',remaining)
        selectors=[s for p in timing['predicates'] for s in p['events']]
        if remaining in ('','不修改任何文件','不修改任何文件完成后核验并提交报告','完成后核验并提交报告') and all(s['tool'] in ('read_file','open_document','read_document_chunk','document_coverage') for s in selectors):
            reads=[{'kind':'read','path':p} for p in dict.fromkeys(s['path'] for s in selectors if 'path' in s)]
            if reads:result=_compile_file_goal(objective,initial,reads,initial_roots=initial_roots);result['source']='bounded_temporal_reading'
    result['requirements'] += copy.deepcopy([r for r in explicit or () if r.get('kind')=='temporal'])
    result['temporal']=timing
    if timing['state']=='review_required':result['reason']=timing['reason']
    return result
