import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';

test('account and chat presentation ship the same canonical visual layer',()=>{
  assert.doesNotThrow(()=>execFileSync(process.execPath,['scripts/sync-geneloop-theme.mjs','--check'],{cwd:new URL('../',import.meta.url)}));
  const css=readFileSync(new URL('../src/adapters/geneloop_theme.css',import.meta.url),'utf8');
  // These settings remain owned by the native app, including hidden controls
  // and user-selected type sizes. A future style edit must not override them.
  assert.doesNotMatch(css,/--dsh-content-font-size\s*:|\[hidden\][^{]*\{[^}]*display\s*:\s*(?!none)/);
  assert.doesNotMatch(css,/@import\b|https?:\/\//);
});
