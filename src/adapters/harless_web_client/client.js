/** Native /harless popupSelect decoration; no composer DOM writes. */
window.__ModuleLoader__.load({
  id: 'deepseek-harless-web-client',
  factory: () => {
    const endpoint = '/api/harless/settings';
    async function settings(session, signal) {
      const response = await fetch(`${endpoint}?session_id=${encodeURIComponent(session.sessionId)}`,
        { credentials: 'same-origin', cache: 'no-store', signal });
      const value = await response.json();
      if (!response.ok || value.error) throw Error(value.error?.message || 'Could not load Harless settings');
      return value;
    }
    async function select(session, patch) {
      const response = await fetch(endpoint, {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'select', session_id: session.sessionId, selection: patch }),
      });
      const value = await response.json();
      if (!response.ok || value.error) throw Error(value.error?.message || 'Could not save Harless settings');
    }
    async function choosePreviewScene(session, sceneId) {
      const response = await fetch(endpoint, {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: sceneId ? 'select_preview_scene' : 'clear_preview_scene',
          session_id: session.sessionId, ...(sceneId ? { scene_id: sceneId } : {}) }),
      });
      const value = await response.json();
      if (!response.ok || value.error) throw Error(value.error?.message || 'Could not choose scene');
    }
    function options(value) {
      const current = value.selection;
      const rows = value.preview_scenes.map(scene => ({
        id: `scene:${scene.id}`, label: scene.label, detail: 'UI preview · runtime coming later',
        active: value.preview_scene === scene.id,
      }));
      if (value.preview_scene) rows.push({ id: 'scene:clear', label: 'Clear scene choice',
        detail: 'Return to the current runtime', active: false });
      for (const [id, label, detail] of [
        ['baseline', 'Baseline', 'Standard Harness, RSI Off'],
        ['shadow', 'Shadow', 'Observe RSI candidates'],
        ['execute', 'Execute', 'Run certified motifs'],
      ]) {
        if (id === 'execute' && !value.scenes.find(scene => scene.id === current.scene)?.execute_available) continue;
        rows.push({ id: `mode:${id}`, label: `Mode · ${label}`, detail, active: current.mode === id });
      }
      rows.push({ id: 'rsi:on', label: 'RSI · On', detail: 'Enable structural reuse', active: current.rsi },
        { id: 'rsi:off', label: 'RSI · Off', detail: 'Use standard Harness', active: !current.rsi });
      return rows;
    }
    function apply(ctx) {
      const command = ctx.get('commandUi');
      ctx.effect(() => command.decorate({
        name: 'harless', available: () => true,
        ui: {
          kind: 'popupSelect',
          options: async (session, signal) => options(await settings(session, signal)),
          onSelect: async (option, session) => {
            const [kind, id] = option.id.split(':', 2);
            if (kind === 'scene') {
              await choosePreviewScene(session, id === 'clear' ? null : id);
            } else if (kind === 'mode' && ['baseline', 'shadow', 'execute'].includes(id)) {
              await select(session, { mode: id });
            } else if (kind === 'rsi' && ['on', 'off'].includes(id)) {
              await select(session, { rsi: id === 'on' });
            } else throw Error('Unknown Harless option');
          },
        },
      }), 'harless: native command picker');
    }
    return { apply };
  },
});
