/** Scene references use Harness's native trigger, editor chip and session APIs. */
window.__ModuleLoader__.load({
  id: 'deepseek-harless-web-client',
  factory: (require) => {
    const React = require('react');
    // Use the exact safe AST renderer used by native Harness assistant messages.
    const primitives = require('@deepseek-ai/dsh-client-ui-primitives');
    const MarkdownText = primitives?.MarkdownText;
    const inject = ['commandUi', 'inputTriggers', 'sessions', 'conversation', 'uiConversation', 'slots', 'workspaces', 'uiWorkspace', 'layout'];
    const endpoint = '/api/harless/settings';
    const observers = new Map(), lexiconObservers = new Map(), cache = new Map(), choosing = new Map(), revisions = new Map();
    const draftSelections = new Map();
    const aliases = { ppt: 'ppt', 'paper-proofreading': 'paper', 'research-data-analysis': 'data', 'new-scene': 'chat' };
    const shortcut = scene => scene.shortcut || aliases[scene.id] || scene.id;
    const modeLabel = mode => mode === 'baseline' ? 'Origin' : mode[0].toUpperCase() + mode.slice(1);
    const displayValue = (id, value) => value && draftSelections.has(id) ? { ...value,
      selection: { ...value.selection, scene: draftSelections.get(id) },
      ...(draftSelections.get(id) === 'new-scene' ? { paired_comparison: false } : {}) } : value;
    function publish(id, value) {
      const oldNames = cache.get(id)?.scenes.map(shortcut).join('\n');
      cache.set(id, value);
      for (const listener of observers.get(id) || []) listener(displayValue(id, value));
      // Native controllers refetch candidates when their lexicon changes. A
      // settings read must not invalidate the unchanged lexicon and recursively
      // trigger another settings read while the menu is open.
      if (oldNames !== value.scenes.map(shortcut).join('\n'))
        for (const listener of lexiconObservers.get(id) || []) listener();
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
    function HarlessStatus({ sessionId, openSession }) {
      const [value, setValue] = React.useState(null);
      React.useEffect(() => {
        const abort = new AbortController(); setValue(displayValue(sessionId, cache.get(sessionId)) || null);
        const listener = next => { if (!abort.signal.aborted) setValue(next); };
        const group = observers.get(sessionId) || new Set(); group.add(listener); observers.set(sessionId, group);
        settings({ sessionId }, abort.signal).catch(() => {});
        return () => { abort.abort(); group.delete(listener); if (!group.size) observers.delete(sessionId); };
      }, [sessionId]);
      const scene = value?.scenes.find(row => row.id === value.selection.scene);
      const name = scene ? '/' + shortcut(scene) : 'GeneLoop';
      const detail = value ? value.paired_comparison ? 'Baseline / Motif 对照' : `${modeLabel(value.selection.mode)} · RSI ${value.selection.rsi ? 'On' : 'Off'}${value.conversation_only ? ' · 文字对话' : ''}` : '';
      return React.createElement('span', { role: 'status', 'aria-label': `${name} ${detail}`, title: `${name} ${detail}`,
        style: { display: 'inline-flex', alignItems: 'center', gap: '6px', maxWidth: 'min(380px, 52vw)', overflow: 'hidden',
          whiteSpace: 'nowrap', borderRadius: '6px', padding: '2px 7px', fontSize: '13px', lineHeight: '20px',
          color: 'var(--dsw-alias-label-secondary, #767c88)' } },
        React.createElement('strong', { style: { fontWeight: 600, color: 'var(--dsw-alias-state-business-primary, #4d78e8)' } }, name),
        detail && React.createElement('span', { style: { overflow: 'hidden', textOverflow: 'ellipsis' } }, detail),
        value?.comparison_parent_session_id && React.createElement('button', { type: 'button', onClick: () => openSession(value.comparison_parent_session_id),
          style: { color: 'var(--dsw-alias-link, #729cf7)', background: 'none', border: 0, cursor: 'pointer', padding: '2px 4px', font: 'inherit', flexShrink: 0 } }, '返回双栏结果与下载'));
    }
    function apply(ctx) {
      window.__installGeneLoopBrand?.(ctx, React);
      window.__installGeneLoopWorkspaces?.(ctx, React, primitives);
      const command = ctx.get('commandUi'), triggers = ctx.get('inputTriggers');
      const sessions = ctx.get('sessions'), conversation = ctx.get('conversation');
      const h = React.createElement;
      const busyComparisons = new Map();
      const busyReason = '左右两侧正在运行，请等待完成或取消本次对照。';
      function updateBusy(session,id,busy){
        const group=busyComparisons.get(session)||new Map(), count=(group.get(id)||0)+(busy?1:-1);
        if(count>0)group.set(id,count);else group.delete(id);
        if(group.size)busyComparisons.set(session,group);else busyComparisons.delete(session);
        const current=conversation.blocks.storeFor(session).getSnapshot();
        if(group.size&&(!current||current.reason===busyReason))conversation.blocks.set(session,{reason:busyReason});
        if(!group.size&&current?.reason===busyReason)conversation.blocks.set(session,undefined);
      }
      const settled = value => ['completed', 'failed', 'cancelled'].includes(value.status);
      const markdownLabels = { code: { copyLabel: '复制', copiedLabel: '已复制' }, footnotes: '注释' };
      function apiError(status, message) {
        const labels = { 401: '登录已过期，请重新登录。', 403: '当前账号没有权限访问此结果。',
          404: '该结果或文件不存在，或不属于当前账号。', 409: '结果已更新，请刷新后再操作。',
          429: '请求较多，请稍后重试。', 502: '服务器连接暂时中断，请稍后重试。',
          503: '服务正在恢复，请稍后重试。', 504: '服务器响应超时，请稍后重试。' };
        const error = Error(labels[status] || message || `请求失败（HTTP ${status}）`);
        error.status = status; return error;
      }
      const networkMessage = error => error.status ? error.message : '网络连接暂时中断，已保留当前结果。';
      function comparisonUrl(value, lane, file) {
        return '/api/harless/comparisons?session_id=' + encodeURIComponent(value.session_id) + '&id=' + encodeURIComponent(value.id)
          + (lane ? '&lane=' + lane + '&file=' + encodeURIComponent(file.id) : '');
      }
      async function withDeadline(signal, milliseconds, operation) {
        const abort = new AbortController(); let expired = false;
        const cancel = () => abort.abort();
        if (signal?.aborted) cancel(); else signal?.addEventListener('abort', cancel, { once: true });
        const timer = setTimeout(() => { expired = true; abort.abort(); }, milliseconds);
        try {
          // Keep the deadline through response body consumption and integrity checks.
          const result = await operation(abort.signal);
          if (expired) throw apiError(408, '连接超时，请稍后重试。');
          return result;
        } catch (error) {
          if (expired && !signal?.aborted) throw apiError(408, '连接超时，请稍后重试。');
          throw error;
        } finally { clearTimeout(timer); signal?.removeEventListener('abort', cancel); }
      }
      async function comparisonRequest(value, body, signal) {
        return withDeadline(signal, 30000, async requestSignal => {
          const response = await fetch(comparisonUrl(value), { method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', signal: requestSignal,
            ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, session_id: value.session_id, id: value.id }) } : {}) });
          let result;
          try { result = await response.json(); } catch { throw apiError(response.status || 502, '服务器未返回有效结果，请稍后刷新。'); }
          if (!response.ok || result.error) throw apiError(response.status, result.error?.message);
          if (result.id !== value.id || result.session_id !== value.session_id || !result.lanes?.baseline || !result.lanes?.motif)
            throw apiError(502, '服务器未返回当前对照结果。');
          return result;
        });
      }
      function artifactFor(files, raw) {
        let path = String(raw || '').trim();
        try { path = decodeURIComponent(path); } catch { return undefined; }
        path = path.replace(/^sandbox:/, '').replace(/^file:\/\//, '').replace(/\\/g, '/');
        // Match only immutable server-approved rows; ambiguous basenames stay inert.
        const exact = files.filter(file => path === file.name || path.endsWith('/' + file.name));
        if (exact.length === 1) return exact[0];
        if (!path.includes('/')) {
          const matches = files.filter(file => file.name.split('/').pop() === path);
          if (matches.length === 1) return matches[0];
        }
        return undefined;
      }
      function ComparisonNode({ node }) {
        const [value, setValue] = React.useState(node.data), [error, setError] = React.useState(''), [saving, setSaving] = React.useState(false);
        const [connection, setConnection] = React.useState(''), [downloads, setDownloads] = React.useState({});
        const generation = React.useRef(0), actionBusy = React.useRef(false), downloadBusy = React.useRef(new Set());
        const alive = React.useRef(true), transferControllers = React.useRef(new Set()), refreshNow = React.useRef(() => {});
        React.useEffect(() => {
          alive.current = true; setDownloads({}); setError(''); setConnection(''); setSaving(false);
          actionBusy.current = false; downloadBusy.current.clear(); generation.current++;
          return () => { alive.current = false; for (const abort of transferControllers.current) abort.abort(); };
        }, [node.data.id, node.data.session_id]);
        // Persisted start-event data may be reassembled with a fresh object while
        // GET already holds newer results. Reset only when viewing another turn.
        React.useEffect(() => { setValue(node.data); }, [node.data.id, node.data.session_id]);
        React.useEffect(() => {
          const abort = new AbortController(); let timer, failures = 0, pending = false, rerun = false;
          const poll = async () => {
            if (abort.signal.aborted) return;
            if (pending) { rerun = true; return; }
            clearTimeout(timer); pending = true; let delay = 0;
            const revision = generation.current;
            try {
              const next = await comparisonRequest(node.data, undefined, abort.signal);
              if (!abort.signal.aborted && revision === generation.current && !actionBusy.current) {
                setValue(next); setConnection(''); failures = 0;
              }
              if (!settled(next) || actionBusy.current) delay = document.hidden ? 8000 : 1800;
            } catch (e) {
              if (!abort.signal.aborted) {
                failures++;
                const denied = [401, 403, 404].includes(e.status);
                setConnection(networkMessage(e) + (denied ? '' : ' 正在自动重连…'));
                if (!denied) delay = Math.min(30000, 1800 * 2 ** Math.min(failures, 5));
              }
            } finally { pending = false; }
            if (!abort.signal.aborted && (delay || rerun)) { timer = setTimeout(poll, rerun ? 0 : delay); rerun = false; }
          };
          const wake = () => { if (!document.hidden) void poll(); };
          refreshNow.current = poll;
          window.addEventListener('online', wake); window.addEventListener('focus', wake); document.addEventListener('visibilitychange', wake);
          void poll();
          return () => { abort.abort(); clearTimeout(timer); refreshNow.current = () => {};
            window.removeEventListener('online', wake); window.removeEventListener('focus', wake); document.removeEventListener('visibilitychange', wake); };
        }, [node.data.id, node.data.session_id]);
        React.useEffect(() => {
          if (settled(value)) return;
          updateBusy(value.session_id, value.id, true);
          return () => updateBusy(value.session_id, value.id, false);
        }, [value.session_id, value.id, value.status]);
        const action = async body => {
          if (actionBusy.current) return;
          actionBusy.current = true; generation.current++; setSaving(true); setError('');
          const revision = generation.current, abort = new AbortController(); transferControllers.current.add(abort);
          const current = () => alive.current && generation.current === revision && !abort.signal.aborted;
          try { const next = await comparisonRequest(value, body, abort.signal); if (current()) { setValue(next); setConnection(''); } }
          catch (e) { if (current()) setError(networkMessage(e) + (!e.status || e.status === 408 ? ' 将重新读取状态，请勿重复提交。' : '')); }
          finally {
            transferControllers.current.delete(abort);
            if (alive.current && generation.current === revision) { actionBusy.current = false; setSaving(false); void refreshNow.current(); }
          }
        };
        const download = async (lane, file) => {
          const key = lane + ':' + file.id;
          if (downloadBusy.current.has(key)) return;
          downloadBusy.current.add(key);
          const abort = new AbortController(); transferControllers.current.add(abort);
          const state = row => { if (alive.current) setDownloads(old => ({ ...old, [key]: row })); };
          state({ phase: 'pending', message: '正在准备下载…' });
          try {
            const blob = await withDeadline(abort.signal, 60000, async requestSignal => {
              const response = await fetch(comparisonUrl(value, lane, file), { credentials: 'same-origin', cache: 'no-store', signal: requestSignal });
              if (!response.ok) throw apiError(response.status);
              // A gateway/login HTML document must never be saved as the requested PDF.
              const contentType = response.headers.get('content-type') || '';
              if (/text\/html|application\/json/i.test(contentType) && !/\.(html|json)$/i.test(file.name)) throw apiError(502, '未收到交付文件，请刷新后重试。');
              const blob = await response.blob();
              if (Number.isFinite(file.bytes) && blob.size !== file.bytes) throw apiError(409, '文件大小校验失败，请刷新后重试。');
              if (file.sha256 && window.crypto?.subtle) {
                const digest = await window.crypto.subtle.digest('SHA-256', await blob.arrayBuffer());
                const hex = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
                if (hex !== file.sha256) throw apiError(409, '文件内容校验失败，请刷新后重试。');
              }
              return blob;
            });
            if (abort.signal.aborted) return;
            const url = URL.createObjectURL(blob), link = document.createElement('a');
            link.href = url; link.download = file.name.split('/').pop(); link.hidden = true;
            document.body.appendChild(link); link.click(); link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 60000);
            state({ phase: 'success', message: '已交给浏览器下载，请查看下载列表。' });
          } catch (e) { if (!abort.signal.aborted) state({ phase: 'error', message: networkMessage(e) + ' 点击文件重试。' }); }
          finally { downloadBusy.current.delete(key); transferControllers.current.delete(abort); }
        };
        const labels = { preparing: '准备中', queued: '等待执行', running: '运行中', completed: '回复完成', failed: '失败', cancelled: '已取消' };
        const pane = lane => {
          const result = value.lanes[lane], files = result.artifacts || [], title = lane === 'baseline' ? 'Baseline · DSH' : result.mode === 'shadow' ? 'Motif · Shadow' : 'Motif · DSH';
          const captureLink = event => {
            const link = event.target.closest?.('a'); if (!link) return;
            const raw = link.getAttribute('href') || '', file = artifactFor(files, raw);
            if (file) { event.preventDefault(); event.stopPropagation(); void download(lane, file); }
            else if (raw && !/^(https?:|mailto:|#)/i.test(raw)) {
              event.preventDefault(); event.stopPropagation();
              setError('此路径尚未登记为可下载成品，请使用该侧“交付文件”中的下载按钮。');
            }
          };
          const mentions = { resolve: raw => { const file = artifactFor(files, raw); return file ? {
            title: file.name, label: '下载 ' + file.name.split('/').pop(), open: () => { void download(lane, file); },
          } : undefined; } };
          return h('section', { key: lane, className: 'harless-paired-pane', 'aria-label': title },
            h('header', null, h('strong', null, title), h('span', { role: 'status' }, result.status === 'completed' && result.delivery_status === 'available' ? '已交付' : labels[result.status] || result.status)),
            result.fallback_reason && h('p', { className: 'harless-paired-notice' }, '优化未启用，已回退普通 DSH：' + result.fallback_reason),
            result.failure && h('p', { role: 'alert', className: 'harless-paired-notice' }, result.failure),
            h('div', { className: 'harless-paired-answer', onClickCapture: captureLink }, (result.answer_display ?? result.answer)
              ? MarkdownText ? h(MarkdownText, { text: result.answer_display ?? result.answer, streaming: !settled(result), labels: markdownLabels, fileMentions: mentions })
                : h('p', { style: { whiteSpace: 'pre-wrap' } }, result.answer_display ?? result.answer)
              : h('p', { className: 'harless-paired-muted' }, result.status === 'queued' ? '等待当前任务结束后开始。' : !settled(result) ? '正在处理，结果会自动更新…' : '本轮未生成文字回复。')),
            files.length > 0 && h('section', { className: 'harless-paired-deliveries', 'aria-label': title + '交付文件' },
              h('h4', null, '交付文件'), h('ul', { className: 'harless-paired-files' }, ...files.map(file => {
                const status = downloads[lane + ':' + file.id];
                return h('li', { key: file.id }, h('a', { href: comparisonUrl(value, lane, file), download: file.name.split('/').pop(), rel: 'nofollow',
                  'aria-disabled': status?.phase === 'pending', onClick: event => { event.preventDefault(); void download(lane, file); } },
                  h('span', { className: 'harless-paired-filename', title: file.name }, file.name.split('/').pop()),
                  h('span', { className: 'harless-paired-download-label' }, status?.phase === 'pending' ? '准备中…' : '下载')),
                  status && h('small', { role: status.phase === 'error' ? 'alert' : 'status', className: status.phase === 'error' ? 'harless-paired-error' : 'harless-paired-muted' }, status.message));
              }))),
            result.delivery_message && h('p', { className: 'harless-paired-notice', role: 'status' }, result.delivery_message),
            h('footer', null, h('small', null, `模型请求 ${result.stats?.upstream_requests || 0} · ${result.mode === 'shadow' ? '预测候选 ' + (result.stats?.shadow_candidates || 0) : '已验证跳过 ' + (result.stats?.verified_skips || 0)}`),
              ['failed', 'cancelled'].includes(result.status) && settled(value) && h('button', { type: 'button', disabled: saving, onClick: () => action({ action: 'retry', lane }) }, '重试此侧'),
              h('fieldset', { disabled: !value.scoring_available || saving, 'aria-label': title + '评分' }, h('legend', null, value.scoring_available ? '结果评分' : '两侧完成后评分'),
                ...[1, 2, 3, 4, 5].map(score => h('label', { key: score, className: value.scores[lane] === score ? 'selected' : '' }, h('input', {
                  type: 'radio', name: value.id + '-' + lane, value: score, checked: value.scores[lane] === score,
                  onChange: () => action({ action: 'rate', lane, score, revision: value.score_revision, output_sha256: result.output_sha256 }) }), score)))));
        };
        return h('div', { className: 'harless-paired', 'data-comparison-id': value.id },
          h('style', null, `.harless-paired{width:100%;min-width:0;container-type:inline-size;margin:18px 0;color:var(--dsw-alias-label-primary,inherit);font-family:var(--dsw-font-family,inherit);font-size:var(--dsh-content-font-size,14px)}.harless-paired-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}.harless-paired-pane{min-width:0;border:1px solid var(--dsw-alias-outline-default,#8885);border-radius:16px;padding:18px;background:var(--dsw-alias-fill-tertiary,transparent)}.harless-paired-pane>header{display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid #8883;padding-bottom:12px}.harless-paired-pane>header>span,.harless-paired-pane small{font-size:12px;line-height:1.5;color:var(--dsw-alias-label-secondary,inherit)}.harless-paired-pane>header>strong{font-size:15px}.harless-paired-answer{overflow-wrap:anywhere;line-height:1.65;margin:18px 0;min-width:0}.harless-paired-answer pre{max-width:100%;overflow-x:auto}.harless-paired-answer table{font-size:inherit}.harless-paired-notice{font-size:13px;line-height:1.6;border-left:3px solid #b99555;padding-left:10px}.harless-paired-pane>footer{display:grid;gap:12px;margin-top:20px;padding-top:14px;border-top:1px solid #8883}.harless-paired-pane fieldset{display:flex;flex-wrap:wrap;gap:6px;border:0;padding:0;min-width:0}.harless-paired-pane legend{font-size:12px;color:var(--dsw-alias-label-secondary,inherit);margin-bottom:8px}.harless-paired-pane fieldset label{display:flex;align-items:center;justify-content:center;gap:4px;border:1px solid #8885;border-radius:8px;padding:6px 8px;min-height:32px;cursor:pointer}.harless-paired-pane label.selected{color:var(--dsw-alias-link,#729cf7);border-color:currentColor;background:#729cf719}.harless-paired button{border:1px solid #8885;border-radius:8px;padding:7px 12px;background:transparent;color:inherit;cursor:pointer;font:inherit}.harless-paired button:disabled{opacity:.5}.harless-paired-pane fieldset:disabled{opacity:.45}.harless-paired-error{font-size:13px;line-height:1.6;color:var(--dsw-alias-state-error-primary,#d66)!important;margin-top:10px}.harless-paired-connection{font-size:13px;line-height:1.6;margin:12px 0;color:var(--dsw-alias-label-secondary,inherit)}.harless-paired-connection button{margin-left:8px}.harless-paired-deliveries h4{font-size:13px;margin:0 0 8px}.harless-paired-files{list-style:none;padding:0;display:grid;gap:8px}.harless-paired-files li{min-width:0}.harless-paired-files a{display:flex;align-items:center;gap:12px;justify-content:space-between;padding:10px 12px;border:1px solid #8884;border-radius:10px;color:var(--dsw-alias-link,#729cf7);text-decoration:none}.harless-paired-files a:hover{background:#8881}.harless-paired-filename{min-width:0;overflow-wrap:anywhere}.harless-paired-download-label{flex-shrink:0;font-size:12px}.harless-paired-muted{color:var(--dsw-alias-label-secondary,inherit);font-size:13px}.harless-paired-files small{display:block;margin-top:5px}@container(max-width:650px){.harless-paired-grid{grid-template-columns:1fr}.harless-paired-pane{padding:16px}}`),
          h('div', { className: 'harless-paired-grid' }, pane('baseline'), pane('motif')),
          !settled(value) && h('button', { type: 'button', disabled: saving, onClick: () => action({ action: 'cancel' }), style: { marginTop: 12 } }, '取消本次对照'),
          connection && h('div', { role: 'status', className: 'harless-paired-connection' }, connection,
            h('button', { type: 'button', onClick: () => refreshNow.current() }, '重新连接'),
            connection.includes('登录') && h('a', { href: '/login', style: { marginLeft: 8 } }, '登录')),
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
      const isCurrent = session => !sessions.list || sessions.list.getSnapshot().current === session.sessionId;
      function watchSession(session, signal) {
        const abort = new AbortController();
        const check = () => { if (!isCurrent(session)) abort.abort(); };
        const cancel = () => abort.abort();
        if (signal?.aborted) cancel(); else signal?.addEventListener('abort', cancel, { once: true });
        const off = sessions.list?.subscribe(check) || (() => {}); check();
        return { signal: abort.signal, dispose() { off(); signal?.removeEventListener('abort', cancel); }, check() {
          if (abort.signal.aborted) { const error = Error('会话已切换，原输入已保留'); error.name = 'AbortError'; throw error; }
        } };
      }
      function leadingSpan(id) {
        const state = inputFor(id).state.getSnapshot();
        const match = /^(\s*)\/[a-z0-9_-]*/i.exec(state.draft);
        if (!match) throw Error('输入已改变，请重新选择场景');
        return { start: match[1].length, end: match[0].length, draftRev: state.draftRev };
      }
      const sceneToken = draft => /^(\s*)\/([a-z][a-z0-9_-]*)(?=$|\s|[\u3400-\u9fff])/i.exec(draft);
      const choiceVersions = new Map(), draftWatches = new Map(), suppressDraftReset = new Set(), deferredResets = new Map();
      const resetReason = '正在切换为普通对话…';
      const cancelledChoice = () => { const error = Error('场景选择已取消'); error.name = 'AbortError'; return error; };
      function displaySelection(id, scene) {
        if (scene) draftSelections.set(id, scene); else draftSelections.delete(id);
        const value = cache.get(id);
        if (value) for (const listener of observers.get(id) || []) listener(displayValue(id, value));
      }
      function clearResetBlock(id) {
        const blocks = conversation.blocks;
        if (blocks?.storeFor(id).getSnapshot()?.reason?.startsWith('普通对话切换失败')
          || blocks?.storeFor(id).getSnapshot()?.reason === resetReason) blocks.set(id, undefined);
      }
      const knownDraftScene = (id, draft) => {
        const token = sceneToken(draft);
        if (!token) return undefined;
        const name = token[2].toLowerCase(), value = cache.get(id);
        return value ? value.scenes.find(scene => shortcut(scene) === name)?.id
          : Object.keys(aliases).find(id => aliases[id] === name);
      };
      function watchDraft(session) {
        const id = session.sessionId;
        if (draftWatches.has(id)) return;
        const input = inputFor(id); let previous = input.state.getSnapshot();
        const off = input.state.subscribe(() => {
          const next = input.state.getSnapshot(), before = previous; previous = next;
          if (suppressDraftReset.has(id) || before.draftRev === next.draftRev || before.phase !== 'plain' || next.phase !== 'plain') return;
          // Only an actual edit that removes a complete leading scene token is
          // a cancellation. Empty drafts on mount, session changes and the
          // native adjudicating -> committed-draft transition keep the scene.
          const removed = knownDraftScene(id, before.draft);
          if (removed && removed !== 'new-scene' && !knownDraftScene(id, next.draft)) void resetScene(session);
        });
        draftWatches.set(id, off);
      }
      async function resetScene(session, handoffRetries = 1) {
        const id = session.sessionId, previous = choosing.get(id), version = (choiceVersions.get(id) || 0) + 1;
        choiceVersions.set(id, version); revisions.set(id, (revisions.get(id) || 0) + 1);
        deferredResets.delete(id);
        displaySelection(id, 'new-scene');
        const blocks = conversation.blocks, existing = blocks?.storeFor(id).getSnapshot();
        if (!existing || existing.reason === resetReason) blocks?.set(id, { reason: resetReason });
        const current = () => choiceVersions.get(id) === version;
        const operation = (async () => {
          // An aborted HTTP request can still mutate the server. Let the old
          // mount settle, then overwrite it; never race a reset against a pick.
          await previous?.catch(() => {});
          if (!current()) return;
          let next;
          try { next = await request(session, { action: 'select', session_id: id, selection: { scene: 'new-scene' } }); }
          catch (error) {
            if (error.code !== 'scene_requires_new_session') throw error;
            if (!current()) return;
            next = await request(session, { action: 'new_session', inherit_session: id, selection: { scene: 'new-scene' } });
            if (!current()) return;
            await sessions.refresh();
            if (!current()) return;
            const targetDraft = draftSnapshot(inputFor(next.session_id));
            const handoff = () => {
              if (!current()) return;
              const oldInput = inputFor(id), draft = draftSnapshot(oldInput), fresh = inputFor(next.session_id);
              if (draft.phase !== 'plain') throw Error('请等待当前发送完成后再切换普通对话');
              if (targetDraft.draft || targetDraft.attachmentIds.length || !sameDraft(fresh, targetDraft, targetDraft.attachmentIds)) {
                // The addressed target is already visible in the session list.
                // Never overwrite text/files entered there while we waited.
                if (handoffRetries > 0) { void resetScene(session, handoffRetries - 1); return; }
                throw Error('新普通会话已有输入，两边草稿均已保留。请刷新页面后重试。');
              }
              fresh.setDraft(draft.draft);
              if (draft.attachmentIds.length) {
                if (!fresh.addAttachments(draft.attachmentIds)) throw Error('附件未能转移，原输入已保留');
                conversation.rebindDraftFiles(next.session_id, draft.attachmentIds);
                for (const attachment of draft.attachmentIds) oldInput.removeAttachment(attachment);
              }
              suppressDraftReset.add(id);
              try { oldInput.setDraft(''); } finally { suppressDraftReset.delete(id); }
              displaySelection(id, undefined); clearResetBlock(id);
              publish(next.session_id, next); sessions.open(next.session_id);
              fresh.notify('info', '已切换为普通对话，原场景聊天已保留。');
            };
            // Finishing a background mount must never steal another chat's
            // focus. Complete the addressed handoff if this chat is reopened.
            if (!isCurrent(session)) deferredResets.set(id, handoff); else handoff();
            return;
          }
          if (current()) draftSelections.delete(id);
          publish(id, next); // Canonical state may change under a newer draft overlay.
        })();
        choosing.set(id, operation);
        try { await operation; if (current() && !deferredResets.has(id)) clearResetBlock(id); }
        catch (error) {
          if (current()) {
            blocks?.set(id, { reason: '普通对话切换失败，请刷新页面后重试。' });
            report(session, error);
          }
        } finally { if (choosing.get(id) === operation) choosing.delete(id); }
      }
      ctx.effect(() => {
        const attach = () => {
          const id = sessions.list?.getSnapshot().current;
          if (!id) return;
          try {
            watchDraft({ sessionId: id });
            const handoff = deferredResets.get(id);
            if (handoff) { deferredResets.delete(id); handoff(); }
          } catch (error) {
            if (conversation.blocks?.storeFor(id).getSnapshot()?.reason === resetReason)
              conversation.blocks.set(id, { reason: '普通对话切换失败，请刷新页面后重试。' });
            report({ sessionId: id }, error);
          }
        };
        const off = sessions.list?.subscribe(attach) || (() => {}); attach();
        return () => { off(); for (const stop of draftWatches.values()) stop(); draftWatches.clear(); };
      }, 'harless: scene draft cancellation');
      const sameAttachments = (left, right) => left.length === right.length && left.every((id, index) => id === right[index]);
      const draftSnapshot = input => { const state = input.state.getSnapshot(); return { ...state, attachmentIds: [...state.attachmentIds] }; };
      const sameDraft = (input, span, expectedAttachments) => {
        const state = input.state.getSnapshot();
        return state.draftRev === span.draftRev && state.phase === 'plain'
          && (expectedAttachments === undefined || sameAttachments(state.attachmentIds, expectedAttachments));
      };
      async function chooseScene(session, id, span, fromCommand = false, automatic = false) {
        // The current span, not a formerly highlighted menu row, owns the pick.
        watchDraft(session);
        const oldInput = inputFor(session.sessionId), initial = draftSnapshot(oldInput);
        if (!sameDraft(oldInput, span)) throw Error('输入已改变，请重新选择场景');
        const token = initial.draft.slice(span.start, span.end).toLowerCase();
        const known = cache.get(session.sessionId)?.scenes.find(row => row.id === id);
        if (!/^\/[a-z0-9_-]*$/i.test(token) || (fromCommand ? token !== '/harless' : known && !('/' + shortcut(known)).startsWith(token)))
          throw Error('候选已更新，请按当前输入重新选择场景');
        const previous = choosing.get(session.sessionId), version = (choiceVersions.get(session.sessionId) || 0) + 1;
        choiceVersions.set(session.sessionId, version);
        deferredResets.delete(session.sessionId);
        // Commit the native chip synchronously. The backend may need to mount
        // an MCP; that must not delay visual acknowledgement of a valid pick.
        let expectedSpan = span, optimistic = false;
        if (known && known.available !== false) {
          if (!oldInput.insertReference(reference(known), span)) throw Error('输入已改变，请重新选择场景');
          optimistic = true;
          expectedSpan = { ...span, draftRev: oldInput.state.getSnapshot().draftRev };
          displaySelection(session.sessionId, id);
        }
        const guard = watchSession(session);
        const checkChoice = () => { guard.check(); if (choiceVersions.get(session.sessionId) !== version) throw cancelledChoice(); };
        const operation = (async () => {
          if (previous) await previous.catch(() => {});
          checkChoice();
          const oldInput = inputFor(session.sessionId);
          const value = cache.get(session.sessionId) || await settings(session, guard.signal), scene = value.scenes.find(row => row.id === id);
          checkChoice();
          if (!scene || scene.available === false) throw Error('该场景暂不可用：' + (scene?.unavailable_reason || '未部署'));
          if (!sameDraft(oldInput, expectedSpan, initial.attachmentIds)
            && !(optimistic && !automatic && knownDraftScene(session.sessionId, oldInput.state.getSnapshot().draft) === id))
            throw Error('输入或附件已改变，请重新选择场景');
          if (!fromCommand && !('/' + shortcut(scene)).startsWith(token)) throw Error('候选已更新，请按当前输入重新选择场景');
          let next;
          try {
            next = await request(session, { action: 'select', session_id: session.sessionId, selection: { scene: id } }, guard.signal);
            checkChoice();
          } catch (error) {
            checkChoice();
            if (error.code !== 'scene_requires_new_session') throw error;
            // A scene switch cannot rewrite an immutable started preset. Create
            // an addressed new session and hand off only the unchanged draft.
            if (!sameDraft(oldInput, expectedSpan, initial.attachmentIds)) throw Error('输入或附件已改变，请重新选择场景');
            const draft = initial;
            next = await request(session, { action: 'new_session', inherit_session: session.sessionId, selection: { scene: id } }, guard.signal);
            checkChoice();
            await sessions.refresh();
            checkChoice();
            const fresh = inputFor(next.session_id);
            if (!sameDraft(oldInput, expectedSpan, draft.attachmentIds)) {
              fresh.notify('info', '新场景会话已创建；原输入有新修改，已保留在原会话。');
              throw Error('输入或附件已改变，原输入已保留；请在会话列表打开新场景。');
            }
            fresh.setDraft(draft.draft);
            if (!fresh.insertReference(reference(scene), { ...span, draftRev: fresh.state.getSnapshot().draftRev }))
              throw Error('无法保留输入，请重新打开新场景会话');
            if (draft.attachmentIds.length) {
              if (!fresh.addAttachments(draft.attachmentIds)) throw Error('附件未能转移，原输入已保留');
              conversation.rebindDraftFiles(next.session_id, draft.attachmentIds);
              for (const attachment of draft.attachmentIds) oldInput.removeAttachment(attachment);
            }
            suppressDraftReset.add(session.sessionId);
            try { oldInput.setDraft(''); } finally { suppressDraftReset.delete(session.sessionId); }
            command.popupFor(sessions.scope(session.sessionId)).dismiss();
            displaySelection(session.sessionId, undefined); clearResetBlock(session.sessionId);
            publish(next.session_id, next); guard.dispose(); sessions.open(next.session_id);
            fresh.notify('info', `已新建 ${scene.label} 会话，原聊天已保留。`);
            return { input: fresh, state: draftSnapshot(fresh), sessionId: next.session_id };
          }
          if (!optimistic && !sameDraft(oldInput, expectedSpan, initial.attachmentIds)
            && !knownDraftScene(session.sessionId, oldInput.state.getSnapshot().draft)) {
            void resetScene(session); throw cancelledChoice();
          }
          draftSelections.delete(session.sessionId); clearResetBlock(session.sessionId); publish(session.sessionId, next);
          // A manual pick only selects; typing while its mount completes is
          // normal. Keep those edits. Automatic handoff still requires CAS.
          if (optimistic && !automatic && !sameDraft(oldInput, expectedSpan, initial.attachmentIds))
            return { input: oldInput, state: draftSnapshot(oldInput), sessionId: session.sessionId };
          if (!sameDraft(oldInput, expectedSpan, initial.attachmentIds) || (!optimistic && !oldInput.insertReference(reference(scene), span)))
            throw Error('场景已选择，但输入或附件已改变；已保留草稿，请确认后重新发送。');
          return { input: oldInput, state: draftSnapshot(oldInput), sessionId: session.sessionId };
        })();
        choosing.set(session.sessionId, operation);
        try { return await operation; }
        catch (error) {
          if (choiceVersions.get(session.sessionId) === version) {
            displaySelection(session.sessionId, undefined);
            clearResetBlock(session.sessionId);
            if (optimistic && sameDraft(oldInput, expectedSpan, initial.attachmentIds)) {
              suppressDraftReset.add(session.sessionId);
              try { oldInput.setDraft(initial.draft); } finally { suppressDraftReset.delete(session.sessionId); }
            }
          }
          throw error;
        } finally { guard.dispose(); if (choosing.get(session.sessionId) === operation) choosing.delete(session.sessionId); }
      }
      const report = (session, error) => { if (!isCurrent(session) || error.name === 'AbortError') return; try { inputFor(session.sessionId).notify('error', error.message); } catch {} };
      function handOffAfterSubmit(session, scene, span, signal) {
        // A handled adjudication returns the native machine to plain. Wait for
        // that public state before moving a frozen draft and its attachments.
        const input = inputFor(session.sessionId), frozenAttachments = [...input.state.getSnapshot().attachmentIds];
        let off = () => {}, offSession = () => {}, timer, done = false;
        const stop = () => { done = true; off(); offSession(); clearTimeout(timer); signal.removeEventListener('abort', stop); };
        const check = () => {
          if (done || input.state.getSnapshot().phase === 'adjudicating') return;
          stop();
          if (signal.aborted || !isCurrent(session) || !sameDraft(input, span, frozenAttachments)) return;
          void chooseScene(session, scene.id, span, false, true).then(target => {
            // Submit exactly the explicitly requested draft once. A user edit
            // during handoff wins and remains unsent in its addressed session.
            if (!signal.aborted && isCurrent(target) && sameDraft(target.input, target.state, target.state.attachmentIds))
              target.input.submit();
          }).catch(error => report(session, error));
        };
        off = input.state.subscribe(check);
        offSession = sessions.list?.subscribe(() => { if (!isCurrent(session)) stop(); }) || (() => {});
        signal.addEventListener('abort', stop, { once: true });
        timer = setTimeout(stop, 30000);
      }
      // The native trigger recomputes candidates after every character and owns
      // keyboard/IME handling, span CAS, atomic chip deletion and undo.
      ctx.effect(() => triggers.registerSource({ trigger: '/', name: 'harless-scenes', order: -10,
        candidates: async (session, req) => {
          watchDraft(session);
          if (req.position !== 'leading') return [];
          const query = req.query.toLowerCase();
          if (!/^[a-z0-9_-]*$/.test(query)) return [];
          const value = cache.get(session.sessionId) || await settings(session, req.signal);
          if (req.signal?.aborted) return [];
          return value.scenes.filter(scene => shortcut(scene).startsWith(query)).map(scene => ({
            name: shortcut(scene), value: scene.id, section: 'Scenes', description: scene.available === false
              ? `暂不可用：${scene.unavailable_reason}` : scene.label,
          }));
        },
        onPick: pick => { void chooseScene(pick.session, pick.candidate.value, pick.span).catch(error => report(pick.session, error)); return 'handled'; },
        matchSpace: (session, token) => {
          const scene = cache.get(session.sessionId)?.scenes.find(row => '/' + shortcut(row) === token.toLowerCase());
          // Hot, synchronous native insertion. Selection is confirmed by the
          // Enter hook, so typing quickly cannot send with a previous scene.
          return scene?.available !== false && scene ? { insert: reference(scene) } : undefined;
        },
        matchEnter: async (session, line, signal) => {
          const token = sceneToken(line);
          if (!token) return;
          const name = token[2].toLowerCase(), hot = cache.get(session.sessionId);
          if (hot && !hot.scenes.some(scene => shortcut(scene) === name)) return;
          const pending = choosing.get(session.sessionId);
          if (pending) await pending.catch(() => {});
          if (!isCurrent(session)) return 'handled';
          const guard = watchSession(session, signal);
          try {
          let value;
          try { value = await settings(session, guard.signal); }
          catch (error) { if (!isCurrent(session)) return 'handled'; throw error; }
          if (!isCurrent(session)) return 'handled';
          const scene = value.scenes.find(row => shortcut(row) === name);
          if (!scene) return;
          if (scene.available === false) throw Error('该场景暂不可用：' + (scene.unavailable_reason || '未部署'));
          if (signal.aborted) throw Error('场景选择已取消，输入已保留');
          if (value.selection.scene === scene.id) return;
          try {
            const selected = await request(session, { action: 'select', session_id: session.sessionId, selection: { scene: scene.id } }, guard.signal);
            if (!isCurrent(session)) return 'handled';
            publish(session.sessionId, selected);
          } catch (error) {
            if (!isCurrent(session)) return 'handled';
            if (error.code !== 'scene_requires_new_session') throw error;
            handOffAfterSubmit(session, scene, leadingSpan(session.sessionId), signal);
            return 'handled';
          }
          } finally { guard.dispose(); }
        },
        lexicon: session => cache.get(session.sessionId)?.scenes.map(shortcut),
        subscribeLexicon: (session, listener) => {
          const group = lexiconObservers.get(session.sessionId) || new Set(); group.add(listener); lexiconObservers.set(session.sessionId, group);
          return () => { group.delete(listener); if (!group.size) lexiconObservers.delete(session.sessionId); };
        },
        warm: session => { watchDraft(session); void settings(session).catch(() => {}); },
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
          if (kind === 'scene') return chooseScene(session, id, leadingSpan(session.sessionId), true);
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
        { name: 'conversation.input.left', id: 'harless-status', order: 40, inject: sessionId => ({ sessionId, openSession: id => sessions.open(id) }) }, HarlessStatus));
    }
    return { inject, apply };
  },
});
