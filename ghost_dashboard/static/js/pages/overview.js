/** Overview page */

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;
  const [status, feed] = await Promise.all([
    api.get('/api/status'),
    api.get('/api/feed'),
  ]);

  const s = status;
  const running = s.running;
  const paused = s.paused;
  const statusLabel = paused ? 'PAUSED' : running ? 'RUNNING' : 'STOPPED';
  const statusColor = paused ? 'yellow' : running ? 'green' : 'red';

  const featureKeys = ['tool_loop','memory','skills','plugins','browser','cron','vision','tts','security_audit','session_memory'];
  const featureLabels = { tool_loop:'Tool Loop', memory:'Memory', skills:'Skills', plugins:'Plugins', browser:'Browser', cron:'Cron', vision:'Vision', tts:'TTS', security_audit:'Security Audit', session_memory:'Session Memory' };

  const recentEntries = (feed.entries || []).slice(0, 5);

  container.innerHTML = `
    <h1 class="page-header">Overview</h1>
    <p class="page-desc">Ghost daemon status and quick controls</p>

    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="stat-card col-span-1 md:col-span-2">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-xs text-zinc-500 mb-1">Status</div>
            <div class="flex items-center gap-2">
              <span class="w-3 h-3 rounded-full bg-${statusColor === 'green' ? 'emerald' : statusColor === 'yellow' ? 'amber' : 'red'}-500 ${running && !paused ? 'animate-pulse' : ''}"></span>
              <span class="text-lg font-bold text-white">${statusLabel}</span>
              ${s.pid ? `<span class="text-xs text-zinc-500">PID ${s.pid}</span>` : ''}
            </div>
            <div class="text-xs text-zinc-500 mt-1">Model: <span class="text-zinc-300">${u.escapeHtml(s.model)}</span></div>
          </div>
          <div class="flex gap-2 flex-wrap">
            ${s.embedded ? '<button id="btn-reload" class="btn btn-sm btn-secondary" title="Hot-reload config">Reload</button>' : ''}
            <button id="btn-pause" class="btn btn-sm ${paused ? 'btn-primary' : 'btn-secondary'}">${paused ? 'Resume' : 'Pause'}</button>
            ${s.embedded ? '<button id="btn-restart" class="btn btn-sm btn-secondary" title="Restart Ghost daemon">Restart</button>' : ''}
            ${s.embedded ? '<button id="btn-shutdown" class="btn btn-sm btn-danger" title="Shut down Ghost completely">Shutdown</button>' : ''}
          </div>
        </div>
      </div>
      <div class="stat-card">
        <div class="text-xs text-zinc-500 mb-1">Today</div>
        <div class="text-2xl font-bold text-white">${s.today_actions}</div>
        <div class="text-xs text-zinc-500">actions</div>
      </div>
      <div class="stat-card">
        <div class="text-xs text-zinc-500 mb-1">Total</div>
        <div class="text-2xl font-bold text-white">${s.total_actions}</div>
        <div class="text-xs text-zinc-500">all time</div>
      </div>
    </div>

    ${s.live ? `
    <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
      <div class="stat-card text-center">
        <div class="text-xs text-zinc-500">Tools</div>
        <div class="text-lg font-bold text-white">${s.live.tools}</div>
      </div>
      <div class="stat-card text-center">
        <div class="text-xs text-zinc-500">Skills</div>
        <div class="text-lg font-bold text-white">${s.live.skills}</div>
      </div>
      <div class="stat-card text-center">
        <div class="text-xs text-zinc-500">Memory</div>
        <div class="text-lg font-bold text-white">${s.live.memory_entries}</div>
      </div>
      <div class="stat-card text-center">
        <div class="text-xs text-zinc-500">Cron Jobs</div>
        <div class="text-lg font-bold text-white">${s.live.cron_enabled}/${s.live.cron_jobs}</div>
      </div>
      <div class="stat-card text-center">
        <div class="text-xs text-zinc-500">Uptime</div>
        <div class="text-lg font-bold text-white">${s.uptime_seconds ? formatUptime(s.uptime_seconds) : '—'}</div>
      </div>
    </div>
    ` : `<div class="mb-6 p-3 rounded-lg" style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.2)">
      <div class="text-xs text-amber-400">Dashboard running in standalone mode — start Ghost to see live stats</div>
    </div>`}

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div>
        <h2 class="text-sm font-semibold text-zinc-400 mb-3">Features</h2>
        <div class="flex flex-wrap gap-2" id="feature-toggles">
          ${featureKeys.map(k => {
            const on = s.features[k];
            return `<button data-feature="${k}" class="badge ${on ? 'badge-green' : 'badge-zinc'} cursor-pointer hover:opacity-80 text-xs px-3 py-1">
              ${on ? '●' : '○'} ${featureLabels[k]}
            </button>`;
          }).join('')}
        </div>

        <h2 class="text-sm font-semibold text-zinc-400 mt-6 mb-3">Type Breakdown</h2>
        <div class="space-y-1.5">
          ${Object.entries(s.type_breakdown || {}).sort((a,b) => b[1]-a[1]).map(([type, count]) => {
            const pct = s.total_actions ? Math.round(count / s.total_actions * 100) : 0;
            return `<div class="flex items-center gap-2 text-xs">
              <span class="w-16 text-zinc-400">${u.TYPE_ICONS[type] || '❓'} ${type}</span>
              <div class="flex-1 h-2 bg-surface-700 rounded-full overflow-hidden">
                <div class="h-full bg-ghost-500/60 rounded-full" style="width:${pct}%"></div>
              </div>
              <span class="w-10 text-right text-zinc-500">${count}</span>
            </div>`;
          }).join('')}
        </div>
      </div>

      <div>
        <h2 class="text-sm font-semibold text-zinc-400 mb-3">Recent Activity</h2>
        <div class="space-y-2">
          ${recentEntries.length === 0 ? '<div class="text-xs text-zinc-600">No activity yet</div>' :
            recentEntries.map(e => `
              <div class="feed-entry type-${e.type || 'unknown'}">
                <div class="flex items-center gap-2 mb-1">
                  <span class="text-xs">${u.TYPE_ICONS[e.type] || '❓'}</span>
                  <span class="badge badge-${u.TYPE_COLORS[e.type] || 'zinc'}">${e.type}</span>
                  <span class="text-[10px] text-zinc-600 ml-auto">${u.timeAgo(e.time)}</span>
                </div>
                <div class="text-xs text-zinc-400 truncate">${u.escapeHtml((e.result || '').slice(0, 120))}</div>
              </div>
            `).join('')}
        </div>
      </div>
    </div>
  `;

  document.getElementById('btn-pause')?.addEventListener('click', async () => {
    if (paused) await api.post('/api/ghost/resume');
    else await api.post('/api/ghost/pause');
    u.toast(paused ? 'Resumed' : 'Paused');
    render(container);
  });

  document.getElementById('btn-reload')?.addEventListener('click', async () => {
    await api.post('/api/ghost/reload');
    u.toast('Config reloaded into daemon');
    render(container);
  });

  document.getElementById('btn-restart')?.addEventListener('click', async () => {
    if (!confirm('Restart Ghost? Active tasks will be interrupted.')) return;
    try {
      await api.post('/api/ghost/restart');
    } catch {
      // Expected — server may die before response completes
    }
    u.toast('Restarting...');
    container.innerHTML = '<div class="flex flex-col items-center justify-center h-64 gap-4"><div class="animate-spin w-8 h-8 border-2 border-ghost-500 border-t-transparent rounded-full"></div><div class="text-zinc-400 text-sm">Ghost is restarting...</div><div class="text-zinc-600 text-xs">This page will refresh automatically.</div></div>';
    const poll = setInterval(async () => {
      try {
        await api.get('/api/status');
        clearInterval(poll);
        u.toast('Ghost is back online');
        render(container);
      } catch {}
    }, 2000);
    setTimeout(() => clearInterval(poll), 30000);
  });

  document.getElementById('btn-shutdown')?.addEventListener('click', async () => {
    if (!confirm('Shut down Ghost completely? You will need to start it again from the terminal.')) return;
    const shutdownMsg = '<div class="flex flex-col items-center justify-center h-64 gap-4"><div class="text-zinc-400 text-lg font-semibold">Ghost has been shut down.</div><div class="text-zinc-600 text-sm">To start again, run:</div><div class="font-mono text-sm text-ghost-400 bg-surface-800 px-4 py-2 rounded-lg">./start.sh</div><div class="text-zinc-600 text-xs">or: python ghost_supervisor.py</div></div>';
    try {
      const res = await api.post('/api/ghost/shutdown');
      u.toast(res.message || 'Shutting down...');
    } catch {
      // Expected — server dies before response completes
    }
    container.innerHTML = shutdownMsg;
  });

  document.getElementById('feature-toggles')?.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-feature]');
    if (!btn) return;
    const key = btn.dataset.feature;
    const configKey = `enable_${key}`;
    const current = s.features[key];
    await api.put('/api/config', { [configKey]: !current });
    u.toast(`${featureLabels[key]} ${!current ? 'enabled' : 'disabled'}`);
    render(container);
  });
}

function formatUptime(secs) {
  if (secs < 60) return secs + 's';
  if (secs < 3600) return Math.floor(secs / 60) + 'm';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return h + 'h ' + m + 'm';
}
