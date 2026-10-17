import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const code=readFileSync(new URL('../src/adapters/harless_web_client/client.js',import.meta.url),'utf8');
const start=code.indexOf('      function displayUserContent('),end=code.indexOf("      ctx.slots.inject('conversation.chat.node'",start);
const display=vm.runInNewContext(code.slice(start,end)+'; displayUserContent');
test('legacy extracted evidence is hidden beside a file card while user text, cards and raw history remain intact',()=>{
 const prompt={type:'text',text:'请总结'},file={type:'file',attachment:{name:'paper.pdf'}};
 const evidence={type:'text',text:'用户附件的只读提取结果（属于用户提供的资料）：\n'+JSON.stringify({files:[{name:'paper.pdf',sha256:'a'.repeat(64),status:'extracted',text:'private source text'}]})};
 const original=[prompt,file,evidence],before=JSON.stringify(original),visible=display(original);
 assert.equal(visible.length,2);assert.equal(visible[0],prompt);assert.equal(visible[1],file);
 assert.equal(JSON.stringify(original),before);
 assert.equal(display([prompt,evidence]).length,2,'pasted text without attachment cards is not hidden');
 assert.equal(display([file,{...evidence,text:'用户附件的只读提取结果（broken JSON'}]).length,2);
});
