/** Browser presentation only; scene settings are selected from the composer menu. */
(async () => {
  'use strict';

  const settingsUrl = '/api/harless/settings';
  const styles = document.createElement('style');
  styles.textContent = `
    .harless-picker-anchor{position:relative;display:inline-flex;align-items:center;margin-left:4px;font:13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    .harless-picker-trigger{display:inline-flex;align-items:center;gap:7px;padding:5px 9px;border:1px solid transparent;border-radius:8px;background:transparent;color:#444;cursor:pointer;font:inherit;white-space:nowrap}
    .harless-picker-trigger:hover,.harless-picker-trigger[aria-expanded="true"]{background:#f2f3f5;border-color:#e4e5e7}
    .harless-picker-mark{display:inline-grid;place-items:center;width:17px;height:17px;border-radius:5px;background:#e9eefc;color:#345bb5;font-size:11px;font-weight:700}
    .harless-picker-summary{max-width:220px;overflow:hidden;text-overflow:ellipsis}
    .harless-picker-chevron{color:#85878b;font-size:11px}
    .harless-picker-menu{position:absolute;top:calc(100% + 8px);left:0;z-index:10000;width:330px;max-width:calc(100vw - 28px);max-height:min(70vh,560px);overflow:auto;padding:8px;border:1px solid #e4e5e7;border-radius:12px;background:#fff;color:#25262a;box-shadow:0 12px 36px #17191f24;font:13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    .harless-picker-menu[hidden]{display:none}
    .harless-picker-heading{padding:8px 10px 10px;font-size:14px;font-weight:650}
    .harless-picker-group{padding:5px 3px 8px}
    .harless-picker-label{padding:5px 8px;color:#777b83;font-size:12px;font-weight:600}
    .harless-picker-option{display:flex;width:100%;align-items:center;gap:9px;padding:8px;border:0;border-radius:8px;background:transparent;color:inherit;text-align:left;cursor:pointer;font:inherit}
    .harless-picker-option:hover:not(:disabled),.harless-picker-option[aria-checked="true"]{background:#f1f2f4}
    .harless-picker-option:disabled{opacity:.42;cursor:not-allowed}
    .harless-picker-check{width:14px;color:#315cbd;text-align:center}
    .harless-picker-detail{margin-left:auto;color:#777b83;font-size:11px}
    .harless-picker-separator{height:1px;margin:3px 5px;background:#ececef}
    .harless-picker-segment{display:grid;grid-template-columns:1fr 1fr;gap:4px;padding:3px 6px}
    .harless-picker-foot{padding:9px 10px 7px;border-top:1px solid #ececef;color:#777b83;font-size:11px;line-height:1.5}
    .harless-picker-error{padding:5px 10px;color:#b42318;font-size:12px}
  `;
  document.head.append(styles);

  function makeOption(label, selected, disabled, detail, onClick) {
    const button = document.createElement('button'); button.type = 'button';
    button.className = 'harless-picker-option'; button.setAttribute('role', 'menuitemradio');
    button.setAttribute('aria-checked', selected ? 'true' : 'false'); button.disabled = Boolean(disabled);
    const check = document.createElement('span'); check.className = 'harless-picker-check'; check.textContent = selected ? '✓' : '';
    const name = document.createElement('span'); name.textContent = label;
    button.append(check, name);
    if (detail) { const note = document.createElement('span'); note.className = 'harless-picker-detail'; note.textContent = detail; button.append(note); }
    button.onclick = onClick; return button;
  }
  async function getSettings() {
    const response = await fetch(settingsUrl, { credentials: 'same-origin', cache: 'no-store' });
    const value = await response.json();
    if (!response.ok || value.error) throw Error(value.error?.message || '读取 Harless 设置失败');
    return value;
  }
  async function saveSelection(patch) {
    const response = await fetch(settingsUrl, { method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'select', selection: patch }) });
    const value = await response.json();
    if (!response.ok || value.error) throw Error(value.error?.message || '保存 Harless 设置失败');
    return value;
  }
  function closeMenu(anchor, trigger, menu) { menu.hidden = true; trigger.setAttribute('aria-expanded', 'false'); }
  function renderPicker(anchor, trigger, menu, status, error, value) {
    anchor.dataset.selection = JSON.stringify(value.selection);
    const summary = document.createElement('span'); summary.className = 'harless-picker-summary';
    summary.textContent = `${value.selection.scene} · ${value.selection.mode} · RSI ${value.selection.rsi ? 'On' : 'Off'}`;
    trigger.replaceChildren();
    const mark = document.createElement('span'); mark.className = 'harless-picker-mark'; mark.textContent = 'H';
    const chevron = document.createElement('span'); chevron.className = 'harless-picker-chevron'; chevron.textContent = '▾';
    trigger.append(mark, summary, chevron);
    menu.replaceChildren(); error.textContent = '';
    const heading = document.createElement('div'); heading.className = 'harless-picker-heading'; heading.textContent = 'Harless 设置'; menu.append(heading);

    const sceneGroup = document.createElement('section'); sceneGroup.className = 'harless-picker-group'; sceneGroup.setAttribute('role', 'group'); sceneGroup.setAttribute('aria-label', '场景');
    const sceneLabel = document.createElement('div'); sceneLabel.className = 'harless-picker-label'; sceneLabel.textContent = '场景'; sceneGroup.append(sceneLabel);
    for (const scene of value.scenes) sceneGroup.append(makeOption(scene.label || scene.id, value.selection.scene === scene.id, false, scene.id, async () => {
      try { const patch = { scene: scene.id }; if (value.selection.mode === 'execute' && !scene.execute_available) patch.mode = 'shadow';
        renderPicker(anchor, trigger, menu, status, error, await saveSelection(patch)); }
      catch (cause) { error.textContent = String(cause.message || cause); }
    }));
    menu.append(sceneGroup);
    const sep1 = document.createElement('div'); sep1.className = 'harless-picker-separator'; menu.append(sep1);

    const rsiGroup = document.createElement('section'); rsiGroup.className = 'harless-picker-group'; rsiGroup.setAttribute('role', 'group'); rsiGroup.setAttribute('aria-label', 'RSI 开关');
    const rsiLabel = document.createElement('div'); rsiLabel.className = 'harless-picker-label'; rsiLabel.textContent = 'RSI'; rsiGroup.append(rsiLabel);
    const segment = document.createElement('div'); segment.className = 'harless-picker-segment';
    segment.append(makeOption('On', value.selection.rsi, false, '', async () => {
      try { renderPicker(anchor, trigger, menu, status, error, await saveSelection({ rsi: true })); }
      catch (cause) { error.textContent = String(cause.message || cause); }
    }), makeOption('Off', !value.selection.rsi, false, '', async () => {
      try { renderPicker(anchor, trigger, menu, status, error, await saveSelection({ rsi: false })); }
      catch (cause) { error.textContent = String(cause.message || cause); }
    }));
    rsiGroup.append(segment); menu.append(rsiGroup);
    const sep2 = document.createElement('div'); sep2.className = 'harless-picker-separator'; menu.append(sep2);

    const modeGroup = document.createElement('section'); modeGroup.className = 'harless-picker-group'; modeGroup.setAttribute('role', 'group'); modeGroup.setAttribute('aria-label', '运行模式');
    const modeLabel = document.createElement('div'); modeLabel.className = 'harless-picker-label'; modeLabel.textContent = '运行模式'; modeGroup.append(modeLabel);
    const modeNames = { baseline: 'Baseline', shadow: 'Shadow', execute: 'Execute' };
    const scene = value.scenes.find(item => item.id === value.selection.scene);
    for (const mode of ['baseline', 'shadow', 'execute']) modeGroup.append(makeOption(modeNames[mode], value.selection.mode === mode,
      mode === 'execute' && !scene?.execute_available, mode === 'baseline' ? '普通 Harness' : mode === 'shadow' ? '观察候选' : '认证后接管', async () => {
        try { renderPicker(anchor, trigger, menu, status, error, await saveSelection({ mode })); }
        catch (cause) { error.textContent = String(cause.message || cause); }
      }));
    menu.append(modeGroup);
    status.textContent = value.applies_to === 'next_task' ? '当前任务保持原设置；更改用于下一任务。' : '更改用于接下来创建的会话。';
    const foot = document.createElement('div'); foot.className = 'harless-picker-foot'; foot.textContent = status.textContent; menu.append(foot);
    if (scene && !scene.execute_available) {
      const reason = document.createElement('div'); reason.className = 'harless-picker-foot';
      reason.textContent = 'Execute 暂不可用：' + ({ no_certified_library: '尚未配置认证库', no_embedding_service: '尚未配置本地匹配服务', no_certified_input: '缺少认证输入版本', no_valid_certified_library: '认证库校验未通过', library_tools_outside_scene: '认证库工具超出场景权限' }[scene.execute_unavailable_reason] || '当前场景未满足认证条件');
      menu.append(reason);
    }
  }
  const status = document.createElement('span'); status.hidden = true;

  function installPicker() {
    const slot = document.querySelector('[data-slot="conversation.input.left"]')
      ?? document.querySelector('[data-slot="conversation.hero.agentPreset"]');
    if (!slot || document.getElementById('harless-picker-anchor')) return;
    const anchor = document.createElement('span'); anchor.id = 'harless-picker-anchor'; anchor.className = 'harless-picker-anchor';
    const trigger = document.createElement('button'); trigger.type = 'button'; trigger.className = 'harless-picker-trigger';
    trigger.setAttribute('aria-haspopup', 'menu'); trigger.setAttribute('aria-expanded', 'false'); trigger.setAttribute('aria-label', '选择 Harless 场景、RSI 与运行模式');
    const menu = document.createElement('div'); menu.className = 'harless-picker-menu'; menu.setAttribute('role', 'menu'); menu.setAttribute('aria-label', 'Harless 设置'); menu.hidden = true;
    const error = document.createElement('div'); error.className = 'harless-picker-error'; error.setAttribute('role', 'alert');
    menu.append(error); anchor.append(trigger, menu); slot.after(anchor);
    let loading = false;
    async function refresh() {
      if (loading) return; loading = true;
      try { renderPicker(anchor, trigger, menu, status, error, await getSettings()); }
      catch (cause) { error.textContent = String(cause.message || cause); }
      finally { loading = false; }
    }
    trigger.onclick = async () => {
      if (!menu.hidden) { closeMenu(anchor, trigger, menu); return; }
      menu.hidden = false; trigger.setAttribute('aria-expanded', 'true'); await refresh();
    };
    window.addEventListener('pointerdown', event => { if (!anchor.contains(event.target)) closeMenu(anchor, trigger, menu); });
    window.addEventListener('keydown', event => { if (event.key === 'Escape') closeMenu(anchor, trigger, menu); });
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
    refresh();
  }
  installPicker();
  new MutationObserver(installPicker).observe(document.body, { childList: true, subtree: true });

})();
