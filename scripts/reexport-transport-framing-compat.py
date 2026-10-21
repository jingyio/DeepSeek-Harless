#!/usr/bin/env python3
"""Model-free exact Gateway framing delta, preserving unpublished v30/v27."""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('transport_framing_compat_base',ROOT/'scripts/reexport-native-capabilities-compat.py')
compat=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(compat)
REVIEWED={'scripts/harless_gateway.mjs'}
compat.RELEASES=[
    ('paper-web-v30','paper-web-v31','paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json',REVIEWED),
    ('ppt-master-v27','ppt-master-v28','ppt',
     'scenarios/ppt_master/contracts.json',REVIEWED),
]
compat.REGISTRY_SELECTED={old:old for old,*_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS=compat.ADDITIONAL_LOCKS|{'scripts/reexport-transport-framing-compat.py'}
original_record=compat.compatibility_record


def compatibility_record(candidate,validation_record):
    value=original_record(candidate,validation_record)
    value['repairs']=['remove_hop_by_hop_headers_when_forwarding_decoded_http_bodies']
    value['runtime_delta']='Gateway removes hop-by-hop and Connection-nominated request/response headers when forwarding decoded model requests, avoiding conflicting Transfer-Encoding and Content-Length. Unpublished v30/v27 candidates remain intact. Learned IR, MCP schemas, historical evidence, model transport limits and all other locked source files remain unchanged.'
    return value


compat.compatibility_record=compatibility_record

if __name__=='__main__':compat.main()
