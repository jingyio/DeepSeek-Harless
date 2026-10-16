/** Reference-report acceptance must not impose a bibliography on general proofreading. */
import {createHash} from 'node:crypto';
import {existsSync, lstatSync, readFileSync, readdirSync} from 'node:fs';
import {join} from 'node:path';
const sha = (data: Uint8Array) => createHash('sha256').update(data).digest('hex');
const regular = (path: string) => { const s = lstatSync(path); return s.isFile() && !s.isSymbolicLink() && s.nlink === 1; };

export function paperReferenceReportRequired(task: any): boolean {
  if (task.scene.id !== 'paper-proofreading' || !task.scene_options.allow_output || task.source_pending) return false;
  try {
    const grant = JSON.parse(readFileSync(join(task.workspace, 'paper-output-grant.json'), 'utf8'));
    return grant.task_id !== task.request.task_id || grant.allow_output !== true || Boolean(grant.audit_sha256) ||
      existsSync(join(task.workspace, 'outputs', 'paper-audits', task.request.task_id, 'draft.json'));
  } catch { return true; } // An absent approval cannot authorize report recovery.
}

export function paperPdfDelivered(task: any): boolean {
  if (!paperReferenceReportRequired(task)) return true;
  const outputs = join(task.workspace, 'outputs'), id = task.request.task_id;
  try {
    const grant = JSON.parse(readFileSync(join(task.workspace, 'paper-output-grant.json'), 'utf8'));
    // Only an admitted reference report or a reference draft started in THIS
    // task requires this acceptance check. Main's generic exporter stays valid.
    if (grant.task_id !== id || grant.allow_output !== true) return false;
    const approved = JSON.parse(readFileSync(join(task.workspace, 'approved-inputs.json'), 'utf8')).files;
    const documents = join(outputs, 'documents');
    if (existsSync(documents) && !lstatSync(documents).isSymbolicLink() && readdirSync(documents).some(name => {
      try {
        const dir = join(documents, name);
        if (!lstatSync(dir).isDirectory() || lstatSync(dir).isSymbolicLink()) return false;
        const receipt = JSON.parse(readFileSync(join(dir, 'delivery.json'), 'utf8'));
        const sources = receipt.source_versions;
        return receipt.task_id === id && receipt.kind === 'source_bound_review' && receipt.category === 'paper-review' &&
          receipt.layout_passed === true && sources &&
          Object.keys(sources).length === Object.keys(approved).length &&
          Object.keys(approved).every(key => sources[key] === approved[key]) &&
          ['paper-review.pdf', 'paper-review.md'].every(file => {
            const path = join(dir, file), row = receipt.files?.find((r: any) => r.name === `outputs/documents/${name}/${file}`);
            return row && regular(path) && sha(readFileSync(path)) === row.sha256;
          });
      } catch { return false; }
    })) return true;
    return readdirSync(outputs).some(name => {
      if (!name.startsWith(id + '-')) return false;
      try {
        const dir = join(outputs, name), pdf = join(dir, 'reference-check-report.pdf');
        if (!lstatSync(dir).isDirectory() || lstatSync(dir).isSymbolicLink()) return false;
        const receipt = JSON.parse(readFileSync(join(dir, 'export-receipt.json'), 'utf8'));
        return regular(pdf) && receipt.artifact_file === `outputs/${name}/reference-check-report.pdf` &&
          receipt.content_coverage?.all_fields_present === true && receipt.output_sha256 === sha(readFileSync(pdf));
      } catch { return false; }
    });
  } catch { return false; }
}
