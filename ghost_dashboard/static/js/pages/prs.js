/** Pull Requests page — PR list, detail view with diff and discussion thread */

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
      <h1 class="page-header">Pull Requests</h1>
    </div>
    <p class="page-desc">Code review history — Ghost's Developer and Reviewer personas discuss every change before it ships.</p>

    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
      <div class="stat-card">
        <div class="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Total</div>
        <div class="text-xl font-bold text-ghost-400">${stats.total || 0}</div>
      </div>
      <div class="stat-card">
        <div class="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Merged</div>
        <div class="text-xl font-bold text-emerald-400">${stats.merged || 0}</div>
      </div>
      <div class="stat-card">
        <div class="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Open</div>
        <div class="text-xl font-bold text-amber-400">${(stats.open || 0) + (stats.reviewing || 0)}</div>
      </div>
      <div class="stat-card">
        <div class="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Blocked / Rejected</div>
        <div class="text-xl font-bold text-red-400">${(stats.blocked || 0) + (stats.rejected || 0)}</div>
      </div>
    </div>

    <div class="border-b border-surface-600/30 mb-4">
      <nav class="flex gap-1" id="pr-tabs">
        ${prTab('all', 'All', stats.total || 0, true)}
        ${prTab('merged', 'Merged', stats.merged || 0)}
        ${prTab('open', 'Open', (stats.open || 0) + (stats.reviewing || 0))}
        ${prTab('blocked', 'Blocked', (stats.blocked || 0) + (stats.rejected || 0))}
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
    return '<div class="text-center py-12 text-xs text-zinc-600">No pull requests found</div>';
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
              <span>${pr.files_changed?.length || 0} file(s)</span>
              <span>${pr.review_rounds}/${pr.max_rounds} rounds</span>
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
    container.innerHTML = '<div class="text-center py-12 text-xs text-red-400">PR not found</div>';
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
      ${pr.merged_at ? `<span class="text-[10px] text-zinc-500 ml-2">Merged ${new Date(pr.merged_at).toLocaleString()}</span>` : ''}
    </div>` : '';

  const canOverride = pr.status !== 'merged';

  container.innerHTML = `
    <button id="pr-back" class="btn btn-ghost btn-sm mb-4 flex items-center gap-1">
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
      Back to PRs
    </button>

    <div class="stat-card mb-4">
      <div class="flex items-center gap-2 mb-2">
        <span class="text-sm font-bold text-white">${u.escapeHtml(pr.title)}</span>
        <span class="badge ${badge}">${pr.status}</span>
      </div>
      <p class="text-xs text-zinc-400 mb-2">${u.escapeHtml(pr.description || '')}</p>
      <div class="flex items-center gap-4 text-[10px] text-zinc-500">
        <span>Branch: <span class="text-zinc-300">${pr.branch}</span></span>
        <span>Rounds: ${pr.review_rounds}/${pr.max_rounds}</span>
        <span>Files: ${pr.files_changed?.join(', ') || 'none'}</span>
        ${pr.feature_id ? `<span>Feature: <span class="text-ghost-400">${pr.feature_id}</span></span>` : ''}
      </div>
    </div>

    ${verdictBanner}

    ${canOverride ? `
    <div class="flex gap-2 mb-4">
      ${pr.status !== 'approved' && pr.status !== 'blocked' ? `<button id="pr-force-approve" class="btn btn-primary btn-sm" style="padding:0.3rem 0.6rem;font-size:10px">Force Approve + Merge</button>` : ''}
      ${pr.status !== 'blocked' ? `<button id="pr-force-block" class="btn btn-danger btn-sm" style="padding:0.3rem 0.6rem;font-size:10px">Force Block</button>` : ''}
      <button id="pr-force-merge" class="btn btn-ghost btn-sm" style="padding:0.3rem 0.6rem;font-size:10px;border:1px solid rgba(139,92,246,0.3)">Force Merge</button>
    </div>` : ''}

    <details class="mb-4" open>
      <summary class="text-xs font-semibold text-white cursor-pointer mb-2">Diff</summary>
      <div class="stat-card overflow-x-auto">
        <pre class="text-[11px] leading-relaxed font-mono whitespace-pre-wrap" id="pr-diff"></pre>
      </div>
    </details>

    <h3 class="text-xs font-semibold text-white mb-3">Discussion (${pr.discussions?.length || 0} messages)</h3>
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
      if (!confirm('Force-approve and merge this PR? Ghost will restart.')) return;
      const r = await api.post(`/api/prs/${prId}/force-approve`);
      if (r.ok) u.toast(r.message || 'Force approved and merged');
      else u.toast(r.error || 'Approve failed', 'error');
      await renderPrDetail(container, prId, api, u);
    });

    document.getElementById('pr-force-block')?.addEventListener('click', async () => {
      const reason = prompt('Block reason:');
      if (!reason) return;
      const r = await api.post(`/api/prs/${prId}/force-block`, { reason });
      if (r.ok) u.toast(r.message || 'PR blocked');
      else u.toast(r.error || 'Block failed', 'error');
      await renderPrDetail(container, prId, api, u);
    });

    document.getElementById('pr-force-merge')?.addEventListener('click', async () => {
      if (!confirm('Force-merge this PR without review? Ghost will restart.')) return;
      const r = await api.post(`/api/prs/${prId}/force-merge`);
      if (r.ok) u.toast(r.message || 'Force merged');
      else u.toast(r.error || 'Merge failed', 'error');
      await renderPrDetail(container, prId, api, u);
    });
  }
}

function renderDiscussion(discussions, u) {
  if (!discussions.length) {
    return '<div class="text-center py-8 text-xs text-zinc-600">No discussion yet</div>';
  }

  let currentRound = 0;
  const parts = [];

  for (const d of discussions) {
    if (d.round !== currentRound) {
      currentRound = d.round;
      parts.push(`<div class="text-[10px] font-semibold text-zinc-600 uppercase tracking-wide pt-2">Round ${currentRound}</div>`);
    }

    const isReviewer = d.role === 'reviewer';
    const accent = isReviewer ? 'border-l-red-500/50' : 'border-l-ghost-500/50';
    const label = isReviewer ? 'Reviewer' : 'Developer';
    const labelColor = isReviewer ? 'text-red-400' : 'text-ghost-400';
    const bg = isReviewer ? 'bg-red-500/5' : 'bg-ghost-500/5';

    parts.push(`
      <div class="stat-card border-l-2 ${accent} ${bg}" style="border-color:inherit">
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
