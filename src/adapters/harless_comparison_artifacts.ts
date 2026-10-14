/** Immutable, account-local result copies. Never expose inputs, logs, or runtime credentials. */
import { createHash } from 'node:crypto';
import { existsSync, lstatSync, realpathSync, readdirSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve, relative, sep } from 'node:path';
const sha = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
const within = (root: string, path: string) => { const rel = relative(realpathSync(root), realpathSync(path)); return rel && !rel.startsWith('..' + sep) && rel !== '..' && !rel.startsWith(sep); };
const valid = (id: string) => /^[a-zA-Z0-9-]{1,100}$/.test(id);
export function comparisonArtifacts(output: string) {
  const root = join(output, 'comparison-artifacts'); mkdirSync(root, { recursive: true, mode: 0o700 });
  return {
    snapshot(turn: string, lane: string, attempt: number, workspace: string, approvedFiles?:Set<string>) {
      if (!valid(turn) || !['baseline', 'motif'].includes(lane) || !Number.isInteger(attempt) || attempt < 0) throw Error('artifact_identity_invalid');
      const destination = join(root, turn, lane, String(attempt));
      const index = join(destination, 'index.json');
      if (existsSync(index)) return JSON.parse(readFileSync(index, 'utf8'));
      mkdirSync(destination, { recursive: true, mode: 0o700 });
      const rows: any[] = []; let total = 0;
      const copy = (path: string, name: string) => {
        if(approvedFiles&&!approvedFiles.has(path))return;
        const st = lstatSync(path);
        if (!st.isFile() || st.isSymbolicLink() || st.nlink !== 1 || !within(workspace, path) ||
            rows.length >= 32 || st.size > 30 * 1024 * 1024 || total + st.size > 80 * 1024 * 1024) return;
        const bytes = readFileSync(path), digest = sha(bytes), id = digest.slice(0, 32) + '-' + rows.length;
        writeFileSync(join(destination, id), bytes, { mode: 0o600, flag: 'wx' });
        rows.push({ id, name, bytes: bytes.length, sha256: digest, attempt }); total += bytes.length;
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
          if (!/\.(?:pdf|pptx|png|jpg|svg|csv|tsv|html|md|tex|bib|txt)$/i.test(name)) continue;
          copy(path, prefix + name);
        }
      };
      // Scene adapters place only derived deliverables here. Literature task/cache/journal are excluded.
      for (const directory of ['outputs', 'output', 'validation', 'literature/outputs', 'literature/deliverables', 'file-results']) scan(join(workspace, directory), directory + '/', 0);
      if (existsSync(join(workspace, 'literature/delivery-receipt.json'))) for (const name of ['research-notes.md', 'evidence.json']) {
        const path = join(workspace, 'literature', name); if (existsSync(path)) copy(path, 'literature/' + name);
      }
      writeFileSync(index, JSON.stringify(rows), { mode: 0o600, flag: 'wx' }); return rows;
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
export function verifiedReportFiles(workspace:string){
  const allowed=new Set<string>(),directory=join(workspace,'outputs/report/records');
  if(!existsSync(directory))return allowed;
  for(const name of readdirSync(directory).slice(0,2048)){
    if(!name.endsWith('.json'))continue;
    const path=join(directory,name),st=lstatSync(path);
    if(!st.isFile()||st.isSymbolicLink()||st.nlink!==1||st.size>1000000)continue;
    try{
      const record=JSON.parse(readFileSync(path,'utf8')),row=record.payload;
      if(record.kind!=='delivery'||row?.delivered!==true||row.quality_passed!==true||typeof row.path!=='string'||
        !existsSync(row.path)||!within(workspace,row.path))continue;
      const file=lstatSync(row.path);
      if(file.isFile()&&!file.isSymbolicLink()&&file.nlink===1&&sha(readFileSync(row.path))===row.sha256)allowed.add(row.path);
    }catch{/* Malformed or changed evidence is not a delivery grant. */}
  }
  return allowed;
}
