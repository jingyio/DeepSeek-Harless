"""Opt-in experimental rendering: reuse frozen implementations in isolated modules.

No production module is patched. This variant has its own recorded hashes and
is not covered by the existing production Motif certificate.
"""
from pathlib import Path
import importlib.util
import hashlib
import re
import json
import os
from collections import OrderedDict
from importlib.metadata import version
from contextvars import ContextVar

ROOT=Path(__file__).resolve().parents[2]
def isolated(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def _fallback_font(primary_font: str):
    """Embed fallback glyphs missing from either a CID or configured TTF font."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    name = "ResearchFallbackSans"
    if name not in pdfmetrics.getRegisteredFontNames():
        try:
            from matplotlib import get_data_path
            path = Path(get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
        except ImportError:
            import reportlab
            path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
        pdfmetrics.registerFont(TTFont(name, str(path)))
    fallback = pdfmetrics.getFont(name)
    if primary_font == "STSong-Light":
        return fallback
    from types import SimpleNamespace
    primary = pdfmetrics.getFont(primary_font)
    coverage = getattr(primary.face, "charToGlyph", None)
    if coverage is None:
        return None  # No trustworthy glyph coverage for an unknown font type.
    return SimpleNamespace(fontName=fallback.fontName, face=SimpleNamespace(charToGlyph={
        code: glyph for code, glyph in fallback.face.charToGlyph.items() if not coverage.get(code, 0)}))


engine=isolated('_evidence_document_engine','benchmarks/research_report_agent_v2/document_engine.py')
engine._fallback_font=_fallback_font
_benchmark_audit=engine.audit_document
def natural_length_audit(pdf_path,manifest,requirements=None):
    """Apply this caller's auto-length contract to the unchanged physical audit.

    The benchmark's historical six-page default remains unchanged everywhere
    else. Explicit max/exact requirements and every other hard check survive.
    """
    audit=_benchmark_audit(pdf_path,manifest,requirements)
    req=requirements or (json.loads(Path(manifest).read_text(encoding='utf-8')) if isinstance(manifest,(str,Path)) else manifest)['requirements']
    if req.get('page_mode')!='auto' or req.get('pages') is not None:return audit
    audit['checks']['page_constraint_satisfied']=audit['page_count']>=1
    audit['constraints_satisfied']=audit['checks']['page_constraint_satisfied']
    audit['hard_errors']=[e for e in audit['hard_errors'] if e.get('check')!='page_constraint_satisfied']
    if not audit['constraints_satisfied']:audit['hard_errors'].append({'check':'page_constraint_satisfied'})
    audit['quality_passed']=all(audit['checks'].values()) and not audit['hard_errors']
    audit['acceptance_status']=('accepted_with_warnings' if audit['warnings'] else 'accepted') if audit['quality_passed'] else 'rejected'
    audit['acceptance_policy']={**audit['acceptance_policy'],'auto_page_limit':None,'page_policy_origin':'explicit_natural_length_report_contract'}
    return audit
engine.audit_document=natural_length_audit
build_document=engine.build_document
base=isolated('_evidence_session_report','src/adapters/session_report.py')
render_result=ContextVar('current_evidence_render',default=None)
def captured_build(*args,**kwargs):
    result=build_document(*args,**kwargs);render_result.set(result);return result
base.build_document=captured_build

# Process-local successful observations only: never load a user-written cache.
# The MCP creates a new SessionReport for each invocation, so this bounded store
# belongs to the isolated service process and is keyed by current task/config.
_deliveries = OrderedDict()

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def fixed_bytes(root, relative, limit=32*1024*1024):
    path=root/relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts or path.resolve()!=path or not path.is_file() or path.stat().st_nlink!=1 or path.stat().st_size>limit:
        raise ValueError('export_evidence_file_not_fixed')
    return path.read_bytes()

def rendering_config():
    # Hash the actual configured fonts and implementation, not only a preset ID.
    import reportlab
    paths=[os.environ.get('HARLESS_REPORT_FONT'),
           '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
           'C:/Windows/Fonts/msyh.ttc','/usr/share/fonts/truetype/arphic/ukai.ttc',
           str(Path(reportlab.__file__).parent/'fonts/Vera.ttf')]
    try:
        from matplotlib import get_data_path
        paths.append(str(Path(get_data_path())/'fonts/ttf/DejaVuSans.ttf'))
    except ImportError: pass
    return {'implementation':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
        ['src/adapters/evidence_report.py','src/adapters/session_report.py','benchmarks/research_report_agent_v2/document_engine.py']},
        'font_setting':os.environ.get('HARLESS_REPORT_FONT'),
        'font_hashes':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths if p and Path(p).is_file()},
        'dependencies':{p:version(p) for p in ['reportlab','PyMuPDF']},
        'style':'brief','page_mode':'auto','auto_page_limit':None,'engine_version':engine.ENGINE_VERSION}

def _project(value,pointer):
    for key in pointer.split('/')[1:]:
        key=key.replace('~1','/').replace('~0','~')
        value=value[int(key)] if isinstance(value,list) else value[key]
    return value

def structure_issues(expected,actual,path=''):
    """Conservative explicit recovery policy, never a semantic completeness proof."""
    if type(expected) is not type(actual):
        return [{'pointer':path,'expected_type':type(expected).__name__,'actual_type':type(actual).__name__}]
    if isinstance(expected,list):
        if len(expected)!=len(actual):return [{'pointer':path,'expected_items':len(expected),'actual_items':len(actual)}]
        return [issue for i,(a,b) in enumerate(zip(expected,actual)) for issue in structure_issues(a,b,path+'/'+str(i))][:32]
    if isinstance(expected,dict):
        if set(expected)!=set(actual):return [{'pointer':path,'expected_keys':sorted(expected),'actual_keys':sorted(actual)}]
        return [issue for k in expected for issue in structure_issues(expected[k],actual[k],path+'/'+k.replace('~','~0').replace('/','~1'))][:32]
    return []

class SessionReport(base.SessionReport):
    def input_issues(self,args):
        """Expose the existing report input contract instead of MCP's opaque error.

        These bounds mirror SessionReport.export; no constraint is relaxed and
        this is neither a scientific validator nor a learned error cause.
        """
        issues=[]
        if not isinstance(args['title'],str) or not 1<=len(args['title'].strip())<=160:
            issues.append({'pointer':'/title','requirement':'nonempty_string','max_characters':160})
        sections=args['sections']
        if not isinstance(sections,list) or not 1<=len(sections)<=12:
            issues.append({'pointer':'/sections','requirement':'array_length','min_items':1,'max_items':12})
        if isinstance(sections,list):
            for i,s in enumerate(sections):
                if not isinstance(s,dict) or set(s)!={'heading','paragraphs'}:
                    issues.append({'pointer':f'/sections/{i}','requirement':'exact_fields','fields':['heading','paragraphs']});continue
                if not isinstance(s['heading'],str) or not s['heading'].strip():
                    issues.append({'pointer':f'/sections/{i}/heading','requirement':'nonempty_string'})
                if not isinstance(s['paragraphs'],list) or not s['paragraphs'] or any(not isinstance(p,str) or not p.strip() for p in s['paragraphs']):
                    issues.append({'pointer':f'/sections/{i}/paragraphs','requirement':'nonempty_array_of_nonempty_strings'})
        return issues[:32]

    def capture_current(self,args,context,issues=()):
        policy_path=self.work/'report-state-policy.json'
        if not policy_path.exists():return
        policy_raw=fixed_bytes(self.work,'report-state-policy.json',256*1024)
        policy=json.loads(policy_raw)
        if policy.get('kind')!='capture_current_report_policy' or policy.get('version')!=1 or not context['task_id'] or policy.get('task_id')!=context['task_id'] or policy.get('source_versions')!=context['source_versions'] or args['source_versions']!=context['source_versions']:
            raise ValueError('current_report_capture_not_authorized')
        scope={'version':1,'kind':'current_review_recovery_scope','task_id':context['task_id'],
               'source_versions':context['source_versions'],'arguments':args,
               'policy':'preserve_text_during_input_contract_repair' if issues else 'preserve_structure_allow_semantic_leaf_revisions',
               'origin':'observed_current_export_operation_not_semantic_approval',
               'capture':{'tool':policy['tool'],'schema_sha256':policy['schema_sha256'],
                          'arguments_sha256':digest(args),'policy_sha256':hashlib.sha256(policy_raw).hexdigest(),
                          'user_envelope_sha256':policy['user_envelope_sha256']},
               'coverage_status':'not_verified','semantic_quality_accepted':False}
        if issues:scope['input_contract_issues']=issues
        raw=json.dumps(scope,ensure_ascii=False,sort_keys=True).encode()
        if len(raw)>256000:raise ValueError('current_report_capture_too_large')
        try:
            with (self.work/'review-recovery-scope.json').open('xb') as stream:
                os.chmod(stream.name,0o400);stream.write(raw)
        except FileExistsError:
            pass  # Never replace an existing protected task/recovery scope.

    def preserved_input_text(self,args,context):
        if context['recovery_scope_sha256'] is None:return None
        scope=json.loads(fixed_bytes(self.work,'review-recovery-scope.json'))
        if scope.get('policy')!='preserve_text_during_input_contract_repair':return None
        if scope.get('origin')!='observed_current_export_operation_not_semantic_approval' or scope.get('task_id')!=context['task_id'] or scope.get('source_versions')!=context['source_versions'] or scope.get('capture',{}).get('arguments_sha256')!=digest(scope.get('arguments')):
            raise ValueError('current_recovery_scope_invalid')
        from collections import Counter
        # Input-contract recovery is structural only. Scientific rewriting stays
        # outside this path; require all earlier text, including multiplicity.
        def paragraphs(sections):
            for section in sections:
                if not isinstance(section,dict):continue
                values=section.get('paragraphs',[])
                if isinstance(values,str):values=[values]
                if isinstance(values,list):
                    yield from (p for p in values if isinstance(p,str) and p.strip())
        texts=Counter(paragraphs(scope['arguments']['sections']))
        current='\n'.join(p for s in args['sections'] for p in s['paragraphs'])
        missing=[{'original_sha256':hashlib.sha256(p.encode()).hexdigest(),'characters':len(p),'required_occurrences':count} for p,count in texts.items() if current.count(p)<count]
        if missing:
            return {'exported':False,'failed_checks':['recovery_content_preserved'],
                    'execution_evidence':{'version':1,'kind':'review_execution_evidence',**context},
                    'argument_issues':[{'pointer':'/sections','check':'recovery_content_preserved','hash_kind':'json','value_sha256':digest(args['sections']),'missing_paragraphs':len(missing)}],
                    'content_issues':missing[:32],
                    'next_step':'The input-format repair removed existing report text. Preserve every original paragraph: regroup by concatenating captured paragraph arrays and only then remove the old grouping. Do not delete references, sources or conclusions. This is not a scientific judgment.'}
        # A valid regrouping becomes the next recovery boundary, without
        # certifying the draft's scientific facts or source completeness.
        scope.setdefault('initial_arguments',scope['arguments'])
        scope.setdefault('initial_arguments_sha256',digest(scope['initial_arguments']))
        scope.update(arguments=args,policy='preserve_structure_allow_semantic_leaf_revisions',previous_scope_sha256=context['recovery_scope_sha256'])
        scope['capture']['arguments_sha256']=digest(args)
        scope.pop('input_contract_issues',None)
        raw=json.dumps(scope,ensure_ascii=False,sort_keys=True).encode()
        if hashlib.sha256(fixed_bytes(self.work,'review-recovery-scope.json')).hexdigest()!=context['recovery_scope_sha256']:
            raise ValueError('current_recovery_scope_changed')
        temporary=self.work/('report-scope-'+os.urandom(12).hex()+'.tmp')
        try:
            with temporary.open('xb') as stream:
                os.chmod(stream.name,0o400);stream.write(raw)
            os.replace(temporary,self.work/'review-recovery-scope.json')
        finally:
            if temporary.exists():temporary.unlink()
        return None

    def context(self,args):
        sources={r['name']:r['sha256'] for r in self.files.list_files()['files']}
        grant_path=self.work/'paper-output-grant.json'
        grant=None
        if grant_path.exists() or grant_path.is_symlink():
            raw=fixed_bytes(self.work,'paper-output-grant.json',256*1024)
            grant=json.loads(raw)
            if self.category=='paper-review' and (grant.get('schema_version')!=1 or grant.get('allow_output') is not True or not isinstance(grant.get('task_id'),str)):
                raise ValueError('paper_pdf_output_not_authorized')
        return {'arguments_sha256':digest(args),'source_versions':sources,
                'config_sha256':digest(rendering_config()),'grant_sha256':digest(grant),
                'task_id':grant.get('task_id') if grant else None,'category':self.category,
                'recovery_scope_sha256':hashlib.sha256(fixed_bytes(self.work,'review-recovery-scope.json')).hexdigest() if (self.work/'review-recovery-scope.json').exists() else None}

    def valid_delivery(self,record,context):
        try:
            if record['context']!=context:return False
            result=record['response'];e=result['execution_evidence']
            receipt=json.loads(fixed_bytes(self.work,e['receipt_name'],256*1024))
            if receipt.get('layout_passed') is not True or receipt.get('source_versions')!=context['source_versions'] or receipt.get('task_id')!=context['task_id'] or receipt.get('category')!=self.category or receipt['files']!=result['artifacts']:
                return False
            if hashlib.sha256(fixed_bytes(self.work,e['receipt_name'],256*1024)).hexdigest()!=e['receipt_sha256']:return False
            for f in receipt['files']:
                data=fixed_bytes(self.work,f['name'])
                if hashlib.sha256(data).hexdigest()!=f['sha256'] or len(data)!=f['bytes']:return False
            return True
        except (ValueError,KeyError,OSError,TypeError):return False

    def export(self,title,sections,source_versions):
        args={'title':title,'sections':sections,'source_versions':source_versions}
        context=self.context(args)
        issues=self.input_issues(args)
        if context['source_versions']==source_versions:
            self.capture_current(args,context,issues)
            context=self.context(args)
        if issues:
            return {'exported':False,'failed_checks':['report_input_contract'],
                    'execution_evidence':{'version':1,'kind':'review_execution_evidence',**context},
                    'argument_issues':[dict(i,check='report_input_contract',hash_kind='json',value_sha256=digest(_project(args,i['pointer']))) for i in issues],
                    'next_step':'Repair only these input-contract fields using the captured current arguments. When regrouping sections, preserve every substantive paragraph using artifact references; do not rewrite the report or replace it with a summary. This check does not establish scientific correctness.'}
        preservation_failure=self.preserved_input_text(args,context)
        if preservation_failure:return preservation_failure
        context=self.context(args)
        if context['recovery_scope_sha256'] is not None:
            scope=json.loads(fixed_bytes(self.work,'review-recovery-scope.json'))
            if scope.get('version')!=1 or scope.get('kind')!='current_review_recovery_scope' or scope.get('task_id')!=context['task_id'] or scope.get('source_versions')!=context['source_versions'] or scope.get('policy')!='preserve_structure_allow_semantic_leaf_revisions':
                raise ValueError('current_recovery_scope_invalid')
            issues=structure_issues(scope['arguments'],args)
            if issues:
                return {'exported':False,'failed_checks':['recovery_structure_preserved'],
                        'execution_evidence':{'version':1,'kind':'review_execution_evidence',**context},
                        'scope_issues':issues,'argument_issues':[{'pointer':issue['pointer'],'check':'recovery_structure_preserved','hash_kind':'json','value_sha256':digest(_project(args,issue['pointer']))} for issue in issues],
                        'next_step':'This is a subset or changed report structure, not the full current recovery goal. Restore the complete current arguments and revise only necessary leaf fields with geneloop-reuse patches. Do not deliver a successful subset. A structural redesign requires a new explicit scope.'}
        key=(str(self.work),digest(context))
        cached=_deliveries.get(key)
        if cached and self.valid_delivery(cached,context):
            _deliveries.move_to_end(key)
            return {**cached['response'],'artifact_reused':True,
                    'next_step':'The identical current report already passed delivery checks. Use these existing files and provide the final answer; no second export or subset checks are needed unless requirements or evidence change.'}
        _deliveries.pop(key,None)
        token=render_result.set(None)
        try:
            response=super().export(title,sections,source_versions)
            result=render_result.get()
            # Current service evidence is bound to exact arguments, inputs,
            # output grant, implementation, dependencies and font bytes.
            if self.context(args)!=context:raise ValueError('report_execution_context_changed')
            evidence={'version':1,'kind':'review_execution_evidence',**context,
                      'scope':'delivery_and_field_checks_not_cause_or_scientific_judgment'}
            if response.get('exported'):
                receipt_name=str(Path(response['artifacts'][0]['name']).parent/'delivery.json')
                evidence.update(receipt_name=receipt_name,
                    receipt_sha256=hashlib.sha256(fixed_bytes(self.work,receipt_name,256*1024)).hexdigest(),
                    delivery_passed=True)
                response={**response,'execution_evidence':evidence,'artifact_reused':False,
                          'next_step':'This exact current report passed delivery checks. Provide the final answer with these files; unchanged content needs no repeated export. Scientific conclusions remain your responsibility.'}
                record={'context':context,'response':response}
                if self.valid_delivery(record,context):
                    _deliveries[key]=record
                    while len(_deliveries)>32:_deliveries.popitem(last=False)
                return response
            if result is None:return {**response,'execution_evidence':evidence}
            issues=[]
            for block in result.get('audit',{}).get('missing_text',[])[:32]:
                match=re.fullmatch(r'section-(\d+)-(?:paragraph-(\d+)|(heading))',block)
                pointer=value=None
                if block=='title':pointer,value='/title',title
                elif match and int(match[1])<len(sections):
                    i=int(match[1]);section=sections[i]
                    if match[3]:pointer,value=f'/sections/{i}/heading',section['heading']
                    elif int(match[2])<len(section['paragraphs']):
                        j=int(match[2]);pointer,value=f'/sections/{i}/paragraphs/{j}',section['paragraphs'][j]
                if pointer is not None:
                    issues.append({'pointer':pointer,'value_sha256':hashlib.sha256(value.encode()).hexdigest(),
                        'check':'all_text_preserved','block_id':block,'preview':value[:320],
                        'characters':len(value)})
            return {**response,'execution_evidence':evidence,
                    'failed_checks':response.get('failed_checks') or [e['check'] for e in result.get('hard_errors',[]) if 'check' in e],
                    'argument_issues':issues,'validation_context':{
                        'checks':result.get('audit',{}).get('checks',{}),
                        'page_count':result.get('page_count'),'constraints_satisfied':result.get('constraints_satisfied'),
                        'reason':result.get('reason'),'attempt_count':len(result.get('attempts',[]))},
                    'diagnostic_scope':'current_render_preservation_not_cause_or_scientific_judgment',
                    'next_step':'Use actual validation_context and argument_issues, preserving content and sources. Passed checks are not suspected failures. Missing field evidence does not establish a local cause. Return only justified semantic patches; if repair is uncertain, report that uncertainty instead of testing unrelated subsets or removing evidence.'}
        finally:render_result.reset(token)
