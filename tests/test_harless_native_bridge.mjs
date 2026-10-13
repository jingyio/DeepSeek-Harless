import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

test('Selecting /harless opens the picker once without editing the native composer', () => {
  const script = readFileSync(new URL('../src/adapters/harless_native_bridge.js', import.meta.url), 'utf8');
  const observers = [];
  const input = { textContent: '/harless ', getAttribute: () => 'claimed' };
  const menu = { hidden: true };
  let clicks = 0;
  const trigger = { click() { clicks += 1; menu.hidden = false; } };
  const anchor = { querySelector: selector => selector === '.harless-picker-trigger' ? trigger : menu };
  const document = {
    head: { append() {} }, body: {},
    createElement: () => ({}),
    querySelector: selector => selector === '[data-composer-input]' ? input : null,
    getElementById: id => id === 'harless-picker-anchor' ? anchor : null,
  };
  class MutationObserver {
    constructor(callback) { this.callback = callback; observers.push(this); }
    observe() {}
    disconnect() {}
  }
  runInNewContext(script, { document, MutationObserver });
  assert.equal(clicks, 1);
  for (let i = 0; i < 100; i += 1) observers.forEach(observer => observer.callback());
  assert.equal(clicks, 1);
  assert.equal(input.textContent, '/harless ');
  input.textContent = 'new task';
  observers.forEach(observer => observer.callback());
  input.textContent = '/harless ';
  menu.hidden = true;
  observers.forEach(observer => observer.callback());
  assert.equal(clicks, 2);
});
