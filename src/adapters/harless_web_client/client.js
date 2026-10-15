/** Scene references use Harness's native trigger, editor chip and session APIs. */
window.__ModuleLoader__.load({
  id: 'deepseek-harless-web-client',
  factory: (require) => {
    const React = require('react');
    const ReactDOM = require('react-dom');
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
      // The server allocates branch suffixes atomically. Native client-side
      // incrementing only sees one source and would rename every branch (1).
      if (typeof sessions.fork === 'function') {
        const originalFork = sessions.fork;
        sessions.fork = function (options) { return originalFork.call(this, { ...options, increaseTitle: false }); };
        ctx.effect(() => () => { sessions.fork = originalFork; }, 'harless: durable branch names');
      }
      const h = React.createElement;
      const busyComparisons = new Map();
      // The journal stores the submission snapshot, not its eventual result.
      // Keep recent authenticated snapshots across chat/trace navigation only;
      // never persist private replies in browser storage.
      const comparisonSnapshots = new Map(), comparisonObservers = new Map();
      const comparisonRatings = new Map(), ratingObservers = new Map();
      let comparisonIdentity = 0;
      const comparisonKey = value => value.session_id + ':' + value.id;
      const olderSnapshot = (next, previous) => previous && (
        Number(next.snapshot_epoch ?? 0) < Number(previous.snapshot_epoch ?? 0)
        || (Number(next.snapshot_epoch ?? 0) === Number(previous.snapshot_epoch ?? 0)
          && (Number(next.snapshot_revision ?? -1) < Number(previous.snapshot_revision ?? -1)
            || (Number(next.snapshot_revision ?? -1) === Number(previous.snapshot_revision ?? -1)
              && Number(next.score_revision ?? -1) < Number(previous.score_revision ?? -1)))));
      const rememberedSnapshot = value => {
        const cached = comparisonSnapshots.get(comparisonKey(value));
        return cached && !olderSnapshot(cached, value) ? cached : value;
      };
      function rememberSnapshot(value) {
        const key = comparisonKey(value);
        if (olderSnapshot(value, comparisonSnapshots.get(key))) return false;
        comparisonSnapshots.delete(key); comparisonSnapshots.set(key, value);
        if (comparisonSnapshots.size > 40) comparisonSnapshots.delete(comparisonSnapshots.keys().next().value);
        for (const listener of comparisonObservers.get(key) || []) listener(value);
        return true;
      }
      const ratingSnapshot = key => {
        const state = comparisonRatings.get(key);
        return { key, pending: Object.fromEntries([...(state?.intents || [])].map(([lane, intent]) => [lane, intent.score])),
          saving: state?.saving || false, error: state?.error || '' };
      };
      function publishRating(key, reconcile = false) {
        const value = ratingSnapshot(key);
        for (const listener of ratingObservers.get(key) || []) listener(value, reconcile);
      }
      function discardComparisonMemory(message = '') {
        comparisonIdentity++;
        for (const [key, state] of comparisonRatings) {
          state.intents.clear(); state.saving = false; state.error = message; state.abort?.abort(); publishRating(key);
        }
        comparisonRatings.clear(); comparisonSnapshots.clear();
      }
      ctx.effect(() => {
        const leavePage = () => discardComparisonMemory();
        window.addEventListener?.('pagehide', leavePage);
        return () => { window.removeEventListener?.('pagehide', leavePage); leavePage(); };
      }, 'harless: account-scoped comparison memory');
      const busyReason = '正在处理当前请求，请等待完成或停止生成。';
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
        const identity = comparisonIdentity;
        return withDeadline(signal, 30000, async requestSignal => {
          const response = await fetch(comparisonUrl(value), { method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', signal: requestSignal,
            ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, session_id: value.session_id, id: value.id }) } : {}) });
          if (identity !== comparisonIdentity) throw apiError(401);
          if ([401, 403].includes(response.status)) {
            const error = apiError(response.status); discardComparisonMemory(error.message); throw error;
          }
          let result;
          try { result = await response.json(); } catch { throw apiError(response.status || 502, '服务器未返回有效结果，请稍后刷新。'); }
          if (identity !== comparisonIdentity) throw apiError(401);
          if (!response.ok || result.error) throw apiError(response.status, result.error?.message);
          if (result.id !== value.id || result.session_id !== value.session_id || !result.lanes?.baseline || (result.presentation !== 'single' && !result.lanes?.motif))
            throw apiError(502, '服务器未返回当前对照结果。');
          return result;
        });
      }
      function saveRating(value, lane, score) {
        const key = comparisonKey(value), authoritative = rememberedSnapshot(value), output = authoritative.lanes[lane]?.output_sha256;
        if (!authoritative.scoring_available || !output) return;
        let state = comparisonRatings.get(key);
        if (!state) {
          state = { confirmed: authoritative, intents: new Map(), saving: false, error: '' }; comparisonRatings.set(key, state);
        }
        if (state.intents.get(lane)?.score === score || (!state.intents.has(lane) && authoritative.scores[lane] === score)) return state.work;
        // The queue belongs to the page, not a mounted card. An explicit last
        // choice keeps saving when the user navigates to another conversation.
        state.intents.set(lane, { score, output }); state.error = ''; state.saving = true; publishRating(key);
        if (state.work) return state.work;
        state.abort = new AbortController();
        const identity = comparisonIdentity, active = () => comparisonRatings.get(key) === state && identity === comparisonIdentity && !state.abort.signal.aborted;
        const work = (async () => {
          try {
            while (active() && state.intents.size) {
              const [name, intent] = state.intents.entries().next().value, latest = rememberedSnapshot(state.confirmed);
              if (!latest.scoring_available || latest.lanes[name]?.output_sha256 !== intent.output) {
                state.intents.clear(); state.error = '结果已更新，请确认新结果后重新评分。'; break;
              }
              if (latest.scores[name] === intent.score) { state.intents.delete(name); publishRating(key); continue; }
              try {
                const next = await comparisonRequest(latest, { action: 'rate', lane: name, score: intent.score,
                  revision: latest.score_revision, output_sha256: intent.output }, state.abort.signal);
                if (!active()) return;
                state.confirmed = next; rememberSnapshot(next);
              } catch (error) {
                if (!active()) return;
                state.error = networkMessage(error) + (!error.status || error.status === 408 ? ' 将重新读取状态，请勿重复提交。' : '');
                // A lost response may already have committed. Read before
                // sending a newer choice; never replay the uncertain POST.
                try {
                  if ([401, 403, 404].includes(error.status)) throw error;
                  const next = await comparisonRequest(latest, undefined, state.abort.signal);
                  if (!active()) return;
                  state.confirmed = next; rememberSnapshot(next);
                } catch {
                  if (!active()) return;
                  state.intents.clear(); break;
                }
              }
              if (state.intents.get(name) === intent) state.intents.delete(name);
              publishRating(key);
            }
          } finally {
            if (active()) {
              state.work = null; state.saving = false; publishRating(key, true);
              if (!state.error) comparisonRatings.delete(key);
              // Keep failed-save notices bounded just like confirmed replies.
              if (comparisonRatings.size > 40) for (const [oldKey, oldState] of comparisonRatings) {
                if (!oldState.saving) comparisonRatings.delete(oldKey);
                if (comparisonRatings.size <= 40) break;
              }
            }
          }
        })();
        state.work = work; return work;
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
      function compactArtifactLabels(root, files) {
        if (!root) return;
        // Native Markdown uses resolve().label only for aria-label and keeps
        // the raw inline-code path as visible button text. Adapt that rendered
        // label, not the Markdown source or the authenticated download target.
        for (const link of root.querySelectorAll('code > button, a')) {
          if (link.closest('pre')) continue;
          const textNodes = [];
          const visit = node => {
            if (node.nodeType === 3) { if (node.nodeValue?.trim()) textNodes.push(node); return; }
            if (node.nodeName?.toLowerCase() === 'svg') return;
            for (const child of node.childNodes || []) visit(child);
          };
          visit(link);
          // Keep custom / formatted link captions intact. The native file
          // button and a plain Markdown path label each have one text node.
          if (textNodes.length !== 1) continue;
          const label = textNodes[0].nodeValue.trim();
          if (!/[\\/]/.test(label) || /^(?:https?:|mailto:|#)/i.test(label)) continue;
          if (!/^(?:[./\\]|[a-z]:[\\/]|sandbox:|file:\/\/|[^\s/\\:]+[\\/])/i.test(label)) continue;
          const file = artifactFor(files, label);
          if (!file) continue;
          const isButton = link.nodeName.toLowerCase() === 'button';
          const target = link.getAttribute(isButton ? 'title' : 'href') || '';
          if (!isButton && /^(?:https?:|mailto:|#)/i.test(target)) continue;
          const name = file.name.split(/[\\/]/).pop();
          // A later native render may update its text node but retain the
          // already-compacted title. Exact label matching still owns the file.
          if (artifactFor(files, target)?.id !== file.id && !(isButton && target === name)) continue;
          textNodes[0].nodeValue = name;
          link.setAttribute('title', name);
        }
      }
      // Public primitives are shared with native Chat; do not duplicate SVGs or
      // depend on private Chat components / generated CSS class names.
      const messageIcon = kind => h(primitives[({ copy: 'IconCopyOutline16', check: 'IconCheckOutline16',
        up: 'IconLikeOutline16', upSelected: 'IconLikeFill16', down: 'IconDislikeOutline16', downSelected: 'IconDislikeFill16',
        fork: 'IconBranchOutline16', usage: 'IconDatabaseOutline16', clock: 'IconClockOutline16' })[kind]], { 'aria-hidden': true });
      const actionButton = (props, icon, label) => h(primitives.Tooltip, { label, side: 'bottom', key: props.key },
        h('button', { type: 'button', className: 'harless-message-icon', ...props }, messageIcon(icon)));
      const durationLabel = milliseconds => {
        if (!Number.isFinite(milliseconds)) return '待统计';
        const seconds = Math.max(0, Math.floor(milliseconds / 1000));
        return seconds < 60 ? seconds + '秒' : Math.floor(seconds / 60) + '分' + String(seconds % 60).padStart(2, '0') + '秒';
      };
      const tokenLabel = total => {
        if (!Number.isFinite(total)) return '待统计';
        const scaled = value => String(value >= 100 ? Math.round(value) : Math.round(value * 10) / 10);
        return (total < 1000 ? total : total < 1000000 ? scaled(total / 1000) + 'K' : scaled(total / 1000000) + 'M') + ' tok';
      };
      const usageFacts = result => {
        const stats = result.stats || {}, usage = result.usage || stats.usage || {};
        const input = usage.input ?? usage.prompt_tokens ?? stats.prompt_tokens ?? stats.input_tokens;
        const output = usage.output ?? usage.completion_tokens ?? stats.completion_tokens ?? stats.output_tokens;
        const total = usage.total ?? usage.total_tokens ?? stats.total_tokens ?? (Number.isFinite(input) && Number.isFinite(output) ? input + output : undefined);
        return { input, output, total };
      };
      const messageClock = time => {
        const date = new Date(time), now = new Date();
        if (!Number.isFinite(date.getTime())) return '';
        const clock = String(date.getHours()).padStart(2, '0') + ':' + String(date.getMinutes()).padStart(2, '0');
        if (date.toDateString() === now.toDateString()) return clock;
        return (date.getFullYear() === now.getFullYear() ? '' : date.getFullYear() + '年') + (date.getMonth() + 1) + '月' + date.getDate() + '日 ' + clock;
      };
      function ReplyMetric({ kind, label, rows, title }) {
        const [open, setOpen] = React.useState(false), rootRef = React.useRef(null), panelRef = React.useRef(null);
        const pos = primitives.useAnchoredPosition({ open, anchorRef: rootRef, panelRef, side: 'top', gap: 8, margin: 12 });
        primitives.useDismissOnOutsidePointer(rootRef, open, setOpen, panelRef);
        React.useEffect(() => {
          if (!open) return;
          const close = event => { if (event.key === 'Escape') { setOpen(false); rootRef.current?.querySelector('button')?.focus(); } };
          document.addEventListener('keydown', close);
          return () => document.removeEventListener('keydown', close);
        }, [open]);
        return h('span', { className: 'harless-message-metric', ref: rootRef, 'data-open': open || undefined },
          h('button', { type: 'button', className: 'harless-message-metric-trigger', 'aria-label': label,
            'aria-haspopup': 'dialog', 'aria-expanded': open, onClick: () => setOpen(!open) }, messageIcon(kind), h('span', { className: 'harless-message-metric-label' }, label)),
          open && ReactDOM.createPortal(h('div', { ref: panelRef, role: 'dialog', 'aria-label': title, className: 'harless-message-stat-panel',
            style: pos || { visibility: 'hidden', left: 0, top: 0 } }, h('strong', null, title),
            h('dl', null, ...rows.flatMap(([name, value]) => [h('dt', { key: name }, name), h('dd', { key: name + '-value' }, value)]))), document.body));
      }
      function TraceRows({ items }) {
        const states = { running: '进行中', completed: '完成', failed: '失败', interrupted: '已中断', cancelled: '已取消', skipped: '已跳过' };
        return h('ol', { className: 'harless-trace-list' }, ...items.map((entry, index) => {
          const skip = entry.verified_skip === true, optimized = entry.optimized === true;
          const label = skip ? '已验证跳过模型请求' : optimized ? '已应用优化' : undefined;
          const detail = entry.text || entry.details;
          return h('li', { key: entry.id || index, 'data-kind': entry.kind, 'data-optimized': skip || optimized ? 'true' : undefined },
            h('div', { className: 'harless-trace-event' }, h('span', { className: 'harless-trace-dot', 'aria-hidden': true }),
              h('strong', null, entry.label || ({ assistant: '回复', thinking: '正在思考', tool: '工具调用', motif: 'Motif 核验', request: '模型请求' })[entry.kind] || '执行记录'),
              entry.status && h('small', null, states[entry.status] || entry.status),
              entry.time && h('time', { dateTime: entry.time }, new Date(entry.time).toLocaleTimeString('zh-CN', { hour12: false }))),
            label && h('span', { className: 'harless-trace-optimization' }, label),
            entry.tool && h('small', { className: 'harless-trace-tool' }, entry.tool),
            detail && h('details', null, h('summary', null, '查看详情'), h('pre', null, typeof detail === 'string' ? detail : JSON.stringify(detail, null, 2))));
        }));
      }
      function ComparisonNode({ node, traceOnly = false, useChat }) {
        // Observe the whole timeline, including later ordinary Chat turns.
        const latestTurn = useChat?.(snapshot => snapshot.timeline?.turnOrder.at(-1));
        const turn = node.location?.turn?.turn;
        const isLatestTurn = latestTurn === undefined || turn === undefined || latestTurn === turn;
        const key = comparisonKey(node.data), initial = rememberedSnapshot(node.data);
        const [snapshot, setValue] = React.useState(initial), [error, setError] = React.useState(''), [saving, setSaving] = React.useState(false);
        const value = comparisonKey(snapshot) === key ? snapshot : initial;
        const [loadedKey, setLoadedKey] = React.useState(comparisonSnapshots.has(key) || settled(initial) ? key : '');
        const hydrated = loadedKey === key || comparisonSnapshots.has(key) || settled(initial);
        const serverSnapshot = React.useRef(initial);
        const [ratingState, setRatingState] = React.useState(ratingSnapshot(key));
        const ratings = ratingState.key === key ? ratingState : ratingSnapshot(key), pendingRatings = ratings.pending;
        const [connection, setConnection] = React.useState(''), [downloads, setDownloads] = React.useState({});
        const pageLoadRelease = React.useRef();
        React.useLayoutEffect(() => {
          const release = window.__geneLoopPageLoad?.hold(node.data.session_id);
          pageLoadRelease.current = release;
          if (hydrated || error || connection) release?.();
          return () => { release?.(); if (pageLoadRelease.current === release) pageLoadRelease.current = undefined; };
        }, [node.data.id, node.data.session_id]);
        React.useLayoutEffect(() => {
          if (hydrated || error || connection) pageLoadRelease.current?.();
        }, [hydrated, error, connection]);
        const [branching, setBranching] = React.useState(''), branchBusy = React.useRef(false);
        const [copied, setCopied] = React.useState(''), [traceLane, setTraceLane] = React.useState('baseline');
        const copyTimer = React.useRef(), copyPending = React.useRef(false);
        const generation = React.useRef(0), actionBusy = React.useRef(false), downloadBusy = React.useRef(new Set());
        const alive = React.useRef(true), transferControllers = React.useRef(new Set()), refreshNow = React.useRef(() => {});
        const streamConnected = React.useRef(false);
        const streamBlocked = React.useRef(false);
        const closeLiveStream = React.useRef(() => {});
        const acceptSnapshot = next => {
          if (olderSnapshot(next, serverSnapshot.current) || !rememberSnapshot(next)) return false;
          serverSnapshot.current = next; setValue(next); setLoadedKey(comparisonKey(next)); return true;
        };
        React.useEffect(() => {
          alive.current = true; streamBlocked.current = false; setDownloads({}); setError(''); setConnection(''); setSaving(false);
          setCopied(''); setBranching(''); branchBusy.current = false; setTraceLane('baseline');
          serverSnapshot.current = initial;
          actionBusy.current = false; downloadBusy.current.clear(); generation.current++;
          return () => { alive.current = false; clearTimeout(copyTimer.current); for (const abort of transferControllers.current) abort.abort(); };
        }, [node.data.id, node.data.session_id]);
        // Persisted start-event data may be reassembled with a fresh object while
        // GET already holds newer results. Reset only when viewing another turn.
        React.useEffect(() => { setValue(initial); setLoadedKey(comparisonSnapshots.has(key) || settled(initial) ? key : ''); }, [node.data.id, node.data.session_id]);
        React.useEffect(() => {
          // Chat and trajectory can both render the same turn. A result saved
          // by either view must also update the other without a stale flash.
          const listener = next => {
            if (!alive.current || olderSnapshot(next, serverSnapshot.current)) return;
            serverSnapshot.current = next; setValue(next); setLoadedKey(key);
          };
          const group = comparisonObservers.get(key) || new Set(); group.add(listener); comparisonObservers.set(key, group);
          return () => { group.delete(listener); if (!group.size) comparisonObservers.delete(key); };
        }, [node.data.id, node.data.session_id]);
        React.useEffect(() => {
          let wasSaving = ratingSnapshot(key).saving;
          const listener = (next, reconcile) => {
            setRatingState(next);
            if (wasSaving && !next.saving && reconcile) void refreshNow.current();
            wasSaving = next.saving;
          };
          setRatingState(ratingSnapshot(key));
          const group = ratingObservers.get(key) || new Set(); group.add(listener); ratingObservers.set(key, group);
          return () => { group.delete(listener); if (!group.size) ratingObservers.delete(key); };
        }, [node.data.id, node.data.session_id]);
        React.useEffect(() => {
          const abort = new AbortController(); let timer, failures = 0, pending = false, rerun = false;
          const poll = async () => {
            if (abort.signal.aborted) return;
            if (pending) { rerun = true; return; }
            clearTimeout(timer); pending = true; let delay = 0;
            const revision = generation.current;
            try {
              const next = await comparisonRequest(node.data, undefined, abort.signal);
              let applied = false;
              if (!abort.signal.aborted && revision === generation.current && !actionBusy.current) {
                applied = acceptSnapshot(next); setConnection(''); failures = 0;
              }
              // An open HTTP connection does not prove that its proxy forwards
              // snapshots. Keep a low-frequency, read-only recovery path even
              // after the stream has delivered data; never replay a submission.
              if (!applied || !settled(next) || actionBusy.current)
                delay = document.hidden ? 8000 : streamConnected.current ? 5000 : 1800;
            } catch (e) {
              if (!abort.signal.aborted) {
                failures++;
                const denied = [401, 403, 404].includes(e.status);
                if (denied) { streamBlocked.current = true; closeLiveStream.current(); }
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
          if (settled(value) || !window.EventSource) return;
          const identity = comparisonIdentity;
          let stream, retryTimer, stallTimer, disposed = false, failures = 0;
          const stopStream = () => { clearTimeout(stallTimer); stream?.close(); streamConnected.current = false; };
          const close = () => { disposed = true; clearTimeout(retryTimer); stopStream(); };
          closeLiveStream.current = close;
          const connect = () => {
            if (disposed || streamBlocked.current || identity !== comparisonIdentity) return;
            const current = new window.EventSource(comparisonUrl(node.data) + '&stream=1', { withCredentials: true });
            stream = current;
            const alive = () => !disposed && stream === current && !streamBlocked.current && identity === comparisonIdentity;
            const watch = () => { clearTimeout(stallTimer); stallTimer = setTimeout(() => { if (alive()) current.onerror(); }, 10000); };
            // Only an authenticated snapshot establishes stream liveness.
            current.onopen = () => { if (alive()) watch(); };
            current.onmessage = event => {
              if (!alive() || actionBusy.current) return;
              try {
                const next = JSON.parse(event.data);
                if (next.id !== node.data.id || next.session_id !== node.data.session_id || !next.lanes?.baseline
                  || (next.presentation !== 'single' && !next.lanes?.motif)) throw Error('Invalid stream result');
                if (!acceptSnapshot(next)) return;
                streamConnected.current = true; failures = 0; watch();
                generation.current++; setConnection('');
                if (settled(next)) close();
              } catch { current.onerror(); }
            };
            current.addEventListener('snapshot', current.onmessage);
            current.onerror = () => {
              if (!alive()) return;
              stopStream(); stream = undefined;
              // A stream reconnect is read-only. Never replay a paid request.
              void refreshNow.current();
              retryTimer = setTimeout(connect, Math.min(30000, 2000 * 2 ** Math.min(failures++, 4)));
            };
            watch();
          };
          connect();
          return () => { close(); if (closeLiveStream.current === close) closeLiveStream.current = () => {}; };
        }, [node.data.id, node.data.session_id, settled(value)]);
        React.useEffect(() => {
          if (!hydrated || settled(value)) return;
          updateBusy(value.session_id, value.id, true);
          return () => updateBusy(value.session_id, value.id, false);
        }, [value.session_id, value.id, value.status, hydrated]);
        const action = async body => {
          if (actionBusy.current || comparisonRatings.get(key)?.saving) return;
          actionBusy.current = true; generation.current++; setSaving(true); setError('');
          const revision = generation.current, abort = new AbortController(); transferControllers.current.add(abort);
          const current = () => alive.current && generation.current === revision && !abort.signal.aborted;
          try { const next = await comparisonRequest(value, body, abort.signal); if (current()) { acceptSnapshot(next); setConnection(''); } }
          catch (e) { if (current()) setError(networkMessage(e) + (!e.status || e.status === 408 ? ' 将重新读取状态，请勿重复提交。' : '')); }
          finally {
            transferControllers.current.delete(abort);
            if (alive.current && generation.current === revision) { actionBusy.current = false; setSaving(false); void refreshNow.current(); }
          }
        };
        const rate = (lane, score) => {
          if (actionBusy.current) return;
          setError(''); return saveRating(serverSnapshot.current, lane, score);
        };
        const fork = async lane => {
          const output = value.lanes[lane].output_sha256;
          if (branchBusy.current || !output || !settled(value)) return;
          branchBusy.current = true; setBranching(lane); setError('');
          const abort = new AbortController(); transferControllers.current.add(abort);
          try {
            const result = await withDeadline(abort.signal, 30000, async signal => {
              const response = await fetch(comparisonUrl(value), { method: 'POST', credentials: 'same-origin', cache: 'no-store', signal,
                headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: value.session_id, id: value.id,
                  action: 'fork', lane, output_sha256: output }) });
              let body; try { body = await response.json(); } catch { throw apiError(502); }
              if (!response.ok || body.error) throw apiError(response.status, body.error?.message);
              if (typeof body.sessionId !== 'string' || !body.sessionId) throw apiError(502, '服务器未返回分支会话。');
              return body;
            });
            if (alive.current && !abort.signal.aborted) sessions.open(result.sessionId);
          } catch (error) { if (alive.current && !abort.signal.aborted) setError(networkMessage(error)); }
          finally { transferControllers.current.delete(abort); branchBusy.current = false; if (alive.current) setBranching(''); }
        };
        const copy = async lane => {
          const result = value.lanes[lane], text = (result.answer_display ?? result.answer) || result.messages?.at(-1)?.text;
          if (!text || copyPending.current || copied === lane) return;
          const revision = generation.current; copyPending.current = true;
          try {
            if (primitives.writeClipboard) { if (!await primitives.writeClipboard(text)) throw Error('clipboard unavailable'); }
            else { if (!window.navigator?.clipboard?.writeText) throw Error('clipboard unavailable'); await window.navigator.clipboard.writeText(text); }
            if (alive.current && generation.current === revision) {
              clearTimeout(copyTimer.current); setCopied(lane); setError('');
              copyTimer.current = setTimeout(() => { if (alive.current) setCopied(''); }, 1000);
            }
          } catch { if (alive.current && generation.current === revision) setError('未能复制，请选中回复文字后复制。'); }
          finally { copyPending.current = false; }
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
        if (!hydrated) return h('div', { className: 'harless-paired-loading', 'data-comparison-id': value.id, 'aria-busy': true },
          h('style', null, '.harless-paired-loading{width:100%;margin:18px 0}.harless-paired-loading-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.harless-paired-loading section{border:1px solid #8885;border-radius:16px;padding:18px;min-width:0}.harless-paired-loading p{font-size:13px;color:var(--dsw-alias-label-secondary,inherit);line-height:1.6}@media(max-width:650px){.harless-paired-loading-grid{grid-template-columns:1fr}}'),
          traceOnly ? h('p', { role: 'status' }, '正在加载此轮轨迹…') : h('div', { className: 'harless-paired-loading-grid' },
            ...(value.presentation === 'single' ? ['baseline'] : ['baseline', 'motif']).map(lane => h('section', { key: lane },
              h('strong', null, value.presentation === 'single' ? '回复' : lane === 'baseline' ? 'Baseline' : 'Motif'),
              h('p', { role: 'status' }, '正在加载此轮结果…')))),
          connection && h('div', { role: 'status', className: 'harless-paired-connection' }, connection,
            h('button', { type: 'button', onClick: () => refreshNow.current() }, '重新连接'),
            connection.includes('登录') && h('a', { href: '/login', style: { marginLeft: 8 } }, '登录')));
        const pane = lane => {
          const result = value.lanes[lane], files = result.artifacts || [], title = lane === 'baseline' ? 'Baseline' : result.mode === 'shadow' ? 'Motif · 影子评估' : 'Motif';
          const single = value.presentation === 'single';
          const notStarted = result.delivery_status === 'not_started';
          const activity = Array.isArray(result.activity) ? result.activity : [];
          const messages = Array.isArray(result.messages) ? result.messages.filter(message => message.text) : [];
          const answer = (result.answer_display ?? result.answer) || messages.at(-1)?.text || '';
          // The latest message occupies the answer seat. On completion its
          // bound answer_display may differ from raw template text; do not show
          // the unbound last message a second time in the process section.
          const previousMessages = messages.slice(0, -1);
          const progressLabel = result.progress?.label || (!settled(result) ? labels[result.status] : '查看执行过程');
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
          const usage = usageFacts(result), duration = result.duration_ms ?? (Number.isFinite(result.stats?.elapsed_seconds) ? result.stats.elapsed_seconds * 1000 : undefined);
          const count = value => Number.isFinite(value) ? value.toLocaleString('en-US') + ' tok' : '待统计';
          return h('section', { key: lane, className: 'harless-paired-pane' + (single ? ' harless-single-pane' : ''), 'aria-label': single ? '回复' : title,
            'data-actions-reveal': isLatestTurn ? 'always' : 'hover' },
            !single && h('header', null, h('strong', null, title), h('span', { role: 'status' }, notStarted ? '任务未启动' : result.status === 'completed' && result.delivery_status === 'available' ? '已交付' : labels[result.status] || result.status)),
            !settled(result) && h('p', { className: 'harless-live-status', role: 'status', 'aria-live': 'polite' }, h('span', { className: 'harless-live-dot', 'aria-hidden': true }), progressLabel),
            (activity.length > 0 || previousMessages.length > 0) && h('details', { className: 'harless-activity' },
              h('summary', null, '查看执行过程'),
              activity.length > 0 && h('ol', null, ...activity.map((entry, index) => h('li', { key: index, 'data-status': entry.status },
                h('span', null, entry.label), h('small', null, ({ running: '进行中', completed: '完成', failed: '未完成' })[entry.status] || '')))),
              ...(!settled(result) ? [] : previousMessages).map(message => h('section', { key: message.id, className: 'harless-process-message',
                onClickCapture: captureLink, ref: root => compactArtifactLabels(root, files) },
                MarkdownText ? h(MarkdownText, { text: message.text, streaming: message.status === 'streaming', labels: markdownLabels, fileMentions: mentions }) : h('p', null, message.text)))),
            result.fallback_reason && h('p', { className: 'harless-paired-notice' }, '优化未启用，已回退普通模式：' + result.fallback_reason),
            result.failure && h('p', { role: 'alert', className: 'harless-paired-notice' }, result.failure),
            !settled(result) && previousMessages.length > 0 && h('div', { className: 'harless-stream-messages', onClickCapture: captureLink,
              ref: root => compactArtifactLabels(root, files) }, ...previousMessages.map(message => h('section', {
                key: message.id, className: 'harless-process-message', 'data-message-id': message.id,
              }, MarkdownText ? h(MarkdownText, { text: message.text, streaming: message.status === 'streaming', labels: markdownLabels, fileMentions: mentions }) : h('p', null, message.text)))),
            h('div', { className: 'harless-paired-answer', ref: root => compactArtifactLabels(root, files), onClickCapture: captureLink }, answer
              ? MarkdownText ? h(MarkdownText, { text: answer, streaming: !settled(result), labels: markdownLabels, fileMentions: mentions })
                : h('p', { style: { whiteSpace: 'pre-wrap' } }, answer)
              : h('p', { className: 'harless-paired-muted' }, notStarted ? '任务未启动，暂无回复。' : result.status === 'queued' ? '等待当前任务结束后开始。' : !settled(result) ? '正在处理，结果会自动更新…' : '本轮未生成文字回复。')),
            files.length > 0 && h('section', { className: 'harless-paired-deliveries', 'aria-label': title + '交付文件' },
              h('h4', null, '交付文件'), h('ul', { className: 'harless-paired-files' }, ...files.map(file => {
                const status = downloads[lane + ':' + file.id];
                return h('li', { key: file.id }, h('a', { href: comparisonUrl(value, lane, file), download: file.name.split('/').pop(), rel: 'nofollow',
                  'aria-disabled': status?.phase === 'pending', onClick: event => { event.preventDefault(); void download(lane, file); } },
                  h('span', { className: 'harless-paired-filename', title: file.name }, file.name.split('/').pop()),
                  h('span', { className: 'harless-paired-download-label' }, status?.phase === 'pending' ? '准备中…' : '下载')),
                  status && h('small', { role: status.phase === 'error' ? 'alert' : 'status', className: status.phase === 'error' ? 'harless-paired-error' : 'harless-paired-muted' }, status.message));
              }))),
            !single && result.delivery_message && h('p', { className: 'harless-paired-notice', role: 'status' }, result.delivery_message),
            h('footer', null,
              h('div', { className: 'harless-message-actions', 'aria-label': title + '回复操作' },
                actionButton({ 'aria-label': '复制 ' + title + ' 回复', disabled: !answer, onClick: () => copy(lane) }, copied === lane ? 'check' : 'copy', copied === lane ? '已复制' : '复制'),
                ...['up', 'down'].map(vote => actionButton({ key: vote,
                  'aria-label': (vote === 'up' ? '赞 ' : '踩 ') + title + ' 回复', 'aria-pressed': result.feedback === vote,
                  disabled: saving || ratings.saving || !settled(result) || !result.output_sha256,
                  onClick: () => action({ action: 'feedback', lane, vote: result.feedback === vote ? null : vote, output_sha256: result.output_sha256 }) },
                  vote + (result.feedback === vote ? 'Selected' : ''), result.feedback === vote ? '取消标记' : vote === 'up' ? '好的回答' : '有问题的回答')),
                actionButton({ 'aria-label': '从 ' + title + ' 在新对话中分支', disabled: !!branching || !settled(value) || !result.output_sha256,
                  onClick: () => fork(lane) }, 'fork', branching === lane ? '正在创建分支…' : '在新对话中分支'),
                h('span', { className: 'harless-message-metrics' },
                Number.isFinite(usage.total) && h(ReplyMetric, { kind: 'usage', label: '用量 ' + tokenLabel(usage.total), title: title + ' · 本轮用量',
                  rows: [['总用量', count(usage.total)], ['输入', count(usage.input)], ['输出', count(usage.output)]] }),
                Number.isFinite(duration) && h(ReplyMetric, { kind: 'clock', label: '用时 ' + durationLabel(duration), title: title + ' · 本轮用时',
                  rows: [['本轮总用时', durationLabel(duration)], ...(result.started_at ? [['开始时间', messageClock(result.started_at)]] : []),
                    ...(result.finished_at ? [['完成时间', messageClock(result.finished_at)]] : [])] }),
                result.finished_at && messageClock(result.finished_at) && h('time', { className: 'harless-message-time', dateTime: result.finished_at }, messageClock(result.finished_at))),
                copied === lane && h('span', { role: 'status', className: 'harless-visually-hidden' }, '已复制')),
              h('small', null, `模型请求 ${result.stats?.upstream_requests || 0} · ${result.mode === 'shadow' ? '预测候选 ' + (result.stats?.shadow_candidates || 0) : '已验证跳过 ' + (result.stats?.verified_skips || 0)}`),
              ['failed', 'cancelled'].includes(result.status) && settled(value) && h('button', { type: 'button', disabled: saving || ratings.saving, onClick: () => action({ action: 'retry', lane }) }, '重试此侧'),
              !single && h('fieldset', { disabled: !value.scoring_available || saving, 'aria-label': title + '评分', 'aria-busy': pendingRatings[lane] !== undefined },
                h('legend', null, value.scoring_available ? '结果评分' : '两侧完成后评分'),
                ...[1, 2, 3, 4, 5].map(score => h('label', { key: score, className: (pendingRatings[lane] ?? value.scores[lane]) === score ? 'selected' : '' }, h('input', {
                  type: 'radio', name: value.id + '-' + lane, value: score, checked: (pendingRatings[lane] ?? value.scores[lane]) === score,
                  onChange: () => rate(lane, score) }), score))),
              !single && pendingRatings[lane] !== undefined && h('small', { role: 'status', className: 'harless-paired-muted' }, '正在保存评分…')));
        };
        if (traceOnly) {
          const lane = value.lanes[traceLane] ? traceLane : 'baseline', result = value.lanes[lane];
          const laneKeys = Object.keys(value.lanes).filter(key => key === 'baseline' || key === 'motif');
          return h('section', { className: 'harless-comparison-trace', 'data-comparison-id': value.id },
            h('div', { className: 'harless-trace-tabs', role: 'tablist', 'aria-label': '对照执行轨迹', onKeyDown: event => {
              if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
              event.preventDefault();
              const index = event.key === 'Home' ? 0 : event.key === 'End' ? laneKeys.length - 1
                : (laneKeys.indexOf(lane) + (event.key === 'ArrowRight' ? 1 : -1) + laneKeys.length) % laneKeys.length;
              const next = laneKeys[index]; setTraceLane(next); document.getElementById?.(value.id + '-trace-' + next)?.focus();
            } },
              ...laneKeys.map(key => h('button', {
                key, type: 'button', role: 'tab', id: value.id + '-trace-' + key, 'aria-controls': value.id + '-trace-panel',
                'aria-selected': lane === key, tabIndex: lane === key ? 0 : -1, onClick: () => setTraceLane(key),
              }, key === 'baseline' ? 'Baseline' : value.lanes[key].mode === 'shadow' ? 'Motif · 影子评估' : 'Motif'))),
            h('div', { role: 'tabpanel', id: value.id + '-trace-panel', 'aria-labelledby': value.id + '-trace-' + lane, tabIndex: 0 },
              h('p', { role: 'status', 'aria-live': 'polite', className: 'harless-live-status' }, result.progress?.label || labels[result.status]),
              result.trace?.length ? h(TraceRows, { items: result.trace }) : h('p', { className: 'harless-paired-muted' },
                settled(result) ? '此轮没有可用的执行事件。' : '等待实际执行事件…')),
            connection && h('p', { role: 'status', className: 'harless-paired-connection' }, connection));
        }
        return h('div', { className: 'harless-paired', 'data-comparison-id': value.id },
          h('style', null, `.harless-paired{width:100%;min-width:0;container-type:inline-size;margin:18px 0;color:var(--dsw-alias-label-primary,inherit);font-family:var(--dsw-font-family,inherit);font-size:var(--dsh-content-font-size,14px)}.harless-paired-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}.harless-paired-pane{min-width:0;container-type:inline-size;border:1px solid var(--dsw-alias-outline-default,#8885);border-radius:16px;padding:18px;background:var(--dsw-alias-fill-tertiary,transparent)}.harless-paired-pane>header{display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid #8883;padding-bottom:12px}.harless-paired-pane>header>span,.harless-paired-pane small{font-size:12px;line-height:1.5;color:var(--dsw-alias-label-secondary,inherit)}.harless-paired-pane>header>strong{font-size:15px}.harless-paired-answer{overflow-wrap:anywhere;line-height:1.65;margin:18px 0;min-width:0}.harless-paired-answer pre{max-width:100%;overflow-x:auto}.harless-paired-answer table{font-size:inherit}.harless-paired-notice{font-size:13px;line-height:1.6;border-left:3px solid #b99555;padding-left:10px}.harless-paired-pane>footer{display:grid;gap:12px;margin-top:20px;padding-top:14px;border-top:1px solid #8883}.harless-paired-pane fieldset{display:flex;flex-wrap:wrap;gap:6px;border:0;padding:0;min-width:0}.harless-paired-pane legend{font-size:12px;color:var(--dsw-alias-label-secondary,inherit);margin-bottom:8px}.harless-paired-pane fieldset label{display:flex;align-items:center;justify-content:center;gap:4px;border:1px solid #8885;border-radius:8px;padding:6px 8px;min-height:32px;cursor:pointer}.harless-paired-pane label.selected{color:var(--dsw-alias-link,#729cf7);border-color:currentColor;background:#729cf719}.harless-paired button{border:1px solid #8885;border-radius:8px;padding:7px 12px;background:transparent;color:inherit;cursor:pointer;font:inherit}.harless-paired button:disabled{opacity:.5}.harless-paired-pane fieldset:disabled{opacity:.45}.harless-paired-error{font-size:13px;line-height:1.6;color:var(--dsw-alias-state-error-primary,#d66)!important;margin-top:10px}.harless-paired-connection{font-size:13px;line-height:1.6;margin:12px 0;color:var(--dsw-alias-label-secondary,inherit)}.harless-paired-connection button{margin-left:8px}.harless-paired-deliveries h4{font-size:13px;margin:0 0 8px}.harless-paired-files{list-style:none;padding:0;display:grid;gap:8px}.harless-paired-files li{min-width:0}.harless-paired-files a{display:flex;align-items:center;gap:12px;justify-content:space-between;padding:10px 12px;border:1px solid #8884;border-radius:10px;color:var(--dsw-alias-link,#729cf7);text-decoration:none}.harless-paired-files a:hover{background:#8881}.harless-paired-filename{min-width:0;overflow-wrap:anywhere}.harless-paired-download-label{flex-shrink:0;font-size:12px}.harless-paired-muted{color:var(--dsw-alias-label-secondary,inherit);font-size:13px}.harless-paired-files small{display:block;margin-top:5px}@container(max-width:650px){.harless-paired-grid{grid-template-columns:1fr}.harless-paired-pane{padding:16px}}`),
          h('style', null, `.harless-single-pane{border:0;border-radius:0;padding:0;background:transparent}.harless-activity{font-size:13px;line-height:1.6;color:var(--dsw-alias-label-secondary,inherit);margin:12px 0}.harless-activity summary{cursor:pointer}.harless-activity ol{padding-left:20px;margin:8px 0}.harless-activity li{padding:4px 0}.harless-activity li small{margin-left:12px}.harless-activity li[data-status=running]{color:var(--dsw-alias-state-business-primary,#729cf7)}`),
          h('style', null, `.harless-message-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px;min-height:calc(28px + var(--dsh-content-font-delta,0px));margin-left:-6px;color:var(--dsw-alias-label-tertiary)}
.harless-paired .harless-message-icon{display:inline-flex;align-items:center;justify-content:center;width:calc(28px + var(--dsh-content-font-delta,0px));height:calc(28px + var(--dsh-content-font-delta,0px));padding:6px;border:0;border-radius:28px;flex:none;color:var(--dsw-alias-label-tertiary)}
.harless-message-actions svg{width:calc(15px + var(--dsh-content-font-delta,0px));height:calc(15px + var(--dsh-content-font-delta,0px));flex:none}
.harless-paired .harless-message-icon:hover,.harless-paired .harless-message-metric-trigger:hover{background:var(--dsw-alias-interactive-bg-hover);color:var(--dsw-alias-label-secondary)}
.harless-paired .harless-message-icon:disabled{cursor:default;opacity:.4;background:transparent}
.harless-message-icon:focus-visible,.harless-message-metric-trigger:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary,#729cf7);outline-offset:2px}
.harless-message-metrics{display:inline-flex;align-items:center;flex-wrap:wrap;gap:8px;max-width:100%}.harless-message-metric{display:inline-flex;min-width:0}.harless-message-metric+.harless-message-metric{margin-left:-6px}
.harless-paired .harless-message-metric-trigger{display:inline-flex;align-items:center;gap:4px;min-width:0;height:calc(28px + var(--dsh-content-font-delta,0px));padding:6px 8px;border:0;border-radius:28px;color:var(--dsw-alias-label-tertiary);font-size:var(--dsh-content-font-size-secondary,13px);font-variant-numeric:tabular-nums;line-height:calc(24px + var(--dsh-content-font-delta,0px));white-space:nowrap}
.harless-message-metric-label{min-width:0;overflow:hidden;text-overflow:ellipsis}.harless-message-time{font-size:var(--dsh-content-font-size-secondary,13px);line-height:calc(24px + var(--dsh-content-font-delta,0px));color:var(--dsw-alias-label-tertiary);white-space:nowrap}
.harless-visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
@media(hover:hover){.harless-paired-pane[data-actions-reveal=hover] .harless-message-actions{opacity:0;transition:opacity 80ms}.harless-paired-pane[data-actions-reveal=hover]:hover .harless-message-actions,.harless-paired-pane[data-actions-reveal=hover]:focus-within .harless-message-actions,.harless-paired-pane[data-actions-reveal=hover]:has(.harless-message-metric[data-open]) .harless-message-actions{opacity:1}}
@media(prefers-reduced-motion:reduce){.harless-paired-pane[data-actions-reveal=hover] .harless-message-actions{transition:none}}
@media(max-width:480px){.harless-message-metric-label{display:none}}
.harless-message-stat-panel{position:fixed;z-index:1100;box-sizing:border-box;width:280px;max-width:calc(100vw - 24px);max-height:calc(100dvh - 24px);overflow:auto;border:1px solid var(--dsw-alias-outline-default,#8885);border-radius:12px;padding:16px;background:var(--dsw-specific-menu,#262626);color:var(--dsw-alias-label-primary);font-family:inherit;font-size:13px;line-height:1.5;box-shadow:0 8px 32px #0003}
.harless-message-stat-panel>strong{display:block;padding-bottom:12px;border-bottom:1px solid var(--dsw-alias-outline-default,#8885);font-weight:500}.harless-message-stat-panel dl{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 16px;margin:12px 0 0}.harless-message-stat-panel dt{color:var(--dsw-alias-label-secondary)}.harless-message-stat-panel dd{margin:0;font-variant-numeric:tabular-nums}
.harless-live-status{display:flex;align-items:center;gap:8px;font-size:13px;line-height:1.6;color:var(--dsw-alias-label-secondary,inherit);margin:12px 0}.harless-live-dot{width:6px;height:6px;flex:none;border-radius:50%;background:var(--dsw-alias-state-business-primary,#729cf7)}.harless-process-message{padding:10px 0;border-top:1px solid #8883;overflow-wrap:anywhere}.harless-process-message pre{max-width:100%;overflow-x:auto}`),
          h('div', { className: value.presentation === 'single' ? 'harless-single' : 'harless-paired-grid' }, pane('baseline'), value.presentation !== 'single' && pane('motif')),
          !settled(value) && h('button', { type: 'button', disabled: saving, onClick: () => action({ action: 'cancel' }), style: { marginTop: 12 } }, '停止生成'),
          connection && h('div', { role: 'status', className: 'harless-paired-connection' }, connection,
            h('button', { type: 'button', onClick: () => refreshNow.current() }, '重新连接'),
            connection.includes('登录') && h('a', { href: '/login', style: { marginLeft: 8 } }, '登录')),
          (error || ratings.error) && h('div', { role: 'alert', className: 'harless-paired-error' }, error || ratings.error));
      }
      ctx.effect(() => ctx.uiConversation.events.register({ kind: 'harless-comparison', target: 'chat',
        match: event => event.type === 'user/message' && event.data.harless_comparison ? { id: event.data.harless_comparison.id, role: 'start' } : null,
        start: (_context, match) => match.event.data.harless_comparison.value,
        update: context => context.state,
        buildViewNode: context => context.start && context.state ? { key: context.key, kind: 'harless-comparison', id: context.id, target: 'chat',
          anchorSeq:context.start.event.seq,location:context.start.location,visibility:'visible',data: context.state } : null,
      }), 'harless-comparison-definition');
      ctx.slots.inject('conversation.chat.node', () => ctx.slots.register({ name: 'conversation.chat.node', key: 'harless-comparison' }, ComparisonNode));
      function mirrorPublicSlot(source, target) {
        let cleanups = [];
        const sync = () => {
          cleanups.reverse().forEach(dispose => dispose()); cleanups = [];
          for (const [index, entry] of (ctx.slots.entries(source) || []).entries()) {
            const names = Object.fromEntries(Object.keys(entry.children || {}).map(name => [name, `${target}.${index}.${name}`]));
            const children = Object.fromEntries(Object.entries(entry.children || {}).map(([name, spec]) => [names[name], spec]));
            const component = Object.keys(names).length ? props => h(entry.component, { ...props,
              renderSlot: (name, owner, options) => props.renderSlot(names[name] || name, owner, options),
              ...(props.renderSlotChain ? { renderSlotChain: (name, owner, options) => props.renderSlotChain(names[name] || name, owner, options) } : {}),
            }) : entry.component;
            cleanups.push(ctx.slots.register({ name: target, ...entry.options, locale: entry.locale, inject: entry.inject,
              ...(entry.select ? { select: entry.select } : {}), ...(entry.store ? { store: entry.store } : {}),
              ...(Object.keys(children).length ? { children } : {}),
            }, component));
            for (const [name, alias] of Object.entries(names)) cleanups.push(mirrorPublicSlot(name, alias));
          }
        };
        sync(); const unsubscribe = ctx.slots.subscribe?.(source, sync);
        return () => { unsubscribe?.(); cleanups.reverse().forEach(dispose => dispose()); };
      }
      window.__installGeneLoopLoading?.(ctx, React, mirrorPublicSlot);
      // The pinned native tab roster enumerates shadowed entries as well as
      // winners. Adapt only the header's public source to one tab per id; keep
      // the native header, store, title management and scoped child actions.
      ctx.slots.inject('conversation.session.header.lineage', () => {
        const original = ctx.slots.entries?.('conversation.session.header')[0];
        if (!original) return () => {};
        const names = Object.fromEntries(Object.keys(original.children || {}).map(name => [name, 'harless.' + name]));
        const children = Object.fromEntries(Object.entries(original.children || {}).map(([name, spec]) => [names[name], spec]));
        const stop = ctx.slots.register({ name: 'conversation.session.header', priority: -100, locale: original.locale,
          ...(original.store ? { store: original.store } : {}), children,
          inject: (...args) => {
            const face = original.inject(...args), source = face.hooks.conversationViews;
            let previous, cached;
            return { ...face, hooks: { ...face.hooks, conversationViews: {
              subscribe: listener => source.subscribe(listener),
              getSnapshot: () => {
                const rows = source.getSnapshot();
                if (rows !== previous) {
                  previous = rows; const ids = new Set();
                  const orders = new Map(ctx.slots.entries('conversation.view').map(entry => [entry.options.id, entry.options.order || 0]));
                  cached = rows.filter(row => !ids.has(row.id) && ids.add(row.id)).sort((a, b) => (orders.get(a.id) || 0) - (orders.get(b.id) || 0));
                }
                return cached;
              },
            } } };
          },
        }, props => h(original.component, { ...props, renderSlot: (name, owner, options) => props.renderSlot(names[name] || name, owner, options) }));
        const mirrors = Object.entries(names).map(([name, alias]) => mirrorPublicSlot(name, alias));
        return () => { mirrors.reverse().forEach(dispose => dispose()); stop(); };
      });
      // Wrap the public trajectory View rather than replacing native history.
      // Its original inject face still owns image loading and older pages. The
      // image child uses a separate declared slot: a second owner cannot declare
      // conversation.trajectory.images again.
      ctx.slots.inject('conversation.trajectory.images', () => {
        const original = ctx.slots.entries?.('conversation.view').find(entry => entry.options.id === 'trajectory');
        if (!original) return () => {};
        const imageSlot = 'harless.trajectory.images';
        function ProductTrajectory(owner) {
          const chat = owner.useChat(value => value);
          const hasMore = owner.useSession(value => value.hasMore);
          const rows = chat.order.map(key => chat.nodes.get(key)).filter(row => row?.kind === 'harless-comparison' && row.visibility !== 'hidden');
          const [selected, setSelected] = React.useState(''), [native, setNative] = React.useState(false);
          React.useEffect(() => { setSelected(''); setNative(false); }, [owner.sessionId]);
          const active = rows.find(row => row.data.id === selected) || rows.at(-1);
          const nativeProps = { ...owner, renderSlot: (name, props, options) => owner.renderSlot(name === 'conversation.trajectory.images' ? imageSlot : name, props, options) };
          if (!rows.length) return h(original.component, nativeProps);
          return h('div', { className: 'harless-trajectory-view' },
            h('style', null, `.harless-trajectory-view{display:flex;flex-direction:column;min-height:0;height:100%;color:var(--dsw-alias-label-primary,inherit);font:inherit}.harless-trajectory-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:14px 20px;border-bottom:1px solid #8883;flex:none}.harless-trace-tabs{display:flex;gap:6px;flex-wrap:wrap}.harless-trace-tabs button,.harless-trajectory-toolbar button,.harless-trajectory-toolbar select{font:inherit;font-size:13px;color:inherit;background:transparent;border:1px solid #8884;border-radius:8px;padding:7px 10px;cursor:pointer}.harless-trace-tabs button[aria-selected=true],.harless-trajectory-toolbar button[aria-pressed=true]{color:var(--dsw-alias-state-business-primary,#729cf7);border-color:currentColor;background:#729cf719}.harless-trace-tabs button:focus-visible,.harless-trajectory-toolbar button:focus-visible,.harless-trajectory-toolbar select:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary,#729cf7);outline-offset:2px}.harless-trajectory-toolbar select{min-width:0;max-width:100%;color-scheme:dark}.harless-trajectory-content{flex:1;min-height:0;overflow:auto;padding:20px}.harless-trajectory-native{flex:1;min-height:0;position:relative}.harless-comparison-trace{width:100%;max-width:960px;margin:0 auto}.harless-trace-list{list-style:none;padding:0;margin:18px 0}.harless-trace-list>li{position:relative;border-left:2px solid #8884;padding:0 0 22px 18px;margin-left:5px;overflow-wrap:anywhere}.harless-trace-event{display:flex;align-items:center;flex-wrap:wrap;gap:8px;line-height:1.6}.harless-trace-event strong{font-size:13px;font-weight:500}.harless-trace-event small,.harless-trace-event time,.harless-trace-tool{font-size:12px;color:var(--dsw-alias-label-secondary,inherit)}.harless-trace-event time{margin-left:auto;white-space:nowrap}.harless-trace-dot{position:absolute;left:-5px;top:7px;width:8px;height:8px;border-radius:50%;background:var(--dsw-alias-label-secondary,#999)}.harless-trace-list>li[data-optimized=true]{border-color:#36a383}.harless-trace-list>li[data-optimized=true] .harless-trace-dot{background:#36a383}.harless-trace-optimization{display:inline-block;font-size:12px;color:#48c5a1;background:#36a38316;border:1px solid #36a38366;border-radius:5px;padding:2px 6px;margin-top:6px}.harless-trace-tool{display:block;margin:4px 0}.harless-trace-list details{margin-top:8px;font-size:13px}.harless-trace-list summary{cursor:pointer;color:var(--dsw-alias-label-secondary,inherit)}.harless-trace-list pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.65;padding:12px;border:1px solid #8883;border-radius:8px}.harless-live-status{font-size:13px;line-height:1.6;color:var(--dsw-alias-label-secondary,inherit)}@media(max-width:600px){.harless-trajectory-toolbar{padding:12px}.harless-trajectory-content{padding:14px}.harless-trace-event time{margin-left:0}}`),
            h('div', { className: 'harless-trajectory-toolbar' },
              h('button', { type: 'button', 'aria-pressed': !native, onClick: () => setNative(false) }, '对照任务'),
              h('button', { type: 'button', 'aria-pressed': native, onClick: () => setNative(true) }, '普通对话'),
              !native && h('select', { 'aria-label': '选择对照轮次', value: active.data.id, onChange: event => setSelected(event.target.value) },
                ...rows.map((row, index) => h('option', { key: row.data.id, value: row.data.id }, `第 ${row.location?.turn?.turn ?? index + 1} 轮 · /${aliases[row.data.scene] || row.data.scene}`))),
              hasMore && h('button', { type: 'button', onClick: () => owner.loadOlder() }, '加载更早记录')),
            native ? h('div', { className: 'harless-trajectory-native' }, h(original.component, nativeProps))
              : h('div', { className: 'harless-trajectory-content' }, h(ComparisonNode, { key: active.data.id, node: active, traceOnly: true })));
        }
        const removeView = ctx.slots.register({ name: 'conversation.view', ...original.options, priority: -100,
          locale: original.locale, inject: original.inject, ...(original.store ? { store: original.store } : {}),
          children: { [imageSlot]: { kind: 'single', scope: 'session' } } }, ProductTrajectory);
        const stopImages = mirrorPublicSlot('conversation.trajectory.images', imageSlot);
        return () => { stopImages(); removeView(); };
      });
      // Keep the native event stream and safe assistant renderer. Product chat
      // groups process evidence itself: native Compact deliberately expands open
      // turns and incomplete history, which is unsuitable for this interface.
      const processKinds = new Set(['context', 'assistant-step', 'tool-call', 'model-retry']);
      const hiddenChatNode = () => null;
      const turnOf = node => node.location?.turn?.turn ?? node.data?.turn;
      const visibleBlocks = node => (node.data.blocks || []).filter(block => block.kind === 'text' || block.kind === 'image');
      const hasAnswer = node => visibleBlocks(node).some(block => block.kind === 'image' || block.text?.trim());
      const publicProcessText = text => String(text ?? '')
        .replace(/@deepseek-ai\/dsh[\w./-]*/gi, 'GeneLoop')
        .replace(/\bdsh(?:[-_][a-z0-9]+)+\b/gi, 'GeneLoop')
        .replace(/\bDSH\b/gi, 'GeneLoop');
      const contentText = content => (content || []).filter(block => block.type === 'text').map(block => publicProcessText(block.text)).join('\n');
      const toolLabel = block => {
        const name = (block.call?.name || block.name || '').split('__').pop();
        return ({ list_files: '查看文件', read_file: '读取文件', inspect_study: '检查研究资料',
          analyze_data: '分析数据', run_analysis: '分析数据', create_presentation: '生成演示文稿',
          export_report: '生成报告', web_search: '搜索资料', search: '搜索资料' })[name] || '工具调用';
      };
      const toolCount = block => 1 + (block.subCalls || []).reduce((count, child) => count + toolCount(child), 0);
      function ToolEvidence({ block }) {
        const done = block.kind === 'tool-result', text = contentText(block.content);
        return h('section', { className: 'geneloop-tool-evidence' },
          h('div', { className: 'geneloop-process-label' }, toolLabel(block), ' · ', done ? block.isError ? '未完成' : '完成' : '进行中'),
          (block.call?.argsRaw || block.argsRaw) && h('pre', null, publicProcessText(block.call?.argsRaw || block.argsRaw)),
          text && h('pre', null, text),
          ...(block.subCalls || []).map(child => h(ToolEvidence, { key: child.callId, block: child })));
      }
      function AssistantContent({ node, owner, process = false }) {
        const original = ctx.slots.entries?.('conversation.chat.node').find(entry => entry.options.key === 'assistant-step' && entry.component !== ProductChatNode);
        const blocks = process ? node.data.blocks.filter(block => ['text', 'image', 'reasoning'].includes(block.kind)) : visibleBlocks(node);
        // A registered public renderer preserves authorized file mentions,
        // images, Markdown and interruption presentation without private APIs.
        if (original) return h(original.component, { ...owner, node: { ...node, data: { ...node.data, blocks } }, turnProcess: undefined });
        return h('div', { 'data-streaming': node.data.status === 'running' }, ...blocks.map((block, i) =>
          block.kind === 'text' || block.kind === 'reasoning' ? MarkdownText
            ? h(MarkdownText, { key: i, text: block.text, streaming: node.data.status === 'running', labels: markdownLabels })
            : h('p', { key: i }, block.text)
            : block.kind === 'image' ? owner.renderMessageImages?.({ images: [{ attachment: block.attachment }], align: 'start' }) : null));
      }
      function ProductTurn({ owner, rows, answer, running }) {
        const [open, setOpen] = React.useState(false);
        const id = React.useId();
        const evidence = rows.filter(row => row !== answer);
        const reasoning = (answer?.data.blocks || []).filter(block => block.kind === 'reasoning' && block.text);
        const tools = rows.filter(row => row.kind === 'tool-call');
        const count = tools.reduce((total, row) => total + toolCount(row.data.root), 0);
        const messageCount = evidence.filter(row => row.kind === 'assistant-step' && hasAnswer(row)).length;
        const hasProcess = evidence.length > 0 || reasoning.length > 0;
        const active = tools.findLast(row => row.data.root.kind !== 'tool-result');
        const status = active ? '正在' + toolLabel(active.data.root) : answer?.data.status === 'running' && hasAnswer(answer) ? '正在回复' : '正在处理';
        const label = count ? `${count} 次工具调用${messageCount ? ` · ${messageCount} 条过程消息` : ''}` : '查看处理过程';
        return h('section', { className: 'geneloop-product-turn' },
          h('style', null, `.geneloop-product-turn{min-width:0}.geneloop-process-toggle{display:flex;align-items:center;gap:8px;border:0;border-radius:8px;padding:7px 9px;margin:0 0 8px -9px;background:transparent;color:var(--dsw-alias-label-secondary);font:inherit;font-size:13px;cursor:pointer;text-align:left}.geneloop-process-toggle:hover{background:var(--dsw-alias-interactive-bg-hover)}.geneloop-process-toggle:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary,#729cf7);outline-offset:2px}.geneloop-process-toggle svg{flex:none;transition:transform .15s}.geneloop-process-toggle[aria-expanded=true] svg{transform:rotate(90deg)}.geneloop-process-evidence{border-left:2px solid var(--dsw-alias-border-l2,#8885);padding-left:14px;margin:4px 0 18px;color:var(--dsw-alias-label-secondary);font-size:13px;line-height:1.6}.geneloop-process-evidence>section{margin:12px 0}.geneloop-process-evidence pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere;margin:6px 0}.geneloop-process-label{font-weight:500}.geneloop-process-status{font-size:13px;color:var(--dsw-alias-label-secondary);margin:0 0 8px}@media(prefers-reduced-motion:reduce){.geneloop-process-toggle svg{transition:none}}`),
          hasProcess && h('button', { type: 'button', className: 'geneloop-process-toggle', 'aria-expanded': open, 'aria-controls': id,
            onClick: () => setOpen(value => !value) },
            h('svg', { width: 12, height: 12, viewBox: '0 0 12 12', fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, 'aria-hidden': true }, h('path', { d: 'm4 2 4 4-4 4' })), label),
          running && h('p', { role: 'status', 'aria-live': 'polite', className: 'geneloop-process-status' }, status + '…'),
          h('div', { id, className: 'geneloop-process-evidence', hidden: !open }, open && [
            ...evidence.map(row => row.kind === 'assistant-step'
              ? h('section', { key: row.key }, h('div', { className: 'geneloop-process-label' }, '过程消息'), h(AssistantContent, { node: row, owner, process: true }))
              : row.kind === 'tool-call' ? h(ToolEvidence, { key: row.key, block: row.data.root })
              : h('section', { key: row.key }, h('div', { className: 'geneloop-process-label' }, row.kind === 'model-retry' ? '请求重试' : '上下文'),
                h('pre', null, row.kind === 'model-retry' ? '请求暂未完成，正在尝试恢复。' : contentText(row.data.content)))),
            ...reasoning.map((block, i) => h('section', { key: 'reasoning-' + i }, h('div', { className: 'geneloop-process-label' }, '思考过程'), h('pre', null, publicProcessText(block.text))))]),
          answer && h(AssistantContent, { node: answer, owner }));
      }
      function ProductChatNode(owner) {
        const { node } = owner;
        const snapshot = owner.useChat(value => value), turn = turnOf(node);
        const rows = snapshot.order.map(key => snapshot.nodes.get(key)).filter(row => row && row.visibility !== 'hidden' && turnOf(row) === turn && processKinds.has(row.kind));
        const assistants = rows.filter(row => row.kind === 'assistant-step');
        const closed = (snapshot.timeline?.turns.get(turn)?.status ?? node.location?.turn?.status) === 'closed';
        // While generating, show the latest real text delta. After completion,
        // retain the final content-bearing message even if the tail is empty.
        const answer = closed ? assistants.findLast(hasAnswer) : assistants.at(-1);
        // Respect the public outer-seat boundary even when the last native
        // assistant block is an extension type rather than visible prose.
        const declaredAnswer = closed ? assistants.find(row => row.data.step === owner.turnProcess?.spec?.answerStep) : undefined;
        const anchor = declaredAnswer || answer || rows.at(-1);
        if (!anchor || anchor.key !== node.key) return hiddenChatNode();
        return h(ProductTurn, { key: `${owner.sessionId}:${turn}`, owner, rows, answer, running: !closed });
      }
      for (const key of processKinds) ctx.slots.inject('conversation.chat.node', () =>
        ctx.slots.register({ name: 'conversation.chat.node', key, priority: -100, locale: 'chat' }, ProductChatNode));
      for (const key of ['system-prompt', 'turn-process']) ctx.slots.inject('conversation.chat.node', () =>
        ctx.slots.register({ name: 'conversation.chat.node', key, priority: -100 }, hiddenChatNode));
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
      const choiceVersions = new Map(), draftWatches = new Map(), suppressDraftReset = new Set();
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
        const face = sessions.binding?.(id)?.session;
        const beginSubmission = face?.beginSubmission;
        const pendingSubmissions = new Set();
        // The public retirement callback distinguishes accepted sends from a
        // native optimistic editor clear. Never consume a scene on rejection.
        if (beginSubmission) face.beginSubmission = function (submission) {
          const version = choiceVersions.get(id) || 0, pending = {};
          pendingSubmissions.add(pending);
          try { return beginSubmission.call(this, { ...submission, onRetire: settlement => {
            pendingSubmissions.delete(pending);
            if (settlement.reason === 'observed' && version === (choiceVersions.get(id) || 0)) {
              revisions.set(id, (revisions.get(id) || 0) + 1);
              draftSelections.delete(id);
              const value = cache.get(id);
              if (value) publish(id, { ...value, selection: { ...value.selection, scene: 'new-scene' }, paired_comparison: false });
            }
            submission.onRetire?.(settlement);
          } }); } catch (error) { pendingSubmissions.delete(pending); throw error; }
        };
        const input = inputFor(id); let previous = input.state.getSnapshot();
        // The composer describes this draft, never the scene used by history.
        displaySelection(id, knownDraftScene(id, previous.draft) || 'new-scene');
        const off = input.state.subscribe(() => {
          const next = input.state.getSnapshot(), before = previous; previous = next;
          if (suppressDraftReset.has(id) || before.draftRev === next.draftRev || before.phase !== 'plain' || next.phase !== 'plain') return;
          // Native sends clear the draft before acceptance. The callback above
          // resets only the next input; the server owns the frozen running task.
          if (pendingSubmissions.size && !next.draft.trim()) return;
          const removed = knownDraftScene(id, before.draft);
          if (removed && removed !== 'new-scene' && !knownDraftScene(id, next.draft)) void resetScene(session);
        });
        draftWatches.set(id, () => { off(); if (beginSubmission) face.beginSubmission = beginSubmission; });
      }
      async function resetScene(session) {
        const id = session.sessionId, previous = choosing.get(id), version = (choiceVersions.get(id) || 0) + 1;
        choiceVersions.set(id, version); revisions.set(id, (revisions.get(id) || 0) + 1);
        displaySelection(id, 'new-scene');
        const blocks = conversation.blocks, existing = blocks?.storeFor(id).getSnapshot();
        if (!existing || existing.reason === resetReason) blocks?.set(id, { reason: resetReason });
        const current = () => choiceVersions.get(id) === version;
        const operation = (async () => {
          // An aborted HTTP request can still mutate the server. Let the old
          // mount settle, then overwrite it; never race a reset against a pick.
          await previous?.catch(() => {});
          if (!current()) return;
          // The visible conversation owns the scene choice. Immutable tool
          // agents are rotated privately by the server; drafts never move.
          const next = await request(session, { action: 'select', session_id: id, selection: { scene: 'new-scene' } });
          if (current()) draftSelections.delete(id);
          publish(id, next); // Canonical state may change under a newer draft overlay.
        })();
        choosing.set(id, operation);
        try { await operation; if (current()) clearResetBlock(id); }
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
          const next = await request(session, { action: 'select', session_id: session.sessionId, selection: { scene: id } }, guard.signal);
          checkChoice();
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
            if (!isCurrent(session) || guard.signal.aborted) return 'handled';
            publish(session.sessionId, selected);
          } catch (error) { if (!isCurrent(session) || guard.signal.aborted) return 'handled'; throw error; }
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
