#!/usr/bin/env python3
"""Model-free v28/v25 -> v29/v26 sandbox member-resource path compatibility.

Only reviewed Gateway/member/host deployment composition may differ. Native tools,
presets, MCP schemas, evidence and the learned online programs stay unchanged.
Default --preview performs no writes; --write requires the final source freeze.
"""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('member_path_compat_base',ROOT/'scripts/reexport-native-capabilities-compat.py')
compat=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(compat)
REVIEWED={'scripts/harless_gateway.mjs','scripts/harless_member_scenes.mjs','src/adapters/geneloop_native_host.mjs'}
compat.RELEASES=[
    ('paper-web-v28','paper-web-v29','paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json',REVIEWED),
    ('ppt-master-v25','ppt-master-v26','ppt',
     'scenarios/ppt_master/contracts.json',REVIEWED),
]
compat.REGISTRY_SELECTED={old:old for old,*_ in compat.RELEASES}
compat.ADDITIONAL_LOCKS=compat.ADDITIONAL_LOCKS|{'scripts/reexport-member-path-compat.py'}
original_record=compat.compatibility_record


def compatibility_record(candidate,validation_record):
    value=original_record(candidate,validation_record)
    value['repairs']=['map_verified_native_resources_to_member_sandbox_mount_targets',
                      'activate_reviewed_native_providers_with_official_host_patch_semantics']
    value['runtime_delta']='Member policy receives sandbox-visible project and approved skill/resource paths from verified mounts. Host composition disables shipped fs/subprocess entries and inserts the reviewed providers with independent IDs under official patch semantics. Host broker paths, native tool implementations, presets, certified MCP schemas, evidence and learned IR are unchanged.'
    return value


compat.compatibility_record=compatibility_record

if __name__=='__main__':compat.main()
