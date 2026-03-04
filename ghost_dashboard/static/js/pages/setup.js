/** Multi-provider setup wizard */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

const PROVIDER_META = {
  openrouter: {
    name: 'OpenRouter',
    icon: '🌐', badge: t('setup.badgeRecommended'), badgeColor: 'purple',
    desc: t('setup.descOpenRouter'),
    keyPrefix: 'sk-or-', keyPlaceholder: 'sk-or-v1-...',
    keyHelp: 'Get yours at <a href="https://openrouter.ai/keys" target="_blank" class="text-ghost-400 hover:text-ghost-300 underline">openrouter.ai/keys</a>',
  },
  'openai-codex': {
    name: 'OpenAI Codex',
    icon: '⚡', badge: t('setup.badgeFreeSubscription'), badgeColor: 'green',
    desc: t('setup.descCodex'),
    authType: 'oauth',
  },
  openai: {
    name: 'OpenAI',
    icon: '🤖', badge: t('setup.badgePaid'), badgeColor: 'blue',
    desc: t('setup.descOpenAI'),
    keyPrefix: 'sk-', keyPlaceholder: 'sk-...',
    keyHelp: 'Get yours at <a href="https://platform.openai.com/api-keys" target="_blank" class="text-ghost-400 hover:text-ghost-300 underline">platform.openai.com</a>',
  },
  anthropic: {
    name: 'Anthropic',
    icon: '🧠', badge: t('setup.badgePaid'), badgeColor: 'yellow',
    desc: t('setup.descAnthropic'),
    keyPrefix: 'sk-ant-', keyPlaceholder: 'sk-ant-...',
    keyHelp: 'Get yours at <a href="https://console.anthropic.com/settings/keys" target="_blank" class="text-ghost-400 hover:text-ghost-300 underline">console.anthropic.com</a>',
  },
  google: {
    name: 'Google',
    icon: '💎', badge: t('setup.badgeFreeTier'), badgeColor: 'green',
    desc: t('setup.descGoogle'),
    keyPrefix: 'AIza', keyPlaceholder: 'AIza...',
    keyHelp: 'Get yours at <a href="https://aistudio.google.com/apikey" target="_blank" class="text-ghost-400 hover:text-ghost-300 underline">aistudio.google.com</a>',
  },
  xai: {
    name: 'xAI',
    icon: '🚀', badge: t('setup.badgePaid'), badgeColor: 'blue',
    desc: t('setup.descXai'),
    keyPrefix: 'xai-', keyPlaceholder: 'xai-... or xai-api-key-...',
    keyHelp: 'Get yours at <a href="https://console.x.ai/" target="_blank" class="text-ghost-400 hover:text-ghost-300 underline">console.x.ai</a>',
  },
  ollama: {
    name: 'Ollama',
    icon: '🦙', badge: t('setup.badgeFreeLocal'), badgeColor: 'green',
    desc: t('setup.descOllama'),
    authType: 'none',
  },
  deepseek: {
    name: 'DeepSeek',
    icon: '🔍', badge: t('setup.badgePaid'), badgeColor: 'blue',
    desc: t('setup.descDeepSeek'),
    keyPrefix: 'sk-', keyPlaceholder: 'sk-...',
    keyHelp: 'Get yours at <a href="https://platform.deepseek.com/api_keys" target="_blank" class="text-ghost-400 hover:text-ghost-300 underline">platform.deepseek.com</a>',
  },
};

let selectedProviders = [];
let currentStep = 1;
let doctorLastResult = null;

async function fetchDoctorStatus(api) {
  try {
    const res = await api.get('/api/setup/doctor/status');
    return res || { ok: false, checks: [] };
  } catch {
    return { ok: false, checks: [], error: 'Failed to load setup doctor status' };
  }
}

function renderDoctorPanel(status = {}, runResult = null) {
  const checks = Array.isArray(status.checks) ? status.checks : [];
  const blockers = checks.filter(c => c?.severity === 'blocker').length;
  const warnings = checks.filter(c => c?.severity === 'warning').length;
  const healthy = checks.filter(c => c?.status === 'ok').length;

  return `
    <div class="stat-card mt-4">
      <div class="flex items-center justify-between gap-3 mb-3">
        <div>
          <h3 class="text-sm font-semibold text-white">${t('setup.setupDoctor')}</h3>
          <p class="text-xs text-zinc-400">${t('setup.preflight')}</p>
        </div>
        <span class="badge ${blockers > 0 ? 'badge-red' : warnings > 0 ? 'badge-yellow' : 'badge-green'} text-[10px]">
          ${blockers > 0 ? `${blockers} ${t('setup.blockers')}` : warnings > 0 ? `${warnings} ${t('setup.warnings')}` : t('security.healthy')}
        </span>
      </div>

      <div class="grid grid-cols-3 gap-2 mb-3">
        <div class="bg-surface-700 rounded p-2 border border-surface-600/40">
          <div class="text-[10px] text-zinc-500">${t('setup.checks')}</div>
          <div class="text-sm text-white font-semibold">${checks.length}</div>
        </div>
        <div class="bg-surface-700 rounded p-2 border border-surface-600/40">
          <div class="text-[10px] text-zinc-500">${t('security.healthy')}</div>
          <div class="text-sm text-emerald-400 font-semibold">${healthy}</div>
        </div>
        <div class="bg-surface-700 rounded p-2 border border-surface-600/40">
          <div class="text-[10px] text-zinc-500">${t('setup.blockers')}</div>
          <div class="text-sm text-red-400 font-semibold">${blockers}</div>
        </div>
      </div>

      <div class="flex gap-2 mb-3">
        <button id="doctor-run-dry" class="btn btn-secondary btn-sm">${t('setup.runDryScan')}</button>
        <button id="doctor-fix-all" class="btn btn-primary btn-sm">${t('setup.applySafeFixes')}</button>
      </div>

      <div class="space-y-1 max-h-44 overflow-y-auto pr-1">
        ${checks.length === 0 ? `<div class="text-xs text-zinc-500">${t('setup.noChecks')}</div>` : checks.map(c => `
          <div class="bg-surface-700 border border-surface-600/40 rounded p-2">
            <div class="flex items-center justify-between">
              <div class="text-xs text-zinc-200">${c?.title || c?.id || t('setup.check')}</div>
              <span class="badge ${c?.severity === 'blocker' ? 'badge-red' : c?.severity === 'warning' ? 'badge-yellow' : 'badge-green'} text-[10px]">${c?.severity || c?.status || 'info'}</span>
            </div>
            ${c?.message ? `<div class="text-[11px] text-zinc-400 mt-1">${c.message}</div>` : ''}
          </div>
        `).join('')}
      </div>

      ${runResult ? `<div class="mt-3 text-[11px] text-zinc-300 bg-surface-700 border border-surface-600/40 rounded p-2">${runResult}</div>` : ''}
    </div>
  `;
}

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;
  selectedProviders = [];
  currentStep = 1;

  container.innerHTML = `
    <div class="max-w-2xl mx-auto mt-8">
      <div class="text-center mb-8">
        <pre class="text-ghost-500/70 text-[10px] leading-[1.1] inline-block">  ██████  ██  ██
 ██       ████
 ██  ███  ██  ██
  ██████  ██  ██</pre>
        <h1 class="text-3xl font-bold text-white mt-4">${t('setup.welcome')}</h1>
        <p class="text-zinc-400 mt-2">${t('setup.letsConnect')}</p>
      </div>

      <div class="flex items-center justify-center gap-2 mb-8" id="step-indicator">
        ${[1,2,3,4].map(s => `
          <div class="step-dot ${s === 1 ? 'active' : ''}" data-step="${s}">
            <div class="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold
              ${s === 1 ? 'bg-ghost-600 text-white' : 'bg-surface-800 text-zinc-500 border border-surface-600/30'}">${s}</div>
            <div class="text-[10px] mt-1 ${s === 1 ? 'text-ghost-400' : 'text-zinc-600'}">${[t('setup.choose'), t('setup.configureStep'), t('setup.confirmStep'), t('setup.doneStep')][s-1]}</div>
          </div>
          ${s < 4 ? '<div class="w-8 h-px bg-surface-600/30 mt-[-10px]"></div>' : ''}
        `).join('')}
      </div>

      <div id="wizard-content"></div>
    </div>
  `;

  const doctorStatus = await fetchDoctorStatus(api);
  container.insertAdjacentHTML('beforeend', renderDoctorPanel(doctorStatus, doctorLastResult));

  const dryBtn = document.getElementById('doctor-run-dry');
  const fixBtn = document.getElementById('doctor-fix-all');

  if (dryBtn) {
    dryBtn.addEventListener('click', async () => {
      dryBtn.disabled = true;
      try {
        const res = await api.post('/api/setup/doctor/run', { dry_run: true, steps: [] });
        doctorLastResult = (res && (res.summary || res.message)) ? (res.summary || res.message) : t('config.dryRunCompleted');
      } catch {
        doctorLastResult = t('config.dryRunFailed');
      }
      await render(container);
      dryBtn.disabled = false;
    });
  }

  if (fixBtn) {
    fixBtn.addEventListener('click', async () => {
      if (!confirm(t('setup.confirmFixAll'))) return;
      fixBtn.disabled = true;
      try {
        const res = await api.post('/api/setup/doctor/fix-all', { confirm: true });
        doctorLastResult = (res && (res.summary || res.message)) ? (res.summary || res.message) : t('config.safeFixesApplied');
      } catch {
        doctorLastResult = t('config.fixAllFailed');
      }
      await render(container);
      fixBtn.disabled = false;
    });
  }

  renderStep1(container, api, u);
}

function updateStepIndicator(step) {
  currentStep = step;
  document.querySelectorAll('.step-dot').forEach(dot => {
    const s = parseInt(dot.dataset.step);
    const circle = dot.querySelector('div:first-child');
    const label = dot.querySelector('div:last-child');
    if (s <= step) {
      circle.className = 'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold bg-ghost-600 text-white';
      label.className = 'text-[10px] mt-1 text-ghost-400';
    } else {
      circle.className = 'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold bg-surface-800 text-zinc-500 border border-surface-600/30';
      label.className = 'text-[10px] mt-1 text-zinc-600';
    }
  });
}

function renderStep1(container, api, u) {
  const content = document.getElementById('wizard-content');
  content.innerHTML = `
    <div class="stat-card">
      <h2 class="text-lg font-semibold text-white mb-1">${t('setup.chooseProviders')}</h2>
      <p class="text-sm text-zinc-400 mb-4">${t('setup.chooseProvidersDesc')}</p>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3" id="provider-cards"></div>
      <div class="flex justify-end mt-6">
        <button id="btn-step1-next" class="btn btn-primary" disabled>${t('setup.continue')}</button>
      </div>
    </div>
  `;

  const grid = document.getElementById('provider-cards');
  const providers = Object.keys(PROVIDER_META);

  providers.forEach(pid => {
    const meta = PROVIDER_META[pid];
    const card = document.createElement('div');
    card.className = 'provider-select-card p-4 rounded-lg border border-surface-600/30 bg-surface-800 cursor-pointer transition-all hover:border-ghost-500/40';
    card.dataset.provider = pid;
    card.innerHTML = `
      <div class="flex items-start gap-3">
        <span class="text-2xl">${meta.icon}</span>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <span class="text-sm font-medium text-white">${meta.name || pid.charAt(0).toUpperCase() + pid.slice(1)}</span>
            <span class="badge badge-${meta.badgeColor} text-[10px]">${meta.badge}</span>
          </div>
          <p class="text-xs text-zinc-500">${meta.desc}</p>
        </div>
        <div class="provider-check w-5 h-5 rounded border border-surface-600/50 flex items-center justify-center flex-shrink-0 mt-0.5">
        </div>
      </div>
    `;
    card.addEventListener('click', () => toggleProvider(pid, card));
    grid.appendChild(card);
  });

  document.getElementById('btn-step1-next').addEventListener('click', () => {
    if (selectedProviders.length > 0) {
      updateStepIndicator(2);
      renderStep2(container, api, u);
    }
  });
}

function toggleProvider(pid, card) {
  const idx = selectedProviders.indexOf(pid);
  const check = card.querySelector('.provider-check');
  if (idx >= 0) {
    selectedProviders.splice(idx, 1);
    card.classList.remove('border-ghost-500', 'bg-ghost-900/20');
    card.classList.add('border-surface-600/30');
    check.innerHTML = '';
  } else {
    selectedProviders.push(pid);
    card.classList.add('border-ghost-500', 'bg-ghost-900/20');
    card.classList.remove('border-surface-600/30');
    check.innerHTML = '<svg class="w-3.5 h-3.5 text-ghost-400" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>';
  }
  const btn = document.getElementById('btn-step1-next');
  btn.disabled = selectedProviders.length === 0;
}

function renderStep2(container, api, u) {
  const content = document.getElementById('wizard-content');
  content.innerHTML = `
    <div class="space-y-4" id="config-cards"></div>
    <div class="flex justify-between mt-6">
      <button id="btn-step2-back" class="btn btn-ghost">${t('common.back')}</button>
      <button id="btn-step2-next" class="btn btn-primary" disabled>${t('setup.continue')}</button>
    </div>
  `;

  const cards = document.getElementById('config-cards');
  const configStatus = {};

  selectedProviders.forEach((pid, i) => {
    const meta = PROVIDER_META[pid];
    configStatus[pid] = false;
    const card = document.createElement('div');
    card.className = 'stat-card';
    card.id = `config-${pid}`;

    if (meta.authType === 'oauth') {
      card.innerHTML = `
        <div class="flex items-start gap-3 mb-3">
          <span class="text-xl">${meta.icon}</span>
          <div class="flex-1">
            <h3 class="text-sm font-semibold text-white">${t('setup.codexTitle')}</h3>
            <p class="text-xs text-zinc-500 mt-0.5">${t('setup.codexDesc')}</p>
          </div>
          <div class="config-status-${pid}"></div>
        </div>
        <button class="btn btn-primary w-full oauth-btn" data-provider="${pid}">
          <span class="oauth-text">${t('setup.signInChatgpt')}</span>
          <span class="oauth-spinner hidden">
            <svg class="animate-spin h-4 w-4 inline mr-1" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
            ${t('setup.waitingLogin')}
          </span>
        </button>
        <p class="text-[10px] text-zinc-600 mt-2">${t('setup.opensBrowser')}</p>
      `;
    } else if (meta.authType === 'none') {
      card.innerHTML = `
        <div class="flex items-start gap-3 mb-3">
          <span class="text-xl">${meta.icon}</span>
          <div class="flex-1">
            <h3 class="text-sm font-semibold text-white">${t('setup.ollamaTitle')}</h3>
            <p class="text-xs text-zinc-500 mt-0.5">${t('setup.ollamaDesc')}</p>
          </div>
          <div class="config-status-${pid}"></div>
        </div>
        <button class="btn btn-secondary w-full detect-btn" data-provider="${pid}">${t('setup.detectOllama')}</button>
        <p class="text-[10px] text-zinc-600 mt-2">Install from <a href="https://ollama.com" target="_blank" class="text-ghost-400 underline">ollama.com</a> if not installed.</p>
      `;
    } else {
      const provName = meta.name || pid.charAt(0).toUpperCase() + pid.slice(1);
      card.innerHTML = `
        <div class="flex items-start gap-3 mb-3">
          <span class="text-xl">${meta.icon}</span>
          <div class="flex-1">
            <h3 class="text-sm font-semibold text-white">${provName}</h3>
            <p class="text-xs text-zinc-500 mt-0.5">${meta.desc}</p>
          </div>
          <div class="config-status-${pid}"></div>
        </div>
        <div class="space-y-2">
          <input type="password" class="form-input w-full font-mono text-sm provider-key" data-provider="${pid}" placeholder="${meta.keyPlaceholder || 'API key...'}" autocomplete="off">
          <p class="text-[10px] text-zinc-600">${meta.keyHelp || ''}</p>
          <div class="flex gap-2">
            <button class="btn btn-secondary flex-1 test-btn" data-provider="${pid}">${t('integrations.testConnection')}</button>
            <button class="btn btn-primary flex-1 save-btn" data-provider="${pid}">${t('common.save')}</button>
          </div>
          <div class="provider-error-${pid} text-xs text-red-400 hidden"></div>
        </div>
      `;
    }

    cards.appendChild(card);
  });

  function checkAllConfigured() {
    const allDone = selectedProviders.every(pid => configStatus[pid]);
    document.getElementById('btn-step2-next').disabled = !allDone;
  }

  function markConfigured(pid, success) {
    configStatus[pid] = success;
    const statusEl = document.querySelector(`.config-status-${pid}`);
    if (statusEl) {
      statusEl.innerHTML = success
        ? '<span class="text-emerald-400 text-sm">✓</span>'
        : '';
    }
    checkAllConfigured();
  }

  // API key save handlers
  cards.querySelectorAll('.save-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const pid = btn.dataset.provider;
      const input = cards.querySelector(`.provider-key[data-provider="${pid}"]`);
      const key = input.value.trim();
      const errorEl = cards.querySelector(`.provider-error-${pid}`);
      errorEl.classList.add('hidden');

      if (!key) {
        errorEl.textContent = t('setup.apiKeyRequired');
        errorEl.classList.remove('hidden');
        return;
      }

      btn.disabled = true;
      btn.textContent = t('common.saving');
      try {
        await api.post(`/api/setup/providers/${pid}/configure`, { api_key: key });
        markConfigured(pid, true);
        u.toast(`${pid} ${t('setup.saved')}`);
      } catch (e) {
        errorEl.textContent = e.message || t('setup.saveFailed');
        errorEl.classList.remove('hidden');
      } finally {
        btn.disabled = false;
        btn.textContent = t('common.save');
      }
    });
  });

  // Test handlers
  cards.querySelectorAll('.test-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const pid = btn.dataset.provider;
      const input = cards.querySelector(`.provider-key[data-provider="${pid}"]`);
      const key = input?.value.trim() || '';
      const errorEl = cards.querySelector(`.provider-error-${pid}`);
      errorEl.classList.add('hidden');

      btn.disabled = true;
      btn.textContent = t('common.testing');
      try {
        const result = await api.post(`/api/setup/providers/${pid}/test`, { api_key: key });
        if (result.ok) {
          u.toast(`${pid} ${t('setup.connectionOK')}`);
          markConfigured(pid, true);
        } else {
          errorEl.textContent = result.error || t('setup.connectionFailed');
          errorEl.classList.remove('hidden');
        }
      } catch (e) {
        errorEl.textContent = e.message;
        errorEl.classList.remove('hidden');
      } finally {
        btn.disabled = false;
        btn.textContent = t('integrations.testConnection');
      }
    });
  });

  // OAuth handler
  cards.querySelectorAll('.oauth-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const text = btn.querySelector('.oauth-text');
      const spinner = btn.querySelector('.oauth-spinner');
      text.classList.add('hidden');
      spinner.classList.remove('hidden');
      btn.disabled = true;

      try {
        await api.post('/api/setup/oauth/codex/start');

        const poll = setInterval(async () => {
          try {
            const status = await api.get('/api/setup/oauth/codex/status');
            if (status.configured) {
              clearInterval(poll);
              text.textContent = t('setup.codexConnected');
              text.classList.remove('hidden');
              spinner.classList.add('hidden');
              markConfigured('openai-codex', true);
              u.toast(t('setup.codexOauthConnected'));
            }
          } catch {}
        }, 2000);

        setTimeout(() => clearInterval(poll), 300000);
      } catch (e) {
        text.classList.remove('hidden');
        spinner.classList.add('hidden');
        btn.disabled = false;
        u.toast(t('setup.oauthFailed') + ' ' + e.message, 'error');
      }
    });
  });

  // Ollama detect handler
  cards.querySelectorAll('.detect-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = t('setup.detecting');
      try {
        const result = await api.post('/api/setup/providers/ollama/test');
        if (result.ok) {
          await api.post('/api/setup/providers/ollama/configure', {});
          markConfigured('ollama', true);
          u.toast(t('setup.ollamaDetected', {n: result.count || 0}));
        } else {
          u.toast(t('setup.ollamaNotRunning') + ' ' + (result.error || ''), 'error');
        }
      } catch (e) {
        u.toast(t('setup.detectionFailed') + ' ' + e.message, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = t('setup.detectOllama');
      }
    });
  });

  document.getElementById('btn-step2-back').addEventListener('click', () => {
    updateStepIndicator(1);
    renderStep1(container, api, u);
  });

  document.getElementById('btn-step2-next').addEventListener('click', () => {
    updateStepIndicator(3);
    renderStep3(container, api, u);
  });
}

function renderStep3(container, api, u) {
  const content = document.getElementById('wizard-content');
  const provList = selectedProviders.map((pid, i) => {
    const meta = PROVIDER_META[pid];
    const name = meta.name || pid.charAt(0).toUpperCase() + pid.slice(1);
    return `
      <label class="flex items-center gap-3 p-3 rounded-lg bg-surface-800 border border-surface-600/30 cursor-pointer hover:border-ghost-500/30 transition-all">
        <input type="radio" name="primary-provider" value="${pid}" class="accent-purple-500" ${i === 0 ? 'checked' : ''}>
        <span class="text-lg">${meta.icon}</span>
        <span class="text-sm text-white flex-1">${name}</span>
        <span class="text-emerald-400 text-xs">${t('status.connected')}</span>
      </label>
    `;
  }).join('');

  content.innerHTML = `
    <div class="stat-card">
      <h2 class="text-lg font-semibold text-white mb-1">${t('setup.allSet')}</h2>
      <p class="text-sm text-zinc-400 mb-4">${t('setup.providersConfigured', {n: selectedProviders.length})}</p>
      <div class="text-xs text-zinc-500 mb-2">${t('setup.primaryProvider')}</div>
      <div class="space-y-2 mb-6">${provList}</div>
      <div class="grid grid-cols-2 gap-3 mb-6">
        <div class="p-3 rounded-lg bg-surface-800 border border-surface-600/30">
          <div class="text-sm font-medium text-white">${t('setup.multiFallback')}</div>
          <div class="text-xs text-zinc-500 mt-1">${t('setup.multiFallbackDesc')}</div>
        </div>
        <div class="p-3 rounded-lg bg-surface-800 border border-surface-600/30">
          <div class="text-sm font-medium text-white">${t('setup.autoTokenRefresh')}</div>
          <div class="text-xs text-zinc-500 mt-1">${t('setup.autoTokenRefreshDesc')}</div>
        </div>
      </div>
      <button id="btn-launch" class="btn btn-primary w-full">${t('setup.startGhost')}</button>
    </div>
  `;

  document.getElementById('btn-launch').addEventListener('click', async () => {
    const primaryRadio = content.querySelector('input[name="primary-provider"]:checked');
    const primary = primaryRadio?.value || selectedProviders[0] || 'openrouter';

    await api.put('/api/primary-provider', { provider: primary });

    if (selectedProviders.includes('openrouter')) {
      const key = document.querySelector('.provider-key[data-provider="openrouter"]')?.value?.trim();
      if (key) {
        await api.post('/api/setup/complete', { api_key: key });
      }
    }

    await api.put('/api/setup/provider-order', { order: selectedProviders });

    updateStepIndicator(4);
    window.location.href = window.location.pathname + '#chat';
    setTimeout(() => window.location.reload(), 100);
  });
}
