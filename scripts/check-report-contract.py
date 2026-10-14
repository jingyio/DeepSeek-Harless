"""Actual MCP positive/negative delivery checks; scripted file selection is not learning evidence."""
import argparse,asyncio,json,os,sys
from pathlib import Path
from uuid import uuid4
from mcp import Client,StdioServerParameters
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import save,digest
async def check(exp,c):
    out=exp/'contract-checks'/uuid4().hex;out.mkdir(parents=True,mode=0o700)
    env={**os.environ,'FM_TASK_FILE':str(Path(c['task_dir'])/'input.json'),'FM_OUTPUT':str(out/'delivery')};env.pop('DEEPSEEK_API_KEY',None)
    async with Client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'scenarios/file-management/report_tools.py')],cwd=ROOT,env=env)) as client:
        async def call(name,args):
            result=await client.call_tool(name,args)
            if result.is_error:raise ValueError((name,result.model_dump(mode='json')))
            return json.loads(result.content[0].text)
        schemas=await client.list_tools();assert len(schemas.tools)==14;save(out/'tool-schemas.json',[t.model_dump(mode='json') for t in schemas.tools])
        task=await call('read_task',{});listing=await call('list_files',{});collections=[];first=[];second=[]
        for stage in ('stage_a/','stage_b/'):
            rows=[r for r in listing['files'] if r['path'].startswith(stage)];selected=await call('select_files',{'file_ids':[r['file_id'] for r in rows]});reads=[]
            for r in rows:
                pin=await call('pin_file',{'file_id':r['file_id']});reads.append(await call('read_file',{'source_id':pin['source_id']}))
            collections.append(await call('collect_reads',{'collection_id':selected['collection_id'],'source_ids':[r['source_id'] for r in reads]}))
            if stage=='stage_a/':first=reads
            else:second=reads
        wrong_index=await client.call_tool('build_index',{'source_ids':[r['source_id'] for r in first+second]});assert wrong_index.is_error
        await call('build_index',{'source_ids':[r['source_id'] for r in second]})
        query=json.loads(next(r['text'] for r in first if r['path']=='stage_a/followup.txt'))['query'];search=await call('search_index',{'query':query})
        wrong_ids=await client.call_tool('submit_report',{'summary':'all inspected is not search result','file_ids':[r['file_id'] for r in first+second],'gaps':[],
                         'report_kind':'literal_search','search_receipt_id':search['search_receipt_id']});assert wrong_ids.is_error
        wrong_kind=await client.call_tool('submit_report',{'summary':'wrong kind','file_ids':search['file_ids'],'gaps':[],'report_kind':'task_result'});assert wrong_kind.is_error
        assert not (out/'delivery/report.json').exists()
        receipt=await call('submit_report',{'summary':'literal hits in target only','file_ids':search['file_ids'],'gaps':['text scope only'],
                     'report_kind':'literal_search','search_receipt_id':search['search_receipt_id']})
        report=json.loads((out/'delivery/report.json').read_text());assert receipt['artifact_sha256']==digest(report)
        result={'task':c['task_id'],'tools':14,'query':query,'hits':len(search['file_ids']),'wrong_index_rejected':True,'wrong_set_rejected_without_delivery':True,
                'wrong_kind_rejected':True,'correct_receipt_verified':True,'real_api_requests':0,'scripted_selection_not_training':True}
        save(out/'outcome.json',result);return result
def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);a=p.parse_args();exp=a.experiment.resolve();protocol=json.loads((exp/'protocol.json').read_text())
    cases=[c for c in protocol['tasks'] if c['role']=='quality' and c['family']=='content_search' and c['arm']=='H' and c['repetition']==0]
    for c in cases:print(json.dumps(asyncio.run(check(exp,c))),flush=True)
if __name__=='__main__':main()
