#!/usr/bin/env python3
"""Model-free v27/v24 -> v28/v25 public command target-isolation compatibility.

Only the reviewed Gateway guard and its Task-host wiring may differ. Original
IR, MCP schemas, evidence and prior candidates remain byte-for-byte unchanged.
Default --preview performs no writes; final release requires explicit --write.
"""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('private_command_compat_base',ROOT/'scripts/reexport-native-capabilities-compat.py')
compat=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(compat)
REVIEWED={'src/adapters/geneloop_runtime_routes.ts','src/adapters/dsh_web_tasks.ts'}
compat.RELEASES=[
    ('paper-web-v27','paper-web-v28','paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json',REVIEWED),
    ('ppt-master-v24','ppt-master-v25','ppt',
     'scenarios/ppt_master/contracts.json',REVIEWED),
]
compat.REGISTRY_SELECTED={old:old for old,*_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS=compat.ADDITIONAL_LOCKS|{'scripts/reexport-private-command-compat.py'}
original_record=compat.compatibility_record

def compatibility_record(candidate,validation_record):
    value=original_record(candidate,validation_record)
    value['repairs']=['restrict_public_Gateway_commands_to_owned_public_conversation_targets']
    value['runtime_delta']='Public Carrier target admission only; internal native command calls, native tool vocabulary, certified MCP schemas, source evidence and IR are unchanged.'
    return value

compat.compatibility_record=compatibility_record

if __name__=='__main__':compat.main()
