"""Bounded official arXiv Atom metadata batches, without publication judgments."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from xml.etree import ElementTree as ET

ATOM='http://www.w3.org/2005/Atom'
ARXIV='http://arxiv.org/schemas/atom'
ID=re.compile(r'\d{4}\.\d{4,5}(?:v[1-9]\d*)?')
MAX_BYTES=2_000_000
_lock=threading.Lock()
_last_request=0.0


def validate_ids(ids):
    if not isinstance(ids,list) or len(ids)>64 or any(
            not isinstance(i,str) or ID.fullmatch(i) is None for i in ids) or len(ids)!=len(set(ids)):
        raise ValueError('expected at most 64 unique literal arXiv syntax candidates')


def parse_feed(body: bytes, ids: list[str]):
    validate_ids(ids)
    if len(body)>MAX_BYTES: raise ValueError('arXiv response too large')
    text=body.decode('utf-8')
    if re.search(r'<!\s*(DOCTYPE|ENTITY)\b',text,re.I): raise ValueError('XML declarations rejected')
    root=ET.fromstring(text)
    if root.tag!='{'+ATOM+'}feed': raise ValueError('expected Atom feed, not HTML or an error page')
    found={}; errors=[]
    def value(entry, namespace, name):
        return ' '.join((entry.findtext('{'+namespace+'}'+name) or '').split()) or None
    for entry in root.findall('{'+ATOM+'}entry'):
        entry_url=value(entry,ATOM,'id') or ''
        url=urlsplit(entry_url)
        if url.hostname=='arxiv.org' and url.path.startswith('/api/errors'):
            errors.append({'source_url':entry_url,'message':value(entry,ATOM,'summary')});continue
        match=re.fullmatch(r'/abs/(\d{4}\.\d{4,5})(v[1-9]\d*)?',url.path)
        if url.scheme not in {'http','https'} or url.netloc!='arxiv.org' or url.query or url.fragment or not match:
            raise ValueError('unexpected arXiv entry identifier')
        full_id=match.group(1)+(match.group(2) or '')
        selected=full_id if full_id in ids else match.group(1)
        if selected not in ids: raise ValueError('unsolicited entry outside requested identifiers')
        if selected in found: raise ValueError('ambiguous duplicate entry/version')
        title=value(entry,ATOM,'title')
        authors=[' '.join((a.findtext('{'+ATOM+'}name') or '').split()) for a in entry.findall('{'+ATOM+'}author')]
        if not title or not authors or not all(authors): raise ValueError('missing title or author metadata')
        dates={name:value(entry,ATOM,name) for name in ['published','updated']}
        for date in dates.values():
            if not date or datetime.fromisoformat(date.replace('Z','+00:00')).tzinfo is None:
                raise ValueError('missing or invalid arXiv timestamp')
        doi=value(entry,ARXIV,'doi')
        if doi and not re.fullmatch(r'10\.\d{4,9}/\S+',doi,re.I): raise ValueError('malformed DOI metadata')
        found[selected]={'requested_id':selected,'returned_id':full_id,'status':'metadata_obtained',
            'source_url':'https://arxiv.org/abs/'+full_id,'title':title,'authors':authors,**dates,
            'doi':doi,'journal_reference':value(entry,ARXIV,'journal_ref'),
            'comments':value(entry,ARXIV,'comment'),
            'formal_publication_confirmed':False,'bibliography_match_confirmed':False}
    return {'requested_ids':ids,'items':[found.get(i,{'requested_id':i,'status':'missing_from_feed',
            'formal_publication_confirmed':False,'bibliography_match_confirmed':False}) for i in ids],
            'feed_errors':errors,'response_sha256':hashlib.sha256(body).hexdigest(),
            'coverage':'arxiv_metadata_only_not_formal_publication_verification'}


class FixedRedirects(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        url=urlsplit(newurl)
        if url.scheme!='https' or url.netloc!='export.arxiv.org' or url.path.rstrip('/')!='/api/query':
            raise URLError('unexpected metadata redirect')
        return super().redirect_request(request,fp,code,msg,headers,newurl)


def fetch_metadata(ids: list[str]):
    global _last_request
    validate_ids(ids)
    fetched=datetime.now(timezone.utc).isoformat()
    if not ids: return {**parse_feed(('<feed xmlns="'+ATOM+'"/>').encode(),[]),'fetch_status':'no_identifiers','fetched_at':fetched}
    url='https://export.arxiv.org/api/query?'+urlencode({'id_list':','.join(ids),'max_results':len(ids)})
    request=Request(url,headers={'User-Agent':'DeepSeekHarless-research-probe/0.1','Accept':'application/atom+xml'})
    try:
        with _lock:
            delay=3-(time.monotonic()-_last_request)
            if delay>0: time.sleep(delay)
            _last_request=time.monotonic()
            with build_opener(FixedRedirects()).open(request,timeout=40) as response:
                if response.status!=200: raise ValueError('non-success response')
                body=response.read(MAX_BYTES+1)
        result=parse_feed(body,ids)
        return {**result,'fetch_status':'obtained','request_url':url,'http_status':200,'fetched_at':fetched}
    except (HTTPError,URLError,TimeoutError,OSError,ValueError,ET.ParseError) as exc:
        return {'requested_ids':ids,'items':[{'requested_id':i,'status':'fetch_failed',
                'formal_publication_confirmed':False,'bibliography_match_confirmed':False} for i in ids],
                'fetch_status':'failed','request_url':url,'http_status':exc.code if isinstance(exc,HTTPError) else None,
                'error_type':type(exc).__name__,'fetched_at':fetched,
                'coverage':'arxiv_metadata_only_not_formal_publication_verification'}
