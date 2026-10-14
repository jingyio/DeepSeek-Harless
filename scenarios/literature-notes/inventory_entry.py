"""Frozen task frame shared by the offline learner and the original PDF SDK entry."""
import hashlib
import json
from pathlib import Path
from pdf_tools import ROOT, digest
HERE=Path(__file__).resolve().parent
SOURCE='mcp__literature_pdf__list_pdfs'
PREPARE='mcp__literature_pdf__prepare_pdf'

def execution_version():
    return digest({n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in
        ['pdf_tools.py','pdf_layout.py','pdf_read_plan.py','pdf-contracts.json']})

def entry_task(scene,task_id):
    papers=scene.task['sources']['papers'];ids=[p['paper_id'] for p in papers]
    return {'schema_version':1,'task_id':task_id,'input_version':digest(scene.task),
        'execution_version_sha256':execution_version(),'inventory_papers':papers,'inventory_sha256':digest(papers),
        'question':scene.task['question'],'target_ids':ids,'target_ids_sha256':digest(ids),
        'target_versions':{pid:scene.document_version(pid) for pid in ids},'parser_profile_sha256':digest(scene.profile)}

def private_policy(path):
    path=Path(path)
    if path.is_symlink() or not path.resolve(strict=True).is_relative_to(ROOT/'.local') or not path.is_file():
        raise ValueError('entry policy must be a regular private artifact')
    value=json.loads(path.read_text())
    if (value.get('format')!='sss-entry-inventory-v1' or value.get('execution_version_sha256')!=execution_version()
            or value.get('policy_digest')!=digest({k:v for k,v in value.items() if k!='policy_digest'})):
        raise ValueError('inventory policy or reader version changed; independently recertify')
    return value
