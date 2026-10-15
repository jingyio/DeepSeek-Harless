import test from 'node:test';
import assert from 'node:assert/strict';

test('手写场景前缀支持空格与中文，拒绝不完整词、路径及正文中斜杠', {skip:!process.features?.typescript}, async () => {
  const {parseSceneShortcut} = await import('../src/adapters/harless_settings.ts');
  const scenes = ['ppt','paper-proofreading','research-data-analysis','literature'].map(id=>({id}));
  for (const [text,scene,rest] of [
    ['/ppt 做报告','ppt','做报告'], ['/ppt做报告','ppt','做报告'],
    ['/data请分析数据','research-data-analysis','请分析数据'],
    [' /PAPER 修订','paper-proofreading','修订'], ['/literature 检索','literature','检索'],
  ]) assert.deepEqual(parseSceneShortcut(text,scenes), {scene,text:rest});
  for (const text of ['/d','/p','/pptx do','/database','/ppt/file','/ppt.json','请用 /ppt 报告'])
    assert.equal(parseSceneShortcut(text,scenes),undefined,text);
});
