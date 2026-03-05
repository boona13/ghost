/** Media Gallery page — browse generated images, audio, video, and 3D assets */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

const TYPE_ICONS = { image: '🖼', audio: '🎵', video: '🎬', '3d': '📐', other: '📄' };

let _currentPage = 0;
const PAGE_SIZE = 60;

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  const type = new URLSearchParams(window.location.hash.split('?')[1] || '').get('type') || '';

  container.innerHTML = `
    <div class="flex items-center justify-between mb-1">
      <h1 class="page-header">${t('gallery.title')}</h1>
      <div class="flex gap-2 items-center">
        <span class="badge badge-zinc">${t('common.loading')}</span>
      </div>
    </div>
    <p class="page-desc">${t('gallery.subtitle')}</p>
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mt-6">
      ${Array(8).fill('<div class="stat-card aspect-square bg-surface-800 animate-pulse rounded-lg"></div>').join('')}
    </div>
  `;

  _currentPage = 0;

  let data;
  try {
    data = await api.get(`/api/media?limit=${PAGE_SIZE}${type ? `&type=${type}` : ''}`);
  } catch (e) {
    container.innerHTML = `<div class="stat-card border-red-500/30 p-6 text-center">
      <div class="text-red-400 font-medium">${t('gallery.loadError')}</div>
      <div class="text-xs text-zinc-500 mt-1">${u.escapeHtml(e.message)}</div>
      <button class="btn btn-secondary btn-sm mt-3" onclick="window.location.reload()">${t('common.retry')}</button>
    </div>`;
    return;
  }

  if (data.error) {
    container.innerHTML = `<div class="stat-card border-red-500/30 p-6 text-center">
      <div class="text-red-400 font-medium">${t('gallery.storeUnavailable')}</div>
      <div class="text-xs text-zinc-500 mt-1">${u.escapeHtml(data.error)}</div>
    </div>`;
    return;
  }

  const items = data.items || [];
  const stats = data.stats || {};
  const byType = stats.by_type || {};
  const usagePercent = stats.budget_mb ? ((stats.total_size_mb || 0) / stats.budget_mb) * 100 : 0;
  const budgetBarColor = usagePercent > 90 ? 'bg-red-500' : usagePercent > 70 ? 'bg-amber-500' : 'bg-ghost-500';

  container.innerHTML = `
    <div class="flex items-center justify-between mb-1">
      <h1 class="page-header">${t('gallery.title')}</h1>
      <div class="flex gap-2 items-center">
        <span class="badge badge-green">${stats.total_count || 0} ${t('gallery.items')}</span>
        <span class="badge badge-zinc">${stats.total_size_mb || 0} MB</span>
      </div>
    </div>
    <p class="page-desc">${t('gallery.subtitle')}</p>

    <!-- Type Filter -->
    <div class="flex gap-2 mb-6 flex-wrap" role="tablist" aria-label="${t('gallery.filterByType')}">
      <button class="gallery-filter px-3 py-1.5 text-xs rounded-full ${!type ? 'bg-ghost-600 text-white' : 'bg-surface-700 text-zinc-400 hover:bg-surface-600'}" data-type="" role="tab" aria-selected="${!type}">
        ${t('common.all')} (${stats.total_count || 0})
      </button>
      ${Object.entries(byType).map(([mediaType, info]) => `
        <button class="gallery-filter px-3 py-1.5 text-xs rounded-full ${type === mediaType ? 'bg-ghost-600 text-white' : 'bg-surface-700 text-zinc-400 hover:bg-surface-600'}" data-type="${mediaType}" role="tab" aria-selected="${type === mediaType}">
          <span aria-hidden="true">${TYPE_ICONS[mediaType] || '📄'}</span> ${t('gallery.type_' + mediaType) || (mediaType.charAt(0).toUpperCase() + mediaType.slice(1))} (${info.count})
        </button>
      `).join('')}
    </div>

    <!-- Media Grid -->
    <div id="media-grid" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
      ${items.length === 0 ? `
        <div class="col-span-full text-center py-12 text-zinc-500">
          <div class="text-4xl mb-3">🎨</div>
          <div>${t('gallery.empty')}</div>
          <div class="text-xs mt-1">${t('gallery.emptyHint')}</div>
          <a href="#nodes" class="btn btn-primary btn-sm mt-4 inline-block">${t('gallery.goToNodes')}</a>
        </div>
      ` : items.map(item => renderMediaItem(item, u)).join('')}
    </div>

    ${items.length >= PAGE_SIZE ? `
      <div class="text-center mt-6">
        <button id="load-more-btn" class="btn btn-secondary btn-sm">${t('gallery.loadMore')}</button>
      </div>
    ` : ''}

    <!-- Disk Budget -->
    <div class="mt-8 stat-card">
      <div class="flex items-center justify-between mb-2">
        <span class="text-xs text-zinc-400">${t('gallery.diskUsage')}</span>
        <span class="text-xs text-zinc-500">${stats.total_size_mb || 0} / ${stats.budget_mb || 5000} MB
          <span class="text-zinc-600">(${Math.max(0, (stats.budget_mb || 5000) - (stats.total_size_mb || 0))} MB ${t('gallery.remaining')})</span>
        </span>
      </div>
      <div class="w-full bg-surface-800 rounded-full h-1.5" role="progressbar" aria-valuenow="${stats.total_size_mb || 0}" aria-valuemin="0" aria-valuemax="${stats.budget_mb || 5000}" aria-label="${t('gallery.diskUsage')}">
        <div class="${budgetBarColor} h-1.5 rounded-full transition-all" style="width: ${Math.min(100, usagePercent)}%"></div>
      </div>
      <div class="mt-3 flex gap-2">
        <button id="cleanup-btn" class="btn btn-secondary btn-sm">${t('gallery.cleanup')}</button>
      </div>
    </div>

    <!-- Detail Modal -->
    <div id="media-modal" class="modal-overlay hidden" role="dialog" aria-modal="true" aria-label="${t('gallery.mediaDetail')}">
      <div class="modal-panel max-w-3xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div id="modal-content"></div>
      </div>
    </div>
  `;

  // --- Filter clicks ---
  container.querySelectorAll('.gallery-filter').forEach(btn => {
    btn.addEventListener('click', () => {
      const filterType = btn.dataset.type;
      window.location.hash = filterType ? `gallery?type=${filterType}` : 'gallery';
    });
  });

  // --- Media card clicks (open detail modal) ---
  container.querySelectorAll('.media-item').forEach(card => {
    card.addEventListener('click', () => {
      const itemId = card.dataset.id;
      const item = items.find(i => i.id === itemId);
      if (item) openDetailModal(container, item, u, api);
    });
  });

  // --- Delete buttons ---
  container.querySelectorAll('.media-delete-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const mediaId = btn.dataset.id;
      if (!confirm(t('gallery.confirmDelete'))) return;
      try {
        await api.del(`/api/media/${mediaId}`);
        render(container);
      } catch (err) {
        u.toast?.(err.message || t('gallery.deleteFailed'), 'error');
      }
    });
  });

  // --- Load More ---
  const loadMoreBtn = container.querySelector('#load-more-btn');
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', async () => {
      _currentPage++;
      loadMoreBtn.disabled = true;
      loadMoreBtn.textContent = t('common.loading');
      try {
        const more = await api.get(`/api/media?limit=${PAGE_SIZE}&offset=${_currentPage * PAGE_SIZE}${type ? `&type=${type}` : ''}`);
        const moreItems = more.items || [];
        if (moreItems.length > 0) {
          const grid = container.querySelector('#media-grid');
          grid.insertAdjacentHTML('beforeend', moreItems.map(item => renderMediaItem(item, u)).join(''));
          moreItems.forEach(item => items.push(item));

          grid.querySelectorAll('.media-item:not([data-bound])').forEach(card => {
            card.setAttribute('data-bound', '1');
            card.addEventListener('click', () => {
              const it = items.find(i => i.id === card.dataset.id);
              if (it) openDetailModal(container, it, u, api);
            });
          });
          grid.querySelectorAll('.media-delete-btn:not([data-bound])').forEach(btn => {
            btn.setAttribute('data-bound', '1');
            btn.addEventListener('click', async (e) => {
              e.stopPropagation();
              if (!confirm(t('gallery.confirmDelete'))) return;
              try { await api.del(`/api/media/${btn.dataset.id}`); render(container); }
              catch (err) { u.toast?.(err.message || t('gallery.deleteFailed'), 'error'); }
            });
          });
        }
        if (moreItems.length < PAGE_SIZE) {
          loadMoreBtn.remove();
        } else {
          loadMoreBtn.disabled = false;
          loadMoreBtn.textContent = t('gallery.loadMore');
        }
      } catch (e) {
        u.toast?.(e.message, 'error');
        loadMoreBtn.disabled = false;
        loadMoreBtn.textContent = t('gallery.loadMore');
      }
    });
  }

  // --- Cleanup button ---
  const cleanupBtn = container.querySelector('#cleanup-btn');
  if (cleanupBtn) {
    cleanupBtn.addEventListener('click', async () => {
      cleanupBtn.disabled = true;
      cleanupBtn.textContent = t('common.loading');
      try {
        const result = await api.post('/api/media/cleanup');
        const total = (result.expired_deleted || 0) + (result.budget_deleted || 0);
        u.toast?.(t('gallery.cleanedUp', { count: total }), 'success');
        render(container);
      } catch (err) {
        u.toast?.(err.message || t('gallery.cleanupFailed'), 'error');
        cleanupBtn.disabled = false;
        cleanupBtn.textContent = t('gallery.cleanup');
      }
    });
  }
}

function openDetailModal(container, item, u, api) {
  const modal = container.querySelector('#media-modal');
  const content = container.querySelector('#modal-content');
  if (!modal || !content) return;

  const isImage = item.media_type === 'image';
  const isAudio = item.media_type === 'audio';
  const isVideo = item.media_type === 'video';
  const icon = TYPE_ICONS[item.media_type] || '📄';

  let meta = {};
  try { meta = JSON.parse(item.metadata || '{}'); } catch (e) {}

  const prompt = item.prompt || meta.prompt || '';
  const sizeMb = ((item.size_bytes || 0) / (1024 * 1024)).toFixed(2);
  const date = item.created_at ? new Date(item.created_at * 1000).toLocaleString() : '';

  const metaEntries = Object.entries(meta)
    .filter(([k]) => !['prompt'].includes(k))
    .map(([k, v]) => `<span class="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 bg-surface-700 text-zinc-400 rounded"><b class="text-zinc-300">${u.escapeHtml(k)}:</b> ${u.escapeHtml(String(v).slice(0, 80))}</span>`)
    .join(' ');

  content.innerHTML = `
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-sm font-semibold text-white truncate mr-4">${u.escapeHtml(item.filename)}</h3>
      <button class="modal-close-btn text-zinc-400 hover:text-white text-xl" aria-label="${t('common.close')}">&times;</button>
    </div>

    <div class="bg-surface-800 rounded-lg flex items-center justify-center overflow-hidden mb-4" style="max-height: 60vh;">
      ${isImage
        ? `<img src="/api/media/${item.id}/file" alt="${u.escapeHtml(item.filename)}" class="max-w-full max-h-[60vh] object-contain">`
        : isVideo
          ? `<video src="/api/media/${item.id}/file" controls class="max-w-full max-h-[60vh]" autoplay muted></video>`
          : isAudio
            ? `<div class="py-8 text-center"><span class="text-5xl mb-4 block">🎵</span><audio src="/api/media/${item.id}/file" controls class="w-full max-w-md" autoplay></audio></div>`
            : `<div class="py-8 text-center text-5xl">${icon}</div>`
      }
    </div>

    ${prompt ? `<div class="mb-3"><div class="text-[10px] text-zinc-500 mb-1">${t('gallery.prompt')}</div><div class="text-xs text-zinc-300 bg-surface-800 p-2 rounded">${u.escapeHtml(prompt)}</div></div>` : ''}
    ${metaEntries ? `<div class="mb-3 flex flex-wrap gap-1">${metaEntries}</div>` : ''}

    <div class="flex items-center justify-between text-[10px] text-zinc-500 mb-4">
      <span>${sizeMb} MB · ${date}</span>
      <div class="flex items-center gap-2">
        ${(item.provider && item.provider !== 'local') || meta.provider ? `<span class="px-1.5 py-0.5 bg-sky-500/20 text-sky-400 rounded">${u.escapeHtml(item.provider || meta.provider || 'local')}</span>` : '<span class="px-1.5 py-0.5 bg-surface-700 text-zinc-500 rounded">local</span>'}
        ${(item.cost_usd > 0 || meta.cost_usd > 0) ? `<span class="px-1.5 py-0.5 bg-amber-500/20 text-amber-400 rounded">$${(item.cost_usd || meta.cost_usd || 0).toFixed(2)}</span>` : ''}
        ${item.source_node ? `<span class="text-ghost-400">${u.escapeHtml(item.source_node)}</span>` : ''}
      </div>
    </div>

    <div class="flex gap-2">
      <a href="/api/media/${item.id}/file" download="${u.escapeHtml(item.filename)}" class="btn btn-primary btn-sm">${t('gallery.download')}</a>
      <button class="modal-delete-btn btn btn-sm bg-red-500/20 text-red-400 hover:bg-red-500/30" data-id="${item.id}">${t('common.delete')}</button>
    </div>
  `;

  modal.classList.remove('hidden');

  content.querySelector('.modal-close-btn')?.addEventListener('click', () => modal.classList.add('hidden'));
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.add('hidden'); });

  content.querySelector('.modal-delete-btn')?.addEventListener('click', async () => {
    if (!confirm(t('gallery.confirmDelete'))) return;
    try {
      await api.del(`/api/media/${item.id}`);
      modal.classList.add('hidden');
      render(container);
    } catch (err) {
      u.toast?.(err.message || t('gallery.deleteFailed'), 'error');
    }
  });

  document.addEventListener('keydown', function escHandler(e) {
    if (e.key === 'Escape') {
      modal.classList.add('hidden');
      document.removeEventListener('keydown', escHandler);
    }
  });
}

function renderMediaItem(item, u) {
  const isImage = item.media_type === 'image';
  const isAudio = item.media_type === 'audio';
  const isVideo = item.media_type === 'video';
  const icon = TYPE_ICONS[item.media_type] || '📄';

  const sizeMb = ((item.size_bytes || 0) / (1024 * 1024)).toFixed(1);
  const date = item.created_at ? new Date(item.created_at * 1000).toLocaleDateString() : '';

  let meta = {};
  try { meta = JSON.parse(item.metadata || '{}'); } catch (e) {}

  const promptSnippet = item.prompt || meta.prompt || '';
  const provider = item.provider || meta.provider || 'local';
  const costUsd = item.cost_usd || meta.cost_usd || 0;
  const isCloud = provider && provider !== 'local';
  const providerBadge = isCloud
    ? `<span class="text-[10px] px-1.5 py-0.5 bg-sky-500/20 text-sky-400 rounded">${u.escapeHtml(provider)}</span>`
    : '';
  const costBadge = costUsd > 0
    ? `<span class="text-[10px] px-1.5 py-0.5 bg-amber-500/20 text-amber-400 rounded">$${costUsd.toFixed(2)}</span>`
    : '';

  return `
    <div class="media-item stat-card hover:border-ghost-500/30 transition-colors cursor-pointer group relative overflow-hidden" data-id="${item.id}" role="button" tabindex="0" aria-label="${u.escapeHtml(item.filename)}">
      <!-- Preview -->
      <div class="aspect-square bg-surface-800 rounded-lg mb-2 flex items-center justify-center overflow-hidden">
        ${isImage
          ? `<img src="/api/media/${item.id}/file" alt="${u.escapeHtml(item.filename)}" class="w-full h-full object-cover rounded-lg" loading="lazy">`
          : isAudio
            ? `<div class="text-center"><span class="text-3xl" aria-hidden="true">🎵</span><audio src="/api/media/${item.id}/file" controls preload="none" class="w-full mt-2" style="max-width: 180px"></audio></div>`
            : isVideo
              ? `<video src="/api/media/${item.id}/file" class="w-full h-full object-cover rounded-lg" muted preload="metadata" controls></video>`
              : `<span class="text-4xl" aria-hidden="true">${icon}</span>`
        }
      </div>

      <!-- Info -->
      <div class="text-xs text-zinc-300 truncate font-medium">${u.escapeHtml(item.filename)}</div>
      ${promptSnippet ? `<div class="text-[10px] text-zinc-500 truncate mt-0.5" title="${u.escapeHtml(promptSnippet)}">${u.escapeHtml(promptSnippet)}</div>` : ''}
      <div class="flex items-center justify-between mt-1">
        <span class="text-[10px] text-zinc-600">${sizeMb} MB · ${date}</span>
        <div class="flex items-center gap-1">
          ${providerBadge}${costBadge}
          ${item.source_node ? `<span class="text-[10px] text-ghost-400">${u.escapeHtml(item.source_node)}</span>` : ''}
        </div>
      </div>

      <!-- Action buttons (visible on hover + focus-within for touch) -->
      <div class="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
        <a href="/api/media/${item.id}/file" download="${u.escapeHtml(item.filename)}" class="bg-surface-800/90 text-zinc-300 hover:text-white rounded-full w-6 h-6 flex items-center justify-center text-xs" aria-label="${t('gallery.download')}" onclick="event.stopPropagation()">↓</a>
        <button class="media-delete-btn bg-red-500/80 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs"
                data-id="${item.id}" aria-label="${t('gallery.deleteItem')}">×</button>
      </div>
    </div>
  `;
}
