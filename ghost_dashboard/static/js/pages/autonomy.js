/** Autonomy page — Action Items + Growth Log */

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  const [actionsData, logData, statusData] = await Promise.all([
    api.get('/api/autonomy/actions'),
    api.get('/api/autonomy/growth-log'),
    api.get('/api/autonomy/status'),
  ]);

  const actions = actionsData.items || [];
  const growthLog = logData.entries || [];
  const routines = statusData.routines || [];
  const crashReport = statusData.crash_report;

  const priorityBadge = (p) => {
    const colors = { critical: 'bg-red-500/20 text-red-400', warning: 'bg-amber-500/20 text-amber-400', info: 'bg-blue-500/20 text-blue-400' };
    return `<span class="text-[10px] px-1.5 py-0.5 rounded-full font-medium ${colors[p] || colors.info}">${p}</span>`;
  };

  const categoryIcon = (c) => {
    const icons = { api_key: '🔑', integration: '🔗', config: '⚙️', security: '🛡️' };
    return icons[c] || '📋';
  };

  const timeAgo = (ts) => {
    if (!ts) return '';
    const d = new Date(ts);
    const s = Math.floor((Date.now() - d.getTime()) / 1000);
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.floor(s/60)}m ago`;
    if (s < 86400) return `${Math.floor(s/3600)}h ago`;
    return `${Math.floor(s/86400)}d ago`;
  };

  const msTimeAgo = (ms) => {
    if (!ms) return 'never';
    return timeAgo(new Date(ms).toISOString());
  };

  container.innerHTML = `
    <h1 class="page-header">Autonomy</h1>
    <p class="page-desc">Ghost's autonomous growth system — self-improvement, action items, and activity log</p>

    ${crashReport ? `
    <div class="stat-card mb-6" style="border: 1px solid rgba(239,68,68,0.3); background: rgba(239,68,68,0.05);">
      <div class="flex items-center gap-2 mb-2">
        <svg class="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/></svg>
        <h3 class="text-sm font-semibold text-red-400">Crash Detected</h3>
        <span class="text-[10px] text-zinc-500 ml-auto">${crashReport.timestamp || ''}</span>
      </div>
      <div class="text-xs text-zinc-400">Exit code ${crashReport.exit_code} — Ghost is attempting self-repair (crash #${crashReport.crash_count})</div>
    </div>
    ` : ''}

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div class="lg:col-span-1 space-y-6">
        <div class="stat-card">
          <h3 class="text-sm font-semibold text-white mb-3">Action Items
            ${actions.length > 0 ? `<span class="ml-2 text-[10px] bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded-full">${actions.length}</span>` : ''}
          </h3>
          <div id="action-items-list" class="space-y-3">
            ${actions.length === 0 ? '<div class="text-xs text-zinc-600 py-4 text-center">No pending action items</div>' :
              actions.map(a => `
                <div class="p-3 bg-surface-700/50 rounded-lg border border-surface-600/30" data-action-id="${a.id}">
                  <div class="flex items-start gap-2">
                    <span class="text-lg">${categoryIcon(a.category)}</span>
                    <div class="flex-1 min-w-0">
                      <div class="flex items-center gap-2 mb-1">
                        <span class="text-xs font-medium text-zinc-200">${u.escapeHtml(a.title)}</span>
                        ${priorityBadge(a.priority)}
                      </div>
                      <div class="text-[11px] text-zinc-500 leading-relaxed">${u.escapeHtml(a.description)}</div>
                      <div class="flex gap-2 mt-2">
                        <button class="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 btn-resolve" data-id="${a.id}">Resolve</button>
                        <button class="text-[10px] px-2 py-0.5 rounded bg-zinc-700 text-zinc-400 hover:bg-zinc-600 btn-dismiss" data-id="${a.id}">Dismiss</button>
                      </div>
                    </div>
                  </div>
                </div>
              `).join('')}
          </div>
        </div>

        <div class="stat-card">
          <h3 class="text-sm font-semibold text-white mb-3">Growth Routines</h3>
          <div class="space-y-2">
            ${routines.map(r => `
              <div class="flex items-center justify-between py-1.5 border-b border-surface-600/30 last:border-0">
                <div>
                  <div class="text-xs text-zinc-300">${u.escapeHtml(r.name)}</div>
                  <div class="text-[10px] text-zinc-600">${r.schedule || 'not scheduled'}</div>
                </div>
                <div class="text-right">
                  <div class="text-[10px] ${r.last_status === 'ok' ? 'text-emerald-400' : r.last_status === 'error' ? 'text-red-400' : 'text-zinc-600'}">
                    ${r.last_status || 'never run'}
                  </div>
                  <div class="text-[10px] text-zinc-600">${msTimeAgo(r.last_run)}</div>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      </div>

      <div class="lg:col-span-2">
        <div class="stat-card">
          <h3 class="text-sm font-semibold text-white mb-3">Growth Log
            <span class="ml-2 text-[10px] text-zinc-600">${growthLog.length} entries</span>
          </h3>
          <div id="growth-log-list" class="space-y-3 max-h-[600px] overflow-y-auto">
            ${growthLog.length === 0 ? '<div class="text-xs text-zinc-600 py-8 text-center">No growth activity yet. Ghost will start improving autonomously based on the configured schedules.</div>' :
              growthLog.map(e => `
                <div class="flex gap-3 p-3 bg-surface-700/30 rounded-lg">
                  <div class="flex-shrink-0 w-8 h-8 rounded-full bg-ghost-500/20 flex items-center justify-center">
                    <span class="text-xs">${routineIcon(e.routine)}</span>
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 mb-0.5">
                      <span class="text-[10px] font-medium text-ghost-400">${u.escapeHtml(e.routine || '')}</span>
                      <span class="text-[10px] text-zinc-600">${timeAgo(e.timestamp)}</span>
                    </div>
                    <div class="text-xs text-zinc-300">${u.escapeHtml(e.summary || '')}</div>
                    ${e.details ? `<div class="text-[11px] text-zinc-500 mt-1">${u.escapeHtml(e.details).substring(0, 200)}</div>` : ''}
                  </div>
                </div>
              `).join('')}
          </div>
        </div>
      </div>
    </div>
  `;

  container.querySelectorAll('.btn-resolve').forEach(btn => {
    btn.addEventListener('click', async () => {
      await api.post('/api/autonomy/actions/' + btn.dataset.id + '/resolve');
      u.toast('Action item resolved');
      render(container);
    });
  });

  container.querySelectorAll('.btn-dismiss').forEach(btn => {
    btn.addEventListener('click', async () => {
      await api.post('/api/autonomy/actions/' + btn.dataset.id + '/dismiss');
      u.toast('Action item dismissed');
      render(container);
    });
  });
}

function routineIcon(routine) {
  const icons = {
    tech_scout: '🔭', health_check: '💚', user_context: '👤',
    skill_improver: '⚡', soul_evolver: '🧬', bug_hunter: '🐛',
    self_repair: '🔧', competitive_intel: '🕵️', content_health: '📄',
    security_patrol: '🛡️', visual_monitor: '👁️',
  };
  return icons[routine] || '🤖';
}
