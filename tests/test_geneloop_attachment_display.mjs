import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {publicSessionEvent} from '../src/adapters/harless_public_output.ts';
const code=readFileSync(new URL('../src/adapters/harless_web_client/client.js',import.meta.url),'utf8');
const start=code.indexOf('      function displayUserContent('),end=code.indexOf("      ctx.slots.inject('conversation.chat.node'",start);
const display=vm.runInNewContext(code.slice(start,end)+'; displayUserContent');
test('server-verified legacy extraction is hidden while the UI preserves admitted text, cards and raw history',()=>{
 const prompt={type:'text',text:'请总结'},file={type:'file',attachment:{name:'paper.pdf'}};
 const evidence={type:'text',text:'用户附件的只读提取结果（属于用户提供的资料）：\n'+JSON.stringify({files:[{name:'paper.pdf',sha256:'a'.repeat(64),status:'extracted',text:'private source text'}]})};
 const original=[prompt,file,evidence],before=JSON.stringify(original);
 const event={type:'user/message',data:{source:{kind:'user',rpcId:'persisted-request'},content:original}};
 const admitted=[prompt,{type:'file',receiptId:'owned-receipt'}];
 const projected=publicSessionEvent(event,admitted),visible=display(projected.data.content);
 assert.equal(visible.length,2);assert.equal(visible[0],prompt);assert.equal(visible[1],file);
 assert.equal(visible,projected.data.content,'UI does not reinterpret the server provenance decision');
 assert.equal(JSON.stringify(original),before);
 assert.equal(display(original),original,'an unverified JSON paste with an attachment remains verbatim');
 assert.equal(publicSessionEvent(event),event,'legacy-looking text alone cannot prove generated provenance');
 assert.equal(publicSessionEvent(event,original),event,'a genuinely admitted full JSON paste remains user input');
 assert.equal(display([prompt,evidence]).length,2,'pasted text without attachment cards is not hidden');
 assert.equal(display([file,{...evidence,text:'用户附件的只读提取结果（broken JSON'}]).length,2);
});

test('a verified concatenated legacy prompt keeps complete multiline user text and its attachment card',()=>{
 const text='你好吗\n请保留完整的第二行';
 const raw=text+'\n用户附件的只读提取结果（属于用户提供的资料）：\n'+JSON.stringify({files:[{name:'paper.pdf',sha256:'a'.repeat(64),status:'extracted',text:'private source text'}]});
 const input=[{type:'text',text:raw},{type:'file',attachment:{name:'paper.pdf'}}];
 const event={type:'user/message',data:{source:{kind:'user',rpcId:'persisted-multiline'},content:input}};
 const before=JSON.stringify(input),shown=display(publicSessionEvent(event,[{type:'text',text},{type:'file',receiptId:'owned'}]).data.content);
 assert.equal(shown[0].text,text);assert.equal(shown[1],input[1]);
 assert.equal(display(input),input,'without verified server projection the complete raw text must survive');
 assert.equal(JSON.stringify(input),before);
});

test('normal user and queued steering renderers pass through the authoritative projection and suppress internal producers',()=>{
 const start=code.indexOf("      ctx.slots.inject('conversation.chat.node'",code.indexOf('      function displayUserContent('));
 const end=code.indexOf('      function ProductChatNode(',start);
 const entries=['user','steering'].map(key=>({options:{key},component:()=>{},inject:()=>({native:true})}));
 const wrappers=[];let disposed=0;
 const internalStart=code.indexOf('      const internalAttachmentContext =');
 const internalEnd=code.indexOf('\n',internalStart);
 const internalAttachmentContext=vm.runInNewContext(code.slice(internalStart,internalEnd)+'; internalAttachmentContext');
 vm.runInNewContext(code.slice(start,end),{ctx:{slots:{entries:()=>entries,
   inject:(_name,callback)=>callback(),register:(options,component)=>{wrappers.push({options,component});return()=>disposed++;}}},
   h:(component,props)=>({component,props}),displayUserContent:display,internalAttachmentContext});
 assert.deepEqual(wrappers.map(x=>x.options.key),['user','steering']);
 const content=[{type:'text',text:'你好吗'},{type:'file',attachment:{name:'paper.pdf'}},
  {type:'text',text:'用户附件的只读提取结果（资料）：\n'+JSON.stringify({files:[{name:'paper.pdf',sha256:'b'.repeat(64),status:'extracted',text:'do not show'}]})}];
 const event={type:'user/message',data:{source:{kind:'user',rpcId:'owned'},content}};
 const projected=publicSessionEvent(event,[content[0],{type:'file',receiptId:'owned-file'}]).data.content;
 for(let i=0;i<wrappers.length;i++){
  const owner={node:{source:{kind:'user'},data:{content:projected}},renderMessageImages:'native images',t:'native locale'};
  const out=wrappers[i].component(owner);
  assert.equal(out.props.node.data.content.length,2);
  assert.equal(out.props.node.data.content,projected);
  assert.equal(out.props.node.data.content[0],content[0]);assert.equal(out.props.renderMessageImages,owner.renderMessageImages);
  assert.equal(wrappers[i].inject,undefined);assert.equal(wrappers[i].options.inject,entries[i].inject);
  const raw=wrappers[i].component({...owner,node:{...owner.node,data:{content}}});
  assert.equal(raw.props.node.data.content,content,'valid pasted JSON is not deleted by either native wrapper');
  assert.equal(wrappers[i].component({...owner,node:{source:{kind:'plugin',plugin:'geneloop-attachment-context'},data:{content:[]}}}),null);
 }
 assert.equal(content.length,3);
});
