import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createConversationTitles, summarizeConversation } from '../src/adapters/geneloop_conversation_titles.ts';

test('short topics ignore slash prefixes, greetings and server paths', () => {
  assert.deepEqual(summarizeConversation(['你好', '/chat 请帮我阅读这篇文献，总结主要结论。']), { title: '文献阅读', provisional: false });
  assert.equal(summarizeConversation(['/data 请分析实验数据并生成报告']).title, '数据分析报告');
  assert.equal(summarizeConversation(['/ppt 请制作介绍研究成果的PPT']).title, '演示文稿制作');
  assert.equal(summarizeConversation(['你好']).provisional, true);
  assert.equal(summarizeConversation(['你好，请介绍本项目的安装方式']).title, '介绍本项目的安装方式');
  assert.doesNotMatch(summarizeConversation(['阅读 /home/private/secret.pdf 文件']).title, /\/home|secret/);
  assert.ok([...summarizeConversation(['介绍这项非常复杂的多模态材料数据分析研究的所有细节']).title].length <= 16);
});

test('titles serialize duplicates per workspace, recover after restart, and preserve manual or branch names', async () => {
  const output = mkdtempSync(join(tmpdir(), 'geneloop-titles-'));
  const sessions = new Map(['a','b','c','d'].map(id => [id, {meta:{title:'新会话'},events:[]}]));
  const host = {
    inspect: async id => structuredClone(sessions.get(id)),
    siblings: id => id === 'c' ? ['c'] : ['a','b','d'],
    rename: async (id,title) => { const events=sessions.get(id).events; events.push({type:'session/title',data:{title}}); return {title,seq:events.length-1}; },
  };
  const title = id => sessions.get(id).events.at(-1)?.data.title ?? sessions.get(id).meta.title;
  try {
    let service = createConversationTitles(output,'account',host);
    await Promise.all(['a','b','c'].map(id => service.refresh(id,'请阅读这篇文献')));
    assert.equal(title('a'),'文献阅读'); assert.equal(title('b'),'文献阅读（2）'); assert.equal(title('c'),'文献阅读');
    await service.refresh('d','你好'); assert.equal(title('d'),'日常交流');
    service = createConversationTitles(output,'account',host);
    await service.refresh('d','请分析这份数据'); assert.equal(title('d'),'数据分析报告');
    assert.deepEqual(await service.rename('d','新会话'),{title:'新会话',seq:2});
    await service.refresh('d','请帮我制作PPT'); assert.equal(title('d'),'新会话');
    sessions.get('c').meta.isSeeded = true;
    await service.refresh('c','不同的话题'); assert.equal(title('c'),'文献阅读');
    sessions.set('old',{meta:{title:'我的课题'},events:[]});
    await service.refresh('old','请制作PPT'); assert.equal(title('old'),'我的课题');
  } finally { rmSync(output,{recursive:true,force:true}); }
});

test('old default names are repaired from genuine user history; concurrent manual name wins', async () => {
  const output = mkdtempSync(join(tmpdir(), 'geneloop-titles-'));
  const snapshot = {meta:{title:'新会话'},events:[{type:'user/message',data:{source:{kind:'user'},content:[{type:'text',text:'/paper 请校对这篇论文'}]}}]};
  const host = { inspect: async () => structuredClone(snapshot), siblings: () => [], rename:async (_id,title) => {snapshot.meta.title=title;} };
  try {
    const service=createConversationTitles(output,'account',host);
    await Promise.all([service.refresh('a'),service.rename('a','我的手工标题')]);
    assert.equal(snapshot.meta.title,'我的手工标题');
    await service.refresh('a','请分析数据'); assert.equal(snapshot.meta.title,'我的手工标题');
  } finally { rmSync(output,{recursive:true,force:true}); }
});
