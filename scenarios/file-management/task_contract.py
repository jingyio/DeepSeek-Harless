"""Versioned operation/read acceptance for new tasks; legacy benchmarks stay frozen."""
from __future__ import annotations
import csv, io, json
from pathlib import Path, PurePosixPath
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from common import digest, sha, snapshot

VERSION = 'sss-file-task-v1'

def relative(value):
    p = PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or '\\' in value or str(p) != value or value.startswith('.experiment-copy'):
        raise ValueError('invalid contract relative path')
    return value

class Conversion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: str
    destination: str
    format: Literal['text', 'csv', 'jpeg']

class Route(BaseModel):
    model_config = ConfigDict(extra='forbid')
    literal: str = Field(min_length=1, max_length=120)
    destination_prefix: str

class TaskContract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    version: Literal['sss-file-task-v1']
    kind: Literal['rename', 'convert', 'content_classify']
    source_prefix: str = 'inbox/'
    destination_prefix: str = 'normalized/'
    conversions: list[Conversion] = Field(default_factory=list, max_length=32)
    routes: list[Route] = Field(default_factory=list, max_length=8)
    allow_output_verification_reads: bool = True
    require_output_verification_reads: bool = False
    allow_optional_original_reads: bool = False

    @model_validator(mode='after')
    def valid(self):
        for prefix in (self.source_prefix, self.destination_prefix, *(r.destination_prefix for r in self.routes)):
            if not prefix.endswith('/'): raise ValueError('contract prefix must end with /')
            relative(prefix[:-1])
        for row in self.conversions:
            relative(row.source); relative(row.destination)
            if Path(row.destination).suffix.lower() != {'text':'.txt','csv':'.csv','jpeg':'.jpg'}[row.format]:
                raise ValueError('conversion destination extension differs')
        if len({r.source for r in self.conversions}) != len(self.conversions) or len({r.destination for r in self.conversions}) != len(self.conversions):
            raise ValueError('duplicate conversion input/output')
        if self.kind == 'convert' and (not self.conversions or self.routes): raise ValueError('conversion list required; no classification routes')
        if self.kind == 'content_classify' and (not self.routes or self.conversions): raise ValueError('classification routes required; no conversions')
        if self.kind == 'rename' and (self.conversions or self.routes): raise ValueError('rename cannot include conversions/routes')
        if any(not r.literal.strip() for r in self.routes): raise ValueError('blank route literal')
        if self.require_output_verification_reads and (self.kind != 'convert' or not self.allow_output_verification_reads):
            raise ValueError('required output reads must be authorized conversions')
        if self.allow_optional_original_reads and self.kind != 'rename':
            raise ValueError('optional original reads apply only to metadata rename tasks')
        return self

def contract(spec):
    c = TaskContract.model_validate(spec['task_contract'])
    if c.kind != spec['family']: raise ValueError('contract family differs')
    initial = {n for n in spec['initial_snapshot'] if n != '.experiment-copy'}
    if c.kind == 'convert' and any(r.source not in initial or r.destination in initial for r in c.conversions):
        raise ValueError('conversion source absent or output already exists')
    return c

def rename_targets(spec, c=None):
    c = c or contract(spec)
    names = sorted(n for n in spec['initial_snapshot'] if n.startswith(c.source_prefix))
    return {n: f'{c.destination_prefix}{Path(n).suffix.lower()[1:] or "no-extension"}/item_{i:02d}{Path(n).suffix.lower()}'
            for i, n in enumerate(names, 1)}

def required_inputs(spec, c=None):
    c = c or contract(spec)
    if c.kind == 'rename': return set()
    if c.kind == 'convert': return {r.source for r in c.conversions}
    return {n for n in spec['initial_snapshot'] if n.startswith(c.source_prefix) and Path(n).suffix.lower() in ('.docx','.txt','.md')}

def optional_inputs(spec,c):
    if not c.allow_optional_original_reads: return {}
    result = {n:h for n,h in spec['initial_snapshot'].items() if n!='.experiment-copy'}
    result.update({d:spec['initial_snapshot'][n] for n,d in rename_targets(spec,c).items()})
    return result

def reading_contract(spec, c=None):
    c = c or contract(spec)
    return {'version':VERSION, 'required_input_paths':sorted(required_inputs(spec,c)),
            'allowed_optional_input_paths':sorted(optional_inputs(spec,c)),
            'allowed_output_verification_paths':sorted(r.destination for r in c.conversions) if c.allow_output_verification_reads else [],
            'required_output_verification_paths':sorted(r.destination for r in c.conversions) if c.require_output_verification_reads else [],
            'input_collection':'at least one complete collection containing exactly all required original inputs; earlier subsets remain recorded',
            'empty_text':'actual readable observation and complete collection membership required; empty/whitespace text stays in place',
            'output_reads':'optional, only after successful conversion with a matching current journal and output bytes/version',
            'other_reads':'forbidden; neither repair nor a new report erases earlier reads',
            'parser_limits':'6000 delivered characters; PDF first two physical pages; images metadata only, no OCR'}

def scope_errors(spec, out):
    c = contract(spec); required = required_inputs(spec,c); optional = optional_inputs(spec,c)
    reads = [json.loads(p.read_text()) for p in (Path(out)/'reads').glob('*.json')]
    allowed_outputs = {r.destination for r in c.conversions} if c.allow_output_verification_reads else set()
    errors = []
    for r in reads:
        if r['path'] not in required | allowed_outputs | set(optional): errors.append('read outside declared input/output scope: '+r['path'])
        elif r['path'] in required | set(optional) and r.get('sha256') != optional.get(r['path'],spec['initial_snapshot'].get(r['path'])): errors.append('original input read version differs: '+r['path'])
    if c.require_output_verification_reads and not allowed_outputs <= {r['path'] for r in reads}:
        errors.append('required generated output verification reads missing')
    if not required <= {r['path'] for r in reads if r.get('sha256') == spec['initial_snapshot'].get(r['path'])}:
        errors.append('required original input reads missing (including empty text)')
    packets = [json.loads(p.read_text()) for p in (Path(out)/'collections').glob('*/summary.json')]
    if required and not any({r['path'] for r in p['files']} == required for p in packets): errors.append('no complete exact original input collection')
    for p in packets:
        if p.get('coverage_sha256') != digest(p['files']): errors.append('collection coverage digest differs')
        for row in p['files']:
            actual = next((r for r in reads if r['source_id'] == row['source_id']), None)
            if not actual or row.get('read_sha256') != digest(actual) or any(row.get(k) != actual.get(k) for k in ('path','file_id','source_version','status')):
                errors.append('collection not bound to actual read observation')
    return errors, reads

def verify_task(spec, report, out, events):
    """Machine postconditions, actual read scope and versioned receipts; no semantic quality claim."""
    from file_tools import FileScene
    from report_tools import CONTRACT_VERSION, report_version
    from task_tools import task_version
    c = contract(spec); errors, reads = scope_errors(spec,out)
    calls = {e['data']['callId']:e for e in events if e.get('type') == 'tool/call'}
    actual = []
    for e in events:
        if e.get('type') != 'tool/result': continue
        for block in e['data']['message'].get('content',[]):
            call = calls.get(block.get('toolCallId'))
            if block.get('type') != 'tool-result' or block.get('isError') or not call: continue
            try: value = json.loads(block['content'][0]['text'])
            except (ValueError,KeyError,IndexError,TypeError): continue
            actual.append((call['data']['name'],call['seq'],e['seq'],value))
    root = Path(spec['workspace']); final = snapshot(root); expected = dict(spec['initial_snapshot'])
    parser = FileScene.__new__(FileScene); moved = {}
    if c.kind == 'rename': moved = rename_targets(spec,c)
    elif c.kind == 'content_classify':
        for name in sorted(required_inputs(spec,c)):
            observed = next((r for r in reads if r['path'] == name and r.get('sha256') == expected[name]), None)
            if observed and observed.get('status') == 'readable' and observed.get('text','').strip():
                route = next((r for r in c.routes if r.literal.casefold() in observed['text'].casefold()), None)
                if route: moved[name] = route.destination_prefix + name[len(c.source_prefix):]
    for name, dest in moved.items(): expected[dest] = expected.pop(name)
    generated = {}
    if c.kind == 'convert':
        for row in c.conversions:
            p = root / row.destination
            if not p.is_file(): errors.append('conversion output missing: '+row.destination); continue
            expected[row.destination] = sha(p)
            try:
                if row.format == 'jpeg':
                    from PIL import Image
                    with Image.open(root/row.source) as original, Image.open(p) as converted:
                        converted.verify()
                        if converted.format != 'JPEG' or converted.size != original.size: errors.append('JPEG format/dimensions differ')
                        buffer = io.BytesIO(); original.convert('RGB').save(buffer,'JPEG')
                        if p.read_bytes() != buffer.getvalue(): errors.append('JPEG pixels/encoding differ from declared conversion')
                else:
                    status,text,meta = parser.parse(root/row.source)
                    if status != 'readable': errors.append('conversion source unreadable')
                    elif row.format == 'text' and p.read_text(encoding='utf-8') != text: errors.append('converted text content differs')
                    elif row.format == 'csv' and list(csv.reader(io.StringIO(p.read_text(encoding='utf-8')))) != meta['rows']: errors.append('converted CSV rows differ')
            except Exception as exc: errors.append('conversion validation '+type(exc).__name__)
            generated[row.destination] = row
    if final != expected: errors.append('workspace postconditions differ; preserve every unrelated original byte')
    # Replay observations against bytes still present in the final workspace (moves retain extensions).
    for r in reads:
        matches = [v for name,_,_,v in actual if name == 'mcp__file_management__read_file' and digest(v) == digest(r)]
        if not matches: errors.append('read observation absent from successful native tool events: '+r['path'])
        if r.get('source_version') != digest({'path':r['path'],'sha':r.get('sha256'),'parser':'fm-parser-v1'}): errors.append('read source version differs')
        path = root / moved.get(r['path'],r['path'])
        if not path.is_file() or sha(path) != r.get('sha256'): errors.append('actual read bytes no longer verifiable: '+r['path']); continue
        try: status,text,meta = parser.parse(path)
        except Exception:
            if r.get('status') != 'unreadable': errors.append('read parser status differs')
        else:
            if (r.get('status'),r.get('text',''),r.get('metadata',{}),r.get('truncated',False)) != (status,text[:6000],meta,len(text)>6000):
                errors.append('read parser observation differs: '+r['path'])
        if r['path'] in generated:
            row = generated[r['path']]; origin_id = 'file:local:'+digest({'path':row.source,'sha':spec['initial_snapshot'][row.source]})[:24]
            matches = []
            for p in (Path(out)/'journals').glob('*.json'):
                j = json.loads(p.read_text())
                if j.get('status') == 'executed_verified' and j.get('after',{}).get(row.destination) == r['sha256'] and any(
                    a['op']=='convert' and a['file_ids']==[origin_id] and a['destination']==row.destination and a['format']==row.format for a in j.get('completed',[])):
                    matches.append(j)
            if not matches: errors.append('output read lacks successful matching conversion journal')
            if not any(j['before'].get(row.source)==spec['initial_snapshot'][row.source] for j in matches): errors.append('output journal input version differs')
            read_calls = [call_seq for name,call_seq,_,value in actual if name=='mcp__file_management__read_file' and digest(value)==digest(r)]
            if not any(result_seq < read_seq and receipt.get('status')=='executed_verified' and any(
                    receipt.get('plan_id')==j['plan_id'] and receipt.get('journal_sha256')==digest(j) for j in matches)
                    for name,_,result_seq,receipt in actual if name=='mcp__file_management__execute_plan' for read_seq in read_calls):
                errors.append('output verification read preceded successful conversion receipt')
    for p in (Path(out)/'collections').glob('*/summary.json'):
        packet = json.loads(p.read_text())
        if not any(name=='mcp__file_management__collect_reads' and digest(value)==digest(packet) for name,_,_,value in actual):
            errors.append('collection summary absent from successful native tool events')
    if not report: errors.append('no verified task report')
    else:
        if (report.get('contract_version') != CONTRACT_VERSION or report.get('report_kind') != 'task_result'
                or report.get('report_execution_version_sha256') != report_version()): errors.append('report contract/version differs')
        if report.get('task_contract_version') != VERSION or report.get('task_execution_version_sha256') != task_version(): errors.append('task acceptance version differs')
        if report.get('input_sha256') != digest(spec) or report.get('final_snapshot') != final: errors.append('report task/snapshot differs')
        wanted = {'file:local:'+digest({'path':n,'sha':h})[:24] for n,h in final.items() if n!='.experiment-copy'}
        if set(report.get('file_ids',[])) != wanted or len(report.get('file_ids',[])) != len(wanted): errors.append('report must cover all current result identities')
        if report.get('read_statuses') != {r['source_id']:r['status'] for r in reads}: errors.append('report reading statuses differ')
    return {'passed':not errors,'errors':errors,'required_input_paths':sorted(required_inputs(spec,c)),
            'actual_read_paths':sorted({r['path'] for r in reads}),'output_verification_read_paths':sorted({r['path'] for r in reads}&set(generated)),
            'final_snapshot_sha256':digest(final),'contract_version':VERSION,'human_blind_review':False,'real_business_semantic_generalization':False}
