"""Fixed Crossref DOI/title lookups: candidate evidence, never version judgments."""
from datetime import datetime, timezone
import hashlib
import json
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

DOI = re.compile(r'10\.\d{4,9}/[^\s\x00-\x1f]{1,300}', re.I)
MAX_BYTES = 2_000_000
_lock = threading.Lock()
_last = 0.0


class FixedRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        url = urlsplit(newurl)
        if url.scheme != 'https' or url.netloc != 'api.crossref.org' or not url.path.startswith('/works'):
            raise URLError('Crossref redirect outside fixed metadata service')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def scalar_fields(raw):
    """Preserve deposited fields and differences for the model, no fuzzy accept."""
    if not isinstance(raw, dict) or DOI.fullmatch(raw.get('DOI', '')) is None:
        raise ValueError('missing DOI record identity')
    titles = raw.get('title')
    if not isinstance(titles, list) or not titles or not all(isinstance(t, str) and t.strip() for t in titles):
        raise ValueError('missing deposited title')
    fields = ('DOI','title','author','issued','published','published-print','published-online',
              'container-title','publisher','volume','issue','page','article-number','type','URL','relation')
    result = {k: raw[k] for k in fields if k in raw}
    if len(json.dumps(result, ensure_ascii=False).encode()) > 80000:
        raise ValueError('record exceeds evidence bound')
    return result


def parse_response(body, *, doi=None):
    if len(body) > MAX_BYTES:
        raise ValueError('Crossref response too large')
    raw = json.loads(body)
    if raw.get('status') != 'ok':
        raise ValueError('unsuccessful metadata envelope')
    message = raw.get('message')
    if doi is not None:
        row = scalar_fields(message)
        if row['DOI'].casefold() != doi.casefold():
            raise ValueError('DOI identity mismatch')
        rows = [row]
    else:
        if not isinstance(message, dict) or not isinstance(message.get('items'), list) or len(message['items']) > 3:
            raise ValueError('bounded search result required')
        rows = [scalar_fields(r) for r in message['items']]
    return {'records':rows,'response_sha256':hashlib.sha256(body).hexdigest(),
            'work_identity_confirmed':False,'formal_version_selected':False}


def fetch_crossref(*, doi=None, title=None):
    global _last
    if (doi is None) == (title is None):
        raise ValueError('one deposited DOI or source title required')
    if doi is not None:
        if not isinstance(doi,str) or DOI.fullmatch(doi) is None:
            raise ValueError('invalid literal DOI')
        url = 'https://api.crossref.org/works/'+quote(doi,safe='')
    else:
        if not isinstance(title,str) or not title.strip() or len(title)>512 or '\x00' in title:
            raise ValueError('bounded literal source title required')
        url = 'https://api.crossref.org/works?'+urlencode({'query.bibliographic':title,'rows':3,
            'select':'DOI,title,author,issued,published,container-title,publisher,volume,issue,page,type,URL'})
    base={'request_url':url,'fetched_at':datetime.now(timezone.utc).isoformat(),
          'method':'deposited_doi' if doi else 'source_title_search',
          'work_identity_confirmed':False,'formal_version_selected':False}
    try:
        with _lock:
            delay=0.5-(time.monotonic()-_last)
            if delay>0:time.sleep(delay)
            _last=time.monotonic()
            request=Request(url,headers={'User-Agent':'DeepSeekHarless-research-probe/0.1',
                                         'Accept':'application/json'})
            with build_opener(FixedRedirects()).open(request,timeout=30) as response:
                if response.status!=200:raise ValueError('non-success response')
                body=response.read(MAX_BYTES+1)
        parsed=parse_response(body,doi=doi)
        return {**base,**parsed,'fetch_status':'obtained' if parsed['records'] else 'empty','http_status':200}
    except (HTTPError,URLError,TimeoutError,OSError,ValueError,TypeError) as exc:
        return {**base,'records':[],'fetch_status':'failed','error_type':type(exc).__name__,
                'http_status':exc.code if isinstance(exc,HTTPError) else None}


def literal_field(raw, field):
    """Read one literal brace/quote BibTeX field; unsupported macros stay absent."""
    match=re.search(r'\b'+re.escape(field)+r'\s*=\s*([{\"])',raw,re.I)
    if not match:return None
    start=match.end();opener=match[1];depth=1;escaped=False
    for i in range(start,len(raw)):
        char=raw[i]
        if escaped:escaped=False;continue
        if char=='\\':escaped=True;continue
        if opener=='"' and char=='"':
            return ' '.join(raw[start:i].split())
        if opener=='{':
            if char=='{':depth+=1
            if char=='}':
                depth-=1
                if depth==0:return ' '.join(raw[start:i].replace('{','').replace('}','').split())
    return None
