/** Scene references use Harness's native trigger, editor chip and session APIs. */
window.__ModuleLoader__.load({
  id: 'deepseek-harless-web-client',
  factory: (require) => {
    const React = require('react');
    const inject = ['commandUi', 'inputTriggers', 'sessions', 'conversation', 'uiConversation', 'slots'];
    const endpoint = '/api/harless/settings';
    const observers = new Map(), cache = new Map(), choosing = new Set(), revisions = new Map();
    const aliases = { ppt: 'ppt', 'paper-proofreading': 'paper', 'research-data-analysis': 'data', 'new-scene': 'chat' };
    const shortcut = scene => scene.shortcut || aliases[scene.id] || scene.id;
    const modeLabel = mode => mode === 'baseline' ? 'Origin' : mode[0].toUpperCase() + mode.slice(1);
    function publish(id, value) {
      cache.set(id, value);
      for (const listener of observers.get(id) || []) listener(value);
    }
    async function request(session, body, signal) {
      if (body) revisions.set(session.sessionId, (revisions.get(session.sessionId) || 0) + 1);
      const response = await fetch(body ? endpoint : `${endpoint}?session_id=${encodeURIComponent(session.sessionId)}`, {
        method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', signal,
        ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}),
      });
      const value = await response.json();
      if (!response.ok || value.error) {
        const error = Error(value.error?.message || '无法加载场景设置'); error.code = value.error?.code; throw error;
      }
      return value;
    }
    async function settings(session, signal) {
      const revision = revisions.get(session.sessionId) || 0;
      const value = await request(session, undefined, signal);
      if (!signal?.aborted && revision === (revisions.get(session.sessionId) || 0)) publish(session.sessionId, value);
      return value;
    }
    const reference = scene => ({ source: 'harless-scenes', ref: shortcut(scene),
      label: '/' + shortcut(scene), appearance: 'file', clipboardText: '/' + shortcut(scene) });
    function HarlessStatus({ sessionId }) {
      const [value, setValue] = React.useState(null);
      React.useEffect(() => {
        const abort = new AbortController(); setValue(cache.get(sessionId) || null);
        const listener = next => { if (!abort.signal.aborted) setValue(next); };
        const group = observers.get(sessionId) || new Set(); group.add(listener); observers.set(sessionId, group);
        settings({ sessionId }, abort.signal).catch(() => {});
        return () => { abort.abort(); group.delete(listener); if (!group.size) observers.delete(sessionId); };
      }, [sessionId]);
      const scene = value?.scenes.find(row => row.id === value.selection.scene);
      const name = scene ? '/' + shortcut(scene) : 'Harless';
      const detail = value ? value.paired_comparison ? 'Baseline / Motif 对照' : `${modeLabel(value.selection.mode)} · RSI ${value.selection.rsi ? 'On' : 'Off'}${value.conversation_only ? ' · 文字对话' : ''}` : '';
      return React.createElement('span', { role: 'status', 'aria-label': `${name} ${detail}`, title: `${name} ${detail}`,
        style: { display: 'inline-flex', alignItems: 'center', gap: '6px', maxWidth: 'min(380px, 52vw)', overflow: 'hidden',
          whiteSpace: 'nowrap', borderRadius: '6px', padding: '2px 7px', fontSize: '13px', lineHeight: '20px',
          color: 'var(--dsw-alias-label-secondary, #767c88)' } },
        React.createElement('strong', { style: { fontWeight: 600, color: 'var(--dsw-alias-state-business-primary, #4d78e8)' } }, name),
        detail && React.createElement('span', { style: { overflow: 'hidden', textOverflow: 'ellipsis' } }, detail));
    }
    function apply(ctx) {
      const command = ctx.get('commandUi'), triggers = ctx.get('inputTriggers');
      const sessions = ctx.get('sessions'), conversation = ctx.get('conversation');
      const h = React.createElement;
      const busyComparisons = new Map();
      const busyReason = '左右两侧正在运行，请等待完成或取消本次对照。';
      function updateBusy(session,id,busy){
        const group=busyComparisons.get(session)||new Set();
        busy?group.add(id):group.delete(id);
        if(group.size)busyComparisons.set(session,group);else busyComparisons.delete(session);
        const current=conversation.blocks.storeFor(session).getSnapshot();
        if(group.size&&(!current||current.reason===busyReason))conversation.blocks.set(session,{reason:busyReason});
        if(!group.size&&current?.reason===busyReason)conversation.blocks.set(session,undefined);
      }
      async function comparisonRequest(value, body, signal) {
        const url = '/api/harless/comparisons?session_id=' + encodeURIComponent(value.session_id) + '&id=' + encodeURIComponent(value.id);
        const response = await fetch(url, { method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', signal,
          ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, session_id: value.session_id, id: value.id }) } : {}) });
        const result = await response.json(); if (!response.ok) throw Error(result.error?.message || '无法读取对照结果'); return result;
      }
      function ComparisonNode({ node }) {
        const [value, setValue] = React.useState(node.data), [error, setError] = React.useState(''), [saving, setSaving] = React.useState(false);
        React.useEffect(() => { setValue(node.data); }, [node.data]);
        React.useEffect(() => {
          const abort = new AbortController(); let timer;
          const poll = async () => {
            try { const next = await comparisonRequest(node.data, undefined, abort.signal); if (!abort.signal.aborted) { setValue(next); setError(''); } }
            catch (e) { if (!abort.signal.aborted) setError(e.message); }
            if (!abort.signal.aborted) timer = setTimeout(poll, 1800);
          };
          poll(); return () => { abort.abort(); clearTimeout(timer); };
        }, [node.data.id, node.data.session_id]);
        React.useEffect(() => {
          updateBusy(value.session_id,value.id,!['completed', 'failed', 'cancelled'].includes(value.status));
          return () => updateBusy(value.session_id,value.id,false);
        }, [value.session_id, value.id, value.status]);
        const action = async body => {
          if (saving) return; setSaving(true);
          try { setValue(await comparisonRequest(value, body)); setError(''); } catch (e) { setError(e.message); }
          finally { setSaving(false); }
        };
        const labels = { preparing: '准备中', queued: '等待执行', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' };
        const pane = lane => {
          const result = value.lanes[lane], title = lane === 'baseline' ? 'Baseline · DSH' : result.mode==='shadow'?'Motif · Shadow':'Motif · DSH';
          return h('section', { key: lane, className: 'harless-paired-pane', 'aria-label': title },
            h('header', null, h('strong', null, title), h('span', { role: 'status' }, labels[result.status] || result.status)),
            result.fallback_reason && h('p', { className: 'harless-paired-notice' }, '优化未启用，已回退普通 DSH：' + result.fallback_reason),
            result.failure && h('p', { role: 'alert', className: 'harless-paired-notice' }, result.failure),
            h('div', { className: 'harless-paired-answer' }, result.answer || (result.status === 'queued' ? '等待当前任务结束后开始。' : '')),
            result.artifacts?.length > 0 && h('ul', { className: 'harless-paired-files' }, ...result.artifacts.map(file => h('li', { key: file.id }, h('a', {
              href: '/api/harless/comparisons?session_id=' + encodeURIComponent(value.session_id) + '&id=' + encodeURIComponent(value.id) + '&lane=' + lane + '&file=' + file.id,
              download: file.name.split('/').pop(), rel: 'nofollow' }, file.name.split('/').pop())))),
            h('footer', null, h('small', null, `模型请求 ${result.stats?.upstream_requests || 0} · ${result.mode==='shadow'?'预测候选 '+(result.stats?.shadow_candidates||0):'已验证跳过 '+(result.stats?.verified_skips||0)}`),
              ['failed', 'cancelled'].includes(result.status) && ['completed', 'failed', 'cancelled'].includes(value.status) && h('button', { type: 'button', disabled: saving, onClick: () => action({ action: 'retry', lane }) }, '重试此侧'),
              h('fieldset', { disabled: !value.scoring_available || saving, 'aria-label': title + '评分' }, h('legend', null, value.scoring_available ? '结果评分' : '两侧完成后评分'),
                ...[1, 2, 3, 4, 5].map(score => h('label', { key: score, className: value.scores[lane] === score ? 'selected' : '' }, h('input', {
                  type: 'radio', name: value.id + '-' + lane, value: score, checked: value.scores[lane] === score,
                  onChange: () => action({ action: 'rate', lane, score, revision: value.score_revision, output_sha256: result.output_sha256 }) }), score)))));
        };
        return h('div', { className: 'harless-paired', 'data-comparison-id': value.id },
          h('style', null, `.harless-paired{width:100%;margin:18px 0;color:var(--dsw-alias-label-primary,inherit)}.harless-paired-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.harless-paired-pane{min-width:0;border:1px solid var(--dsw-alias-outline-default,#8885);border-radius:16px;padding:18px;background:var(--dsw-alias-fill-tertiary,transparent)}.harless-paired-pane header{display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid #8883;padding-bottom:12px}.harless-paired-pane header span,.harless-paired-pane small{font-size:12px;opacity:.7}.harless-paired-answer{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7;margin:18px 0;max-height:70vh;overflow:auto}.harless-paired-notice{font-size:13px;border-left:3px solid #dba351;padding-left:10px}.harless-paired-pane footer{display:grid;gap:12px}.harless-paired-pane fieldset{display:flex;gap:8px;border:0;padding:0}.harless-paired-pane legend{font-size:12px;opacity:.7;margin-bottom:8px}.harless-paired-pane label{display:flex;align-items:center;justify-content:center;gap:4px;border:1px solid #8885;border-radius:8px;padding:7px 10px;cursor:pointer}.harless-paired-pane label.selected{color:#729cf7;border-color:#729cf7;background:#729cf719}.harless-paired button{border:1px solid #8885;border-radius:8px;padding:7px 12px;background:transparent;color:inherit;cursor:pointer}.harless-paired button:disabled{opacity:.5}.harless-paired-pane fieldset:disabled{opacity:.45}.harless-paired-error{font-size:13px;color:#d66;margin-top:10px}.harless-paired-files{padding-left:20px;overflow-wrap:anywhere}.harless-paired-files a{color:#729cf7}@media(max-width:760px){.harless-paired-grid{grid-template-columns:1fr}}`),
          h('div', { className: 'harless-paired-grid' }, pane('baseline'), pane('motif')),
          !['completed', 'failed', 'cancelled'].includes(value.status) && h('button', { type: 'button', disabled: saving, onClick: () => action({ action: 'cancel' }), style: { marginTop: 12 } }, '取消本次对照'),
          error && h('div', { role: 'alert', className: 'harless-paired-error' }, error));
      }
      ctx.effect(() => ctx.uiConversation.events.register({ kind: 'harless-comparison', target: 'chat',
        match: event => event.type === 'user/message' && event.data.harless_comparison ? { id: event.data.harless_comparison.id, role: 'start' } : null,
        start: (_context, match) => match.event.data.harless_comparison.value,
        update: context => context.state,
        buildViewNode: context => context.start && context.state ? { key: context.key, kind: 'harless-comparison', id: context.id, target: 'chat',
          anchorSeq:context.start.event.seq,location:context.start.location,visibility:'visible',data: context.state } : null,
      }), 'harless-comparison-definition');
      ctx.slots.inject('conversation.chat.node', () => ctx.slots.register({ name: 'conversation.chat.node', key: 'harless-comparison' }, ComparisonNode));
      function inputFor(id) {
        const scope = sessions.scope(id);
        if (!scope) throw Error('会话已关闭，请重新打开');
        return conversation.input.for(scope);
      }
      function leadingSpan(id) {
        const state = inputFor(id).state.getSnapshot();
        const match = /^(\s*)\/[a-z_-]*/i.exec(state.draft);
        if (!match) throw Error('输入已改变，请重新选择场景');
        return { start: match[1].length, end: match[0].length, draftRev: state.draftRev };
      }
      const sameDraft = (input, span) => {
        const state = input.state.getSnapshot();
        return state.draftRev === span.draftRev && state.phase === 'plain';
      };
      async function chooseScene(session, id, span) {
        if (choosing.has(session.sessionId)) return;
        choosing.add(session.sessionId);
        try {
          const oldInput = inputFor(session.sessionId);
          const value = await settings(session), scene = value.scenes.find(row => row.id === id);
          if (!scene || scene.available === false) throw Error('该场景暂不可用：' + (scene?.unavailable_reason || '未部署'));
          if (!sameDraft(oldInput, span)) throw Error('输入已改变，请重新选择场景');
          let next;
          try {
            next = await request(session, { action: 'select', session_id: session.sessionId, selection: { scene: id } });
          } catch (error) {
            if (error.code !== 'scene_requires_new_session') throw error;
            // A scene switch cannot rewrite an immutable started preset. Create
            // an addressed new session and hand off only the unchanged draft.
            if (!sameDraft(oldInput, span)) throw Error('输入已改变，请重新选择场景');
            const draft = oldInput.state.getSnapshot();
            next = await request(session, { action: 'new_session', inherit_session: session.sessionId, selection: { scene: id } });
            await sessions.refresh();
            const fresh = inputFor(next.session_id);
            if (!sameDraft(oldInput, span)) {
              fresh.notify('info', '新场景会话已创建；原输入有新修改，已保留在原会话。');
              throw Error('输入已改变，原输入已保留；请在会话列表打开新场景。');
            }
            fresh.setDraft(draft.draft);
            if (!fresh.insertReference(reference(scene), { ...span, draftRev: fresh.state.getSnapshot().draftRev }))
              throw Error('无法保留输入，请重新打开新场景会话');
            if (draft.attachmentIds.length) {
              if (!fresh.addAttachments(draft.attachmentIds)) throw Error('附件未能转移，原输入已保留');
              conversation.rebindDraftFiles(next.session_id, draft.attachmentIds);
              for (const attachment of draft.attachmentIds) oldInput.removeAttachment(attachment);
            }
            oldInput.setDraft('');
            command.popupFor(sessions.scope(session.sessionId)).dismiss();
            publish(next.session_id, next); sessions.open(next.session_id);
            fresh.notify('info', `已新建 ${scene.label} 会话，原聊天已保留。`);
            return;
          }
          publish(session.sessionId, next);
          if (!oldInput.insertReference(reference(scene), span)) oldInput.notify('info', '场景已选择，输入的新修改已保留。');
        } finally { choosing.delete(session.sessionId); }
      }
      const report = (session, error) => { try { inputFor(session.sessionId).notify('error', error.message); } catch {} };
      // The native trigger recomputes candidates after every character and owns
      // keyboard/IME handling, span CAS, atomic chip deletion and undo.
      ctx.effect(() => triggers.registerSource({ trigger: '/', name: 'harless-scenes', order: -10,
        candidates: async (session, req) => {
          if (req.position !== 'leading') return [];
          const value = await settings(session, req.signal), query = req.query.toLowerCase();
          return value.scenes.filter(scene => shortcut(scene).startsWith(query)).map(scene => ({
            name: shortcut(scene), value: scene.id, section: 'Scenes', description: scene.available === false
              ? `暂不可用：${scene.unavailable_reason}` : scene.label,
          }));
        },
        onPick: pick => { void chooseScene(pick.session, pick.candidate.value, pick.span).catch(error => report(pick.session, error)); return 'handled'; },
        lexicon: session => cache.get(session.sessionId)?.scenes.map(shortcut),
        subscribeLexicon: (session, listener) => {
          const group = observers.get(session.sessionId) || new Set(); group.add(listener); observers.set(session.sessionId, group);
          return () => { group.delete(listener); if (!group.size) observers.delete(session.sessionId); };
        },
        warm: session => { void settings(session).catch(() => {}); },
        codec: { clipboardText: ref => '/' + ref, serialize: async ref => {
          if (!/^[a-z][a-z0-9_-]{0,63}$/.test(ref)) throw Error('无效的场景标识'); return '/' + ref;
        } },
      }), 'harless: scene reference source');
      ctx.effect(() => command.decorate({ name: 'harless', available: () => true, ui: {
        kind: 'popupSelect',
        options: async (session, signal) => {
          const value = await settings(session, signal);
          return [
            ...value.scenes.map(scene => ({ id: `scene:${scene.id}`, label: '/' + shortcut(scene),
              detail: scene.available === false ? `暂不可用：${scene.unavailable_reason}` : scene.label,
              active: value.selection.scene === scene.id })),
            ...(!value.scene_locked ? (value.scene_option_fields || []).flatMap(field => field.values.map(choice => ({
              id: `option:${field.key}=${JSON.stringify(choice.value)}`, label: choice.label,
              detail: choice.detail || field.label, active: (value.scene_options?.[field.key] ?? field.default) === choice.value,
            }))) : []),
            ...(!value.paired_comparison ? ['baseline', 'shadow', 'execute'].map(mode => ({ id: `mode:${mode}`, label: modeLabel(mode), detail: 'Mode', active: value.selection.mode === mode })) : []),
            ...(!value.paired_comparison ? [true, false].map(rsi => ({ id: `rsi:${rsi ? 'on' : 'off'}`, label: `RSI ${rsi ? 'On' : 'Off'}`, active: value.selection.rsi === rsi })) : []),
          ];
        },
        onSelect: async (option, session) => {
          const separator = option.id.indexOf(':'), kind = option.id.slice(0, separator), id = option.id.slice(separator + 1);
          if (kind === 'scene') return chooseScene(session, id, leadingSpan(session.sessionId));
          if (kind === 'option') {
            const current = await settings(session), split = id.indexOf('='), key = id.slice(0, split);
            if (current.scene_locked) throw Error('当前任务已固定选项，请在新会话中设置');
            const selected = JSON.parse(id.slice(split + 1)), field = current.scene_option_fields?.find(row => row.key === key);
            if (!field || !field.values.some(row => row.value === selected)) throw Error('未知任务选项');
            publish(session.sessionId, await request(session, { action: 'set_scene_options', session_id: session.sessionId,
              options: { ...current.scene_options, [key]: selected } }));
            return;
          }
          const patch = kind === 'mode' ? { mode: id } : kind === 'rsi' ? { rsi: id === 'on' } : undefined;
          if (!patch) throw Error('未知设置');
          publish(session.sessionId, await request(session, { action: 'select', session_id: session.sessionId, selection: patch }));
        },
      } }), 'harless: native command picker');
      ctx.slots.inject('conversation.input.left', () => ctx.slots.register(
        { name: 'conversation.input.left', id: 'harless-status', order: 40, inject: sessionId => ({ sessionId }) }, HarlessStatus));
    }
    return { inject, apply };
  },
});
