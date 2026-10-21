#!/usr/bin/env python3
"""Model-free File fee metadata delta; preserve prior Paper/PPT execution evidence."""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('file_fee_metadata_compat_base',ROOT/'scripts/reexport-native-capabilities-compat.py')
compat=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(compat)
REVIEWED={'src/adapters/harless_file_scene.ts'}
compat.RELEASES=[
    ('paper-web-v31','paper-web-v32','paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json',REVIEWED),
    ('ppt-master-v28','ppt-master-v29','ppt',
     'scenarios/ppt_master/contracts.json',REVIEWED),
]
compat.REGISTRY_SELECTED={old:old for old,*_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS=compat.ADDITIONAL_LOCKS|{'scripts/reexport-file-cost-metadata-compat.py'}
original_record=compat.compatibility_record


def compatibility_record(candidate,validation_record):
    value=original_record(candidate,validation_record)
    value['repairs']=['distinguish_observed_file_fee_from_unknown_reservation']
    value['runtime_delta']='Only the independent File public fee projection changes: observed usage requires the same scoped sealed record, otherwise cost_usd remains null and its original reservation upper amount is retained. Paper/PPT execution, learned IR, MCP schemas and historical evidence remain unchanged. This compatibility export performs no learning, model call or quality promotion.'
    return value


compat.compatibility_record=compatibility_record

if __name__=='__main__':compat.main()
