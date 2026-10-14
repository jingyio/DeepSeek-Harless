/** Commit the generated bridge so existing Node 20 runtimes need no TS loader. */
import { stripTypeScriptTypes } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
for (const name of ['approved_plan_continuation', 'source_dereference']) {
  const source = new URL(`../src/motif_core/${name}.ts`, import.meta.url);
  const output = new URL(`../src/motif_core/${name}.generated.mjs`, import.meta.url);
  const generated = `// Generated from ${name}.ts; do not edit.\n` +
    stripTypeScriptTypes(readFileSync(source, 'utf8'), { mode: 'strip' }).replace(/[\t ]+$/gm, '');
  if (process.argv.includes('--check')) {
    if (readFileSync(output, 'utf8') !== generated) throw new Error(`${name} TypeScript bridge is stale`);
  } else writeFileSync(output, generated);
}
