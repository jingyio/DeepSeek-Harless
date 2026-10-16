// The brand head script is the existing public presentation entry point.
// Embed the canonical CSS at development time so no runtime/task code changes
// or extra asset requests are needed. --check is used by the regression suite.
import {readFileSync,writeFileSync} from 'node:fs';
const source=new URL('../src/adapters/geneloop_theme.css',import.meta.url);
const target=new URL('../src/adapters/geneloop_brand.js',import.meta.url);
const start='  // BEGIN GENERATED GENELOOP THEME',end='  // END GENERATED GENELOOP THEME';
const css=readFileSync(source,'utf8').replaceAll('\r\n','\n');
const embedded=[start,'  const visualTheme = document.createElement(\'style\');',
  '  visualTheme.id = \'geneloop-visual-theme\';',
  '  visualTheme.textContent = '+JSON.stringify(css).replaceAll('<','\\u003c')+';',
  '  document.head.append(visualTheme);',end].join('\n');
const current=readFileSync(target,'utf8').replaceAll('\r\n','\n');
const first=current.indexOf(start),last=current.indexOf(end);
if(first<0||last<first)throw new Error('GeneLoop theme markers are missing');
const next=current.slice(0,first)+embedded+current.slice(last+end.length);
if(process.argv.includes('--check')){
  if(current!==next)throw new Error('Run node scripts/sync-geneloop-theme.mjs after changing geneloop_theme.css');
}else if(current!==next)writeFileSync(target,next);
