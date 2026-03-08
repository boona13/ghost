/** Overview page — Ghost command center */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;
  const [status, feed, usage] = await Promise.all([
    api.get('/api/status'),
    api.get('/api/feed'),
    api.get('/api/usage/live').catch(() => ({})),
  ]);

  const s = status;
  const running = s.running;
  const paused = s.paused;
  const statusLabel = paused ? t('status.paused') : running ? t('status.runningStatus') : t('status.stopped');
  const statusColor = paused ? 'amber' : running ? 'emerald' : 'red';

  let modelDisplay = s.model || '\u2014';
  let providerPart = '';
  let modelPart = modelDisplay;
  if (modelDisplay.includes(':')) {
    const idx = modelDisplay.indexOf(':');
    providerPart = modelDisplay.slice(0, idx);
    modelPart = modelDisplay.slice(idx + 1);
  }

  const recentEntries = (feed.entries || []).slice(0, 8);

  const sessionTokens = usage.session_tokens || s.session_tokens || 0;
  const sessionCalls = usage.calls_this_session || s.calls_this_session || 0;

  const featureKeys = ['tool_loop','memory','skills','plugins','browser','cron','vision','tts','security_audit','session_memory'];
  const featureLabels = { tool_loop:t('overview.featureToolLoop'), memory:t('overview.featureMemory'), skills:t('overview.featureSkills'), plugins:t('overview.featurePlugins'), browser:t('overview.featureBrowser'), cron:t('overview.featureCron'), vision:t('overview.featureVision'), tts:t('overview.featureTts'), security_audit:t('overview.featureSecurityAudit'), session_memory:t('overview.featureSessionMemory') };
  const allFeaturesOn = featureKeys.every(k => s.features?.[k]);

  const quickActions = [
    { page: 'chat', icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/>', label: t('overview.qaChat'), desc: t('overview.qaChatDesc') },
    { page: 'skills', icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13 10V3L4 14h7v7l9-11h-7z"/>', label: t('overview.qaSkills'), desc: t('overview.qaSkillsDesc') },
    { page: 'memory', icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>', label: t('overview.qaMemory'), desc: t('overview.qaMemoryDesc') },
    { page: 'cron', icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>', label: t('overview.qaCron'), desc: t('overview.qaCronDesc') },
  ];

  container.innerHTML = `
    <div class="overview-hero mb-6">
      <div class="flex items-start justify-between gap-4 flex-wrap">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-3 mb-2">
            <span class="inline-block w-3 h-3 rounded-full bg-${statusColor}-500 ${running && !paused ? 'animate-pulse' : ''} flex-shrink-0"></span>
            <span class="text-lg font-bold text-white">${statusLabel}</span>
          </div>
          <div class="flex items-center gap-2 text-sm">
            ${providerPart ? `<span class="text-zinc-500">${u.escapeHtml(providerPart)}</span><span class="text-zinc-700">/</span>` : ''}
            <span class="text-zinc-200 font-medium">${u.escapeHtml(modelPart)}</span>
          </div>
        </div>
        <div class="flex items-center gap-4 flex-shrink-0">
          ${s.uptime_seconds ? `<div class="text-right"><div class="text-[10px] text-zinc-600 uppercase tracking-wider">${t('overview.uptime')}</div><div class="text-sm font-mono text-zinc-300">${formatUptime(s.uptime_seconds)}</div></div>` : ''}
          <div class="flex gap-2">
            ${s.embedded ? `<button id="btn-reload" class="btn btn-sm btn-secondary">${t('overview.reload')}</button>` : ''}
            <button id="btn-pause" class="btn btn-sm ${paused ? 'btn-primary' : 'btn-secondary'}">${paused ? t('overview.resume') : t('overview.pause')}</button>
            ${s.embedded ? `<button id="btn-restart" class="btn btn-sm btn-secondary">${t('overview.restart')}</button>` : ''}
            ${s.embedded ? `<button id="btn-shutdown" class="btn btn-sm btn-danger">${t('overview.shutdown')}</button>` : ''}
          </div>
        </div>
      </div>
    </div>

    ${s.live ? `
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
      <div class="metric-card" data-goto="feed">
        <div class="metric-card-label">${t('overview.sessionsToday')}</div>
        <div class="metric-card-value">${s.today_actions}</div>
        <div class="metric-card-sub">${s.total_actions} ${t('overview.allTime')}</div>
      </div>
      <div class="metric-card">
        <div class="metric-card-label">${t('overview.tokensSession')}</div>
        <div class="metric-card-value">${sessionTokens.toLocaleString()}</div>
        <div class="metric-card-sub">${sessionCalls} ${t('overview.llmCalls')}</div>
      </div>
      <div class="metric-card" data-goto="skills">
        <div class="metric-card-label">${t('overview.skills')}</div>
        <div class="metric-card-value">${s.live.skills}</div>
        <div class="metric-card-sub">${t('overview.skillsReady')}</div>
      </div>
      <div class="metric-card" data-goto="memory">
        <div class="metric-card-label">${t('overview.memory')}</div>
        <div class="metric-card-value">${s.live.memory_entries}</div>
        <div class="metric-card-sub">${t('overview.memoriesStored')}</div>
      </div>
    </div>
    ` : `<div class="mb-6 p-3 rounded-lg" style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.2)">
      <div class="text-xs text-amber-400">${t('overview.standaloneMode')}</div>
    </div>`}

    <div class="grid grid-cols-1 lg:grid-cols-5 gap-6 mb-6">
      <div class="lg:col-span-3">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-zinc-400">${t('overview.recentActivity')}</h2>
          <a href="#feed" class="text-[11px] text-ghost-400 hover:text-ghost-300 transition-colors">${t('overview.viewAll')} &rarr;</a>
        </div>
        <div class="space-y-2">
          ${recentEntries.length === 0 ? `<div class="text-xs text-zinc-600 py-8 text-center">${t('overview.noActivity')}</div>` :
            recentEntries.map(e => `
              <div class="feed-entry type-${e.type || 'unknown'}">
                <div class="flex items-center gap-2 mb-1">
                  <span class="text-xs">${u.TYPE_ICONS[e.type] || '\u2753'}</span>
                  <span class="badge badge-${u.TYPE_COLORS[e.type] || 'zinc'}">${e.type}</span>
                  <span class="text-[10px] text-zinc-600 ml-auto">${u.timeAgo(e.time)}</span>
                </div>
                <div class="text-xs text-zinc-400 line-clamp-2">${u.escapeHtml((e.result || '').slice(0, 200))}</div>
              </div>
            `).join('')}
        </div>
      </div>

      <div class="lg:col-span-2">
        <h2 class="text-sm font-semibold text-zinc-400 mb-3">${t('overview.quickActions')}</h2>
        <div class="grid grid-cols-2 gap-2 mb-4">
          ${quickActions.map(qa => `
            <div class="quick-action-card" data-goto="${qa.page}">
              <svg class="w-5 h-5 text-ghost-400 mb-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">${qa.icon}</svg>
              <div class="text-xs font-medium text-zinc-200">${qa.label}</div>
              <div class="text-[10px] text-zinc-600 mt-0.5">${qa.desc}</div>
            </div>
          `).join('')}
        </div>

        ${s.live ? `
        <h2 class="text-sm font-semibold text-zinc-400 mb-3">${t('overview.systemHealth')}</h2>
        <div class="stat-card">
          <div class="space-y-2">
            <div class="health-item">
              <span class="health-dot health-dot-ok"></span>
              <span class="text-xs text-zinc-300">${t('overview.healthModel')}</span>
              <span class="text-[10px] text-zinc-500 ml-auto font-mono">${u.escapeHtml(modelPart)}</span>
            </div>
            <div class="health-item">
              <span class="health-dot ${s.live.cron_enabled === s.live.cron_jobs ? 'health-dot-ok' : 'health-dot-warn'}"></span>
              <span class="text-xs text-zinc-300">${t('overview.healthCron')}</span>
              <span class="text-[10px] text-zinc-500 ml-auto">${s.live.cron_enabled}/${s.live.cron_jobs}</span>
            </div>
            <div class="health-item">
              <span class="health-dot health-dot-ok"></span>
              <span class="text-xs text-zinc-300">${t('overview.healthMemory')}</span>
              <span class="text-[10px] text-zinc-500 ml-auto">${s.live.memory_entries} ${t('common.entries')}</span>
            </div>
            <div class="health-item">
              <span class="health-dot health-dot-ok"></span>
              <span class="text-xs text-zinc-300">${t('overview.healthTools')}</span>
              <span class="text-[10px] text-zinc-500 ml-auto">${s.live.tools} ${t('overview.registered')}</span>
            </div>
          </div>
        </div>
        ` : ''}
      </div>
    </div>

    ${!allFeaturesOn ? `
    <div class="mb-6">
      <h2 class="text-sm font-semibold text-zinc-400 mb-3">${t('overview.features')}</h2>
      <div class="flex flex-wrap gap-2" id="feature-toggles">
        ${featureKeys.map(k => {
          const on = s.features?.[k];
          return `<button data-feature="${k}" class="badge ${on ? 'badge-green' : 'badge-zinc'} cursor-pointer hover:opacity-80 text-xs px-3 py-1">
            ${on ? '\u25CF' : '\u25CB'} ${featureLabels[k]}
          </button>`;
        }).join('')}
      </div>
    </div>
    ` : ''}
  `;

  // Navigation for metric cards and quick actions
  container.querySelectorAll('[data-goto]').forEach(el => {
    el.style.cursor = 'pointer';
    el.addEventListener('click', () => {
      window.location.hash = '#' + el.dataset.goto;
    });
  });

  document.getElementById('btn-pause')?.addEventListener('click', async () => {
    if (paused) await api.post('/api/ghost/resume');
    else await api.post('/api/ghost/pause');
    u.toast(paused ? t('overview.resumed') : t('overview.paused'));
    render(container);
  });

  document.getElementById('btn-reload')?.addEventListener('click', async () => {
    await api.post('/api/ghost/reload');
    u.toast(t('overview.configReloaded'));
    render(container);
  });

  document.getElementById('btn-restart')?.addEventListener('click', async () => {
    if (!confirm(t('overview.restartConfirm'))) return;
    try {
      await api.post('/api/ghost/restart');
    } catch {
      // Expected — server may die before response completes
    }
    u.toast(t('overview.restarting'));
    container.innerHTML = `<div class="flex flex-col items-center justify-center h-64 gap-4"><div class="animate-spin w-8 h-8 border-2 border-ghost-500 border-t-transparent rounded-full"></div><div class="text-zinc-400 text-sm">${t('overview.ghostRestarting')}</div><div class="text-zinc-600 text-xs">${t('overview.refreshAuto')}</div></div>`;
    const poll = setInterval(async () => {
      try {
        await api.get('/api/status');
        clearInterval(poll);
        u.toast(t('overview.ghostBack'));
        render(container);
      } catch {}
    }, 2000);
    setTimeout(() => clearInterval(poll), 30000);
  });

  document.getElementById('btn-shutdown')?.addEventListener('click', async () => {
    if (!confirm(t('overview.shutdownConfirm'))) return;
    const shutdownMsg = `<div class="flex flex-col items-center justify-center h-64 gap-4"><div class="text-zinc-400 text-lg font-semibold">${t('overview.ghostShutdown')}</div><div class="text-zinc-600 text-sm">${t('overview.toStartAgain')}</div><div class="font-mono text-sm text-ghost-400 bg-surface-800 px-4 py-2 rounded-lg">./start.sh</div><div class="text-zinc-600 text-xs">${t('overview.altStartCmd')}</div></div>`;
    try {
      const res = await api.post('/api/ghost/shutdown');
      u.toast(res.message || t('overview.shuttingDown'));
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
    u.toast(`${featureLabels[key]} ${!current ? t('common.enabled') : t('common.disabled')}`);
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
