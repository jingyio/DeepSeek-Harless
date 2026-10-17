/** Display-clock diagnostics; no network/model calls. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../src/adapters/harless_web_client/client.js', import.meta.url), 'utf8');
const code = source.slice(source.indexOf('    function useBufferedBlocks'), source.indexOf('    const inject ='));
function fixture(text = '', live = true, reduced = false) {
  let time = 0, cursor = 0, next = 0, identity = 'turn-a', output;
  const hooks = [], slots = [], effects = [], timers = new Map();
  const document = { hidden: false }, window = { matchMedia: () => ({ matches: reduced }) };
  const clearTimeout = id => timers.delete(id);
  const React = {
    useRef(value) { return hooks[cursor++] ||= { current: value }; },
    useState(value) { const i = cursor++; if (!(i in hooks)) hooks[i] = value;
      return [hooks[i], update => { hooks[i] = typeof update === 'function' ? update(hooks[i]) : update; }]; },
    useEffect(fn, deps) { const i = cursor++, previous = slots[i];
      if (!previous || deps.some((value, index) => value !== previous.deps[index])) {
        const slot = { deps, cleanup: previous?.cleanup }; slots[i] = slot;
        effects.push(() => { slot.cleanup?.(); slot.cleanup = fn(); });
      }
    },
    createElement: (type, props, ...children) => ({ type, props, children }),
  };
  const scope = { React, document, window, Date: { now: () => time }, clearTimeout,
    setTimeout(fn, delay) { const id = ++next; timers.set(id, { at: time + delay, fn }); return id; },
    MarkdownText: function NativeSafeMarkdown() {} };
  runInNewContext(code + '\nthis.renderBuffered = BufferedMarkdown;', scope);
  const render = () => { cursor = 0; output = scope.renderBuffered({ text, streaming: live, identity, fileMentions: { verified: true } });
    effects.splice(0).forEach(fn => fn()); return output.props.text; };
  render();
  return { timers, document, render, value: () => output.props.text, node: () => output,
    set(value, active = live, id = identity) { text = value; live = active; identity = id; return render(); },
    advance(ms) { const end = time + ms;
      while (true) { const due = [...timers].sort((a, b) => a[1].at - b[1].at)[0];
        if (!due || due[1].at > end) break;
        time = due[1].at; timers.delete(due[0]); due[1].fn(); render();
      }
      time = end; return output.props.text;
    },
    dispose() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}

test('bursts are paced into small updates, retain native Markdown, and complete exactly', () => {
  const answer = '**结果**\n' + '连续文本🙂。'.repeat(100) + '\n[下载](https://example.org/file)';
  const f = fixture(); f.set(answer);
  assert.ok(f.value().length < 20);
  let previous = f.value();
  for (let i = 0; i < 10; i++) {
    const next = f.advance(40);
    assert.ok(next.startsWith(previous)); assert.ok(next.length - previous.length <= 30);
    assert.doesNotMatch(next, /[\uD800-\uDBFF]$/); previous = next;
  }
  assert.equal(f.node().type.name, 'NativeSafeMarkdown');
  assert.equal(f.node().props.fileMentions.verified, true);
  f.set(answer, false); assert.ok(f.value().length < answer.length);
  f.advance(1240); assert.equal(f.value(), answer); assert.equal(f.node().props.streaming, false);
  assert.equal(f.timers.size, 0); f.dispose();
});

test('rapid incoming chunks do not starve the display timer and lulls consume the buffer', () => {
  const f = fixture(); let target = '';
  for (let i = 0; i < 60; i++) { target += '文本增量'; f.set(target); f.advance(10); }
  assert.ok(f.value().length > 20); assert.ok(f.value().length < target.length);
  const before = f.value().length; f.advance(160); assert.ok(f.value().length > before);
  f.advance(5000); assert.equal(f.value(), target); assert.equal(f.timers.size, 0); f.dispose();
});

test('history, reduced motion and hidden tabs display complete content without a replay', () => {
  const text = '历史完整结果'.repeat(100);
  for (const f of [fixture(text, false), fixture(text, true, true)]) {
    assert.equal(f.value(), text); assert.equal(f.timers.size, 0); f.dispose();
  }
  const f = fixture(text); f.document.hidden = true; f.advance(40);
  assert.equal(f.value(), text); assert.equal(f.timers.size, 0); f.dispose();
});

test('authoritative corrections, cancellation tails and navigation never leak stale text or timers', () => {
  const f = fixture('旧结果'.repeat(100)); f.advance(40);
  assert.equal(f.set('权威更正'), '权威更正');
  f.set('另一轮'.repeat(100), true, 'turn-b');
  assert.doesNotMatch(f.value(), /旧结果|权威更正/);
  f.set('另一轮已生成部分', false); f.advance(1240);
  assert.equal(f.value(), '另一轮已生成部分');
  f.set('下一轮'.repeat(100), true, 'turn-c'); assert.equal(f.timers.size, 1);
  f.dispose(); assert.equal(f.timers.size, 0);
});
