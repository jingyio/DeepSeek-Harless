/** One host composition for fresh launchers, release candidates and members.
 * Pure configuration: no services, filesystem scans or model calls are started.
 */
import {isAbsolute,resolve} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {readFileSync} from 'node:fs';

const switches={'llm-retry':false,'compaction-basic':true,'command-compact':false,goal:true,'goal-round-driver':true};
const providers=[
 {upstreamId:'fs-sandbox',upstreamName:'@deepseek-ai/dsh-fs-sandbox',id:'geneloop-fs',file:'geneloop_fs.ts'},
 {upstreamId:'subprocess',upstreamName:'@deepseek-ai/dsh-subprocess-local',id:'geneloop-fs-search',file:'geneloop_fs_search.ts'},
];
const nativeIds=new Set([...Object.keys(switches),...providers.flatMap(row=>[row.upstreamId,row.id]),'geneloop-native-work']);

export function composeNativeHost(input,sourceDir,{member=false}={}){
 if(!Array.isArray(input)||typeof sourceDir!=='string'||!isAbsolute(sourceDir))throw Error('Invalid native host composition');
 const source=pathToFileURL(resolve(sourceDir)).href.replace(/\/?$/,'/'),sandbox='file:///app/src/';
 const patch=[];
 const clean=row=>{
  if(!row||typeof row!=='object'||Array.isArray(row))throw Error('Invalid host patch row');
  if(nativeIds.has(row.id))return null;
  const result=structuredClone(row);
  if(result.insert!==undefined){
   if(!Array.isArray(result.insert))throw Error('Invalid host patch insert');
   result.insert=result.insert.map(clean).filter(Boolean);
   if(!result.insert.length&&Object.keys(result).length===1)return null;
  }
  return result;
 };
 for(const row of input){const kept=clean(row);if(kept)patch.push(kept);}
 // Include patches treat `name` as an identity guard, not a replacement.
 // Disable each shipped provider and insert our implementation under its own
 // entry id, so the actual loader activates exactly one service per seam.
 patch.push(...Object.entries(switches).map(([id,disabled])=>({id,disabled})),
  ...providers.map(({upstreamId:id,upstreamName:name})=>({id,name,disabled:true})),
  {insert:[...providers.map(({id,file})=>({id,name:source+'adapters/'+file})),
   {id:'geneloop-native-work',name:source+'adapters/geneloop_native_work.ts'}]});
 const map=row=>{
  if(typeof row.name==='string'&&row.name.startsWith('file:')){
   const uri=new URL(row.name);
   if(uri.href!==row.name||uri.search||uri.hash||/%2f|%5c/i.test(row.name))throw Error('Invalid plugin source URI');
   if(!row.name.startsWith(source)&&!(member&&row.name.startsWith(sandbox)))throw Error('Plugin is outside source directory');
   if(member&&row.name.startsWith(source))row.name=sandbox+row.name.slice(source.length);
  }
  if(row.insert)row.insert.forEach(map);
 };
 patch.forEach(map);return patch;
}

// The Python launcher feeds its in-memory JSON patch through stdin and captures
// stdout. No private configuration is passed in command-line arguments.
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{
  const args=process.argv.slice(2);
  if(args[0]!=='--source-dir'||!args[1]||args.length>3||args[2]!==undefined&&args[2]!=='--member')throw Error('Expected --source-dir ABSOLUTE_SRC [--member]');
  process.stdout.write(JSON.stringify(composeNativeHost(JSON.parse(readFileSync(0,'utf8')),args[1],{member:args[2]==='--member'}))+'\n');
 }catch(error){process.stderr.write((error instanceof SyntaxError?'Invalid host patch JSON':error.message)+'\n');process.exitCode=1;}
}
