/** Future Features page — backlog management for autonomous feature implementation */

let currentFeatures = [];
let currentFilter = 'all';
let metadata = { statuses: [], priorities: [], sources: [], efforts: [] };

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  const [featuresData, statsData, metaData] = await Promise.all([
    api.get('/api/future-features/list'),
    api.get('/api/future-features/stats'),
    api.get('/api/future-features/metadata').catch(() => ({ ok: true, statuses: [], priorities: [], sources: [], efforts: [] })),
  ]);

  currentFeatures = featuresData.features || [];
  metadata = metaData;

  const stats = statsData.stats || {};
  const activeCount = (stats.pending || 0) + (stats.approval_required || 0) + (stats.in_progress || 0);

  container.innerHTML = `
    <div class="flex items-center justify-between mb-1">
      <h1 class="page-header">Future Features</h1>
      <button id="ff-add-btn" class="btn btn-primary btn-sm flex items-center gap-1.5">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
        Add Feature
      </button>
    </div>
    <p class="page-desc">Autonomous feature backlog — Tech Scout and Competitive Intel add features here. Feature Implementer runs daily to implement them.</p>

    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
      <div class="stat-card">
        <div class="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Active</div>
        <div class="text-xl font-bold text-ghost-400">${activeCount}</div>
      </div>
      <div class="stat-card">
        <div class="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Pending</div>
        <div class="text-xl font-bold text-amber-400">${stats.pending || 0}</div>
      </div>
      <div class="stat-card">
        <div class="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Need Approval</div>
        <div class="text-xl font-bold text-red-400">${stats.approval_required || 0}</div>
      </div>
      <div class="stat-card">
        <div class="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Implemented</div>
        <div class="text-xl font-bold text-emerald-400">${stats.implemented || 0}</div>
      </div>
    </div>

    <div class="stat-card mb-6">
      <h3 class="text-xs font-semibold text-white mb-2">By Priority</h3>
      <div class="flex gap-4 text-xs">
        <div class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-red-500"></span>
          <span class="text-zinc-400">P0: ${stats.by_priority?.P0 || 0}</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-orange-500"></span>
          <span class="text-zinc-400">P1: ${stats.by_priority?.P1 || 0}</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-yellow-500"></span>
          <span class="text-zinc-400">P2: ${stats.by_priority?.P2 || 0}</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-zinc-500"></span>
          <span class="text-zinc-400">P3: ${stats.by_priority?.P3 || 0}</span>
        </div>
      </div>
    </div>

    <div class="border-b border-surface-600/30 mb-4">
      <nav class="flex gap-1">
        ${renderTab('all', 'All', stats.total || 0)}
        ${renderTab('pending', 'Pending', stats.pending || 0)}
        ${renderTab('approval_required', 'Need Approval', stats.approval_required || 0)}
        ${renderTab('in_progress', 'In Progress', stats.in_progress || 0)}
        ${renderTab('implemented', 'Completed', stats.implemented || 0)}
        ${renderTab('failed', 'Failed', (stats.failed || 0) + (stats.deferred || 0))}
      </nav>
    </div>

    <div id="ff-list" class="space-y-3">
      ${renderFeatureList(currentFeatures, currentFilter, u)}
    </div>

    <div id="ff-modal" class="hidden fixed inset-0 z-50 flex items-center justify-center" style="background:rgba(0,0,0,0.6)">
      <div class="stat-card w-full max-w-lg mx-4" style="border-color:rgba(139,92,246,0.3)">
        <h3 class="text-sm font-bold text-white mb-4">Add Future Feature</h3>
        <form id="ff-form" class="space-y-3">
          <div>
            <label class="form-label">Title</label>
            <input type="text" id="ff-title" required class="form-input w-full">
          </div>
          <div>
            <label class="form-label">Description</label>
            <textarea id="ff-description" rows="3" required class="form-input w-full" style="resize:vertical"></textarea>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="form-label">Priority</label>
              <select id="ff-priority" class="form-input w-full">
                ${metadata.priorities.map(p => `<option value="${p.value}">${p.label}</option>`).join('')}
              </select>
            </div>
            <div>
              <label class="form-label">Effort</label>
              <select id="ff-effort" class="form-input w-full">
                ${metadata.efforts.map(e => `<option value="${e.value}">${e.label}</option>`).join('')}
              </select>
            </div>
          </div>
          <div class="flex items-center gap-2 py-1">
            <div class="toggle on" id="ff-auto-toggle"><span class="toggle-dot"></span></div>
            <span class="text-xs text-zinc-400">Auto-implement (toggle off to require approval)</span>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button type="button" id="ff-cancel" class="btn btn-secondary btn-sm">Cancel</button>
            <button type="submit" class="btn btn-primary btn-sm">Add Feature</button>
          </div>
        </form>
      </div>
    </div>
  `;

  // Auto-implement toggle
  document.getElementById('ff-auto-toggle')?.addEventListener('click', (e) => {
    e.currentTarget.classList.toggle('on');
  });

  document.getElementById('ff-add-btn').addEventListener('click', () => {
    document.getElementById('ff-modal').classList.remove('hidden');
  });

  document.getElementById('ff-cancel').addEventListener('click', () => {
    document.getElementById('ff-modal').classList.add('hidden');
    document.getElementById('ff-form').reset();
    document.getElementById('ff-auto-toggle').classList.add('on');
  });

  // Close modal on backdrop click
  document.getElementById('ff-modal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) {
      document.getElementById('ff-modal').classList.add('hidden');
      document.getElementById('ff-form').reset();
      document.getElementById('ff-auto-toggle').classList.add('on');
    }
  });

  document.getElementById('ff-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = {
      title: document.getElementById('ff-title').value,
      description: document.getElementById('ff-description').value,
      priority: document.getElementById('ff-priority').value,
      estimated_effort: document.getElementById('ff-effort').value,
      auto_implement: document.getElementById('ff-auto-toggle').classList.contains('on'),
      source: 'user',
    };

    const res = await api.post('/api/future-features/add', data);
    if (res.ok) {
      document.getElementById('ff-modal').classList.add('hidden');
      document.getElementById('ff-form').reset();
      document.getElementById('ff-auto-toggle').classList.add('on');
      u.toast('Feature added');
      const newData = await api.get('/api/future-features/list');
      currentFeatures = newData.features || [];
      document.getElementById('ff-list').innerHTML = renderFeatureList(currentFeatures, currentFilter, u);
    }
  });

  // Filter tabs
  container.querySelectorAll('.ff-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      currentFilter = tab.dataset.filter;
      container.querySelectorAll('.ff-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById('ff-list').innerHTML = renderFeatureList(currentFeatures, currentFilter, u);
    });
  });

  // Feature actions (delegation)
  document.getElementById('ff-list').addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;

    const featureId = btn.dataset.id;
    const action = btn.dataset.action;

    if (action === 'approve') {
      await api.post(`/api/future-features/${featureId}/approve`);
      u.toast('Feature approved');
    } else if (action === 'start') {
      const res = await api.post(`/api/future-features/${featureId}/start`);
      if (res.ok) {
        u.toast('Implementation started');
      } else {
        u.toast(res.error || 'Cannot start feature', 'error');
        return;
      }
    } else if (action === 'complete') {
      const summary = prompt('Implementation summary:');
      if (summary) {
        await api.post(`/api/future-features/${featureId}/complete`, { summary });
        u.toast('Feature completed');
      }
    } else if (action === 'fail') {
      const error = prompt('Failure reason:');
      if (error) {
        await api.post(`/api/future-features/${featureId}/fail`, { error });
        u.toast('Marked as failed');
      }
    } else if (action === 'retry') {
      const res = await api.post(`/api/future-features/${featureId}/retry`);
      if (res.ok) {
        u.toast('Retrying — implementation started');
      } else {
        u.toast(res.error || 'Cannot retry feature', 'error');
        return;
      }
    } else if (action === 'reject') {
      const reason = prompt('Rejection reason:');
      if (reason) {
        await api.post(`/api/future-features/${featureId}/reject`, { reason });
        u.toast('Feature rejected');
      }
    } else if (action === 'delete') {
      if (confirm('Permanently delete this feature?')) {
        await api.post(`/api/future-features/${featureId}/delete`);
        u.toast('Feature deleted');
      }
    }

    const newData = await api.get('/api/future-features/list');
    currentFeatures = newData.features || [];
    document.getElementById('ff-list').innerHTML = renderFeatureList(currentFeatures, currentFilter, u);
  });
}

function renderTab(id, label, count) {
  const isActive = id === 'all';
  return `<button data-filter="${id}" class="ff-tab evo-tab ${isActive ? 'active' : ''}">${label} <span class="ml-1 text-[10px] opacity-60">${count}</span></button>`;
}

function renderFeatureList(features, filter, u) {
  const filtered = filter === 'all'
    ? features
    : features.filter(f => {
        if (filter === 'implemented') return f.status === 'implemented' || f.status === 'completed';
        if (filter === 'failed') return f.status === 'failed' || f.status === 'deferred';
        return f.status === filter;
      });

  if (filtered.length === 0) {
    return `<div class="text-center py-12 text-xs text-zinc-600">No features found</div>`;
  }

  return filtered.map(f => {
    const statusInfo = metadata.statuses.find(s => s.value === f.status) || { emoji: '❓', label: f.status };
    const priorityBadge = {
      P0: 'badge-red',
      P1: 'badge-yellow',
      P2: 'badge-blue',
      P3: 'badge-zinc',
    }[f.priority] || 'badge-zinc';

    const statusBadge = {
      pending: 'badge-yellow',
      approval_required: 'badge-red',
      in_progress: 'badge-purple',
      implemented: 'badge-green',
      completed: 'badge-green',
      failed: 'badge-red',
      rejected: 'badge-zinc',
      cancelled: 'badge-zinc',
    }[f.status] || 'badge-zinc';

    const actions = [];
    if (f.status === 'approval_required') {
      actions.push(`<button data-action="approve" data-id="${f.id}" class="btn btn-primary btn-sm" style="padding:0.25rem 0.5rem;font-size:10px">Approve</button>`);
      actions.push(`<button data-action="reject" data-id="${f.id}" class="btn btn-danger btn-sm" style="padding:0.25rem 0.5rem;font-size:10px">Reject</button>`);
    } else if (f.status === 'pending') {
      actions.push(`<button data-action="start" data-id="${f.id}" class="btn btn-primary btn-sm" style="padding:0.25rem 0.5rem;font-size:10px">Start</button>`);
      actions.push(`<button data-action="reject" data-id="${f.id}" class="btn btn-danger btn-sm" style="padding:0.25rem 0.5rem;font-size:10px">Reject</button>`);
    } else if (f.status === 'in_progress') {
      actions.push(`<button data-action="complete" data-id="${f.id}" class="btn btn-primary btn-sm" style="padding:0.25rem 0.5rem;font-size:10px">Complete</button>`);
      actions.push(`<button data-action="fail" data-id="${f.id}" class="btn btn-danger btn-sm" style="padding:0.25rem 0.5rem;font-size:10px">Fail</button>`);
    } else if (f.status === 'failed' || f.status === 'deferred') {
      actions.push(`<button data-action="retry" data-id="${f.id}" class="btn btn-primary btn-sm" style="padding:0.25rem 0.5rem;font-size:10px">Retry</button>`);
      actions.push(`<button data-action="delete" data-id="${f.id}" class="btn btn-ghost btn-sm" style="padding:0.25rem 0.5rem;font-size:10px">Delete</button>`);
    } else {
      actions.push(`<button data-action="delete" data-id="${f.id}" class="btn btn-ghost btn-sm" style="padding:0.25rem 0.5rem;font-size:10px">Delete</button>`);
    }

    const timeAgo = (ts) => {
      if (!ts) return '';
      const s = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
      if (s < 60) return 'just now';
      if (s < 3600) return `${Math.floor(s / 60)}m ago`;
      if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
      return `${Math.floor(s / 86400)}d ago`;
    };

    return `
      <div class="stat-card">
        <div class="flex items-start justify-between gap-3">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap mb-1">
              <span class="text-sm">${statusInfo.emoji}</span>
              <span class="text-xs font-semibold text-white">${u.escapeHtml(f.title)}</span>
              <span class="badge ${priorityBadge}">${f.priority}</span>
              <span class="badge ${statusBadge}">${statusInfo.label}</span>
            </div>
            <p class="text-[11px] text-zinc-500 leading-relaxed">${u.escapeHtml(f.description)}</p>
            ${f.last_error && (f.status === 'failed' || f.status === 'deferred') ? `<p class="text-[10px] text-red-400/80 mt-1">Error: ${u.escapeHtml(f.last_error.substring(0, 200))}</p>` : ''}
            <div class="flex items-center gap-3 mt-2 text-[10px] text-zinc-600">
              <span>${f.source || 'unknown'}</span>
              <span>effort: ${f.estimated_effort || 'medium'}</span>
              <span>${timeAgo(f.created_at)}</span>
              ${f.implementation_attempts ? `<span>attempts: ${f.implementation_attempts}</span>` : ''}
            </div>
          </div>
          <div class="flex items-center gap-2 flex-shrink-0">
            ${actions.join('')}
          </div>
        </div>
      </div>
    `;
  }).join('');
}
