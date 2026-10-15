import test from 'node:test';
import assert from 'node:assert/strict';
import {certify, permits, baseProgram, validateProgram} from '../dist/guard.js';
import {validateDeck} from '../dist/render.js';

test('RSI 保留反例，修复后才允许进入下一任务',()=>{
  const failed=certify({...baseProgram,min_text_chars:100});
  assert.equal(failed.accepted,false);
  assert.equal(failed.failures[0].id,'short_pdf');
  const repaired=certify({...failed.program,min_text_chars:20});
  assert.equal(repaired.accepted,true);
  assert.equal(permits(repaired.program,{format:'pdf',page_count:5,text_chars:0}),false);
  assert.equal(permits(repaired.program,{format:'pdf',page_count:5,text_chars:1200}),true);
});
test('候选不能添加任意代码或放宽固定外层边界',()=>{
  for(const p of [{...baseProgram,code:'process.exit()'},{...baseProgram,min_text_chars:0},
    {...baseProgram,max_pages:201},{...baseProgram,formats:['exe']}]) assert.throws(()=>validateProgram(p));
  for(const facts of [{format:'pdf',page_count:NaN,text_chars:99},{format:'pdf',page_count:1.5,text_chars:99},
    {format:'pptx',page_count:1,text_chars:-1}]) assert.equal(permits(baseProgram,facts),false);
});
test('版面预检拒绝溢出和任意网络图片',()=>{
  const deck={title:'test',slides:[{title:'Evidence',bullets:['a'.repeat(151)],sources:['source']} ]};
  assert.throws(()=>validateDeck(deck));
  deck.slides[0].bullets=['短句'];
  deck.slides[0].image={data:'https://example.com/image.png',width:10,height:10};
  assert.throws(()=>validateDeck(deck));
});
