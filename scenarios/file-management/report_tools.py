"""Explicit literal-search delivery contract shared by ordinary and library-assisted Harness."""
from __future__ import annotations
import copy,json,os
from pathlib import Path
from typing import Literal
from uuid import uuid4
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from common import HERE,digest,sha,save
from collection_tools import CollectionScene,execution_version as collection_version

CONTRACT_VERSION='sss-file-report-v3'
def report_version():
    return digest({'report_tools.py':sha(__file__),'inherited_collection_version':collection_version(),
                   'contract':CONTRACT_VERSION})

class ReportScene(CollectionScene):
    """Explicit source-scope guard changes the read execution version; libraries require fresh native certification."""
    def __init__(self,spec,output):
        super().__init__(spec,output);self.search_receipts={};self.execution_version=report_version()
        contract=spec.get('report_contract',{})
        if contract.get('version')!=CONTRACT_VERSION or contract.get('kind') not in ('task_result','inspection','literal_search'):
            raise ValueError('explicit versioned report contract required')
        self.report_contract=copy.deepcopy(contract)

    def read_task(self):
        """Read the objective and explicit report kind: search file_ids are hits, never the inspection set."""
        return {**super().read_task(),'report_contract':self.report_contract,
                'report_execution_version_sha256':report_version(),
                'collection_execution_version_sha256':self.execution_version}

    def stage_members(self,stage):
        prefix=stage['path_prefix'];extensions=stage.get('extensions')
        if stage.get('extensions_notice_path'):
            observed=[r for r in self.reads.values() if r['path']==stage['extensions_notice_path'] and r['status']=='readable']
            if len(observed)!=1:raise ToolError('read and complete the first-stage notice before selecting followup files')
            try:extensions=json.loads(observed[0]['text'])['followup_extensions']
            except (ValueError,KeyError,TypeError) as exc:raise ToolError('followup extension data unavailable') from exc
        if extensions is not None and (not isinstance(extensions,list) or not extensions or any(not isinstance(x,str) for x in extensions)):
            raise ToolError('extension scope data invalid')
        return {fid for fid,name in self.files().items() if name.startswith(prefix)
                and (extensions is None or '*' in extensions or Path(name).suffix.lower() in extensions)}

    def select_files(self,file_ids:list[str]):
        """Declare the exact current task stage. Followup scope is restricted to its prefix and actual notice extensions."""
        self.active();stages=self.report_contract.get('inspection_stages')
        if stages:
            if len(self.collections)!=len(self.collection_results):raise ToolError('complete the outstanding collection before another selection')
            step=len(self.collection_results)
            if step>=len(stages):raise ToolError('all declared inspection stages already complete')
            if len(file_ids)!=len(set(file_ids)) or set(file_ids)!=self.stage_members(stages[step]):
                raise ToolError('selected set differs from declared stage '+str(step+1)+' prefix '+stages[step]['path_prefix']+'; followup selection must exclude the first-stage context')
        return super().select_files(file_ids)

    def target_collection(self):
        self.active()
        if not self.collection_results:raise ToolError('complete the target collection with collect_reads first')
        packet=list(self.collection_results.values())[-1]
        expected=self.report_contract.get('collection_count')
        if expected is not None and len(self.collection_results)!=expected:
            raise ToolError('complete the required collection stages before search')
        if packet['snapshot_sha256']!=digest(self.expected):raise ToolError('report collection is no longer current')
        return packet

    def expected_query(self):
        query=self.report_contract.get('query')
        notice_path=self.report_contract.get('query_notice_path')
        if notice_path:
            notices=[r for r in self.reads.values() if r['path']==notice_path and r['status']=='readable']
            if len(notices)!=1:raise ToolError('query must come from the actual notice read')
            try:query=json.loads(notices[0]['text'])['query']
            except (ValueError,KeyError,TypeError) as exc:raise ToolError('notice query data unavailable') from exc
        if not isinstance(query,str) or not query.strip() or len(query)>120:
            raise ToolError('literal query must be 1-120 nonblank characters')
        return query

    def build_index(self,source_ids:list[str]):
        """For literal search, index exactly the last complete target collection; never the earlier context set."""
        if self.report_contract['kind']=='literal_search':
            packet=self.target_collection();wanted=[r['source_id'] for r in packet['files']]
            if len(source_ids)!=len(wanted) or set(source_ids)!=set(wanted):
                raise ToolError('search index must contain exactly the target collection read handles')
            if self.index and set(self.index)!={r['file_id'] for r in packet['files']}:
                raise ToolError('existing index contains a different scope; prepare a new attempt')
        return super().build_index(source_ids)

    def search_index(self,query:str):
        """Return literal hits and a scope/version-bound search receipt. Only matches belong in report file_ids."""
        if self.report_contract['kind']!='literal_search':return super().search_index(query)
        packet=self.target_collection()
        if query!=self.expected_query():raise ToolError('query differs from the task/actual notice; use its exact query data')
        if set(self.index)!={r['file_id'] for r in packet['files']}:
            raise ToolError('build the complete target collection index before search')
        for r in packet['files']:
            if r['read_sha256']!=digest(self.index[r['file_id']]):raise ToolError('indexed observation changed')
        base=super().search_index(query)
        body={**base,'contract_version':CONTRACT_VERSION,'report_kind':'literal_search',
              'collection_id':packet['collection_id'],'coverage_sha256':packet['coverage_sha256'],
              'input_sha256':self.input_digest,'snapshot_sha256':digest(self.expected),
              'report_execution_version_sha256':report_version(),
              'indexed_observations_sha256':digest(self.index),
              'file_ids':[r['file_id'] for r in base['matches']],
              'file_ids_meaning':'exact literal hits in the target collection, not all inspected files',
              'unsearchable':[{'file_id':r['file_id'],'path':r['path'],'status':r['status']}
                              for r in packet['files'] if r['status']!='readable'],
              'limitations':['case-insensitive literal substring in delivered text only',
                             'PDF first two physical pages; at most 6000 delivered characters per file',
                             'images have no OCR; absent text is not semantic absence'],
              'semantic_judgment_certified':False}
        receipt_id='search-'+uuid4().hex;body['search_receipt_id']=receipt_id
        body['search_sha256']=digest(body);self.search_receipts[receipt_id]=copy.deepcopy(body)
        save(self.output/'searches'/f'{receipt_id}.json',body)
        return copy.deepcopy(body)

    def submit_report(self,summary:str,file_ids:list[str],gaps:list[str],
                      report_kind:Literal['task_result','inspection','literal_search'],search_receipt_id:str|None=None):
        """Publish only the declared report kind. Literal-search file_ids must equal the cited search receipt hits."""
        self.active()
        if report_kind!=self.report_contract['kind']:raise ToolError('report_kind must match read_task.report_contract.kind')
        if len(file_ids)!=len(set(file_ids)):raise ToolError('report file_ids must be unique')
        search=None
        if report_kind=='inspection':
            required=len(self.report_contract.get('inspection_stages',[])) or self.report_contract.get('collection_count',1)
            if len(self.collection_results)!=required:raise ToolError('complete all declared inspection collections before delivery')
            wanted={r['file_id'] for p in self.collection_results.values() for r in p['files']}
            if set(file_ids)!=wanted:raise ToolError('inspection file_ids must include every member of all completed collect_reads collections, including first-stage context; correct and resubmit')
            if {r['file_id'] for r in self.reads.values()}!=wanted:raise ToolError('inspection reads outside completed collections')
        elif report_kind=='literal_search':
            search=self.search_receipts.get(search_receipt_id)
            if not search:raise ToolError('use the exact search_index.search_receipt_id before delivering search')
            packet=self.target_collection()
            if (search['input_sha256']!=self.input_digest or search['snapshot_sha256']!=digest(self.expected)
                    or search['collection_id']!=packet['collection_id'] or search['coverage_sha256']!=packet['coverage_sha256']
                    or search['indexed_observations_sha256']!=digest(self.index)
                    or search['query']!=self.expected_query() or search['report_execution_version_sha256']!=report_version()):
                raise ToolError('search receipt scope/query/version changed; search the current target again')
            if set(file_ids)!=set(search['file_ids']):
                raise ToolError('file_ids must equal search_index matches for this receipt, not all inspected files; correct and resubmit')
        elif search_receipt_id is not None:raise ToolError('task_result must omit search_receipt_id')
        receipt=super().submit_report(summary,file_ids,gaps)
        body=json.loads((self.output/'report.json').read_text())
        body.update(report_kind=report_kind,contract_version=CONTRACT_VERSION,
                    report_execution_version_sha256=report_version(),search_receipt=search,
                    inspection_receipts=list(self.collection_results.values()) if report_kind=='inspection' else None)
        save(self.output/'report.json',body);receipt['artifact_sha256']=digest(body)
        return receipt

def serve():
    scene=ReportScene(json.loads(Path(os.environ['FM_TASK_FILE']).read_text()),os.environ['FM_OUTPUT'])
    server=MCPServer('file_management')
    for name in ('read_task','list_files','select_files','pin_file','read_file','collect_reads','hash_files','build_index',
                 'search_index','compare_snapshot','preview_actions','execute_plan','restore_plan','submit_report'):
        server.tool(name=name,annotations=ToolAnnotations(readOnlyHint=name not in ('build_index','execute_plan','restore_plan','submit_report'),
                    destructiveHint=False,openWorldHint=False))(getattr(scene,name))
    server.run()
if __name__=='__main__':serve()
