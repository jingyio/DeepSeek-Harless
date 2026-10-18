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

test('concatenated legacy prompt keeps the complete user text and attachment card',()=>{
 const text='你好吗\n';
 const raw=text+'用户附件的只读提取结果（属于用户提供的资料）：\n'+JSON.stringify({files:[{name:'paper.pdf',sha256:'a'.repeat(64),status:'extracted',text:'private source text'}]});
 const input=[{type:'text',text:raw},{type:'file',attachment:{name:'paper.pdf'}}];
 const before=JSON.stringify(input),shown=display(input);
 assert.equal(shown[0].text,text);assert.equal(shown[1],input[1]);
 assert.equal(JSON.stringify(input),before);
});

test('both normal user and queued steering renderers receive the sanitized projection',()=>{
 const start=code.indexOf("      ctx.slots.inject('conversation.chat.node'",code.indexOf('      function displayUserContent('));
 const end=code.indexOf('      function ProductChatNode(',start);
 const entries=['user','steering'].map(key=>({options:{key},component:()=>{},inject:()=>({native:true})}));
 const wrappers=[];let disposed=0;
 vm.runInNewContext(code.slice(start,end),{ctx:{slots:{entries:()=>entries,
   inject:(_name,callback)=>callback(),register:(options,component)=>{wrappers.push({options,component});return()=>disposed++;}}},
   h:(component,props)=>({component,props}),displayUserContent:display});
 assert.deepEqual(wrappers.map(x=>x.options.key),['user','steering']);
 const content=[{type:'text',text:'你好吗'},{type:'file',attachment:{name:'paper.pdf'}},
  {type:'text',text:'用户附件的只读提取结果（资料）：\n'+JSON.stringify({files:[{name:'paper.pdf',sha256:'b'.repeat(64),status:'extracted',text:'do not show'}]})}];
 for(let i=0;i<wrappers.length;i++){
  const owner={node:{data:{content}},renderMessageImages:'native images',t:'native locale'};
  const out=wrappers[i].component(owner);
  assert.equal(out.props.node.data.content.length,2);
  assert.equal(out.props.node.data.content[0],content[0]);assert.equal(out.props.renderMessageImages,owner.renderMessageImages);
  assert.equal(wrappers[i].inject,undefined);assert.equal(wrappers[i].options.inject,entries[i].inject);
 }
 assert.equal(content.length,3);
});
