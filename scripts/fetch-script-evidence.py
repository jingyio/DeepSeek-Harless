#!/usr/bin/env python3
"""Trusted read-only HTTP boundary, using the existing metadata authority limits.

Generated programs NEVER receive a network-capable process. Only this helper
performs a fresh GET after validating the requested fixed service and limits.
"""
import hashlib
import json
import re
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit, parse_qs
from urllib.request import Request, build_opener

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.adapters.arxiv_metadata import FixedRedirects as ArxivRedirects
from src.adapters.crossref_metadata import FixedRedirects as CrossrefRedirects


def validate(url):
    parts=urlsplit(url)
    if parts.scheme!='https' or parts.username or parts.password or parts.port not in (None,443) or parts.fragment or len(url)>4096:
        raise ValueError('fixed_metadata_https_required')
    if parts.netloc=='export.arxiv.org' and parts.path=='/api/query':
        query=parse_qs(parts.query,keep_blank_values=True)
        ids=query.get('id_list',[''])[0].split(',')
        if any(len(v)!=1 for v in query.values()) or set(query)-{'id_list','max_results','start'} or not 1<=len(ids)<=64 or any(re.fullmatch(r'\d{4}\.\d{4,5}(?:v[1-9]\d*)?',i) is None for i in ids) or not 1<=int(query.get('max_results',['64'])[0])<=64 or int(query.get('start',['0'])[0])!=0:
            raise ValueError('bounded_identifier_query_required')
        return ArxivRedirects()
    if parts.netloc=='api.crossref.org' and (parts.path=='/works' or parts.path.startswith('/works/')):
        query=parse_qs(parts.query,keep_blank_values=True)
        if any(len(v)!=1 for v in query.values()):raise ValueError('single_metadata_parameters_required')
        if parts.path=='/works' and not 1<=int(query.get('rows',['1000'])[0])<=3:
            raise ValueError('bounded_crossref_candidates_required')
        if set(query)-{'rows','query.bibliographic','query.title','select','mailto'} or 'mailto' in query:
            raise ValueError('unsupported_metadata_query')
        return CrossrefRedirects()
    raise ValueError('unapproved_metadata_authority')


def main():
    url=sys.argv[1];redirects=validate(url);start=time.monotonic()
    with build_opener(redirects).open(Request(url,headers={'User-Agent':'GeneLoop-ScriptEvidence/1.0'}),timeout=20) as response:
        body=response.read(2_000_001)
    if len(body)>2_000_000:raise ValueError('metadata_response_too_large')
    output=Path(sys.argv[2]);output.write_bytes(body);output.chmod(0o600)
    print(json.dumps({'url':url,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body),'fetched_at':time.time(),'elapsed_seconds':time.monotonic()-start}))


if __name__=='__main__':main()
