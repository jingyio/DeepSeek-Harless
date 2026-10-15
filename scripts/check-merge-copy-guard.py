"""Free actual MCP: duplicate previews have no effects; restore releases prior byte group."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scenarios/file-management'))
import auto_rsi as rsi
from common import snapshot,save


async def check(out,spec,case):
    checks=[]
    async with rsi.h.mcp.Connection(out,spec) as conn:
        task=await conn.call('read_task');rows=(await conn.call('list_files'))['files'];by={r['path']:r for r in rows}
        for name in task['workflow_contract']['context_paths']:
            pin=await conn.call('pin_file',{'file_id':by[name]['file_id']});await conn.call('read_file',{'source_id':pin['source_id']})
        grouped=await conn.call('hash_files',{'file_ids':[by[n]['file_id'] for n in task['workflow_contract']['source_paths']]})
        try:
            await conn.call('submit_report',{'summary':'intentionally incomplete free probe','file_ids':[r['file_id'] for r in rows],'gaps':[],'report_kind':'task_result'})
            raise AssertionError('submission accepted without any output groups')
        except Exception as error:
            assert 'missing original SHA groups' in str(error),str(error)
        assert not (out/'delivery/report.json').exists()
        checks.append('missing_groups_submission_rejected_including_empty_groups')
        group=next(g for g in grouped['groups'] if len(g['files'])>=2)
        a,b=group['files'][:2];prefix=task['workflow_contract']['destination_prefixes'][0]
        aa=[{'op':'copy','file_ids':[r['file_id']],'destination':prefix+r['path']} for r in (a,b)]
        before=snapshot(spec['workspace'])
        try:
            await conn.call('preview_actions',{'actions':aa})
            raise AssertionError('duplicate single-plan preview accepted')
        except Exception as error:
            assert 'duplicate SHA group' in str(error),str(error)
        assert snapshot(spec['workspace'])==before and not list((out/'delivery/journals').glob('*'))
        checks.append('single_plan_duplicate_rejected_without_effects')
        plan=await conn.call('preview_actions',{'actions':aa[:1]});receipt=await conn.call('execute_plan',{'plan_id':plan['plan_id']})
        assert (await conn.call('execute_plan',{'plan_id':plan['plan_id']}))==receipt
        checks.append('execute_idempotent')
        copied=snapshot(spec['workspace'])
        try:
            await conn.call('preview_actions',{'actions':aa[1:]})
            raise AssertionError('duplicate later-plan preview accepted')
        except Exception as error:
            assert 'duplicate SHA group' in str(error),str(error)
        assert snapshot(spec['workspace'])==copied
        checks.append('later_plan_duplicate_rejected_without_effects')
        await conn.call('restore_plan',{'plan_id':plan['plan_id']})
        assert snapshot(spec['workspace'])==before
        replacement=await conn.call('preview_actions',{'actions':aa[1:]})
        await conn.call('execute_plan',{'plan_id':replacement['plan_id']})
        await conn.call('restore_plan',{'plan_id':replacement['plan_id']})
        assert snapshot(spec['workspace'])==before
        checks.append('restored_group_can_be_replaced')
    value={'task_id':case['task_id'],'checks':checks,'passed':True,'actual_MCP':True,'real_api_requests':0,'not_training':True,'output':str(out)}
    save(out/'free-guard-outcome.json',value)
    return value


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--experiment',type=Path,required=True);args=parser.parse_args()
    exp=args.experiment.resolve();p=rsi.read(exp/'protocol.json');results=[]
    for case in p['tasks'][::2][:3]:
        out,spec,env,_=rsi.h.instantiate(exp,{**case,'arm':'S'},p,True)
        results.append(asyncio.run(check(out,spec,case)))
    save(exp/'free-merge-guard-summary.json',{'checks':sum(len(r['checks']) for r in results),'passed':len(results),'results':results,'real_api_requests':0})
    print(json.dumps({'actual_MCP_materials':len(results),'guard_checks':sum(len(r['checks']) for r in results),'passed':len(results),'real_api_requests':0}))


if __name__=='__main__':main()
