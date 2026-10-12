"""Normal write differences -> compact plans and independent patch expectations.

The oracle is a verifier; its Python implementation is never the serving tool.
"""
from copy import deepcopy
from collections import Counter


def patch_input(report, plan):
    rows=[{'key':r['key'],'path':f'/references/{i}','id_path':f'/references/{i}/arxiv_id'}
          for i,r in enumerate(report['references'])]
    return {'rows':rows,'rows_reverse':list(reversed(rows)),'plan':deepcopy(plan)}


def patch_expectation(report, plan):
    values={r['key']:r['arxiv_id'] for r in plan['set_ids']}
    replacements=[{'path':f'/references/{i}/arxiv_id','value':values[r['key']]}
                  for i,r in enumerate(report['references']) if r['key'] in values]
    first={}
    for i,r in enumerate(report['references']):first.setdefault(r['key'],i)
    removals=[f'/references/{i}' for i in range(len(report['references'])-1,-1,-1)
              if report['references'][i]['key'] in plan['remove_keys'] or
              (report['references'][i]['key'] in plan['keep_once_keys'] and first[report['references'][i]['key']]!=i)]
    return {'replacements':replacements,'removals':removals,'additions':deepcopy(plan['add_records'])}


def observed_revision_plan(before,after):
    old=before['references'];new=after['references']
    oldkeys={r['key'] for r in old};newkeys={r['key'] for r in new}
    if len(newkeys)!=len(new):raise ValueError('source_final_duplicates')
    counts=Counter(r['key'] for r in old)
    ids=[{'key':r['key'],'arxiv_id':r['arxiv_id']} for r in new if r['key'] in oldkeys and
         any(v['key']==r['key'] and v['arxiv_id']!=r['arxiv_id'] for v in old)]
    additions=[deepcopy(r) for r in new if r['key'] not in oldkeys]
    if any(set(r)!={'key','arxiv_id','status'} or r['status']!='待进一步核验' for r in additions):raise ValueError('source_not_minimal_placeholder')
    without=lambda r:{k:v for k,v in r.items() if k!='arxiv_id'}
    if any(not any(v['key']==r['key'] and without(v)==without(r) for v in old) for r in new if r['key'] in oldkeys):
        raise ValueError('source_changed_protected_fields')
    if {k:v for k,v in before.items() if k!='references'}!={k:v for k,v in after.items() if k!='references'}:
        raise ValueError('source_changed_top_level')
    return {'set_ids':ids,'keep_once_keys':[k for k,n in counts.items() if n>1 and k in newkeys],
            'remove_keys':[k for k in dict.fromkeys(r['key'] for r in old) if k not in newkeys],'add_records':additions}


def patch_cases(packets):
    development=[]
    for p in packets:
        before=p['before_report'];plan=observed_revision_plan(before,p['after_report'])
        development.append({'id':'observed-'+p['packet_id'],'input':patch_input(before,plan),'expected':patch_expectation(before,plan)})
    sample=deepcopy(packets[0]['before_report'])
    empty={'set_ids':[],'keep_once_keys':[],'remove_keys':[],'add_records':[]}
    development.append({'id':'development-empty-plan','input':patch_input(sample,empty),'expected':patch_expectation(sample,empty)})
    plan={**empty,'remove_keys':[sample['references'][0]['key']]}
    development.append({'id':'development-explicit-removal','input':patch_input(sample,plan),'expected':patch_expectation(sample,plan)})
    heldout=[]
    # Fixed, undisclosed indices/counts/order variants; not new independent papers.
    for n in [0,1,2,5,12,23]:
        report={'references':[{'key':f'fresh-{i//3}','arxiv_id':'original','source_urls':['kept-a','kept-b']} for i in range(n)]}
        keys=list(dict.fromkeys(r['key'] for r in report['references']))
        for flavor in ['empty','mixed','remove-all']:
            plan=deepcopy(empty)
            if flavor=='mixed':
                plan['set_ids']=[{'key':k,'arxiv_id':f'new-{i}'} for i,k in enumerate(keys)]
                plan['keep_once_keys']=keys
                plan['add_records']=[{'key':'fresh-added','arxiv_id':'fresh-id','status':'待进一步核验'}]
            if flavor=='remove-all':plan['remove_keys']=keys
            heldout.append({'id':f'heldout-{n}-{flavor}','input':patch_input(report,plan),'expected':patch_expectation(report,plan)})
    return development,heldout
