"""Model-selected reading scope and verified aggregation; no original-file effects."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
from uuid import uuid4
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from common import HERE,digest,sha,save
from file_tools import FileScene

def execution_version():
    return digest({p.name:sha(p) for p in (HERE/'file_tools.py',HERE/'common.py',Path(__file__))})

class CollectionScene(FileScene):
    def __init__(self,spec,output):
        super().__init__(spec,output);self.collections={};self.collection_results={}
        self.execution_version=execution_version()

    def inventory_rows(self):
        return [{**row,'source_version':digest({'path':row['path'],'sha':row['sha256'],'parser':'fm-parser-v1'})}
                for row in self.list_files()['files']]

    def select_files(self,file_ids:list[str]):
        """Declare the exact model-selected reading set; return current members, never read or classify them."""
        self.active()
        if len(file_ids)>32 or len(file_ids)!=len(set(file_ids)):raise ToolError('select 0-32 unique current file_ids')
        rows={r['file_id']:r for r in self.inventory_rows()}
        if any(fid not in rows for fid in file_ids):raise ToolError('unknown or stale selected file_id')
        cid='collection-'+uuid4().hex
        packet={'collection_id':cid,'input_sha256':self.input_digest,'snapshot_sha256':digest(self.expected),
                'execution_version_sha256':self.execution_version,'files':[rows[fid] for fid in file_ids],
                'selection':'actual_model_selected_members','count':len(file_ids)}
        packet['collection_sha256']=digest(packet);self.collections[cid]=copy.deepcopy(packet)
        save(self.output/'collections'/cid/'selection.json',packet)
        return packet

    def collect_reads(self,collection_id:str,source_ids:list[str]):
        """Verify complete actual reads for one declared set; summarize versions/statuses, leaving semantic judgment to the model."""
        self.active();packet=self.collections.get(collection_id)
        if not packet or packet['snapshot_sha256']!=digest(self.expected):raise ToolError('unknown or stale collection')
        if len(source_ids)>32 or len(source_ids)!=len(set(source_ids)):raise ToolError('unique read handles required')
        selected={r['file_id']:r for r in packet['files']};by_file={}
        for sid in source_ids:
            row=self.reads.get(sid)
            if row is None:raise ToolError('collection requires actual read_file observations')
            self.file(row['file_id'])
            if row['file_id'] not in selected or row['file_id'] in by_file:raise ToolError('read outside set or repeated member')
            if row['source_version']!=selected[row['file_id']]['source_version']:raise ToolError('selected version changed')
            by_file[row['file_id']]=row
        if set(by_file)!=set(selected):raise ToolError('collection has missing reads')
        rows=[{'file_id':fid,'path':by_file[fid]['path'],'source_id':by_file[fid]['source_id'],
               'source_version':by_file[fid]['source_version'],'status':by_file[fid]['status'],
               'read_sha256':digest(by_file[fid])} for fid in selected]
        body={'status':'collection_complete','collection_id':collection_id,'collection_sha256':packet['collection_sha256'],
              'input_sha256':self.input_digest,'execution_version_sha256':self.execution_version,
              'snapshot_sha256':digest(self.expected),'count':len(rows),'files':rows,'semantic_judgment_certified':False}
        body['coverage_sha256']=digest(rows);self.collection_results[collection_id]=body
        save(self.output/'collections'/collection_id/'summary.json',body)
        return copy.deepcopy(body)

def serve():
    spec=json.loads(Path(os.environ['FM_TASK_FILE']).read_text());scene=CollectionScene(spec,os.environ['FM_OUTPUT'])
    server=MCPServer('file_management')
    names=('read_task','list_files','select_files','pin_file','read_file','collect_reads','hash_files','build_index',
           'search_index','compare_snapshot','preview_actions','execute_plan','restore_plan','submit_report')
    for name in names:
        write=name in ('build_index','execute_plan','restore_plan','submit_report')
        server.tool(name=name,annotations=ToolAnnotations(readOnlyHint=not write,destructiveHint=False,openWorldHint=False))(getattr(scene,name))
    server.run()

if __name__=='__main__':serve()
