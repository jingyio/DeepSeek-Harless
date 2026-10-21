/** Immutable, account-local result copies. Never expose inputs, logs, or runtime credentials. */
import { createHash } from 'node:crypto';
import { existsSync, lstatSync, realpathSync, readdirSync, readFileSync, mkdirSync, writeFileSync, renameSync } from 'node:fs';
import { join, resolve, relative, sep } from 'node:path';
import {nativePresentedFiles} from './geneloop_native_work.ts';
const sha = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
const within = (root: string, path: string) => { const rel = relative(realpathSync(root), realpathSync(path)); return rel && !rel.startsWith('..' + sep) && rel !== '..' && !rel.startsWith(sep); };
const valid = (id: string) => /^[a-zA-Z0-9-]{1,100}$/.test(id);
export function comparisonArtifacts(output: string) {
  const root = join(output, 'comparison-artifacts'); mkdirSync(root, { recursive: true, mode: 0o700 });
  return {
    snapshot(turn: string, lane: string, attempt: number, workspace: string, approvedFiles?:Set<string>, recoverEmpty = false, codeFiles = new Set<string>(), timeWindow?: {start:number;end:number}, expectedHashes=new Map<string,string>()) {
      if (!valid(turn) || !['baseline', 'motif'].includes(lane) || !Number.isInteger(attempt) || attempt < 0) throw Error('artifact_identity_invalid');
      const destination = join(root, turn, lane, String(attempt));
      const index = join(destination, 'index.json');
      const previous = existsSync(index) ? JSON.parse(readFileSync(index, 'utf8')) : undefined;
      // Stored bytes are immutable. Older indexes may contain drafts; only
      // task-bound evidence can migrate their public list and add verified files.
      if (previous && !approvedFiles) return previous;
      if (previous && !recoverEmpty) return previous.filter((row:any)=>
        ['data-report-delivery-v1','code-output-v1'].includes(row.verification)||approvedFiles!.has(join(workspace,row.name)));
      mkdirSync(destination, { recursive: true, mode: 0o700 });
      const rows: any[] = previous ? previous.filter((row:any)=>row.verification==='code-output-v1'||
        approvedFiles!.has(join(workspace,row.name))&&existsSync(join(workspace,row.name))&&
        sha(readFileSync(join(workspace,row.name)))===row.sha256).map((row:any)=>({...row,
          verification:row.verification==='code-output-v1'?'code-output-v1':'data-report-delivery-v1'})) : [];
      let total = rows.reduce((sum,row)=>sum+row.bytes,0), nextIndex = previous?.length ?? 0;
      const copy = (path: string, name: string) => {
        const commandFile = name.startsWith('outputs/code/') || name.startsWith('code/');
        if (commandFile && !codeFiles.has(path)) return;
        if(approvedFiles&&!approvedFiles.has(path))return;
        if(rows.some(row=>row.name===name))return;
        const st = lstatSync(path);
        if (timeWindow && !expectedHashes.has(path) && (st.mtimeMs < timeWindow.start || st.mtimeMs >= timeWindow.end + 1)) return;
        if (!st.isFile() || st.isSymbolicLink() || st.nlink !== 1 || !within(workspace, path) ||
            rows.length >= 32 || st.size > 30 * 1024 * 1024 || total + st.size > 80 * 1024 * 1024) return;
        const bytes = readFileSync(path), digest = sha(bytes);
        if(expectedHashes.has(path)&&expectedHashes.get(path)!==digest)return;
        let id = digest.slice(0, 32) + '-' + nextIndex++;
        while(existsSync(join(destination,id)))id=digest.slice(0,32)+'-'+nextIndex++;
        writeFileSync(join(destination, id), bytes, { mode: 0o600, flag: 'wx' });
        rows.push({ id, name, bytes: bytes.length, sha256: digest, attempt,
          ...(commandFile ? {verification:'code-output-v1'} : approvedFiles?{verification:'data-report-delivery-v1'}:{}) }); total += bytes.length;
      };
      const scan = (directory: string, prefix: string, depth: number) => {
        if (!existsSync(directory) || depth > 5) return;
        const stat = lstatSync(directory); if (!stat.isDirectory() || stat.isSymbolicLink() || !within(workspace, directory)) return;
        for (const name of readdirSync(directory).sort()) {
          if (name.startsWith('.') || rows.length >= 32) continue;
          const path = join(directory, name), st = lstatSync(path);
          if (st.isSymbolicLink() || !within(workspace, path)) continue;
          if (st.isDirectory()) { scan(path, prefix + name + '/', depth + 1); continue; }
          if (!st.isFile() || st.nlink !== 1 || st.size > 30 * 1024 * 1024 || total + st.size > 80 * 1024 * 1024) continue;
          if (!expectedHashes.has(path) && !/\.(?:pdf|pptx|png|jpg|svg|csv|tsv|html|md|tex|bib|txt)$/i.test(name) &&
              !((prefix.startsWith('outputs/code/') || prefix.startsWith('code/')) && /\.(?:docx|xlsx|json|zip|py|js)$/i.test(name))) continue;
          copy(path, prefix + name);
        }
      };
      // Scene adapters place only derived deliverables here. Literature task/cache/journal are excluded.
      for (const directory of ['outputs', 'output', 'validation', 'literature/outputs', 'literature/deliverables', 'file-results', 'code']) scan(join(workspace, directory), directory + '/', 0);
      if (existsSync(join(workspace, 'literature/delivery-receipt.json'))) for (const name of ['research-notes.md', 'evidence.json']) {
        const path = join(workspace, 'literature', name); if (existsSync(path)) copy(path, 'literature/' + name);
      }
      if (previous) {
        writeFileSync(index + '.tmp', JSON.stringify(rows), { mode: 0o600 }); renameSync(index + '.tmp', index);
      } else writeFileSync(index, JSON.stringify(rows), { mode: 0o600, flag: 'wx' });
      return rows;
    },
    read(turn: string, lane: string, row: any) {
      if (!valid(turn) || !['baseline', 'motif'].includes(lane) || !/^[a-f0-9]{32}-\d+$/.test(row.id) || !Number.isInteger(row.attempt)) throw Error('artifact_identity_invalid');
      const path = resolve(root, turn, lane, String(row.attempt), row.id), st = lstatSync(path);
      if (!within(root, path) || !st.isFile() || st.isSymbolicLink() || st.nlink !== 1 || st.size !== row.bytes) throw Error('artifact_version_changed');
      const bytes = readFileSync(path); if (sha(bytes) !== row.sha256) throw Error('artifact_version_changed'); return bytes;
    },
  };
}

/** Layout drafts are not delivered reports. Only a successful immutable
 * delivery receipt, matching actual PDF bytes, permits a public download. */
export function verifiedReportFiles(workspace:string, deliveredReports?:Map<string,string>){
  const allowed=new Set<string>(),directory=join(workspace,'outputs/report/records');
  if(!existsSync(directory))return allowed;
  const verifiedFile=(path:unknown,digest:unknown)=>{
    if(typeof path!=='string'||typeof digest!=='string'||!/^[a-f0-9]{64}$/.test(digest)||
       !existsSync(path)||!within(workspace,path))return false;
    const file=lstatSync(path);
    return file.isFile()&&!file.isSymbolicLink()&&file.nlink===1&&file.size<=30*1024*1024&&sha(readFileSync(path))===digest;
  };
  const recordFor=(identifier:unknown,kind:string,delivery:any)=>{
    if(typeof identifier!=='string'||!/^rra-[a-z_]+-[a-f0-9]+$/.test(identifier))return;
    const path=join(directory,identifier+'.json');if(!existsSync(path)||!within(workspace,path))return;
    const st=lstatSync(path);if(!st.isFile()||st.isSymbolicLink()||st.nlink!==1||st.size>1000000)return;
    const record=JSON.parse(readFileSync(path,'utf8'));
    if(record.id!==identifier||record.kind!==kind||record.workspace_id!==delivery.workspace_id||
       record.source_version!==delivery.source_version||record.payload?.plan_id!==delivery.payload.plan_id)return;
    return record.payload;
  };
  for(const name of readdirSync(directory).slice(0,2048)){
    if(!name.endsWith('.json'))continue;
    const path=join(directory,name),st=lstatSync(path);
    if(!st.isFile()||st.isSymbolicLink()||st.nlink!==1||st.size>1000000)continue;
    try{
      const record=JSON.parse(readFileSync(path,'utf8')),row=record.payload;
      if(record.kind!=='delivery'||row?.delivered!==true||row.quality_passed!==true||typeof row.path!=='string'||
        !existsSync(row.path)||!within(workspace,row.path))continue;
      if(deliveredReports&&deliveredReports.get(row.path)!==row.sha256)continue;
      if(!verifiedFile(row.path,row.sha256))continue;
      allowed.add(row.path);
      // A delivered report also owns its verified charts. Do not publish all
      // images in the workspace: trace the same plan's immutable evidence chain.
      const report=recordFor(row.report_id,'report',record);
      if(!report||report.quality_passed!==true||report.path!==row.path||report.sha256!==row.sha256)continue;
      const draft=recordFor(report.draft_id,'report_draft',record);
      const packet=draft&&recordFor(draft.packet_id,'evidence_packet',record);
      if(packet?.quality_passed!==true)continue;
      const bundle=recordFor(packet.figure_bundle_id,'figure_bundle',record);
      if(!bundle||bundle.analysis_id!==packet.analysis_id||bundle.evidence_id!==packet.evidence_id)continue;
      for(const figure of (Array.isArray(bundle.figures)?bundle.figures:[]).slice(0,32))for(const extension of ['pdf','png','svg']){
        const path=figure.paths?.[extension];
        if(typeof path==='string'&&path.toLowerCase().endsWith('.'+extension)&&verifiedFile(path,figure.sha256?.[extension]))allowed.add(path);
      }
    }catch{/* Malformed or changed evidence is not a delivery grant. */}
  }
  return allowed;
}

/** Review PDFs are a separate product from verified statistical reports. Their
 * exact files must be named by this task's successful export tool result. */
export function verifiedReviewFiles(workspace:string, proof:Map<string,string>){
  const allowed=new Set<string>(), directory=join(workspace,'outputs/documents');
  if(!existsSync(directory)||lstatSync(directory).isSymbolicLink())return allowed;
  for(const name of readdirSync(directory).slice(0,2048)){
    if(!/^[a-f0-9]{32}$/.test(name))continue;
    const folder=join(directory,name),receiptPath=join(folder,'delivery.json');
    if(lstatSync(folder).isSymbolicLink()||!existsSync(receiptPath)||!within(workspace,receiptPath))continue;
    try{
      const stat=lstatSync(receiptPath);
      if(!stat.isFile()||stat.isSymbolicLink()||stat.nlink!==1||stat.size>1000000)continue;
      const receipt=JSON.parse(readFileSync(receiptPath,'utf8'));
      if(receipt.kind!=='source_bound_review'||receipt.layout_passed!==true||
        !['paper-review','input-review'].includes(receipt.category)||!Array.isArray(receipt.files)||receipt.files.length!==2)continue;
      const approved=JSON.parse(readFileSync(join(workspace,'approved-inputs.json'),'utf8')).files;
      if(Object.keys(approved).length!==Object.keys(receipt.source_versions??{}).length||
         Object.entries(approved).some(([key,value])=>receipt.source_versions[key]!==value))continue;
      const files:string[]=[];
      for(const row of receipt.files){
        if(typeof row.name!=='string'||!/^outputs\/documents\/[a-f0-9]{32}\/(?:paper-review|input-review)\.(?:pdf|md)$/.test(row.name))continue;
        const path=join(workspace,row.name);
        if(proof.get(path)!==row.sha256||!existsSync(path)||!within(folder,path))continue;
        const st=lstatSync(path);
        if(st.isFile()&&!st.isSymbolicLink()&&st.nlink===1&&st.size===row.bytes&&st.size<=30*1024*1024&&sha(readFileSync(path))===row.sha256)files.push(path);
      }
      if(files.length===2)files.forEach(path=>allowed.add(path));
    }catch{/* Changed sources or deliverables are not a publication grant. */}
  }
  return allowed;
}

/** A later model-summary failure does not revoke a verified report delivery.
 * Incomplete drafts and other scenes still require normal task completion. */
export function captureComparisonDeliveries(service: ReturnType<typeof comparisonArtifacts>, context: {
  turn: string; lane: string; attempt: number; workspace: string; adapter?: string; status: string;
  eventsPath?: string; startedAt?: string; finishedAt?: string; recoverMissing?: boolean; answer?: string;
}) {
  // Retrospective recovery needs a scene-specific proof format. A directory
  // scan of a persistent Session could otherwise pick up a later turn's files.
  if (context.recoverMissing && context.adapter !== 'data-report') return [];
  if (!['completed','failed','budget_exhausted','cancelled'].includes(context.status)) return [];
  if(context.status!=='completed'&&context.adapter!=='data-report')return [];
  let approved: Set<string> | undefined;
  const codeFiles = new Set<string>();
  const start = Date.parse(context.startedAt ?? ''), end = Date.parse(context.finishedAt ?? '');
  const mentioned = new Set<string>();
  // Scratch contains implementation files too. Publish only primary outputs
  // explicitly named in the task's closing prose, never every scratch file.
  for (const match of (context.answer ?? '').matchAll(/`([^`\n]+)`|\]\(([^)\s]+)\)/g)) mentioned.add(match[1] ?? match[2]);
  const scanCode = (path:string, depth=0, scratch=false) => {
    if (depth>5 || codeFiles.size>=32 || !existsSync(path)) return;
    const st=lstatSync(path);
    if (st.isSymbolicLink() || !within(context.workspace,path)) return;
    if (st.isDirectory()) for (const name of readdirSync(path).slice(0,256)) { if(!name.startsWith('.'))scanCode(join(path,name),depth+1,scratch); }
    else if(st.isFile() && st.nlink===1 && st.mtimeMs>=start && st.mtimeMs<end+1) {
      const local = relative(join(context.workspace,'code'),path).split(sep).join('/');
      if (!scratch || [local, '/work/'+local, 'sandbox:/work/'+local].some(name=>mentioned.has(name))) codeFiles.add(path);
    }
  };
  if(context.status==='completed'&&!context.recoverMissing&&Number.isFinite(start)&&Number.isFinite(end)){scanCode(join(context.workspace,'outputs/code'));scanCode(join(context.workspace,'code'),0,true);}
  const presented=nativePresentedFiles(context,false);
  for(const path of presented.keys())codeFiles.add(path);
  if (context.adapter === 'data-report') {
    // The Session can contain later successful turns. Only this failed task's
    // own bounded tool events may grant a recovered download.
    const delivered = context.status !== 'completed'||context.recoverMissing ? taskReportDeliveries(context) : undefined;
    approved=verifiedReportFiles(context.workspace,delivered);
    for(const path of verifiedReviewFiles(context.workspace,taskReportDeliveries(context,context.workspace)))approved.add(path);
    for(const path of codeFiles)approved.add(path);
    if ((context.status !== 'completed'||context.recoverMissing)&&!approved.size)return [];
  }
  return service.snapshot(context.turn, context.lane, context.attempt, context.workspace, approved, context.recoverMissing === true, codeFiles,
    context.adapter === 'workspace' && Number.isFinite(start) && Number.isFinite(end) ? {start,end} : undefined,presented);
}

function taskReportDeliveries(context: { eventsPath?: string; startedAt?: string; finishedAt?: string }, reviewWorkspace?:string) {
  const found = new Map<string, string>(), calls = new Set<string>();
  const start = Date.parse(context.startedAt ?? ''), end = Date.parse(context.finishedAt ?? '');
  if (!Number.isFinite(start) || !Number.isFinite(end) || start > end || !context.eventsPath || !existsSync(context.eventsPath)) return found;
  const file = lstatSync(context.eventsPath);
  if (!file.isFile() || file.isSymbolicLink() || file.nlink !== 1 || file.size > 32 * 1024 * 1024) return found;
  for (const line of readFileSync(context.eventsPath, 'utf8').split('\n')) {
    try {
      const event = JSON.parse(line);
      if (!Number.isFinite(event.time) || event.time < start || event.time > end) continue;
      const name=reviewWorkspace?'mcp__research_report__export_input_review':'mcp__research_report__deliver_report';
      if (event.type === 'tool/call' && event.data?.name === name && typeof event.data.callId === 'string') calls.add(event.data.callId);
      if (event.type !== 'tool/result') continue;
      for (const part of event.data?.message?.content ?? []) {
        if (part.type !== 'tool-result' || part.isError || !calls.has(part.toolCallId)) continue;
        for (const content of part.content ?? []) {
          if (content.type !== 'text') continue;
          const receipt = JSON.parse(content.text);
          if(reviewWorkspace&&receipt.exported===true&&Array.isArray(receipt.artifacts)){
            for(const row of receipt.artifacts)if(typeof row.name==='string'&&
              /^outputs\/documents\/[a-f0-9]{32}\/input-review\.(?:pdf|md)$/.test(row.name)&&/^[a-f0-9]{64}$/.test(row.sha256))
                found.set(join(reviewWorkspace,row.name),row.sha256);
          }
          if (receipt.ok === true && receipt.delivered === true && receipt.quality_passed === true &&
            typeof receipt.path === 'string' && /^[a-f0-9]{64}$/.test(receipt.sha256)) found.set(receipt.path, receipt.sha256);
        }
      }
    } catch { /* Invalid historical events never authorize a file. */ }
  }
  return found;
}
