/** Deterministic parsing/transfer diagnostics; browser rendering is separate. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {webcrypto,createHash} from 'node:crypto';
const source=readFileSync(new URL('../src/adapters/harless_web_client/client.js',import.meta.url),'utf8');
function helpers(fetcher){
 const context={Blob,DataView,TextDecoder,Uint8Array,DecompressionStream,AbortController,URL,
  window:{crypto:webcrypto},fetch:fetcher,artifactName:file=>file.name.split(/[\\/]/).pop(),
  apiError:(status,message)=>Error(message||String(status)),comparisonUrl:()=>'/authenticated-file'};
 const first=source.indexOf('const previewAddress ='),last=source.indexOf('function openArtifact(',first);
 return runInNewContext(source.slice(first,last)+'\n({previewAddress,parsePreview,previewType,previewTable,officePreview,readArtifact})',context);
}
test('delivery addresses distinguish account sessions, comparison lanes and file versions without exposing workspace paths',()=>{
 const h=helpers(); const address=h.previewAddress({session_id:'session-a',id:'comparison-a'},'motif',{id:'abc-1',name:'outputs/report/中文 报告.pdf'});
 assert.match(address,/\/motif\/abc-1\//);assert.doesNotMatch(address,/outputs|report/);
 const parsed=h.parsePreview(address); assert.equal(parsed.file.name,'中文 报告.pdf'); assert.equal(parsed.lane,'motif');
 for(const address of ['https://host/file','dsh-resource://geneloop-delivery/a/b/baseline/id/%2Fetc%2Fpasswd','dsh-resource://geneloop-delivery/a/b/other/id/file','dsh-resource://geneloop-delivery/a/b/baseline/id/x%00.txt'])assert.throws(()=>h.parsePreview(address));
});
test('CSV preview preserves quoted commas, escaped quotes, CRLF and multiline cells; malformed quotation is actionable',()=>{
 const h=helpers();assert.equal(JSON.stringify(h.previewTable('id,note\r\na,"first, second\nline and ""quotes"""\r\n')),JSON.stringify([['id','note'],['a','first, second\nline and "quotes"']]));
 assert.equal(JSON.stringify(h.previewTable('a\tb\n1\t2','\t')),JSON.stringify([['a','b'],['1','2']]));
 assert.throws(()=>h.previewTable('a,"unclosed'),/引号未闭合/);
 assert.equal(h.previewType('result.PDF'),'pdf');assert.equal(h.previewType('README.md'),'markdown');assert.equal(h.previewType('notes.docx'),'office');
 assert.equal(h.previewType('script.html'),'text','HTML is source text, not executable app DOM');assert.equal(h.previewType('unknown.exe'),'unsupported');
});
test('preview and download share authentication, body-size and SHA checks; gateway HTML and stale bytes cannot be shown as a PDF',async()=>{
 const bytes=Buffer.from('%PDF test'),file={name:'report.pdf',bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};let options;
 let h=helpers(async(url,init)=>{options=init;assert.equal(url,'/authenticated-file');return new Response(bytes,{headers:{'Content-Type':'application/octet-stream'}})});
 const signal=new AbortController().signal;assert.equal((await h.readArtifact({},'baseline',file,signal)).size,bytes.length);
 assert.equal(options.credentials,'same-origin');assert.equal(options.cache,'no-store');assert.equal(options.signal,signal);
 h=helpers(async()=>new Response('<html>login</html>',{headers:{'Content-Type':'text/html'}}));await assert.rejects(h.readArtifact({},'baseline',file,signal),/未收到交付文件/);
 h=helpers(async()=>new Response(bytes));await assert.rejects(h.readArtifact({},'baseline',{...file,bytes:999},signal),/大小校验/);
 await assert.rejects(h.readArtifact({},'baseline',{...file,sha256:'0'.repeat(64)},signal),/内容校验/);
 h=helpers(async()=>new Response('denied',{status:403}));await assert.rejects(h.readArtifact({},'baseline',file,signal),/403/);
});
test('Office preview refuses malformed archives, excessive expansion and encryption before XML parsing',async()=>{
 const h=helpers(),signal=new AbortController().signal;
 await assert.rejects(h.officePreview(new Blob(['short']),'a.docx',signal),/不完整/);
 await assert.rejects(h.officePreview(new Blob([Buffer.alloc(30)]),'a.docx',signal),/无法读取/);
 function archive({flags=0,length=1}={}){
  const name=Buffer.from('word/document.xml'),central=Buffer.alloc(46);central.writeUInt32LE(0x02014b50);central.writeUInt16LE(flags,8);central.writeUInt32LE(length,24);central.writeUInt16LE(name.length,28);
  const end=Buffer.alloc(22);end.writeUInt32LE(0x06054b50);end.writeUInt16LE(1,10);end.writeUInt32LE(1,16);return new Blob([Buffer.alloc(1),central,name,end]);
 }
 await assert.rejects(h.officePreview(archive({flags:1}),'a.docx',signal),/加密|容量/);
 await assert.rejects(h.officePreview(archive({length:9*1024*1024}),'a.docx',signal),/加密|容量/);
});
