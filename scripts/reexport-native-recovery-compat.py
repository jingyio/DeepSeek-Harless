#!/usr/bin/env python3
"""Model-free Paper v29/PPT v26 -> v30/v27 reviewed recovery compatibility.

The original learned IR, MCP schemas and evidence remain immutable. Only the
explicitly reviewed host/transport/delegation/search/task-mirror code may change.
Default preview is read-only; publication requires the final source freeze.
"""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('native_recovery_compat_base',ROOT/'scripts/reexport-native-capabilities-compat.py')
compat=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(compat)
REVIEWED={'scripts/harless_gateway.mjs','src/adapters/deepseek_cost_gate.py',
          'src/adapters/dsh_web_tasks.ts','src/adapters/geneloop_delegation.ts',
          'src/adapters/geneloop_fs_search.ts'}
NEW_LOCKS={'scripts/reexport-native-recovery-compat.py','src/adapters/geneloop_task_trace.ts',
           'src/adapters/model_transport.py','config/geneloop-transport.json'}
compat.RELEASES=[
    ('paper-web-v29','paper-web-v30','paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json',REVIEWED),
    ('ppt-master-v26','ppt-master-v27','ppt',
     'scenarios/ppt_master/contracts.json',REVIEWED),
]
compat.REGISTRY_SELECTED={old:old for old,*_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS=compat.ADDITIONAL_LOCKS|NEW_LOCKS
original_record=compat.compatibility_record


def compatibility_record(candidate,validation_record):
    value=original_record(candidate,validation_record)
    value['repairs']=['shared_model_request_transport_capacity',
                      'preserve_bound_delegated_model_route',
                      'mirror_native_terminal_turn_events',
                      'sandbox_file_search_argument_compatibility']
    value['runtime_delta']='Reviewed request transport capacity, delegated model route binding, native terminal-turn projection and session-contained file search compatibility. Shared transport configuration/helper and task trace helper are explicitly source-locked. The learned online program, certified MCP schemas and original training evidence are unchanged; this export performs no new model calls or quality promotion.'
    return value


compat.compatibility_record=compatibility_record

if __name__=='__main__':compat.main()
