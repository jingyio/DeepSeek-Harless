#!/usr/bin/env python3
"""Narrow, model-free v26/v23 -> v27/v24 Cordis injection compatibility export.

The reviewed runtime delta must be exactly dsh_web_tasks.ts. The earlier export
implementation is reused without changing its existing code lock. Default mode
is --preview; --write --update-registry explicitly publishes fresh directories.
"""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('cordis_compat_base',ROOT/'scripts/reexport-native-capabilities-compat.py')
compat=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(compat)
compat.RELEASES=[
    ('paper-web-v26','paper-web-v27','paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json',{'src/adapters/dsh_web_tasks.ts'}),
    ('ppt-master-v23','ppt-master-v24','ppt',
     'scenarios/ppt_master/contracts.json',{'src/adapters/dsh_web_tasks.ts'}),
]
compat.REGISTRY_SELECTED={old:old for old,*_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS=compat.ADDITIONAL_LOCKS|{'scripts/reexport-cordis-inject-compat.py'}
original_record=compat.compatibility_record

def compatibility_record(candidate,validation_record):
    value=original_record(candidate,validation_record)
    value['repairs']=['declare_tools_systemPrompt_sessions_for_shared_Cordis_controller_context']
    value['runtime_delta']='Explicit dependency injection only; unchanged native vocabulary, certified MCP schemas, source evidence and IR.'
    return value

compat.compatibility_record=compatibility_record

if __name__=='__main__':compat.main()
