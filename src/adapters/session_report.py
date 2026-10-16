"""Source-bound review exports. No model calls, executable markup or source edits."""
from pathlib import Path
import hashlib
import json
import os
import shutil
from uuid import uuid4

from src.adapters.session_files import SessionFiles
from benchmarks.research_report_agent_v2.document_engine import build_document


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SessionReport:
    def __init__(self, files: SessionFiles, category: str):
        if category not in ('paper-review', 'input-review'):
            raise ValueError('report_category_invalid')
        self.files, self.work, self.category = files, files.root.parent, category

    def _directory(self, parent, name):
        path = parent / name
        if path.is_symlink(): raise ValueError('private_report_directory_required')
        path.mkdir(exist_ok=True, mode=0o700)
        if not path.is_dir() or not path.resolve().is_relative_to(self.work):
            raise ValueError('private_report_directory_required')
        return path

    def export(self, title: str, sections: list[dict], source_versions: dict) -> dict:
        """Only publish complete reviewed files after actual PDF layout checks."""
        current = {r['name']:r['sha256'] for r in self.files.list_files()['files']}
        if not current or source_versions != current:
            # Return a bounded public correction instead of an exception which
            # MCP masks as an internal failure. Keep the exact identity guard:
            # display names must never silently alias admitted doc_1-* names.
            return {'exported':False,'reason':'source_versions_mismatch',
                    'required_source_versions':current,
                    'next_step':'Copy the exact complete filename-to-SHA256 map above, including any doc_1- prefix, then export again. No file was published.'}
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 160:
            raise ValueError('Supply a nonempty report title of at most 160 characters.')
        if not isinstance(sections, list) or not 1 <= len(sections) <= 12:
            raise ValueError('Supply 1–12 substantive sections with heading and paragraphs.')
        for section in sections:
            if (not isinstance(section, dict) or set(section) != {'heading','paragraphs'} or
                not isinstance(section['heading'], str) or not section['heading'].strip() or
                not isinstance(section['paragraphs'], list) or not section['paragraphs'] or
                any(not isinstance(p,str) or not p.strip() for p in section['paragraphs'])):
                raise ValueError('Each section needs heading and nonempty paragraph strings; no paths or markup fields.')
        payload = {'title':title,'subtitle':'资料校对与建议' if self.category=='paper-review' else '资料核对与分析准备',
            'sections':sections + [{'heading':'来源与检查范围','paragraphs':[
                '；'.join(name+'（SHA256 '+version[:12]+'）' for name,version in sorted(current.items())),
                '依据上传资料的可提取文字或模型对原图的识别形成；图像文字可能存在识别误差，不代表图片、版式、文献真实性或科研结论已获独立认证。']}],
            'figures':[],'metrics':[],'requirements':{'style':'brief','page_mode':'auto','pages':None}}
        temporary = self._directory(self._directory(self.work,'report-exports'),uuid4().hex)
        result = build_document(payload,temporary)
        if not result['quality_passed']:
            return {'exported':False,'failed_checks':[k for k,v in result.get('audit',{}).get('checks',{}).items() if not v],
                    'next_step':'Revise this report within the requested scope and export again; no rejected draft is downloadable.'}
        markdown = '# '+title+'\n\n'+'\n\n'.join('## '+s['heading']+'\n\n'+'\n\n'.join(s['paragraphs']) for s in payload['sections'])+'\n'
        if {r['name']:r['sha256'] for r in self.files.list_files()['files']} != current:
            raise ValueError('report_source_version_changed')
        output = self._directory(self._directory(self.work,'outputs'),'documents')
        destination = output/uuid4().hex
        # Publish the PDF, Markdown and receipt together. An interrupted write
        # must not leave a partial report in the downloadable output tree.
        staging = self._directory(temporary,'publication')
        pdf,md = staging/(self.category+'.pdf'),staging/(self.category+'.md')
        shutil.copyfile(result['path'],pdf);pdf.chmod(0o600)
        md.write_text(markdown,encoding='utf-8');md.chmod(0o600)
        receipt={'schema_version':1,'kind':'source_bound_review','category':self.category,
            'source_versions':current,'layout_passed':True,'page_count':result['page_count'],
            'scientific_content_certified':False,
            'files':[{'name':(destination/p.name).relative_to(self.work).as_posix(),'sha256':_hash(p),'bytes':p.stat().st_size} for p in (pdf,md)]}
        path=staging/'delivery.json'
        path.write_text(json.dumps(receipt,ensure_ascii=False),encoding='utf-8');path.chmod(0o600)
        os.rename(staging,destination)
        return {'exported':True,'page_count':result['page_count'],'artifacts':receipt['files'],
                'scope':'source_bound_review_not_statistical_or_authenticity_certification'}
