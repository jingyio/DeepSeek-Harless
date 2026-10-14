"""Trace-mined, source-title-bound query tools for failed publication lookup.

Only fixed Crossref/DBLP read-only API envelopes are accepted. Titles are
parameterized by witnessed literal word transformations, never model keywords.
Results remain metadata candidates; no identity/version decision is made here.
"""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
from urllib.parse import urlsplit,parse_qsl,urlencode
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError,URLError
from datetime import datetime,timezone
from pathlib import Path
from .native_motif_compiler import digest,root_events
from .crossref_metadata import literal_field,scalar_fields


def words(title):return re.findall(r'[A-Za-z0-9]+',title.lower())


def query_payload(raw):
    if len(raw)>2000000:raise ValueError('response limit')
    obj=json.loads(raw);rows=obj['message']['items']
    if obj.get('status')!='ok' or not isinstance(rows,list) or len(rows)>5:raise ValueError('bounded Crossref search required')
    return {'records':[scalar_fields(r) for r in rows]}


def compile_recovery_queries(runs):
    groups=defaultdict(list);protos={};sources={}
    for run in map(Path,runs):
        cfg=json.loads((run/'manifest.json').read_text());metrics=json.loads((run/'metrics.json').read_text())
        if cfg['mode']!='baseline' or metrics['status']!='completed' or not metrics['source_unchanged']:raise ValueError('normal completed baseline required')
        sources[run.name]={'session_id':cfg['session_id'],'events_sha256':hashlib.sha256((run/'session-events.jsonl').read_bytes()).hexdigest()}
        calls={};titles=[]
        for event in root_events(run):
            d=event.get('data',{})
            if event['type']=='tool/call':calls[d['callId']]={**d,'arguments':json.loads(d['arguments']) if isinstance(d['arguments'],str) else d['arguments']}
            if event['type']!='tool/result':continue
            for b in d.get('message',{}).get('content',[]):
                call=calls.get(b.get('toolCallId'))
                if not call or b.get('isError'):continue
                body='\n'.join(c.get('text','') for c in b.get('content',[]) if c.get('type')=='text')
                if call['name']=='mcp__paper_checks__read_pinned_citation_records':
                    try:
                        value=json.loads(body)
                        if value['version_sha256']!=cfg['input_version']:raise ValueError('record epoch changed')
                        titles=[literal_field(r['raw_bibtex'],'title') for r in value['records']]
                    except (ValueError,KeyError,TypeError):titles=[]
                    continue
                if call['name']!='web_fetch' or set(call['arguments'])!={'url'}:continue
                url=call['arguments']['url'];u=urlsplit(url);pairs=parse_qsl(u.query,keep_blank_values=True);args=dict(pairs)
                if u.scheme!='https' or u.fragment or len(pairs)!=len(args) or not body.startswith('Fetched '+url+' (HTTP 200)'):continue
                if u.netloc=='api.crossref.org' and u.path=='/works':
                    key=next((k for k in ['query.title','query.bibliographic'] if k in args),None)
                    if not key or set(args)!={key,'rows','select'} or not re.fullmatch(r'[1-5]',args['rows']):continue
                    allowed={'DOI','title','author','issued','container-title','publisher','type','published','URL'}
                    if not {'DOI','title'}<=set(args['select'].split(','))<=allowed:continue
                    try:parsed,_=json.JSONDecoder().raw_decode(body[body.index('{'):]);query_payload(json.dumps(parsed).encode())
                    except (ValueError,KeyError,TypeError):continue
                    service='crossref'
                elif u.netloc=='dblp.org' and u.path=='/search/publ/api':
                    key='q'
                    if set(args)!={'q','format','h'} or args['format']!='json' or not re.fullmatch(r'[1-5]',args['h']):continue
                    try:
                        parsed,_=json.JSONDecoder().raw_decode(body[body.index('{'):]);assert 'hits' in parsed['result']
                    except (ValueError,KeyError,TypeError,AssertionError):continue
                    service='dblp'
                else:continue
                query=words(args[key]);matching=[words(t) for t in titles if t and len(query)>=4 and words(t)[:len(query)]==query]
                if not matching:continue
                transforms=set('all_words' if query==t else 'prefix_'+str(len(query)) for t in matching)
                if len(transforms)!=1:continue
                proto={'service':service,'base':'https://'+u.netloc+u.path,'query_key':key,'title_transform':transforms.pop(),
                       'constants':{k:v for k,v in args.items() if k!=key},'read_only':True}
                ident=digest(proto);protos[ident]=proto
                groups[ident].append({'run_id':run.name,'session_id':cfg['session_id'],'call_id':call['callId'],
                                     'query_sha256':digest(args[key]),'result_sha256':digest(b['content'])})
    library={'schema_version':1,'scope':'source_title_query_recovery','execution_policy':'bounded_readonly_tool',
             'source_traces':sources,'prototypes':[{'id':'query-'+k[:12],'protocol':protos[k],'witnesses':w,
                'training_session_count':len({r['session_id'] for r in w})} for k,w in sorted(groups.items())],
             'identity_or_formal_version_confirmed':False}
    library['manifest_digest']=digest(library);return library


class ApiRedirects(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        before,after=urlsplit(req.full_url),urlsplit(newurl)
        if after.scheme!='https' or after.netloc!=before.netloc or after.path!=before.path:raise ValueError('untrusted redirect')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def validate_queries(lib):
    if not isinstance(lib,dict):raise ValueError('query library required')
    body={k:v for k,v in lib.items() if k!='manifest_digest'}
    if lib.get('schema_version')!=1 or lib.get('scope')!='source_title_query_recovery' or lib.get('execution_policy')!='bounded_readonly_tool' or digest(body)!=lib.get('manifest_digest'):raise ValueError('query library changed')
    for row in lib['prototypes']:
        p=row['protocol'];u=urlsplit(p['base']);c=p['constants']
        if row['id']!='query-'+digest(p)[:12] or not row['witnesses'] or p['read_only'] is not True:raise ValueError('unwitnessed query')
        if row['training_session_count']!=len({w['session_id'] for w in row['witnesses']}) or any(lib['source_traces'].get(w['run_id'],{}).get('session_id')!=w['session_id'] for w in row['witnesses']):raise ValueError('witness provenance changed')
        if p['service']=='crossref':
            if p['base']!='https://api.crossref.org/works' or p['query_key'] not in ['query.title','query.bibliographic'] or set(c)!={'rows','select'} or not re.fullmatch(r'[1-5]',c['rows']):raise ValueError('unbounded Crossref query')
            if not {'DOI','title'}<=set(c['select'].split(','))<={'DOI','title','author','issued','container-title','publisher','type','published','URL'}:raise ValueError('unbounded projection')
        elif p['service']=='dblp':
            if p['base']!='https://dblp.org/search/publ/api' or p['query_key']!='q' or c.get('format')!='json' or set(c)!={'format','h'} or not re.fullmatch(r'[1-5]',c['h']):raise ValueError('unbounded DBLP query')
        else:raise ValueError('unregistered source')
        if p['title_transform']!='all_words' and not re.fullmatch(r'prefix_(?:[4-9]|1[0-6])',p['title_transform']):raise ValueError('unbounded title transform')


def fetch_query(protocol,title):
    tokens=words(title)
    if protocol['title_transform']!='all_words':tokens=tokens[:int(protocol['title_transform'].split('_')[1])]
    query=' '.join(tokens)
    if not 1<=len(query)<=512:raise ValueError('bounded current source title required')
    url=protocol['base']+'?'+urlencode({protocol['query_key']:query,**protocol['constants']})
    base={'request_url':url,'fetched_at':datetime.now(timezone.utc).isoformat(),'service':protocol['service'],
          'identity_confirmed':False,'formal_version_selected':False}
    try:
        req=Request(url,headers={'User-Agent':'DeepSeekHarless-research-probe/0.1','Accept':'application/json'})
        with build_opener(ApiRedirects()).open(req,timeout=12) as response:
            raw=response.read(2000001)
            if response.status!=200 or len(raw)>2000000:raise ValueError('unbounded/non-success response')
        if protocol['service']=='crossref':payload=query_payload(raw)
        else:
            obj=json.loads(raw);hits=obj['result']['hits'];rows=hits.get('hit',[])
            if not isinstance(rows,list) or len(rows)>5:raise ValueError('unbounded DBLP records')
            payload={'records':[r['info'] for r in rows]}
        return {**base,**payload,'response_sha256':hashlib.sha256(raw).hexdigest(),'fetch_status':'obtained' if payload['records'] else 'empty'}
    except (HTTPError,URLError,OSError,ValueError,KeyError,TypeError) as exc:
        return {**base,'records':[],'fetch_status':'failed','error_type':type(exc).__name__}


def recover_queries(records,library):
    validate_queries(library)
    # At most three witnessed envelopes; deterministic support ranking is solely
    # for bounded query collection, never a publication/candidate ranking.
    protos=[];seen=set()
    for p in sorted(library['prototypes'],key=lambda p:(-p['training_session_count'],p['id'])):
        kind=(p['protocol']['service'],p['protocol']['query_key'],p['protocol']['title_transform'])
        if kind not in seen:protos.append(p);seen.add(kind)
        if len(protos)==2:break
    keys={p['key'] for p in records['required_reference_pairs']};grouped=defaultdict(list)
    for r in records['records']:
        if r['key'] in keys:grouped[r['key']].append(r)
    jobs=[];ambiguous=[]
    for key,rs in grouped.items():
        if len(rs)!=1:ambiguous.append(key);continue
        title=literal_field(rs[0]['raw_bibtex'],'title')
        if title:
            for p in protos:jobs.append((key,rs[0]['record_sha256'],p,title))
    if len(jobs)>30:raise ValueError('recovery batch limit')
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda job:{'key':job[0],'record_sha256':job[1],'query_prototype':job[2]['id'],
            **fetch_query(job[2]['protocol'],job[3])},jobs))
    return {'citation_id':records['citation_id'],'version_sha256':records['version_sha256'],
            'query_library_digest':library['manifest_digest'],'items':results,'ambiguous_keys':ambiguous,
            'work_identity_confirmed':False,'formal_version_selected':False}
