"""Restartable whole-document reading. Only returned chunks count as coverage."""
from __future__ import annotations
import copy,json,os,shutil,subprocess
from pathlib import Path
from typing import Literal
from mcp.server.mcpserver.exceptions import ToolError
from common import digest,sha
from plan_tools import atomic

VERSION='sss-document-reading-v1'
CHUNK=6000
TOOLS=['open_document','read_document_chunk','document_coverage','view_document_page','search_document']

def contract(name):
    return {'format':'sss-mcp-learning-v1','effect':'read','auto_continue':name in ('read_document_chunk','document_coverage'),
            **({'flow_interleaving':True} if name in ('open_document','read_document_chunk','document_coverage') else {}),
            **({'control_fields':{'next_request_id':'nullable_handle','empty_text':'boolean'}} if name=='read_document_chunk' else {}),
            **({'control_fields':{'complete':'boolean'}} if name=='document_coverage' else {}),
            'exports':{'open_document':['document_id','request_id'],
                       'read_document_chunk':['document_id','next_request_id'],
                       'document_coverage':[],'view_document_page':['view_id'],'search_document':[]}[name]}

def run(args,timeout=30):
    result=subprocess.run(args,capture_output=True,timeout=timeout,env={
        'PATH':os.environ.get('PATH','/usr/bin:/bin:/opt/homebrew/bin'),
        **{k:os.environ[k] for k in ('SystemRoot','ComSpec','WINDIR','TEMP','TMP') if k in os.environ},
        'LANG':'en_US.UTF-8','LC_ALL':'en_US.UTF-8'})
    if result.returncode:raise ValueError('document parser failed: '+Path(str(args[0])).name)
    if len(result.stdout)>16*1024*1024:raise ValueError('one page exceeds parser response limit')
    return result.stdout.decode('utf-8',errors='strict')

def executable(variable,default):
    # An explicit operator override must fail visibly if broken; only the
    # absence of a default CLI selects the already installed PyMuPDF backend.
    return os.environ.get(variable) or shutil.which(default)

def render_pdf(path,page,prefix,*,dpi=150,maximum=None):
    tool=executable('FM_PDFTOPPM','pdftoppm')
    if tool:
        size=['-scale-to',str(maximum)] if maximum else ['-r',str(dpi)]
        try:run([tool,'-f',str(page),'-l',str(page),'-singlefile',*size,'-png',str(path),str(prefix)])
        except FileNotFoundError as error:
            raise ValueError('PDF renderer unavailable: resolved pdftoppm executable was not found; check FM_PDFTOPPM') from error
    else:
        try:import pymupdf as fitz
        except ImportError as error:
            raise ValueError('PDF renderer unavailable: install pdftoppm or PyMuPDF, or configure FM_PDFTOPPM') from error
        with fitz.open(path) as pdf:
            p=pdf[page-1];scale=maximum/max(p.rect.width,p.rect.height) if maximum else dpi/72
            p.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).save(str(prefix)+'.png')

def page_count(path):
    if path.suffix.lower()=='.pdf':
        import re
        tool=executable('FM_PDFINFO','pdfinfo')
        if not tool:
            import pymupdf as fitz
            with fitz.open(path) as pdf:
                if pdf.needs_pass or len(pdf)<1:raise ValueError('PDF page count unavailable')
                return len(pdf)
        info=run([tool,str(path)])
        match=re.search(r'^Pages:\s+(\d+)\s*$',info,re.M)
        if not match or int(match[1])<1:raise ValueError('PDF page count unavailable')
        return int(match[1])
    if path.suffix.lower() in ('.png','.jpg','.jpeg','.tif','.tiff','.webp','.bmp'):
        from PIL import Image
        with Image.open(path) as image:
            if getattr(image,'n_frames',1)!=1:raise ValueError('multi-frame images need an explicit frame provider')
            image.verify()
        return 1
    raise ValueError('open_document supports PDF or single-frame images')

def extract_page(path,page,mode,cache):
    """Text layer or explicitly selected OCR; never silent OCR or visual reasoning."""
    if mode=='text':
        if path.suffix.lower()!='.pdf':raise ValueError('images require mode=ocr')
        tool=executable('FM_PDFTOTEXT','pdftotext')
        if tool:return run([tool,'-f',str(page),'-l',str(page),'-layout',str(path),'-']).rstrip('\f'),'text_layer'
        import pymupdf as fitz
        with fitz.open(path) as pdf:return pdf[page-1].get_text(sort=True),'text_layer'
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True);image=path
    if path.suffix.lower()=='.pdf':
        prefix=cache/f'page-{page}'
        render_pdf(path,page,prefix)
        image=prefix.with_suffix('.png')
    tool=executable('FM_TESSERACT','tesseract');languages=os.environ.get('FM_OCR_LANGUAGES','eng+chi_sim')
    if tool:
        from src.adapters.geneloop_pdf import tessdata_directory
        data=tessdata_directory();options=['--tessdata-dir',data] if data else []
        text=run([tool,str(image),'stdout','-l',languages,*options],90)
    else:
        import pymupdf as fitz
        from src.adapters.geneloop_pdf import tessdata_directory
        with fitz.open(image) as picture:
            with fitz.open(stream=picture.convert_to_pdf(),filetype='pdf') as pdf:
                p=pdf[0];tp=p.get_textpage_ocr(language=languages,dpi=150,full=True,tessdata=tessdata_directory())
                text=p.get_text(textpage=tp,sort=True)
    return text,'ocr'

def request_id(document_id,page,offset):return 'chunk-'+digest([document_id,page,offset])[:32]
def parser_identity(mode):
    from importlib.metadata import version
    names=['FM_PDFINFO','FM_PDFTOTEXT']+(['FM_PDFTOPPM','FM_TESSERACT'] if mode=='ocr' else [])
    defaults=['pdfinfo','pdftotext','pdftoppm','tesseract'];tools={}
    for variable,default in zip(['FM_PDFINFO','FM_PDFTOTEXT','FM_PDFTOPPM','FM_TESSERACT'],defaults):
        if variable not in names:continue
        tool=shutil.which(os.environ.get(variable,default))
        tools[variable]={'path':tool,'sha256':sha(Path(tool)) if tool else None}
    fallback=any(not v['path'] for v in tools.values())
    languages={}
    if mode=='ocr':
        from src.adapters.geneloop_pdf import tessdata_directory
        directory=tessdata_directory()
        if directory:
            for name in os.environ.get('FM_OCR_LANGUAGES','eng+chi_sim').split('+'):
                p=Path(directory)/(name+'.traineddata');languages[name]=sha(p) if p.is_file() else None
    return digest({'format':VERSION,'tools':tools,'pillow':version('Pillow'),
        'pymupdf':version('PyMuPDF') if fallback else None,'fallback_ocr_languages':languages,
        'ocr_languages':os.environ.get('FM_OCR_LANGUAGES','eng+chi_sim') if mode=='ocr' else None})

class DocumentReading:
    def search_document(self,document_id:str,query:str):
        """Literal search over ACTUALLY delivered document chunks, with page/offset.
        Never searches unread parser caches; report includes remaining coverage gaps.
        """
        self.active()
        if document_id not in self.documents or not query.strip():raise ToolError('actual document_id and nonempty query required')
        d=self.documents[document_id];matches=[]
        # Adjacent delivered chunks on one page can form a hit across the boundary.
        for page in range(1,d['page_count']+1):
            rows=sorted((r for r in d['chunks'].values() if r['page']==page),key=lambda r:r['offset'])
            text=''.join(r['text'] for r in rows);start=0
            while (i:=text.casefold().find(query.casefold(),start))>=0:
                matches.append({'page':page,'offset':i,'excerpt':text[max(0,i-80):i+len(query)+120]});start=i+len(query)
                if len(matches)>=100:break
            if len(matches)>=100:break
        return self.stamp({'document_id':document_id,'query':query,'matches':matches,'match_limit':100,
            'coverage':coverage(d),'scope':'actual delivered text only; no hit does not prove semantic absence'})
    def view_document_page(self,source_id:str,page:int=1):
        """Deliver real image pixels to the current Harness vision model: image page 1,
        or ANY physical PDF page. This is visual input, not a semantic conclusion.
        PDF text/OCR coverage remains tracked separately by document_coverage.
        """
        import base64,io
        from PIL import Image
        from mcp.types import CallToolResult,TextContent,ImageContent
        self.active();h=self.handles.get(source_id)
        if not h:raise ToolError('use actual pin_file.source_id')
        path=self.path(h['path'])
        if not path.is_file() or sha(path)!=h['sha256']:raise ToolError('bound visual source changed')
        if type(page) is not int or not 1<=page<=page_count(path):raise ToolError('page outside actual document')
        viewid='view-'+digest([self.input_digest,h,page,'poppler-vision-v1'])[:32]
        cache=self.output/'visual-reads'/viewid;cache.mkdir(parents=True,exist_ok=True)
        saved=cache/('source'+path.suffix.lower())
        if not saved.exists():shutil.copyfile(path,saved)
        if sha(saved)!=h['sha256']:raise ToolError('visual source cache changed')
        rendered=cache/'pixels.png'
        if not rendered.exists():
            if path.suffix.lower()=='.pdf':render_pdf(path,page,cache/'pixels',maximum=2400)
            else:
                with Image.open(path) as im:
                    im=im.convert('RGB');im.thumbnail((2400,2400));im.save(rendered,'PNG')
        with Image.open(rendered) as im:width,height=im.size
        from management_provenance import read_provenance
        anchor={**h,'source_id':source_id,'status':'visual_pixels_delivered','text':'','truncated':True}
        anchor['provenance']=read_provenance(self.spec,json.loads(self.state_file.read_text()),anchor)
        row={'view_id':viewid,'page':page,'source_id':source_id,'source_sha256':h['sha256'],
             'image_sha256':sha(rendered),'width':width,'height':height,'anchor':anchor,
             'status':'visual_pixels_delivered','meaning':'Pixels supplied for model interpretation; no automatic semantic verdict.'}
        self.visual_reads[viewid]=row;atomic(cache/'receipt.json',row);self.persist()
        value=self.stamp(copy.deepcopy(row))
        return CallToolResult(content=[TextContent(type='text',text=json.dumps(value,ensure_ascii=False)),
            ImageContent(type='image',mimeType='image/png',data=base64.b64encode(rendered.read_bytes()).decode())],structuredContent=value)
    def open_document(self,source_id:str,mode:Literal['text','ocr']='text'):
        """Open a pinned PDF for ALL pages, or an image for OCR. Opening is not reading.
        Follow request_id through read_document_chunk until next_request_id is null.
        Text-layer coverage does not establish OCR/figure understanding.
        """
        self.active()
        if any(j['status'] in ('executing','restoring') for j in self.journals.values()):raise ToolError('recover unfinished file plan first')
        h=self.handles.get(source_id)
        if not h:raise ToolError('use actual pin_file.source_id')
        path=self.path(h['path'])
        if sha(path)!=h['sha256']:raise ToolError('bound file changed')
        if mode not in ('text','ocr'):raise ToolError('unsupported reading mode')
        parser=parser_identity(mode)
        did='document-'+digest([self.input_digest,h,mode,VERSION,parser])[:32]
        if did not in self.documents:
            try:count=page_count(path)
            except (ValueError,OSError,subprocess.SubprocessError) as e:raise ToolError(str(e)) from e
            if mode=='text' and path.suffix.lower()!='.pdf':raise ToolError('images require mode=ocr')
            from management_provenance import read_provenance
            anchor={**h,'source_id':source_id,'status':'document_opened','text':'','truncated':True}
            anchor['provenance']=read_provenance(self.spec,json.loads(self.state_file.read_text()),anchor)
            saved=self.output/'document-sources'/f'{did}{path.suffix.lower()}'
            saved.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,saved)
            if sha(saved)!=h['sha256']:raise ToolError('source changed while opening')
            self.documents[did]={'format':VERSION,'document_id':did,'anchor':anchor,'handle':copy.deepcopy(h),'source_file':saved.relative_to(self.output).as_posix(),
                'mode':mode,'parser_identity':parser,'page_count':count,'requests':{request_id(did,1,0):{'page':1,'offset':0}},'chunks':{}}
            self.persist()
        d=self.documents[did]
        return self.stamp({'document_id':did,'request_id':request_id(did,1,0),'page_count':d['page_count'],
            'mode':mode,'source_id':source_id,'source_sha256':h['sha256'],'scope':'all physical pages',
            'coverage':'not established by opening','chunk_char_limit':CHUNK})

    def read_document_chunk(self,request_id:str):
        """Read one server-issued page/chunk. Same ID resumes without repeating OCR.
        Continue with next_request_id until null to cover the whole document.
        """
        self.active()
        found=[d for d in self.documents.values() if request_id in d['requests']]
        if len(found)!=1:raise ToolError('unknown request_id; use open_document or preceding chunk result')
        d=found[0]
        if d['parser_identity']!=parser_identity(d['mode']):raise ToolError('original document parser/language changed; reopen and recertify')
        if request_id in d['chunks']:return self.stamp(copy.deepcopy(d['chunks'][request_id]))
        path=self.output/d['source_file']
        if not path.resolve().is_relative_to(self.output/'document-sources'):raise ToolError('document cache outside task')
        if sha(path)!=d['anchor']['sha256']:raise ToolError('document source cache changed')
        q=d['requests'][request_id];page,offset=q['page'],q['offset']
        try:text,kind=extract_page(path,page,d['mode'],self.output/'document-cache'/d['document_id'])
        except (ValueError,OSError,subprocess.SubprocessError) as e:raise ToolError(str(e)) from e
        end=min(len(text),offset+CHUNK)
        nextq=({'page':page,'offset':end} if end<len(text) else {'page':page+1,'offset':0} if page<d['page_count'] else None)
        nextid=globals()['request_id'](d['document_id'],nextq['page'],nextq['offset']) if nextq else None
        if nextq:d['requests'][nextid]=nextq
        row={'format':VERSION,'document_id':d['document_id'],'request_id':request_id,
            'source_id':d['anchor']['source_id'],'source_sha256':d['anchor']['sha256'],
            'mode':d['mode'],'page':page,'offset':offset,'end_offset':end,'page_characters':len(text),
            'text':text[offset:end],'extraction':kind,'empty_text':not text.strip(),
            'next_request_id':nextid,'page_complete':end==len(text)}
        row['response_sha256']=digest(row);d['chunks'][request_id]=row
        atomic(self.output/'document-reads'/f'{request_id}.json',row);self.persist()
        return self.stamp(copy.deepcopy(row))

    def document_coverage(self,document_id:str):
        """Actual delivered coverage, unread pages and limitations; does not read more."""
        self.active()
        if document_id not in self.documents:raise ToolError('unknown document_id')
        return self.stamp(coverage(self.documents[document_id]))

def coverage(d):
    completed=[];empty=[];characters=0;seen=set();qid=request_id(d['document_id'],1,0)
    while qid in d['chunks'] and qid not in seen:
        seen.add(qid);r=d['chunks'][qid];characters+=len(r['text'])
        if r['page_complete']:
            completed.append(r['page'])
            if r['empty_text']:empty.append(r['page'])
        qid=r['next_request_id']
    return {'document_id':d['document_id'],'source_id':d['anchor']['source_id'],'source_sha256':d['anchor']['sha256'],
        'mode':d['mode'],'page_count':d['page_count'],'completed_pages':completed,
        'unread_pages':[p for p in range(1,d['page_count']+1) if p not in completed],
        'delivered_chunks':len(seen),'delivered_characters':characters,'empty_text_pages':empty,
        'complete':qid is None and len(completed)==d['page_count'],
        'limitations':['Text layer only; empty text may require OCR; figures are not interpreted.'] if d['mode']=='text' else
                     ['OCR can contain recognition errors; figures are not interpreted.']}

def verify_documents(spec,state,output,*,pristine=None):
    """Independent replay against source bytes; native trajectory matching is separate."""
    from management_provenance import read_origin,resolve_read_source
    errors=[];out=Path(output)
    for did,d in state.get('documents',{}).items():
        try:
            a=d['anchor'];read_origin(spec,a,state)
            from management_provenance import ReadReplayPath
            source=ReadReplayPath(resolve_read_source(spec,a,state,pristine),a['path']) if pristine else out/d['source_file']
            if not pristine and not Path(source).resolve().is_relative_to(out/'document-sources'):raise ValueError('source cache outside task')
            if sha(source)!=a['sha256'] or page_count(source)!=d['page_count']:raise ValueError('document source/count differs')
            if d['parser_identity']!=parser_identity(d['mode']):raise ValueError('document parser/language changed')
            if did!='document-'+digest([digest(spec),d['handle'],d['mode'],VERSION,d['parser_identity']])[:32]:raise ValueError('document identity differs')
            if any(a.get(k)!=v for k,v in d['handle'].items()):raise ValueError('document source binding differs')
            qid=request_id(did,1,0);page=1;offset=0;seen=set()
            while qid in d['chunks'] and qid not in seen:
                seen.add(qid);row=d['chunks'][qid];text,kind=extract_page(source,page,d['mode'],out/'document-replay'/did)
                end=min(len(text),offset+CHUNK)
                following=(page,end) if end<len(text) else (page+1,0) if page<d['page_count'] else None
                nxt=request_id(did,*following) if following else None
                expected={'format':VERSION,'document_id':did,'request_id':qid,'source_id':a['source_id'],
                    'source_sha256':a['sha256'],'mode':d['mode'],'page':page,'offset':offset,'end_offset':end,
                    'page_characters':len(text),'text':text[offset:end],'extraction':kind,'empty_text':not text.strip(),
                    'next_request_id':nxt,'page_complete':end==len(text)}
                expected['response_sha256']=digest(expected)
                if row!=expected or json.loads((out/'document-reads'/f'{qid}.json').read_text())!=expected:raise ValueError('page chunk differs from replay')
                qid=nxt
                if following:page,offset=following
            if seen!=set(d['chunks']):raise ValueError('non-contiguous document reads')
        except (ValueError,KeyError,OSError,subprocess.SubprocessError) as e:errors.append('document read rejected: '+str(e))
    return errors

def verify_visual_reads(spec,state,output,*,pristine=None):
    from management_provenance import read_origin,resolve_read_source,ReadReplayPath
    from PIL import Image
    errors=[];out=Path(output)
    for vid,v in state.get('visual_reads',{}).items():
        try:
            a=v['anchor'];read_origin(spec,a,state)
            h={k:a[k] for k in ('file_id','path','source_version','sha256')}
            if vid!='view-'+digest([digest(spec),h,v['page'],'poppler-vision-v1'])[:32]:raise ValueError('visual identity differs')
            source=ReadReplayPath(resolve_read_source(spec,a,state,pristine),a['path']) if pristine else out/'visual-reads'/vid/('source'+Path(a['path']).suffix.lower())
            if sha(source)!=a['sha256']:raise ValueError('visual source differs')
            if not 1<=v['page']<=page_count(source):raise ValueError('visual page outside source')
            cache=out/'visual-replay'/vid;cache.mkdir(parents=True,exist_ok=True)
            rendered=cache/'pixels.png'
            if source.suffix.lower()=='.pdf':render_pdf(source,v['page'],cache/'pixels',maximum=2400)
            else:
                with Image.open(source) as im:
                    im=im.convert('RGB');im.thumbnail((2400,2400));im.save(rendered,'PNG')
            if sha(rendered)!=v['image_sha256'] or sha(out/'visual-reads'/vid/'pixels.png')!=v['image_sha256']:raise ValueError('visual pixels differ')
            with Image.open(rendered) as im:
                if im.size!=(v['width'],v['height']):raise ValueError('visual dimensions differ')
        except (ValueError,KeyError,OSError,subprocess.SubprocessError) as e:errors.append('visual input rejected: '+str(e))
    return errors
