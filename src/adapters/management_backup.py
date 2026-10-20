"""Private deduplicated snapshots. Immutable evidence is never rewritten on import."""
import argparse,hashlib,json,math,os,re,shutil,stat,sys,time,zipfile
from pathlib import Path,PurePosixPath
from uuid import uuid4

ROOTS=('.local/rsi','.local/management-copies','.local/web','.local/runs','.local/file-management',
       'testpdf/file-management-experiment','.local/file-jobs','.local/operation-jobs','.local/management-acceptance','.local/management-imports')
FORMAT='sss-management-backup-v1'
EXCLUSIONS='Generated node_modules below dsh/profiles or web-dsh/profiles; DSH .credentials.yaml; provider credential files outside captured roots. Reinstall dependencies after recovery.'
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def hash_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def private_directory(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('symlink recovery destination refused')
    path.mkdir(parents=True,exist_ok=True,mode=0o700);return path.resolve()
def journal(project,action,value):
    p=private_directory(Path(project)/'.local/management-backup-logs')/(uuid4().hex+'.json')
    with p.open('x') as f:json.dump({'action':action,'time':time.time(),**value},f,ensure_ascii=False,indent=2)
    p.chmod(0o600);return str(p)
def process_image(pid):
    """Executable identity, independent of a reused PID or process title."""
    try:
        if sys.platform=='darwin':
            import ctypes
            lib=ctypes.CDLL('/usr/lib/libproc.dylib');buffer=ctypes.create_string_buffer(4096)
            lib.proc_pidpath.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_uint32]
            return buffer.value.decode() if lib.proc_pidpath(pid,buffer,4096)>0 else None
        if os.name!='nt':return os.readlink('/proc/'+str(pid)+'/exe')
        import ctypes
        from ctypes import wintypes
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=wintypes.HANDLE
        k.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
        k.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=k.OpenProcess(0x1000,False,pid)
        if not handle:return None
        try:
            buffer=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(buffer))
            return buffer.value if k.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)) else None
        finally:k.CloseHandle(handle)
    except (OSError,UnicodeError):return None
def offline(project):
    from .process_state import process_exists
    project=Path(project)
    for p in (project/'.local/web').glob('runs/*/process.json'):
        row=json.loads(p.read_text())
        if process_exists(row['harness_pid']):
            image=process_image(row['harness_pid']) if 'port' in row else None
            if image and not re.fullmatch(r'node(?:js|\d+)?(?:\.exe)?',Path(image).name.lower()):
                journal(project,'stale_service_pid',{'process_record':str(p),'pid':row['harness_pid'],'observed_executable':image,'process_untouched':True})
                continue
            raise ValueError('stop the native service before taking or restoring a snapshot')
    for p in (project/'.local/rsi').glob('*/worker.lock'):
        if process_exists(json.loads(p.read_text())['pid']):raise ValueError('wait for the original learner to seal before backup')
def scan(project,roots=ROOTS):
    project=Path(project).resolve();files=[];directories=[]
    for relative in roots:
        if relative not in ROOTS:raise ValueError('unsupported backup data root')
        base=project/relative
        if not base.exists():continue
        if base.is_symlink() or not base.is_dir():raise ValueError('backup root must be a fixed directory')
        directories.append(relative)
        paths=[]
        for parent,dirs,names in os.walk(base,followlinks=False):
            for name in list(dirs):
                p=Path(parent)/name;parts=p.relative_to(project).parts
                if name=='node_modules' and any(parts[i] in ('dsh','web-dsh') and parts[i+1]=='profiles' for i in range(len(parts)-1)):
                    dirs.remove(name)
            paths.extend(Path(parent)/n for n in [*dirs,*names])
        for p in sorted(paths):
            if p.is_symlink():raise ValueError('backup does not follow symlinks: '+str(p.relative_to(project)))
            name=p.relative_to(project).as_posix()
            if p.is_dir():directories.append(name)
            elif p.is_file():
                # Provider credentials are configured separately after restore.
                if p.name=='.credentials.yaml' and any(part in ('dsh','web-dsh') for part in p.relative_to(project).parts):continue
                s=p.stat();files.append({'path':name,'sha256':hash_file(p),'bytes':s.st_size,'executable':bool(s.st_mode&0o100)})
            else:raise ValueError('unsupported backup object')
    return {'files':files,'directories':sorted(set(directories))}
def budget_snapshot(project):
    from .continuous_rsi import ROOT
    if Path(project).resolve()!=ROOT.resolve():return {'series':{'attempts':0,'upstream_requests':0,'estimated_usd':0,'actual_bill_verified':False},'pending_usd':0,'learning_spent_usd':0,'learning_reserved_usd':0}
    import sys
    sys.path.insert(0,str(ROOT/'scenarios/file-management'))
    from experiment import accounting
    from .continuous_rsi import STATE_HOME
    runs=[r for p in STATE_HOME.glob('*/pool.json') for r in json.loads(p.read_text())['runs'].values()]
    prior=imported_budget(ROOT)
    def total(values):return None if None in values else sum(values)
    return {'series':accounting(),'pending_usd':total([r['cap_usd'] for r in runs if r['status']=='reserved']),
            'learning_spent_usd':sum(r.get('cost_usd',0) for r in runs if r['status']=='settled' and r['role']!='ordinary')+prior.get('learning_spent_usd',0),
            'learning_reserved_usd':total([r['cap_usd'] for r in runs if r['status']=='reserved' and r['role']!='ordinary']+[prior.get('learning_reserved_usd',0)])}
def backup(project,output,*,roots=ROOTS):
    project=Path(project).resolve();offline(project);output=Path(output).absolute()
    if output.exists() or output.is_symlink():raise ValueError('backup output already exists')
    if any(output.is_relative_to(project/r) for r in roots):raise ValueError('backup output cannot be inside captured data')
    private_directory(output.parent);before=scan(project,roots);budget=budget_snapshot(project)
    from .management_inventory import inventory
    from .continuous_rsi import ROOT,source_map
    source=source_map() if project==ROOT.resolve() else {}
    manifest={'format':FORMAT,'schema_version':1,'backup_id':uuid4().hex,'original_project':str(project),'roots':list(roots),
              'source_sha256':source,'experience_inventory':inventory(project),
              'snapshot':before,'budget':budget,'exclusions':EXCLUSIONS,'credentials_included':False,'evidence_bytes_rewritten':False}
    manifest['manifest_sha256']=digest(manifest)
    partial=output.with_name(output.name+'.partial-'+uuid4().hex)
    try:
        with partial.open('xb') as raw:
            os.chmod(partial,0o600)
            with zipfile.ZipFile(raw,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as archive:
                seen=set()
                for row in before['files']:
                    if row['sha256'] in seen:continue
                    h=hashlib.sha256()
                    with (project/row['path']).open('rb') as src,archive.open('blobs/'+row['sha256'],'w',force_zip64=True) as dst:
                        for b in iter(lambda:src.read(1024*1024),b''):h.update(b);dst.write(b)
                    if h.hexdigest()!=row['sha256']:raise ValueError('file changed while backing up')
                    seen.add(row['sha256'])
                archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
            raw.flush();os.fsync(raw.fileno())
        if scan(project,roots)!=before or budget_snapshot(project)!=budget or (source and source_map()!=source):raise ValueError('data changed during snapshot; original partial archive retained')
        # Link publishes without replacing an existing destination on either OS.
        os.link(partial,output);partial.unlink();output.chmod(0o600)
        result={'backup_id':manifest['backup_id'],'archive':str(output),'archive_sha256':hash_file(output),
                'files':len(before['files']),'logical_bytes':sum(r['bytes'] for r in before['files']),'archive_bytes':output.stat().st_size,
                'unique_blobs':len(seen),'budget':budget,'cloud_requests':0}
        result['receipt']=journal(project,'backup',result);return result
    except BaseException as e:
        journal(project,'backup_failed',{'partial_archive':str(partial),'reason':str(e)});raise
def read_manifest(archive):
    names=archive.namelist()
    if len(names)!=len(set(names)) or 'manifest.json' not in names:raise ValueError('duplicate or missing backup member')
    if archive.getinfo('manifest.json').file_size>128*1024*1024:raise ValueError('oversized backup manifest')
    m=json.loads(archive.read('manifest.json'))
    if m.get('format')!=FORMAT or m.get('manifest_sha256')!=digest({k:v for k,v in m.items() if k!='manifest_sha256'}):raise ValueError('backup manifest integrity differs')
    budget=m['budget'];series=budget['series']
    for n in ('attempts','upstream_requests'):
        if type(series[n]) is not int or series[n]<0:raise ValueError('invalid original budget counters')
    for v in [series['estimated_usd'],*(budget[n] for n in ('pending_usd','learning_spent_usd','learning_reserved_usd'))]:
        if type(v) not in (int,float) or not math.isfinite(v) or v<0:raise ValueError('invalid original budget amount')
    if not m['roots'] or any(r not in ROOTS for r in m['roots']):raise ValueError('unapproved backup root')
    paths=set();blobs={}
    for row in m['snapshot']['files']:
        n=row['path'];p=PurePosixPath(n)
        if '\\' in n or p.is_absolute() or any(v in ('.','..','') for v in n.split('/')) or not any(n.startswith(r+'/') for r in m['roots']) or n in paths:raise ValueError('unsafe or duplicate backup path')
        h=row['sha256']
        if len(h)!=64 or any(c not in '0123456789abcdef' for c in h) or type(row['bytes']) is not int or row['bytes']<0:raise ValueError('invalid backup blob')
        if h in blobs and blobs[h]!=row['bytes']:raise ValueError('inconsistent duplicate blob')
        paths.add(n);blobs[h]=row['bytes']
    if len(paths)>500000 or sum(r['bytes'] for r in m['snapshot']['files'])>256*1024**3:raise ValueError('backup extraction limit exceeded')
    for n in m['snapshot']['directories']:
        if '\\' in n or PurePosixPath(n).is_absolute() or any(v in ('.','..','') for v in n.split('/')) or not any(n==r or n.startswith(r+'/') for r in m['roots']):raise ValueError('unsafe backup directory')
    if set(names)!={'manifest.json',*('blobs/'+h for h in blobs)}:raise ValueError('unrecognized backup members')
    for h,size in blobs.items():
        info=archive.getinfo('blobs/'+h)
        if info.file_size!=size or stat.S_ISLNK(info.external_attr>>16):raise ValueError('backup blob identity differs')
    return m
def verify_backup(path):
    with zipfile.ZipFile(path) as z:
        m=read_manifest(z);seen=set()
        for row in m['snapshot']['files']:
            h=row['sha256']
            if h in seen:continue
            check=hashlib.sha256()
            with z.open('blobs/'+h) as f:
                for b in iter(lambda:f.read(1024*1024),b''):check.update(b)
            if check.hexdigest()!=h:raise ValueError('backup content hash differs')
            seen.add(h)
    return m
def extract_rows(archive,manifest,destination,predicate=lambda row:True):
    destination=private_directory(destination)
    with zipfile.ZipFile(archive) as z:
        for n in manifest['snapshot']['directories']:
            if predicate({'path':n}):private_directory(destination/n)
        for row in manifest['snapshot']['files']:
            if not predicate(row):continue
            target=destination/row['path'];private_directory(target.parent)
            if target.exists() or target.is_symlink():raise ValueError('restore never overwrites files')
            with z.open('blobs/'+row['sha256']) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            target.chmod(0o700 if row['executable'] else 0o600)
            if hash_file(target)!=row['sha256']:raise ValueError('restored content differs')
def restore(project,archive,destination):
    m=verify_backup(archive);destination=Path(destination).absolute()
    if destination.resolve()!=Path(m['original_project']).resolve():raise ValueError('changed project path requires cold migrate; immutable evidence and old grants are not rewritten')
    private_directory(destination);offline(destination)
    current=scan(destination,m['roots']);wanted=m['snapshot'];missing=[]
    for r in m['roots']:
        def portion(s):return {'files':[v for v in s['files'] if v['path'].startswith(r+'/')],'directories':[v for v in s['directories'] if v==r or v.startswith(r+'/')]}
        now,old=portion(current),portion(wanted)
        if now==old:continue
        if now['files'] or (destination/r).exists():raise ValueError('existing data differs; restore refused before writing: '+r)
        missing.append(r)
    if missing:
        stage=private_directory(destination/'.local/management-restore-staging'/uuid4().hex)
        extract_rows(archive,m,stage,lambda row:any(row['path']==r or row['path'].startswith(r+'/') for r in missing))
        for r in missing:
            target=destination/r;private_directory(target.parent)
            if target.exists():raise ValueError('restore target changed; staged recovery retained')
            (stage/r).rename(target)
    if scan(destination,m['roots'])!=wanted:raise ValueError('restored snapshot differs')
    result={'passed':True,'backup_id':m['backup_id'],'restored_roots':missing,'original_bytes_and_budget_preserved':True,'cloud_requests':0}
    result['receipt']=journal(project,'restore',result);return result
def migrate(project,archive,destination):
    m=verify_backup(archive);destination=Path(destination).absolute()
    if destination.resolve()==Path(m['original_project']).resolve():raise ValueError('use restore for the original path')
    private_directory(destination);offline(destination)
    marker=destination/'.local/management-imports/current.json'
    if marker.exists():
        existing=json.loads(marker.read_text())
        if existing['backup_id']==m['backup_id']:
            imported_budget(destination)
            return {'passed':True,'idempotent':True,'backup_id':m['backup_id'],'cloud_requests':0}
        raise ValueError('a different migration already exists; cannot reset or merge original budgets')
    if any(p.exists() for p in [destination/'.local/rsi',destination/'.local/management-copies',destination/'.local/web']):raise ValueError('cold migration needs an unused target checkout')
    store=private_directory(destination/'.local/management-imports'/m['backup_id']);saved=store/'original.zip'
    if not saved.exists():
        with Path(archive).open('rb') as src,saved.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
        saved.chmod(0o600)
    if hash_file(saved)!=hash_file(archive):raise ValueError('migration archive differs')
    # User copies are portable. Historical tasks/certificates remain exact bytes
    # in the archive; their old absolute paths never become fresh permissions.
    extract_rows(saved,m,store/'user-files',lambda row:row['path']=='.local/management-copies' or row['path'].startswith('.local/management-copies/'))
    # Preserve native whole-service counters independently of the fresh session.
    checkpoints={row['path'] for row in m['snapshot']['files'] if row['path'].startswith('.local/web/runs/') and row['path'].endswith('/global-budget.json')}
    admissions={p.rsplit('/',1)[0]+'/effective-config.json' for p in checkpoints}
    extract_rows(saved,m,destination,lambda row:row['path'] in checkpoints|admissions)
    value={'format':'sss-management-cold-import-v1','backup_id':m['backup_id'],'archive':str(saved.resolve()),'archive_sha256':hash_file(saved),
           'manifest_sha256':m['manifest_sha256'],'budget':m['budget'],'historical_evidence_unchanged':True,
           'old_tasks_resumed':False,'old_candidates_automatically_activated':False,'imported_user_files':str((store/'user-files/.local/management-copies').resolve())}
    value['receipt_sha256']=digest(value);private_directory(marker.parent)
    with marker.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    marker.chmod(0o600);journal(project,'cold_migrate',{'destination':str(destination),'backup_id':m['backup_id']})
    return {'passed':True,**value,'cloud_requests':0}
def imported_budget(project):
    marker=Path(project)/'.local/management-imports/current.json'
    if not marker.exists():return {}
    r=json.loads(marker.read_text())
    if r.get('format')!='sss-management-cold-import-v1' or r.get('receipt_sha256')!=digest({k:v for k,v in r.items() if k!='receipt_sha256'}):raise ValueError('migration budget receipt changed')
    path=Path(r['archive'])
    if not path.resolve().is_relative_to((Path(project)/'.local/management-imports').resolve()) or path.is_symlink():raise ValueError('migration archive outside private import')
    with zipfile.ZipFile(path) as z:m=read_manifest(z)
    if m['backup_id']!=r['backup_id'] or m['manifest_sha256']!=r['manifest_sha256'] or m['budget']!=r['budget']:raise ValueError('migration original budget differs')
    return r['budget']
def imported_inventory(project):
    if not imported_budget(project):return None
    r=json.loads((Path(project)/'.local/management-imports/current.json').read_text())
    with zipfile.ZipFile(r['archive']) as z:return read_manifest(z).get('experience_inventory')
def cli(project,command,argv):
    ap=argparse.ArgumentParser();ap.add_argument('--archive',type=Path);ap.add_argument('--output',type=Path);ap.add_argument('--destination',type=Path)
    a=ap.parse_args(argv)
    if command=='backup':
        if not a.output:ap.error('--output required')
        value=backup(project,a.output)
    else:
        if not a.archive:ap.error('--archive required')
        if command=='verify-backup':
            m=verify_backup(a.archive);value={'passed':True,'backup_id':m['backup_id'],'files':len(m['snapshot']['files']),'budget':m['budget'],'cloud_requests':0}
        elif command=='restore':value=restore(project,a.archive,a.destination or project)
        else:
            if not a.destination:ap.error('--destination required')
            value=migrate(project,a.archive,a.destination)
    print(json.dumps(value,ensure_ascii=False,indent=2));return 0
