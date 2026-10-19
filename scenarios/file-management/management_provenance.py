"""Replay original copy/move journals; equal bytes do not imply equal origins."""
import copy
from pathlib import Path
from common import digest,sha

FORMAT='sss-management-read-provenance-v1'


class ReadReplayPath:
    """Frozen bytes, parsed with the extension actually observed by read_file."""
    def __init__(self,source,observed_path):self.source=Path(source);self.suffix=Path(observed_path).suffix
    def __fspath__(self):return str(self.source)
    def __str__(self):return str(self.source)
    def __getattr__(self,name):return getattr(self.source,name)


def lineage_history(spec,state):
    expected=copy.deepcopy(spec['initial_tree'])
    origins={k+'/'+n:k+'/'+n for k,t in expected.items() for n in t['files']}
    history=[];cursor=[]
    def remember():history.append({'tree':copy.deepcopy(expected),'origins':dict(origins),'cursor':copy.deepcopy(cursor)})
    remember()
    for pid,j in state.get('journals',{}).items():
        if j['before']!=expected:raise ValueError('source lineage journal chain differs')
        plan=state['plans'][pid];before_origins=dict(origins);before_tree=copy.deepcopy(expected)
        if plan['before']!=expected or plan['task_sha256']!=digest(spec):raise ValueError('source lineage original plan differs')
        writes={}
        for a in plan['actions']:
            if a['op'] in ('mkdir','read','delete'):continue
            source=a['source_root']+'/'+a['source']
            if source not in before_origins or expected[a['source_root']]['files'].get(a['source'])!=a['source_sha256']:
                raise ValueError('source lineage lacks original action source')
            writes[a['destination_root']+'/'+a['destination']]=(before_origins[source],a['source_sha256'])
        if len(j['completed'])!=len(j['boundaries']):raise ValueError('source lineage incomplete effect boundaries')
        for e,b in zip(j['completed'],j['boundaries']):
            if b['before']!=expected:raise ValueError('source lineage effect chain differs')
            legal=copy.deepcopy(expected);t=legal[e['root']];key=e['root']+'/'+e['path']
            if e['kind']=='mkdir':t['directories']=sorted(set(t['directories'])|{e['path']})
            elif e['kind']=='unlink':t['files'].pop(e['path'],None);origins.pop(key,None)
            elif e['kind'] in ('publish','replace'):
                if key not in writes or writes[key][1]!=e['sha256']:raise ValueError('source lineage publish is not from the validated action')
                t['files'][e['path']]=e['sha256'];origins[key]=writes[key][0]
            else:raise ValueError('source lineage unknown effect')
            if legal!=b['after']:raise ValueError('source lineage effect footprint differs')
            expected=legal
        complete=len(j['completed'])==len(j['effects'])
        cursor.append([pid,'executed_verified' if complete else 'executing',len(j['completed']),0]);remember()
        if j['status']=='restored_verified':
            chain=j['restore_before']
            if chain!=expected:raise ValueError('source lineage restoration starts elsewhere')
            for b in j.get('restore_boundaries',[]):
                if b['before']!=chain:raise ValueError('source lineage restoration chain differs')
                chain=b['after']
            if chain!=before_tree:raise ValueError('source lineage restoration did not restore the original tree')
            expected=before_tree;origins=before_origins
            cursor[-1]=[pid,'restored_verified',len(j['completed']),j['restored_count']];remember()
        elif j['status']!='executed_verified':
            raise ValueError('source lineage needs the original unfinished plan recovered first')
    if expected!=state['expected_tree']:raise ValueError('source lineage current tree differs')
    return history


def read_provenance(spec,state,readback):
    current=lineage_history(spec,state)[-1];name=readback['path']
    root,relative=name.split('/',1)
    if current['tree'][root]['files'].get(relative)!=readback['sha256']:raise ValueError('read provenance current bytes differ')
    proof={'format':FORMAT,'task_sha256':digest(spec),'source_id':readback['source_id'],
           'origin':current['origins'][name],'snapshot_sha256':digest(current['tree']),'cursor':current['cursor'],
           'readback_sha256':digest({k:v for k,v in readback.items() if k not in ('provenance','_sss_scope','_sss_authorized')})}
    return {**proof,'proof_sha256':digest(proof)}


def read_origin(spec,readback,state,*,allow_legacy=False):
    """Use path identity plus actual journal lineage, never a same-SHA guess."""
    name=readback['path'];root,relative=name.split('/',1)
    if root!='workspace':raise ValueError('external provenance cannot silently become learning authority')
    if readback.get('file_id')!='file:local:'+digest({'path':name,'sha':readback['sha256']})[:24]:raise ValueError('read provenance file identity differs')
    if readback.get('source_version')!=digest({'path':name,'sha':readback['sha256'],'parser':'fm-parser-v1'}):raise ValueError('read provenance source version differs')
    history=lineage_history(spec,state);proof=readback.get('provenance')
    if proof:
        if (proof.get('format')!=FORMAT or proof.get('proof_sha256')!=digest({k:v for k,v in proof.items() if k!='proof_sha256'})
                or proof.get('task_sha256')!=digest(spec) or proof.get('source_id')!=readback['source_id']
                or proof.get('readback_sha256')!=digest({k:v for k,v in readback.items() if k not in ('provenance','_sss_scope','_sss_authorized')})):
            raise ValueError('read provenance immutable binding differs')
        matches=[h for h in history if h['cursor']==proof['cursor'] and digest(h['tree'])==proof['snapshot_sha256']
                 and h['tree'].get(root,{}).get('files',{}).get(relative)==readback['sha256'] and h['origins'].get(name)==proof['origin']]
    elif allow_legacy:
        matches=[h for h in history if h['tree'].get(root,{}).get('files',{}).get(relative)==readback['sha256'] and name in h['origins']]
        if len({h['origins'][name] for h in matches})!=1:raise ValueError('legacy read provenance is absent or ambiguous')
    else:raise ValueError('new read provenance proof required')
    if not matches:raise ValueError('read provenance has no actual original boundary')
    origin=matches[0]['origins'][name];origin_root,origin_path=origin.split('/',1)
    if origin_root!='workspace' or spec['initial_tree'][origin_root]['files'].get(origin_path)!=readback['sha256']:
        raise ValueError('read provenance does not originate in the original task')
    return origin_path


def resolve_read_source(spec,readback,state,pristine,*,allow_legacy=False):
    origin_path=read_origin(spec,readback,state,allow_legacy=allow_legacy)
    base=Path(pristine).resolve();source=base/origin_path
    if not source.resolve().is_relative_to(base) or any(p.is_symlink() for p in (source,*source.parents) if p.is_relative_to(base)):
        raise ValueError('read provenance escapes the frozen material')
    if not source.is_file() or sha(source)!=readback['sha256']:raise ValueError('read provenance original bytes differ')
    return source


def check_goal_action(spec,state,action):
    """Reject known wrong effects before they need cleanup or high-risk deletion."""
    goal=spec.get('quality',{}).get('goal',{})
    if goal.get('state')!='frozen' or 'expected_roots' not in goal:return
    a=action;op=a['op'];expected=goal['expected_roots'];targets=goal.get('expected_origins',{})
    if op=='read':return
    if op=='mkdir':
        if a['destination'] not in expected[a['destination_root']]['directories']:raise ValueError('frozen goal does not request this directory')
        return
    source=a['source_root']+'/'+a['source'];source_kept=expected[a['source_root']]['files'].get(a['source'])==a['source_sha256']
    if op=='delete':
        if source_kept:raise ValueError('frozen goal preserves this original source')
        return
    target=a['destination_root']+'/'+a['destination']
    intermediate=goal.get('intermediate_sources',{}).get(target,{})
    if expected[a['destination_root']]['files'].get(a['destination'],intermediate.get('sha256'))!=a['source_sha256']:
        raise ValueError('frozen goal file mapping differs; use the declared final destination, without extra source-directory layers or quarantine copies')
    current=lineage_history(spec,state)[-1]['origins']
    if targets.get(target,intermediate.get('origin'))!=current.get(source):raise ValueError('frozen goal source lineage differs from the actual original input')
    if op=='copy' and not source_kept:raise ValueError('frozen goal requires moving this source, not leaving an extra copy')
    if op in ('move','rename','quarantine') and source_kept:raise ValueError('frozen goal preserves this source; use a copy instead')
