/** Activity Feed page */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;
  const data = await api.get('/api/feed');
  const entries = data.entries || [];
  const types = [...new Set(entries.map(e => e.type).filter(Boolean))];

  container.innerHTML = `
    <div class="flex items-center justify-between mb-1">
      <h1 class="page-header">${t('feed.title')}</h1>
      <button id="btn-refresh-feed" class="btn btn-ghost btn-sm">${t('common.refresh')}</button>
    </div>
    <p class="page-desc">${t('feed.subtitle')}</p>

    <div class="flex flex-wrap gap-2 mb-4">
      <button class="badge badge-purple cursor-pointer feed-filter active" data-filter="all">${t('feed.allCount', { n: entries.length })}</button>
      ${types.map(tp => {
        const c = entries.filter(e => e.type === tp).length;
        return `<button class="badge badge-${u.TYPE_COLORS[tp] || 'zinc'} cursor-pointer feed-filter" data-filter="${tp}">${u.TYPE_ICONS[tp] || ''} ${tp} (${c})</button>`;
      }).join('')}
    </div>

    <div id="feed-list" class="space-y-2">
      ${renderFeed(entries, u)}
    </div>
  `;

  let activeFilter = 'all';

  container.querySelectorAll('.feed-filter').forEach(btn => {
    btn.addEventListener('click', () => {
      activeFilter = btn.dataset.filter;
      container.querySelectorAll('.feed-filter').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const filtered = activeFilter === 'all' ? entries : entries.filter(e => e.type === activeFilter);
      document.getElementById('feed-list').innerHTML = renderFeed(filtered, u);
    });
  });

  document.getElementById('btn-refresh-feed')?.addEventListener('click', () => render(container));
}

function renderFeed(entries, u) {
  if (!entries.length) return `<div class="text-sm text-zinc-600">${t('feed.noActivity')}</div>`;
  return entries.map(e => `
    <div class="feed-entry type-${e.type || 'unknown'}">
      <div class="flex items-center gap-2 mb-2">
        <span class="text-sm">${u.TYPE_ICONS[e.type] || '❓'}</span>
        <span class="badge badge-${u.TYPE_COLORS[e.type] || 'zinc'}">${e.type || 'unknown'}</span>
        ${e.skill ? `<span class="badge badge-purple">${e.skill}</span>` : ''}
        ${e.tools_used?.length ? `<span class="text-[10px] text-zinc-600">${e.tools_used.length} ${t('common.tools')}</span>` : ''}
        <span class="text-[10px] text-zinc-600 ml-auto">${u.timeAgo(e.time)}</span>
      </div>
      ${e.source ? `<div class="text-[11px] text-zinc-500 truncate mb-1">${u.escapeHtml((e.source || '').slice(0, 150))}</div>` : ''}
      <div class="text-xs text-zinc-300 whitespace-pre-wrap">${u.escapeHtml((e.result || '').slice(0, 500))}</div>
      ${e.fix_command ? `<div class="mt-1 font-mono text-xs text-emerald-400">$ ${u.escapeHtml(e.fix_command)}</div>` : ''}
    </div>
  `).join('');
}
