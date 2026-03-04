/** Pull Requests page — PR list, detail view with diff and discussion thread */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  const hash = window.location.hash;
  const idMatch = hash.match(/[?&]id=([^&]+)/);
  if (idMatch) {
    await renderPrDetail(container, idMatch[1], api, u);
    return;
  }

  const [prsData, statsData] = await Promise.all([
    api.get('/api/prs/list'),
    api.get('/api/prs/stats').catch(() => ({ ok: true, stats: {} })),
  ]);

  const prs = prsData.prs || [];
  const stats = statsData.stats || {};

  container.innerHTML = `
    <div class="flex items-center justify-between mb-1">
      <h1 class="page-header">${t('prs.title')}</h1>
    </div>
    <p class="page-desc">${t('prs.subtitle')}</p>

    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
      <div class="stat-card">
        <div class="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">${t('common.total')}</div>
        <div class="text-xl font-bold text-ghost-400">${stats.total || 0}</div>
      </div>
      <div class="stat-card">
        <div class="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">${t('prs.merged')}</div>
        <div class="text-xl font-bold text-emerald-400">${stats.merged || 0}</div>
      </div>
      <div class="stat-card">
        <div class="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">${t('prs.open')}</div>
        <div class="text-xl font-bold text-amber-400">${(stats.open || 0) + (stats.reviewing || 0)}</div>
      </div>
      <div class="stat-card">
        <div class="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">${t('prs.blocked')}</div>
        <div class="text-xl font-bold text-red-400">${(stats.blocked || 0) + (stats.rejected || 0)}</div>
      </div>
    </div>

    <div class="border-b border-surface-600/30 mb-4">
      <nav class="flex gap-1" id="pr-tabs">
        ${prTab('all', t('common.all'), stats.total || 0, true)}
        ${prTab('merged', t('prs.filterMerged'), stats.merged || 0)}
        ${prTab('open', t('prs.filterOpen'), (stats.open || 0) + (stats.reviewing || 0))}
        ${prTab('blocked', t('prs.filterBlocked'), (stats.blocked || 0) + (stats.rejected || 0))}
      </nav>
    </div>

    <div id="pr-list" class="space-y-2">
      ${renderPrList(prs, 'all', u)}
    </div>
  `;

  let currentPrFilter = 'all';
  container.querySelectorAll('.pr-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      currentPrFilter = tab.dataset.filter;
      container.querySelectorAll('.pr-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById('pr-list').innerHTML = renderPrList(prs, currentPrFilter, u);
      bindPrClicks(api, u, container);
    });
  });

  bindPrClicks(api, u, container);
}

function bindPrClicks(api, u, container) {
  document.getElementById('pr-list')?.querySelectorAll('[data-pr-id]').forEach(row => {
    row.addEventListener('click', async () => {
      const prId = row.dataset.prId;
      window.location.hash = `#prs?id=${prId}`;
      await renderPrDetail(container, prId, api, u);
    });
  });
}

function prTab(id, label, count, active = false) {
  return `<button data-filter="${id}" class="pr-tab evo-tab ${active ? 'active' : ''}">${label} <span class="ml-1 text-[10px] opacity-60">${count}</span></button>`;
}

function renderPrList(prs, filter, u) {
  const filtered = filter === 'all' ? prs : prs.filter(p => {
    if (filter === 'open') return p.status === 'open' || p.status === 'reviewing' || p.status === 'changes_requested';
    if (filter === 'merged') return p.status === 'merged';
    if (filter === 'blocked') return p.status === 'blocked' || p.status === 'rejected';
    return p.status === filter;
  });

  if (!filtered.length) {
    return `<div class="text-center py-12 text-xs text-zinc-600">${t('prs.noPrs')}</div>`;
  }

  return filtered.map(pr => {
    const badge = prStatusBadge(pr.status);
    const verdict = pr.verdict ? ` [${pr.verdict}]` : '';
    return `
      <div class="stat-card cursor-pointer hover:border-ghost-500/30 transition-colors" data-pr-id="${pr.pr_id}">
        <div class="flex items-center justify-between">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span class="text-xs font-semibold text-white">${u.escapeHtml(pr.title)}</span>
              <span class="badge ${badge}">${pr.status}${verdict}</span>
            </div>
            <div class="flex items-center gap-3 text-[10px] text-zinc-600">
              <span>${t('prs.fileCount', {n: pr.files_changed?.length || 0})}</span>
              <span>${pr.review_rounds}/${pr.max_rounds} ${t('prs.roundsLabel')}</span>
              <span>${pr.branch || ''}</span>
              <span>${new Date(pr.created_at).toLocaleDateString()}</span>
            </div>
          </div>
          <svg class="w-4 h-4 text-zinc-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
        </div>
      </div>`;
  }).join('');
}

function prStatusBadge(status) {
  return {
    open: 'badge-yellow', reviewing: 'badge-purple',
    changes_requested: 'badge-yellow', approved: 'badge-blue',
    merged: 'badge-green', blocked: 'badge-red', rejected: 'badge-yellow',
  }[status] || 'badge-zinc';
}

async function renderPrDetail(container, prId, api, u) {
  const res = await api.get(`/api/prs/${prId}`);
  if (!res.ok) {
    container.innerHTML = `<div class="text-center py-12 text-xs text-red-400">${t('prs.prNotFound')}</div>`;
    return;
  }

  const pr = res.pr;
  const badge = prStatusBadge(pr.status);

  const verdictColors = {
    approved: { bg: 'bg-emerald-500/10 border border-emerald-500/30', text: 'text-emerald-400' },
    blocked:  { bg: 'bg-red-500/10 border border-red-500/30', text: 'text-red-400' },
    rejected: { bg: 'bg-amber-500/10 border border-amber-500/30', text: 'text-amber-400' },
  };
  const vc = verdictColors[pr.verdict] || { bg: 'bg-zinc-500/10 border border-zinc-500/30', text: 'text-zinc-400' };
  const verdictBanner = pr.verdict ? `
    <div class="rounded-lg px-4 py-3 mb-4 ${vc.bg}">
      <span class="text-xs font-bold ${vc.text}">${pr.verdict.toUpperCase()}</span>
      ${pr.blocked_reason ? `<span class="text-[10px] text-zinc-400 ml-2">— ${u.escapeHtml(pr.blocked_reason)}</span>` : ''}
      ${pr.merged_at ? `<span class="text-[10px] text-zinc-500 ml-2">${t('prs.mergedAt')}${new Date(pr.merged_at).toLocaleString()}</span>` : ''}
    </div>` : '';

  const canOverride = pr.status !== 'merged';

  container.innerHTML = `
    <button id="pr-back" class="btn btn-ghost btn-sm mb-4 flex items-center gap-1">
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
      ${t('prs.backToPrs')}
    </button>

    <div class="stat-card mb-4">
      <div class="flex items-center gap-2 mb-2">
        <span class="text-sm font-bold text-white">${u.escapeHtml(pr.title)}</span>
        <span class="badge ${badge}">${pr.status}</span>
      </div>
      <p class="text-xs text-zinc-400 mb-2">${u.escapeHtml(pr.description || '')}</p>
      <div class="flex items-center gap-4 text-[10px] text-zinc-500">
        <span>${t('prs.branchLabel')}<span class="text-zinc-300">${pr.branch}</span></span>
        <span>${t('prs.roundsCount')}${pr.review_rounds}/${pr.max_rounds}</span>
        <span>${t('prs.filesLabel')}${pr.files_changed?.join(', ') || t('prs.none')}</span>
        ${pr.feature_id ? `<span>${t('prs.featureLabel')}<span class="text-ghost-400">${pr.feature_id}</span></span>` : ''}
      </div>
    </div>

    ${verdictBanner}

    ${canOverride ? `
    <div class="flex gap-2 mb-4">
      ${pr.status !== 'approved' && pr.status !== 'blocked' ? `<button id="pr-force-approve" class="btn btn-primary btn-sm" style="padding:0.3rem 0.6rem;font-size:10px">${t('prs.forceApprove')}</button>` : ''}
      ${pr.status !== 'blocked' ? `<button id="pr-force-block" class="btn btn-danger btn-sm" style="padding:0.3rem 0.6rem;font-size:10px">${t('prs.forceBlock')}</button>` : ''}
      <button id="pr-force-merge" class="btn btn-ghost btn-sm" style="padding:0.3rem 0.6rem;font-size:10px;border:1px solid rgba(139,92,246,0.3)">${t('prs.forceMerge')}</button>
    </div>` : ''}

    <details class="mb-4" open>
      <summary class="text-xs font-semibold text-white cursor-pointer mb-2">${t('prs.diff')}</summary>
      <div class="stat-card overflow-x-auto">
        <pre class="text-[11px] leading-relaxed font-mono whitespace-pre-wrap" id="pr-diff"></pre>
      </div>
    </details>

    <h3 class="text-xs font-semibold text-white mb-3">${t('prs.discussion', {n: pr.discussions?.length || 0})}</h3>
    <div id="pr-discussion" class="space-y-3 mb-6">
      ${renderDiscussion(pr.discussions || [], u)}
    </div>
  `;

  const diffEl = document.getElementById('pr-diff');
  if (diffEl && pr.diff) {
    diffEl.textContent = pr.diff.substring(0, 50000);
    highlightDiff(diffEl);
  }

  document.getElementById('pr-back').addEventListener('click', () => {
    window.location.hash = '#prs';
    render(container);
  });

  if (canOverride) {
    document.getElementById('pr-force-approve')?.addEventListener('click', async () => {
      if (!confirm(t('prs.forceApproveConfirm'))) return;
      const r = await api.post(`/api/prs/${prId}/force-approve`);
      if (r.ok) u.toast(r.message || t('prs.forceApproved'));
      else u.toast(r.error || t('prs.approveFailed'), 'error');
      await renderPrDetail(container, prId, api, u);
    });

    document.getElementById('pr-force-block')?.addEventListener('click', async () => {
      const reason = prompt(t('prs.blockReason'));
      if (!reason) return;
      const r = await api.post(`/api/prs/${prId}/force-block`, { reason });
      if (r.ok) u.toast(r.message || t('prs.prBlocked'));
      else u.toast(r.error || t('prs.blockFailed'), 'error');
      await renderPrDetail(container, prId, api, u);
    });

    document.getElementById('pr-force-merge')?.addEventListener('click', async () => {
      if (!confirm(t('prs.forceMergeConfirm'))) return;
      const r = await api.post(`/api/prs/${prId}/force-merge`);
      if (r.ok) u.toast(r.message || t('prs.forceMerged'));
      else u.toast(r.error || t('prs.mergeFailed'), 'error');
      await renderPrDetail(container, prId, api, u);
    });
  }
}

function renderDiscussion(discussions, u) {
  if (!discussions.length) {
    return `<div class="text-center py-8 text-xs text-zinc-600">${t('prs.noDiscussion')}</div>`;
  }

  let currentRound = 0;
  const parts = [];

  for (const d of discussions) {
    if (d.round !== currentRound) {
      currentRound = d.round;
      parts.push(`<div class="text-[10px] font-semibold text-zinc-600 uppercase tracking-wide pt-2">${t('prs.round', {n: currentRound})}</div>`);
    }

    const isReviewer = d.role === 'reviewer';
    const accentColor = isReviewer ? 'rgba(239,68,68,0.5)' : 'rgba(139,92,246,0.5)';
    const label = isReviewer ? t('prs.reviewer') : t('prs.developer');
    const labelColor = isReviewer ? 'text-red-400' : 'text-ghost-400';
    const bg = isReviewer ? 'bg-red-500/5' : 'bg-ghost-500/5';

    parts.push(`
      <div class="stat-card ${bg}" style="border-inline-start: 2px solid ${accentColor}">
        <div class="flex items-center gap-2 mb-2">
          <span class="text-[10px] font-bold ${labelColor}">${label}</span>
          <span class="text-[10px] text-zinc-600">${new Date(d.timestamp).toLocaleString()}</span>
        </div>
        <div class="text-xs text-zinc-300 leading-relaxed whitespace-pre-wrap">${u.escapeHtml(d.message)}</div>
      </div>
    `);
  }

  return parts.join('');
}

function highlightDiff(el) {
  const lines = el.textContent.split('\n');
  const html = lines.map(line => {
    if (line.startsWith('+') && !line.startsWith('+++')) {
      return `<span class="text-emerald-400">${escapeHtml(line)}</span>`;
    }
    if (line.startsWith('-') && !line.startsWith('---')) {
      return `<span class="text-red-400">${escapeHtml(line)}</span>`;
    }
    if (line.startsWith('@@')) {
      return `<span class="text-ghost-400">${escapeHtml(line)}</span>`;
    }
    if (line.startsWith('diff ') || line.startsWith('index ')) {
      return `<span class="text-zinc-500">${escapeHtml(line)}</span>`;
    }
    return escapeHtml(line);
  }).join('\n');
  el.innerHTML = html;
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
