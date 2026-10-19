"""Frozen temporal predicates over original Harness call/result/message events.

This is a bounded language compiler, not a semantic plan or a tool router.
Unsupported timing remains review_required; filesystem predicates cannot waive it.
"""
import copy,re
from common import digest
VERSION='sss-management-temporal-v2'
TOOLS={'open_document','read_file','read_document_chunk','document_coverage','prepare_tool_call','execute_tool_call','inspect_tool_result'}
PATH=r'[\w./-]+'

def compile_temporal(objective,initial,explicit=()):
    contract={'format':VERSION,'objective_sha256':digest(objective),'state':'not_requested','predicates':[],'release_after':[],'reason':None}
    predicates=copy.deepcopy([r for r in explicit or () if r.get('kind')=='temporal'])
    clauses=re.findall(r'时序要求[：:]([^。\n]+)',objective)
    if not clauses:
        clauses=[s.strip() for s in re.split(r'[。\n]',objective) if re.search(r'同一(?:条|批)|时序|之前|之后|先.+(?:再|然后)',s)]
    unknown=False
    def selector(tool,name=None,count=1):return {'tool':tool,'min_count':count,**({'path':name} if name else {})}
    def full_read(name):return selector('document_coverage' if name.lower().endswith(('.pdf','.png','.jpg','.jpeg','.tif','.tiff','.webp','.bmp')) else 'read_file',name)
    for block in clauses:
        for clause in block.split('；'):
            clause=clause.strip().replace(',','，')
            m=re.fullmatch(r'在同一条工具调用消息中依次打开 ('+PATH+r'(?:、'+PATH+r')*) 并完整读取 ('+PATH+r')',clause)
            if m:
                opens=[selector('open_document',n) for n in m[1].split('、')];memo=selector('read_file',m[2])
                predicates += [{'kind':'temporal','relation':'same_batch','events':[*opens,memo]},
                    {'kind':'temporal','relation':'before','events':[memo,selector('read_document_chunk')]}];continue
            m=re.fullmatch(r'先打开 ('+PATH+r'(?:、'+PATH+r')*)，再完整读取 ('+PATH+r')，最后读取上述文档正文',clause)
            if m:
                opens=[selector('open_document',n) for n in m[1].split('、')];memo=selector('read_file',m[2])
                predicates += [{'kind':'temporal','relation':'before','events':[o,memo]} for o in opens]
                predicates += [{'kind':'temporal','relation':'before','events':[memo,selector('read_document_chunk')]}];continue
            m=re.fullmatch(r'先完整读取\s*('+PATH+r')\s*，再完整读取\s*('+PATH+r')',clause)
            if m:
                predicates.append({'kind':'temporal','relation':'before','events':[full_read(m[1]),full_read(m[2])]});continue
            m=re.fullmatch(r'先(?:在同一条工具调用消息中)?准备 ([2-9]|1[0-6]) 个工具请求，再执行任何工具请求',clause)
            if m:
                a=selector('prepare_tool_call',count=int(m[1]));b=selector('execute_tool_call')
                predicates.append({'kind':'temporal','relation':'all_before','events':[a,b]})
                if '同一条' in clause:predicates.append({'kind':'temporal','relation':'same_batch','events':[a]})
                continue
            unknown=True
    if not clauses and re.search(r'同一(?:条|批)|时序|之前|之后|先.+(?:再|然后)',objective):unknown=True
    release=[]
    try:
        for p in predicates:
            if set(p)!={'kind','relation','events'} or p['relation'] not in ('before','all_before','same_batch') or not 1<=len(p['events'])<=16:raise ValueError()
            if p['relation']!='same_batch' and len(p['events'])!=2:raise ValueError()
            for s in p['events']:
                if set(s)-{'tool','path','min_count'} or s.get('tool') not in TOOLS or type(s.get('min_count',1)) is not int or not 1<=s.get('min_count',1)<=16:raise ValueError()
                if 'path' in s and s['path'] not in initial['files']:raise ValueError()
            release += p['events'] if p['relation']=='same_batch' else p['events'][:1]
    except (ValueError,TypeError,KeyError):unknown=True
    state='review_required' if unknown else 'frozen' if predicates else 'not_requested'
    contract.update(state=state,predicates=predicates,source_clauses=clauses,release_after=list({digest(s):s for s in release}.values()),
        reason='时序表述或选择器未被完整解析，需要复核；不得声明时序已通过。' if unknown else None)
    return contract

def matches(selector,row,state):
    if not row.get('out') or row['name']!='mcp__file_management__'+selector['tool']:return False
    out=row['out'];args=row.get('args',{})
    if selector['tool']=='read_file' and (out.get('status')!='readable' or out.get('truncated') is not False or out.get('metadata',{}).get('preview_only')):return False
    if selector['tool']=='document_coverage' and out.get('complete') is not True:return False
    if 'path' not in selector:return True
    path=out.get('path')
    if not path and args.get('source_id') in state.get('handles',{}):path=state['handles'][args['source_id']]['path']
    if not path and out.get('document_id') in state.get('documents',{}):path=state['documents'][out['document_id']]['anchor']['path']
    return path=='workspace/'+selector['path']

def verify_temporal(contract,events,state,scope):
    if contract.get('state')=='not_requested':return {'verified':True,'errors':[],'state':'not_requested','proofs':[]}
    if contract.get('state')!='frozen':return {'verified':False,'errors':[],'state':'review_required','proofs':[]}
    if contract.get('format')!=VERSION:return {'verified':False,'errors':['unsupported frozen temporal version'],'state':'failed','proofs':[]}
    if events is None:return {'verified':False,'errors':[],'state':'trace_pending','proofs':[]}
    from src.adapters.continuous_motif_learning import observations
    rows=[r for r in observations(events) if r['out'].get('_sss_scope')==scope]
    errors=[];proofs=[]
    for i,p in enumerate(contract['predicates']):
        groups=[[r for r in rows if matches(s,r,state)] for s in p['events']]
        passed=all(len(g)>=s.get('min_count',1) for s,g in zip(p['events'],groups))
        if passed and p['relation'] in ('before','all_before'):
            boundary=max(r['result_seq'] for r in groups[0]) if p['relation']=='all_before' else min(r['result_seq'] for r in groups[0])
            passed=boundary<min(r['call_seq'] for r in groups[1])
        elif passed:
            # First required occurrences decide the obligation. Later re-reading
            # is legal, but cannot erase an earlier wrong batch or first action.
            groups=[g[:s.get('min_count',1)] for s,g in zip(p['events'],groups)]
            chosen=[r for g in groups for r in g];seqs={r['message_seq'] for r in chosen}
            passed=(len(seqs)==1 and None not in seqs and not any(r['call_id'].startswith('sss-') for r in chosen)
                and len({r['call_id'] for r in chosen})==len(chosen)
                and all(max(r['call_seq'] for r in a)<min(r['call_seq'] for r in b) for a,b in zip(groups,groups[1:])))
        if not passed:errors.append('temporal predicate failed: '+str(i)+' '+p['relation'])
        proofs.append({'predicate':i,'passed':passed,'call_ids':[[r['call_id'] for r in g] for g in groups]})
    return {'verified':not errors,'errors':errors,'state':'verified' if not errors else 'failed','proofs':proofs}
