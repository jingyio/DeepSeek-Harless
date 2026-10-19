"""Read-only inventory; historical experience is never equated with current admission."""
from collections import Counter
from pathlib import Path
from src.motif_core.offline.experience_registry import ExperienceRegistry,read,sha

def inventory(project):
    project=Path(project).resolve();profiles=[];unique=set();historical=set()
    for pointer in sorted((project/'.local/rsi').glob('*/registry/current.json')):
        registry=ExperienceRegistry(pointer.parent);current=registry.load();counts=Counter();compatible=[]
        for version in (pointer.parent/'versions').glob('*.json'):
            state=registry.load(version)
            historical.update((e['kind'],e['artifact_digest']) for e in state['entries'])
        for e in current['entries']:
            unique.add((e['kind'],e['artifact_digest']));counts[e['kind']+':'+e['state']]+=1
            valid=e['state']=='active' and all((project/n).is_file() and sha(project/n)==h for n,h in e.get('runtime_source',{}).items())
            if valid and pointer.parent.parent.name=='daily-management-real-v3':
                from .experience_library import policy_current,sources
                valid=e['runtime_source']==sources() and policy_current(read(pointer.parent/e['payload']),sources())
            if valid:compatible.append(e['entry_id'])
        profiles.append({'profile':pointer.parent.parent.name,'generation':current['generation'],'entries':len(current['entries']),
                         'counts':dict(counts),'compatible_active':len(compatible),'compatible_ids':compatible,
                         'rejected_candidates':sum(1 for _ in (pointer.parent.parent/'learning').glob('*/failure.json'))+
                           sum(1 for _ in (pointer.parent.parent/'experience/jobs').glob('*/failure.json'))})
    from .management_backup import imported_inventory
    from .experience_library import summary
    unified=summary(project/'.local/rsi/daily-management-real-v3')
    return {'format':'sss-management-inventory-v1','profiles':profiles,'unique_current_entries':len(unique),'cold_import_history':imported_inventory(project),
            'unified_experience':unified,
            'unique_historical_entries':len(historical),'count_semantics':'distinct versioned artifacts, not distinct workflow structures',
            'compatibility_semantics':'daily management checks runtime and current MCP catalog; historical profiles check source; each task still checks grants, state and certification',
            'cloud_requests':0}
