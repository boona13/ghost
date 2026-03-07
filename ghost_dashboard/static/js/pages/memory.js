/** Memory page */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;
  const [stats, recent] = await Promise.all([
    api.get('/api/memory/stats'),
    api.get('/api/memory/recent?limit=20'),
  ]);

  const byType = stats.by_type || {};

  container.innerHTML = `
    <h1 class="page-header">${t('memory.title')}</h1>
    <p class="page-desc">${t('memory.subtitle')}</p>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      <div class="stat-card">
        <div class="text-xs text-zinc-500">${t('memory.totalEntries')}</div>
        <div class="text-2xl font-bold text-white">${stats.total || 0}</div>
      </div>
      <div class="stat-card">
        <div class="text-xs text-zinc-500">${t('memory.totalTokens')}</div>
        <div class="text-2xl font-bold text-white">${(stats.total_tokens || 0).toLocaleString()}</div>
      </div>
      <div class="stat-card">
        <div class="text-xs text-zinc-500">${t('memory.types')}</div>
        <div class="flex flex-wrap gap-1 mt-1">
          ${Object.entries(byType).map(([t, c]) => `<span class="badge badge-${u.TYPE_COLORS[t] || 'zinc'}">${t}: ${c}</span>`).join('')}
        </div>
      </div>
    </div>

    <div class="stat-card mb-6">
      <div class="flex gap-2 mb-4">
        <input id="mem-search" type="text" class="form-input flex-1" placeholder="${t('memory.searchPlaceholder')}">
        <button id="btn-mem-search" class="btn btn-primary">${t('common.search')}</button>
      </div>
      <div id="search-results"></div>
    </div>

    <div class="flex items-center justify-between mb-4">
      <h2 class="text-sm font-semibold text-zinc-400">${t('memory.recentMemories')}</h2>
      <div class="flex items-center gap-2">
        <label class="text-xs text-zinc-500">${t('memory.pruneTo')}</label>
        <input id="prune-count" type="number" class="form-input w-24 text-xs" value="1000" min="100" step="100">
        <button id="btn-prune" class="btn btn-danger btn-sm">${t('memory.prune')}</button>
      </div>
    </div>

    <div id="memory-list" class="space-y-2">
      ${renderEntries(recent.results || [], u)}
    </div>
  `;

  document.getElementById('btn-mem-search')?.addEventListener('click', async () => {
    const q = document.getElementById('mem-search').value.trim();
    if (!q) return;
    const r = await api.get(`/api/memory/search?q=${encodeURIComponent(q)}&limit=50`);
    document.getElementById('search-results').innerHTML = renderEntries(r.results || [], u);
    bindDeletes(container, api, u);
  });

  document.getElementById('mem-search')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') document.getElementById('btn-mem-search').click();
  });

  document.getElementById('btn-prune')?.addEventListener('click', async () => {
    const keep = parseInt(document.getElementById('prune-count').value);
    if (!confirm(t('memory.pruneConfirm', { n: keep }))) return;
    await api.post('/api/memory/prune', { keep });
    u.toast(t('memory.pruned'));
    render(container);
  });

  bindDeletes(container, api, u);
}

function renderEntries(entries, u) {
  if (!entries.length) return `<div class="text-xs text-zinc-600">${t('memory.noEntries')}</div>`;
  return entries.map(e => `
    <div class="feed-entry type-${e.type || 'unknown'}">
      <div class="flex items-center gap-2 mb-1">
        <span class="badge badge-${u.TYPE_COLORS[e.type] || 'zinc'}">${e.type || '?'}</span>
        <span class="text-[10px] text-zinc-600">${e.timestamp || ''}</span>
        ${e.tokens_used ? `<span class="text-[10px] text-zinc-600">${e.tokens_used} ${t('common.tokens')}</span>` : ''}
        ${renderCitationBadge(e)}
        <button class="btn btn-ghost btn-sm ml-auto text-red-400 hover:text-red-300" data-mem-del="${e.id}">${t('common.delete')}</button>
      </div>
      ${e.source_preview ? `<div class="text-[11px] text-zinc-500 mb-1">${t('memory.source')} ${u.escapeHtml(e.source_preview)}</div>` : ''}
      <div class="text-xs text-zinc-300">${u.escapeHtml((e.content || '').slice(0, 300))}</div>
      ${e._citation_status ? `<div class="text-[11px] text-zinc-500 mt-1">${u.escapeHtml(e._citation_status.replace(/^\s+/, ''))}</div>` : ''}
      ${e.skill ? `<span class="badge badge-purple mt-1">${e.skill}</span>` : ''}
    </div>
  `).join('');
}

function renderCitationBadge(entry) {
  if (!entry._citation_status) return '';
  if (entry._citation_valid === false) {
    return `<span class="badge badge-yellow">stale</span>`;
  }
  if (entry._citation_valid === true && entry._citation_checked) {
    return `<span class="badge badge-green">verified</span>`;
  }
  return '';
}

function bindDeletes(container, api, u) {
  container.querySelectorAll('[data-mem-del]').forEach(btn => {
    btn.addEventListener('click', async () => {
      await api.del(`/api/memory/${btn.dataset.memDel}`);
      btn.closest('.feed-entry')?.remove();
      u.toast(t('memory.deleted'));
    });
  });
}
