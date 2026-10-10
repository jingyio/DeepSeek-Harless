/** Paid native chat uses the same immutable task preview as /tasks. */
(async () => {
  'use strict';
  const endpoint = '/api/harless/tasks';
  const dialog = document.createElement('dialog');
  dialog.id = 'harless-native-confirmation';
  dialog.setAttribute('aria-label', '确认 DeepSeek Harless 任务');
  dialog.style.cssText = 'max-width:620px;width:calc(100% - 48px);border:1px solid #ddd;border-radius:14px;padding:24px;background:white;color:#202124;';
  const element = (tag, text) => { const node = document.createElement(tag); node.textContent = text; dialog.append(node); return node; };
  element('h2', '确认本次任务与预算');
  element('p', '消息已保存为待确认任务，尚未调用模型。确认后将在当前 Harness 会话执行。');
  const summary = element('p', '');
  const input = element('pre', '');
  input.style.cssText = 'white-space:pre-wrap;overflow:auto;max-height:240px;background:#f5f7fa;padding:12px;';
  const effects = element('p', '');
  const error = element('p', ''); error.setAttribute('role', 'alert'); error.style.color = '#b42318';
  const confirm = element('button', '确认并执行');
  confirm.type = 'button'; confirm.style.cssText = 'padding:10px 16px;background:#245cba;color:white;border:0;border-radius:8px;margin-right:12px;';
  const cancel = element('button', '取消任务'); cancel.type = 'button'; cancel.style.padding = '10px 16px';
  const link = element('a', '查看任务预览与统计'); link.href = '/tasks'; link.style.cssText = 'display:block;margin-top:16px;';
  document.body.append(dialog);
  let current = null, busy = false, polling = false;
  const dismissed = new Set();
  async function api(body) {
    const response = await fetch(endpoint, { method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
      ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) });
    if (response.status === 401) throw Error('登录已失效，请使用本次服务器的认证地址重新登录。');
    const value = await response.json();
    if (!response.ok || value.error) throw Error(value.error?.message || '任务请求失败，请在任务工作台查看记录。');
    return value;
  }
  function close() { if (dialog.open) dialog.close(); current = null; }
  function show(task) {
    current = task; error.textContent = '';
    summary.textContent = `模式：${task.mode}；场景：${task.capability_profile}；本任务上限：$${task.budget_usd}；全局上限：$${task.stats?.global_budget_usd ?? '见工作台'}。`;
    input.textContent = task.input_preview || JSON.stringify(task.input_summary, null, 2);
    effects.textContent = '仅使用服务器配置的 MCP；写入操作仍需场景工具自身确认。新任务不会重置全局预算。';
    link.href = '/tasks?task_id=' + encodeURIComponent(task.task_id);
    if (!dialog.open) dialog.showModal();
  }
  async function poll() {
    if (polling || busy || document.hidden) return;
    polling = true;
    try {
      const result = await api();
      const drafts = (result.tasks || []).filter(task => task.entrypoint === 'native_chat' && task.provider_mode === 'real' &&
        task.status === 'awaiting_confirmation' && !dismissed.has(task.task_id));
      if (current && !drafts.some(task => task.task_id === current.task_id)) close();
      if (!current && drafts.length) show(drafts[drafts.length - 1]);
    } catch (failure) { if (current) error.textContent = failure.message; }
    finally { polling = false; }
  }
  async function act(action) {
    if (busy || !current) return;
    busy = true; confirm.disabled = cancel.disabled = true; error.textContent = '';
    const task = current;
    try {
      await api({ action, task_id: task.task_id, ...(action === 'submit' ? { confirmation_digest: task.confirmation_digest } : {}) });
      dismissed.add(task.task_id); close();
    } catch (failure) { error.textContent = failure.message; }
    finally { busy = false; confirm.disabled = cancel.disabled = false; }
  }
  confirm.onclick = () => act('submit'); cancel.onclick = () => act('cancel');
  dialog.addEventListener('cancel', event => { event.preventDefault(); if (!busy) void act('cancel'); });
  await poll();
  const timer = setInterval(poll, 1000);
  window.addEventListener('pagehide', () => clearInterval(timer), { once: true });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void poll(); });
})();
