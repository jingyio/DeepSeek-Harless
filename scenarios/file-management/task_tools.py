"""Explicit effect/read acceptance for new tasks, with the original certified read graph."""
from __future__ import annotations
import json, os
from pathlib import Path
from typing import Literal
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from common import HERE, digest, sha, save
from file_tools import Action
from report_tools import ReportScene, report_version
from task_contract import VERSION, contract, reading_contract, rename_targets, required_inputs

def task_version():
    return digest({'task_tools.py':sha(__file__),'task_contract.py':sha(HERE/'task_contract.py'),
                   'inherited_report_version':report_version(),'contract':VERSION})

class TaskScene(ReportScene):
    """Shared engineering guard, outside the select/pin/read/collect Motif graph."""
    def __init__(self,spec,output):
        super().__init__(spec,output); self.task_contract = contract(spec)
        if self.report_contract['kind'] != 'task_result': raise ValueError('operation tasks require task_result report')

    def read_task(self):
        c = self.task_contract
        public = {'version':c.version,'kind':c.kind}
        if c.kind == 'rename': public.update(source_prefix=c.source_prefix,destination_prefix=c.destination_prefix,allow_optional_original_reads=c.allow_optional_original_reads)
        elif c.kind == 'convert': public.update(conversions=[r.model_dump() for r in c.conversions],allow_output_verification_reads=c.allow_output_verification_reads,require_output_verification_reads=c.require_output_verification_reads)
        else: public.update(source_prefix=c.source_prefix,routes=[r.model_dump() for r in c.routes],empty_and_unmatched='keep in place; if no moves are needed, complete required reads and submit_report directly without an operation plan')
        result = {**super().read_task(),'task_contract':public,
                  'reading_contract':reading_contract(self.spec,self.task_contract),
                  'task_execution_version_sha256':task_version(),
                  'report_file_ids_meaning':'all current files, including preserved originals and generated results'}
        if self.task_contract.kind == 'rename':
            result['rename_rule'] = 'sort ALL original source-prefix paths by Unicode code point; count globally from 1; lowercase final suffix; no suffix uses no-extension folder; width at least 2'
            result['rename_targets'] = [{'source':n,'destination':d} for n,d in rename_targets(self.spec,self.task_contract).items()]
        if c.kind == 'content_classify':
            result['classification_targets'] = [{'source':n,'allowed_destinations':[r.destination_prefix+n[len(c.source_prefix):] for r in c.routes]}
                                                for n in sorted(required_inputs(self.spec,c))]
            result['classification_targets_meaning'] = 'candidate file paths only; the model must choose a route from actual text or leave the file in place'
        return result

    def preview_actions(self,actions:list[Action]):
        self.active(); c = self.task_contract
        serialized = [a.model_dump() if isinstance(a,Action) else Action(**a).model_dump() for a in actions]
        if not serialized: raise ToolError('no action requested: if the task needs no file changes, complete the required reads/collection and submit_report directly; do not invent a plan')
        required = required_inputs(self.spec,c)
        if required:
            observed = {r['path'] for r in self.reads.values() if r.get('sha256') == self.spec['initial_snapshot'].get(r['path'])}
            if not required <= observed: raise ToolError('read ALL required original inputs, including empty text, before effects; missing: '+', '.join(sorted(required-observed)))
            if not any({r['path'] for r in p['files']} == required for p in self.collection_results.values()):
                raise ToolError('collect_reads must complete one exact required original input collection before effects; prior subsets remain recorded')
        targets = rename_targets(self.spec,c) if c.kind == 'rename' else {}
        conversions = {r.source:r for r in c.conversions}
        for a in serialized:
            if len(a['file_ids']) != 1: raise ToolError('one original source per operation; destination is a complete file path, never just a folder; create one action per file')
            _, name = self.file(a['file_ids'][0])
            if c.kind == 'rename':
                if a['op'] != 'move' or name not in targets or a['destination'] != targets[name]:
                    raise ToolError('global rename target differs; use exact read_task.rename_targets for '+name+': '+str(targets.get(name)))
            elif c.kind == 'convert':
                row = conversions.get(name)
                if not row or a['op'] != 'convert' or a['destination'] != row.destination or a['format'] != row.format:
                    raise ToolError('conversion differs from declared source/destination/format')
            else:
                if name not in required or a['op'] != 'move': raise ToolError('classification only permits moving the declared original text inputs')
                observed = next(r for r in self.reads.values() if r['path']==name and r['sha256']==self.spec['initial_snapshot'][name])
                if observed['status']=='readable' and not observed.get('text','').strip():
                    raise ToolError('empty/whitespace text must stay in place: '+name+'; if no nonblank rule matches need moves, submit_report directly after complete reads')
                destinations = [r.destination_prefix+name[len(c.source_prefix):] for r in c.routes]
                if a['destination'] not in destinations:
                    raise ToolError('classification destination must be one full file path from '+json.dumps(destinations,ensure_ascii=False)+'; choose using actual text, or leave unmatched input in place')
        return super().preview_actions(actions)

    def submit_report(self,summary:str,file_ids:list[str],gaps:list[str],
                      report_kind:Literal['task_result','inspection','literal_search'],search_receipt_id:str|None=None):
        receipt = super().submit_report(summary,file_ids,gaps,report_kind,search_receipt_id)
        body = json.loads((self.output/'report.json').read_text())
        body.update(task_contract_version=VERSION,task_execution_version_sha256=task_version(),
                    reading_contract=reading_contract(self.spec,self.task_contract))
        save(self.output/'report.json',body); receipt['artifact_sha256'] = digest(body)
        return receipt

def serve():
    scene = TaskScene(json.loads(Path(os.environ['FM_TASK_FILE']).read_text()),os.environ['FM_OUTPUT'])
    server = MCPServer('file_management')
    for name in ('read_task','list_files','select_files','pin_file','read_file','collect_reads','hash_files','build_index',
                 'search_index','compare_snapshot','preview_actions','execute_plan','restore_plan','submit_report'):
        server.tool(name=name,annotations=ToolAnnotations(readOnlyHint=name not in ('build_index','execute_plan','restore_plan','submit_report'),
                    destructiveHint=False,openWorldHint=False))(getattr(scene,name))
    server.run()
if __name__ == '__main__': serve()
