"""Trusted product releases of re-certified Motifs, separate from private proof.

Publishing requires the original independent private certificate. Installation
verifies a read-only product manifest and source locks; it never imports user
files, historical task grants, raw traces, or another account's mutable registry.
"""
from pathlib import Path
import re
from src.motif_core.offline.experience_registry import read,sha,digest,durable,ExperienceRegistry

FORMAT='sss-management-seed-release-v1'
CERT='sss-management-seed-attestation-v1'


def validate_historical_certificate(policy,certificate,raw_sha,project=None):
    """Immutable public provenance only; never grants execution on current code."""
    from .continuous_rsi import ROOT
    root=Path(project or ROOT).resolve();cert=read(certificate)
    name=cert.get('release','')
    if not re.fullmatch(r'file-v[1-9][0-9]*',name):raise ValueError('unregistered management seed release')
    release=root/'motif-libraries'/name
    if any(p.is_symlink() for p in (release,*release.parents)):raise ValueError('seed release symlink refused')
    manifest=read(release/'entry.json')
    if manifest.get('format')!=FORMAT or manifest.get('digest')!=digest({k:v for k,v in manifest.items() if k!='digest'}):raise ValueError('seed manifest changed')
    for name,h in manifest['files'].items():
        p=Path(name)
        if not re.fullmatch(r'(?:policies|certificates)/[a-f0-9]{64}\.json',name) or (release/p).is_symlink() or sha(release/p)!=h:raise ValueError('seed release object changed')
    if policy.get('policy_digest') != digest({k:v for k,v in policy.items() if k!='policy_digest'}):raise ValueError('seed policy digest changed')
    item=next((r for r in manifest['entries'] if r['policy_digest']==policy['policy_digest']),None)
    if not item or item['payload_sha256']!=raw_sha or sha(certificate)!=manifest['files'][item['certificate']]:raise ValueError('seed policy/certificate not in trusted release')
    if (cert.get('format')!=CERT or cert.get('policy_digest')!=policy['policy_digest'] or cert.get('payload_sha256')!=raw_sha
        or cert.get('quality')!='sss-management-quality-v7' or cert.get('holdout_used') is not False
        or cert.get('private_evidence_verified') is not True or cert.get('grants_execution') is not False):raise ValueError('invalid public seed attestation')
    witnesses=cert.get('witnesses',[])
    if ([r.get('role') for r in witnesses]!=['native_certification','candidate_certification','candidate_certification']
        or len({r['task_fingerprint'] for r in witnesses})!=3 or set(policy['artifact']['source_task_fingerprints'])&{r['task_fingerprint'] for r in witnesses}
        or any(not r['accepted'] or not r['lifecycle_verified'] or r['repairs'] or r['deferred'] or not r['observed_usage_complete'] for r in witnesses)):
        raise ValueError('public seed lacks clean independent native and actual certification')
    return cert


def validate_certificate(policy,certificate,raw_sha,project=None):
    from .continuous_rsi import ROOT,source_map
    from .mcp_learning import adapter
    from .experience_library import policy_current
    cert=validate_historical_certificate(policy,certificate,raw_sha,project)
    root=Path(project or ROOT).resolve()
    manifest=read(root/'motif-libraries'/cert['release']/'entry.json')
    runtime=source_map(adapter('management_v3').runtime_sources())
    if manifest.get('runtime_source')!=runtime or not policy_current(policy,runtime):raise ValueError('seed runtime/catalog version changed')
    return cert


def install(cfg):
    from .continuous_rsi import ROOT
    from .experience_library import sources
    registry=ExperienceRegistry(Path(cfg['state_root'])/'registry');state=registry.load();known={r['entry_id'] for r in state['entries']}
    releases=sorted((ROOT/'motif-libraries').glob('file-v*'),key=lambda p:int(p.name[6:]) if re.fullmatch(r'file-v[1-9][0-9]*',p.name) else -1,reverse=True)
    additions=[]
    for release in releases:
        if not (release/'entry.json').is_file():continue
        try:
            manifest=read(release/'entry.json')
            if manifest.get('runtime_source')!=sources():continue
            validated=[]
            for item in manifest['entries']:
                if any(not re.fullmatch(r'(?:policies|certificates)/[a-f0-9]{64}\.json',item.get(k,'')) or item[k] not in manifest['files'] for k in ['payload','certificate']):raise ValueError('seed path outside trusted manifest')
                payload=release/item['payload'];certificate=release/item['certificate'];policy=read(payload)
                validate_certificate(policy,certificate,sha(payload))
                if item['policy_digest'] not in known:validated.append((item,payload,certificate))
            for item,payload,certificate in validated:
                additions.append(registry.entry(item['kind'],payload,sources(),certificate));known.add(item['policy_digest'])
            break
        except (ValueError,KeyError,TypeError,OSError) as error:
            # An incompatible or damaged seed is never execution authority and
            # must not prevent an ordinary task from running. Keep one receipt
            # per release/target/failure; never silently rewrite its certificate.
            failure={'release':release.name,'manifest_sha256':sha(release/'entry.json'),
                     'runtime_source':sources(),'reason':str(error),'activated':False}
            receipt=Path(cfg['state_root'])/'seed-rejections'/(digest(failure)+'.json')
            if not receipt.exists():durable(receipt,failure,exclusive=True)
    if additions:return registry.publish(additions,expected=state['generation'],reason='trusted re-certified public seeds; account guards and future learning remain independent')
    return state


def publish(config,release_name):
    """Run only against fully re-certified current private records before commit."""
    from .continuous_rsi import ROOT,load_config
    from .experience_library import sources,policy_current
    from src.motif_core.offline.experience_registry import check_motif_certificate
    if not re.fullmatch(r'file-v[1-9][0-9]*',release_name):raise ValueError('invalid fresh seed release name')
    cfg=load_config(config);root=Path(cfg['state_root'])/'registry';state=ExperienceRegistry(root).load()
    release=ROOT/'motif-libraries'/release_name
    if release.exists():raise ValueError('never overwrite a public release')
    manifest={'format':FORMAT,'quality':'sss-management-quality-v7','runtime_source':sources(),'entries':[],'files':{},
              'raw_private_evidence_published':False,'grants_execution':False}
    checked=[]
    for e in state['entries']:
        if e['state']!='active' or e['runtime_source']!=sources():continue
        policy=read(root/e['payload'])
        if not policy_current(policy,sources()):continue
        certfile=root/e['certificate']['file'];cert=check_motif_certificate(policy,certfile,e['sha256'])
        if cert.get('format')==CERT:continue
        witnesses=[]
        for review in [cert['native_review'],*cert['reviews']]:
            record=read(review['record_file'])
            witnesses.append({'role':record['role'],'task_fingerprint':record['task_fingerprint'],'record_sha256':sha(review['record_file']),
                'accepted':record['accepted'],'lifecycle_verified':record['lifecycle_verified'],'observed_usage_complete':record['observed_usage_complete'],
                'repairs':record['metrics'].get('acceptance_repairs',0),'deferred':bool(record['deferred']),
                'upstream_requests':record['upstream_requests'],'cost_usd':record['cost_usd'],'verified_motif_batches':record['verified_motif_batches']})
        # Any host path in the serialized program is unsuitable for a public seed.
        raw=(root/e['payload']).read_text()
        if str(ROOT) in raw or '/Users/' in raw or '/home/' in raw:raise ValueError('private path remains in serialized seed')
        attestation={'format':CERT,'release':release_name,'policy_digest':policy['policy_digest'],'payload_sha256':e['sha256'],
            'quality':'sss-management-quality-v7','holdout_used':False,'private_evidence_verified':True,'grants_execution':False,
            'original_certificate_sha256':sha(certfile),'witnesses':witnesses}
        checked.append((e,policy,attestation))
    if not checked:raise ValueError('no independently re-certified current seeds to publish')
    release.mkdir(parents=True)
    for e,policy,cert in checked:
        name=e['entry_id'];payload='policies/'+name+'.json';certificate='certificates/'+name+'.json'
        (release/payload).parent.mkdir(exist_ok=True);(release/certificate).parent.mkdir(exist_ok=True)
        (release/payload).write_bytes((root/e['payload']).read_bytes());durable(release/certificate,cert,exclusive=True)
        manifest['entries'].append({'kind':e['kind'],'policy_digest':name,'payload':payload,'payload_sha256':sha(release/payload),'certificate':certificate})
        for f in [payload,certificate]:manifest['files'][f]=sha(release/f)
    manifest['digest']=digest(manifest);durable(release/'entry.json',manifest,exclusive=True)
    return {'release':release_name,'entries':len(checked),'private_raw_files_published':0}
