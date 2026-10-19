/** Check distributed, byte-preserved file-management Motifs; no model or private files. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {digest, validateOnlineManifest} from '../src/motif_core/online_skill_runtime.mjs';
import {validateCollectionPolicy} from '../src/motif_core/collection_read_policy.ts';
import {validateReentryPolicy} from '../src/motif_core/collection_reentry_policy.ts';
import {validatePlanPolicy} from '../src/motif_core/authorized_plan_policy.ts';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const args = process.argv.slice(2);
let bundle = path.join(root, 'examples/motif-library/file-management-v1');
let requiredGroup;
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--bundle' && args[i + 1]) bundle = path.resolve(args[++i]);
  else if (args[i] === '--require-group' && args[i + 1]) requiredGroup = args[++i];
  else throw new Error('usage: node scripts/check-file-management-library.mjs [--bundle DIR] [--require-group workflow14|recovery15]');
}
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const json = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const unsigned = (v, k) => Object.fromEntries(Object.entries(v).filter(([key]) => key !== k));
const hex = v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
function need(value, reason) { if (!value) throw new Error(reason); }
function scoped(base, name) {
  need(typeof name === 'string' && name.length && !name.includes('\\') && !path.isAbsolute(name)
    && name.split('/').every(p => p && p !== '.' && p !== '..'), 'invalid relative path');
  const target = path.resolve(base, name);
  need(target.startsWith(path.resolve(base) + path.sep), 'path escaped package');
  let current = base;
  for (const part of name.split('/')) {
    current = path.join(current, part);
    need(!fs.existsSync(current) || !fs.lstatSync(current).isSymbolicLink(), 'symlink in package');
  }
  return target;
}
function privacy(v) {
  if (Array.isArray(v)) return v.forEach(privacy);
  if (v && typeof v === 'object') {
    for (const [k, x] of Object.entries(v)) {
      need(!/^(api_?key|authorization|password|access_token|secret)$/i.test(k), 'private credential field');
      privacy(x);
    }
  } else if (typeof v === 'string') {
    need(!['/Users/', '/home/', 'Bearer ', 'file://', 'DEEPSEEK_API_KEY'].some(p => v.includes(p))
      && !/\bsk-[A-Za-z0-9_-]{16,}/.test(v),
      'private path or credential string');
    need(v.length <= 500, 'unreviewed long source string');
  }
}
function signatures(v) {
  if (Array.isArray(v)) return v.forEach(signatures);
  if (!v || typeof v !== 'object') return;
  for (const k of ['library_digest', 'policy_digest', 'manifest_digest']) {
    if (Object.hasOwn(v, k)) need(hex(v[k]) && v[k] === digest(unsigned(v, k)), 'changed ' + k);
  }
  // Online manifests contain a projection of the artifact and its original signature.
  // Only full certified artifacts have status + witnesses and can be rehashed here.
  if (Object.hasOwn(v, 'certified_digest') && Object.hasOwn(v, 'status')) {
    need(v.certified_digest === digest(unsigned(v, 'certified_digest')), 'changed certified artifact');
    const training = v.source_task_fingerprints;
    need(Array.isArray(training) && training.length >= 2 && new Set(training).size === training.length
      && !training.includes(v.validation_task_fingerprint) && hex(v.validation_task_fingerprint),
      'training/certification decision overlap');
    need(['trace_validated_read_only', 'trace_validated_effectful'].includes(v.status), 'uncertified candidate');
    if (v.source_trace_ids && v.validation_trace_id) {
      need(!v.source_trace_ids.includes(v.validation_trace_id), 'training/certification trace overlap');
    }
  }
  Object.values(v).forEach(signatures);
}
const catalog = json(path.join(bundle, 'catalog.json'));
privacy(catalog);
need(catalog.schema_version === 1 && catalog.format === 'sss-public-file-management-library-v1'
  && catalog.default_activation === false && catalog.artifact_bytes.startsWith('exact original'), 'unsupported publication');
const lock = json(path.join(bundle, 'files.lock.json'));
need(lock.schema_version === 1 && lock.sha256 && typeof lock.sha256 === 'object', 'invalid file lock');
function inventory(dir, prefix = '') {
  return fs.readdirSync(dir, {withFileTypes: true}).flatMap(entry => {
    need(!entry.isSymbolicLink(), 'symlink in package');
    const name = prefix + entry.name;
    return entry.isDirectory() ? inventory(path.join(dir, entry.name), name + '/') : [name];
  });
}
need(digest(inventory(bundle).filter(n => n !== 'files.lock.json').sort()) === digest(Object.keys(lock.sha256).sort()),
  'unlocked or missing package files');
for (const [name, expected] of Object.entries(lock.sha256)) {
  need(hex(expected) && sha(fs.readFileSync(scoped(bundle, name))) === expected, 'changed package file: ' + name);
}
const contents = new Map();
const validators = {collection_policy: validateCollectionPolicy, reentry_policy: validateReentryPolicy,
  plan_policy: validatePlanPolicy, online_manifest: validateOnlineManifest};
let libraries = 0;
for (const row of catalog.files) {
  need(!contents.has(row.path) && lock.sha256[row.path] === row.sha256, 'duplicate or unlocked artifact');
  const bytes = fs.readFileSync(scoped(bundle, row.path));
  need(sha(bytes) === row.sha256, 'original artifact bytes changed');
  const value = JSON.parse(bytes);
  privacy(value);
  if (row.kind === 'read_library') {
    need(value.schema_version === 1 && value.status === 'certified_read_library'
      && Array.isArray(value.artifacts) && value.artifacts.length > 0, 'invalid read library');
    signatures(value);
    need(!value.training_trace_ids.some(id => value.heldout_trace_ids.includes(id)), 'library role overlap');
    libraries++;
  } else if (validators[row.kind]) {
    // Manifest certified_digest is an original reference, not a signature of its projection.
    if (row.kind !== 'online_manifest') signatures(value);
    validators[row.kind](value);
    if (row.kind !== 'online_manifest') libraries++;
  } else need(['certification_summary', 'source_lock', 'candidate_lock'].includes(row.kind), 'unknown artifact kind');
  contents.set(row.path, value);
}
for (const row of catalog.files.filter(r => r.kind === 'online_manifest')) {
  const manifest = contents.get(row.path), library = contents.get(row.paired_library);
  need(library && manifest.source_library_digest === library.library_digest, 'manifest/library mismatch');
  for (const a of manifest.artifacts) need(library.artifacts.some(b =>
    a.motif_id === b.motif_id && a.certified_digest === b.certified_digest), 'manifest promoted a different artifact');
}
const compat=json(path.join(root,'config/file-management-runtime-compatibility.json'));
const compatible=compat.original_catalog_sha256===sha(fs.readFileSync(path.join(bundle,'catalog.json'))) && compat.new_certification===false;
for (const [name, original] of Object.entries(catalog.runtime_validators)) {
  const expected=compatible?compat.runtime_validators[name]:original;
  need(sha(fs.readFileSync(scoped(root, name))) === expected, 'runtime validator changed: ' + name);
}
const sourceLock = contents.get('workflow-v1/library-lock.json');
for (const row of sourceLock.artifacts) need(lock.sha256['workflow-v1/' + row.path] === row.sha256,
  'original independent certification lock differs');
const compatibility = {};
for (const [group, settings] of Object.entries(catalog.runtime_groups)) {
  const original = sourceLock.groups[group];
  need(original && settings.execution_version_sha256 === original.execution_version_sha256
    && digest(Object.fromEntries(settings.dependencies.map(r => [r.path, r.sha256]))) === digest(original.dependencies),
    'certified source group changed');
  const incompatible = settings.dependencies.filter(r => {
    const p = scoped(root, r.path);
    return !fs.existsSync(p) || sha(fs.readFileSync(p)) !== r.sha256;
  }).map(r => r.path);
  compatibility[group] = {matching_source: incompatible.length === 0, incompatible};
}
if (requiredGroup) need(Object.hasOwn(compatibility, requiredGroup) && compatibility[requiredGroup].matching_source,
  'requested runtime group does not match certified sources: ' + requiredGroup);
console.log(JSON.stringify({passed: true, library_policy_files: libraries, exact_payload_files: catalog.files.length,
  current_runtime_compatibility: compatibility, automatic_activation: false, cloud_requests: 0}, null, 2));
