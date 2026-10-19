"""Independent admission/replay for prepared cross-provider continuations.

The model still selects the provider, tool and every semantic argument. Only
exact prepared-call execution and receipt inspection can bypass a model turn.
New provider businesses need a verifier; mere transport success is insufficient.
"""
from __future__ import annotations
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from src.motif_core.offline.experience_registry import digest, read, sha
from src.adapters.general_tools import digest as gateway_digest

ROOT = Path(__file__).resolve().parents[2]


def operator_contract(name):
    base = {'format': 'sss-mcp-learning-v1', 'effect': 'semantic', 'auto_continue': False, 'exports': []}
    if name == 'prepare_tool_call':
        return {**base, 'effect': 'stage', 'statuses': ['prepared_certifiable'], 'exports': ['request_id'],
                'request_lane': 'sss-prepared-request-v1'}
    if name == 'execute_tool_call':
        return {**base, 'effect': 'authorized_write', 'auto_continue': True,
                'statuses': ['completed'], 'exports': ['receipt_id'], 'request_lane':'sss-prepared-request-v1'}
    if name == 'inspect_tool_result':
        return {**base, 'effect': 'read', 'auto_continue': True, 'statuses': ['completed'], 'request_lane':'sss-prepared-request-v1'}
    return base


def eligible(q):
    default = next(r for r in read(ROOT/'scenarios/file-management/general-tools.json')['providers'] if r['id'] == 'workspace-runtime')
    return (q.get('provider_contract') == default and q.get('provider_id') == 'workspace-runtime'
            and q.get('tool_name') in ('edit_text', 'create_text'))


def ordinary_boundary(q):
    default = next(r for r in read(ROOT/'scenarios/file-management/general-tools.json')['providers'] if r['id'] == 'workspace-runtime')
    return (q.get('provider_contract')==default and q.get('provider_id')=='workspace-runtime'
            and q.get('tool_name') in ('runtime_capabilities','execute_code'))


def lane(q,*,preparing=False):
    # Only this independently replayable provider has immutable inputs and
    # fresh output directories per execution. Registration alone grants nothing.
    isolated=eligible(q) or ordinary_boundary(q)
    if not isolated and not preparing:
        return None
    return {'format':'sss-prepared-request-v1','request_id':q['request_id'],
            'request_sha256':q['request_sha256'],'isolated_outputs':isolated,'stage_only':not isolated}


def verify_general_tools(spec, record, origin, rows):
    work = Path(record['delivery'])/'general/work'
    access = work/'tool-access'
    if not access.exists():
        return
    original = {n: h for n, h in spec['initial_tree']['workspace']['files'].items()
                if n not in ('.experiment-copy', '.management-copy')}
    actual_inputs = {p.relative_to(work/'inputs').as_posix(): sha(p) for p in (work/'inputs').rglob('*') if p.is_file()}
    if actual_inputs != original or read(work/'approved-inputs.json')['files'] != original:
        raise ValueError('cross-tool input identity changed')
    output_files = set()
    scope=next(r['out']['learning_scope'] for r in rows if r['name'].endswith('__read_task'))
    enrollment=read(origin/'enrollment.json') if (origin/'enrollment.json').exists() else {'delivery':record['delivery']}
    original_outputs=Path(enrollment['delivery'])/'general/work/outputs'
    def sealed_artifact(value,category):
        original=Path(value['path'])
        try:relative=original.relative_to(original_outputs/category)
        except ValueError as error:raise ValueError('cross-tool artifact outside original enrolled output') from error
        if '..' in relative.parts:raise ValueError('cross-tool artifact traversal')
        target=work/'outputs'/category/relative
        if target.is_symlink() or not target.resolve().is_relative_to((work/'outputs'/category).resolve()):raise ValueError('cross-tool sealed artifact escaped')
        return target
    for file in (access/'requests').glob('*.json'):
        q = read(file)
        if q['scope']!={**scope,'read_only':spec.get('rules',{}).get('read_only',False)}:
            raise ValueError('cross-tool original permission scope differs')
        expected = gateway_digest({k: v for k, v in q.items() if k not in ('status', 'created_at', 'request_sha256', 'receipt_id')})
        if q['request_sha256'] != expected:
            raise ValueError('cross-tool prepared request mutated')
        if q['status'] == 'prepared':
            continue
        safe=eligible(q);boundary=ordinary_boundary(q)
        if not safe and not boundary:
            raise ValueError('cross-tool business has no independent replay adapter')
        if q['status'] not in (('completed',) if safe else ('completed','tool_error')):
            raise ValueError('failed or unknown cross-tool effects cannot certify')
        if list(Draft202012Validator(q['tool_schema']).iter_errors(q['arguments'])):
            raise ValueError('cross-tool actual argument schema differs')
        if q['catalog_sha256'] != gateway_digest({'provider': q['provider_contract'], 'tools': q['catalog_tools'], 'scope': q['scope']}):
            raise ValueError('cross-tool catalog proof differs')
        r = read(access/'results'/f"{q['receipt_id']}.json")
        if (r['receipt_sha256'] != gateway_digest({k: v for k, v in r.items() if k != 'receipt_sha256'})
                or r['request_sha256'] != q['request_sha256'] or r['scope'] != q['scope']
                or r['status'] != q['status'] or r['provider_id'] != q['provider_id'] or r['tool_name'] != q['tool_name']):
            raise ValueError('cross-tool actual receipt differs')
        prepare_rows = [x for x in rows if x['name'].endswith('__prepare_tool_call') and (x.get('out') or {}).get('request_id') == q['request_id']]
        execute_rows = [x for x in rows if x['name'].endswith('__execute_tool_call') and x['args'].get('request_id') == q['request_id']]
        inspect_rows = [x for x in rows if x['name'].endswith('__inspect_tool_result') and x['args'].get('receipt_id') == q['receipt_id']]
        if (len(prepare_rows) != 1 or not execute_rows or not inspect_rows
                or prepare_rows[0]['args'] != {k: q[k] for k in ('provider_id', 'tool_name', 'arguments')}
                or prepare_rows[0]['out'].get('request_sha256')!=q['request_sha256'] or prepare_rows[0]['out'].get('status')!=('prepared_certifiable' if safe else 'prepared')
                or any(not x.get('out') or x['out'].get('receipt_id')!=q['receipt_id'] or x['out'].get('status')!=q['status'] or safe and x['out'].get('_sss_authorized') is not True for x in execute_rows)
                or any({k:v for k,v in x['out'].items() if k not in ('_sss_scope','_sss_authorized','_sss_request_lane')} != r for x in inspect_rows)
                or any(x['out'].get('_sss_request_lane')!=lane(q) for x in [*prepare_rows,*execute_rows,*inspect_rows])):
            raise ValueError('cross-tool receipt lacks original native calls')
        result = r['actual_mcp_result']
        if boundary and any(x.get('generated') or str(x.get('call_id','')).startswith('sss-') or x.get('message_seq') is None for x in [*prepare_rows,*execute_rows,*inspect_rows]):
            raise ValueError('ordinary semantic boundary cannot become a generated business decision')
        if result.get('isError', result.get('is_error', False)):
            if boundary:continue
            raise ValueError('provider reported an error')
        value = result.get('structuredContent', result.get('structured_content'))
        if value is None:
            value = json.loads(next(c['text'] for c in result['content'] if c['type'] == 'text'))
        args = q['arguments']
        if boundary:
            if q['tool_name']=='execute_code':
                import hashlib
                if value.get('program_sha256')!=hashlib.sha256(args['program'].encode()).hexdigest() or value.get('source_files_unchanged') is not True:
                    raise ValueError('ordinary isolated-code provenance changed')
                for artifact in value.get('artifacts',[]):
                    target=sealed_artifact(artifact,'code')
                    if sha(target)!=artifact['sha256'] or target.stat().st_size!=artifact['bytes']:raise ValueError('ordinary code artifact identity differs')
                    output_files.add(target.resolve())
            # These native calls are retained as semantic barriers. No code or
            # capability decision is inferred, replayed, or certified as a Motif.
            continue
        if q['tool_name'] == 'edit_text':
            name = args['name']
            if name not in original or original[name] != args['sha256']:
                raise ValueError('cross-tool edit source outside original authority')
            text = (origin/'pristine'/name).read_bytes().decode('utf-8')
            for replacement in args['replacements']:
                if text.count(replacement['old']) != replacement.get('expected_count', 1):
                    raise ValueError('cross-tool literal edit precondition differs')
                text = text.replace(replacement['old'], replacement['new'])
        else:
            text = args['text']
        artifact = sealed_artifact(value,'edited')
        allowed = work/'outputs/edited'
        if (not artifact.resolve().is_relative_to(allowed.resolve()) or artifact.is_symlink()
                or value['name'] != args['destination'] or artifact.read_bytes() != text.encode('utf-8')
                or value['sha256'] != sha(artifact) or value['bytes'] != len(text.encode('utf-8'))
                or value['originals_modified'] is not False):
            raise ValueError('cross-tool output differs from independent replay')
        if read(artifact.parents[len(Path(args['destination']).parts)-1]/'derivation.json') != value:
            raise ValueError('cross-tool derivation changed')
        output_files.update([artifact.resolve(), (artifact.parents[len(Path(args['destination']).parts)-1]/'derivation.json').resolve()])
    actual_outputs = {p.resolve() for p in (work/'outputs').rglob('*') if p.is_file()}
    if output_files != actual_outputs:
        raise ValueError('unaccounted cross-tool output')
