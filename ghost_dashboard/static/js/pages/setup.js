/** Multi-provider setup wizard */

const PROVIDER_META = {
  openrouter: {
    name: 'OpenRouter',
    icon: '🌐', badge: 'Recommended', badgeColor: 'purple',
    desc: 'Access 200+ models with one API key. Pay per token.',
    keyPrefix: 'sk-or-', keyPlaceholder: 'sk-or-v1-...',
    keyHelp: 'Get yours at <a href="https://openrouter.ai/keys" target="_blank" class="text-ghost-400 hover:text-ghost-300 underline">openrouter.ai/keys</a>',
  },
  'openai-codex': {
    name: 'OpenAI Codex',
    icon: '⚡', badge: 'Free w/ subscription', badgeColor: 'green',
    desc: 'Use your ChatGPT Plus/Pro subscription. No extra cost.',
    authType: 'oauth',
  },
  openai: {
    name: 'OpenAI',
    icon: '🤖', badge: 'Paid', badgeColor: 'blue',
    desc: 'Direct OpenAI API access. Pay per token.',
    keyPrefix: 'sk-', keyPlaceholder: 'sk-...',
    keyHelp: 'Get yours at <a href="https://platform.openai.com/api-keys" target="_blank" class="text-ghost-400 hover:text-ghost-300 underline">platform.openai.com</a>',
  },
  anthropic: {
    name: 'Anthropic',
    icon: '🧠', badge: 'Paid', badgeColor: 'yellow',
    desc: 'Direct Claude API access. Pay per token.',
    keyPrefix: 'sk-ant-', keyPlaceholder: 'sk-ant-...',
    keyHelp: 'Get yours at <a href="https://console.anthropic.com/settings/keys" target="_blank" class="text-ghost-400 hover:text-ghost-300 underline">console.anthropic.com</a>',
  },
  google: {
    name: 'Google',
    icon: '💎', badge: 'Free tier', badgeColor: 'green',
    desc: 'Google AI API with generous free tier.',
    keyPrefix: 'AIza', keyPlaceholder: 'AIza...',
    keyHelp: 'Get yours at <a href="https://aistudio.google.com/apikey" target="_blank" class="text-ghost-400 hover:text-ghost-300 underline">aistudio.google.com</a>',
  },
  xai: {
    name: 'xAI',
    icon: '🚀', badge: 'Paid', badgeColor: 'blue',
    desc: 'Direct xAI API access for Grok models. Pay per token.',
    keyPrefix: 'xai-', keyPlaceholder: 'xai-... or xai-api-key-...',
    keyHelp: 'Get yours at <a href="https://console.x.ai/" target="_blank" class="text-ghost-400 hover:text-ghost-300 underline">console.x.ai</a>',
  },
  ollama: {
    name: 'Ollama',
    icon: '🦙', badge: 'Free / Local', badgeColor: 'green',
    desc: 'Run models locally. Completely free. Requires Ollama installed.',
    authType: 'none',
  },
  deepseek: {
    name: 'DeepSeek',
    icon: '🔍', badge: 'Paid', badgeColor: 'blue',
    desc: 'High-performance open-source LLMs with strong coding capabilities.',
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
          <h3 class="text-sm font-semibold text-white">Setup Doctor</h3>
          <p class="text-xs text-zinc-400">Preflight scan and safe auto-fix workflow.</p>
        </div>
        <span class="badge ${blockers > 0 ? 'badge-red' : warnings > 0 ? 'badge-yellow' : 'badge-green'} text-[10px]">
          ${blockers > 0 ? `${blockers} blocker${blockers === 1 ? '' : 's'}` : warnings > 0 ? `${warnings} warning${warnings === 1 ? '' : 's'}` : 'Healthy'}
        </span>
      </div>

      <div class="grid grid-cols-3 gap-2 mb-3">
        <div class="bg-surface-700 rounded p-2 border border-surface-600/40">
          <div class="text-[10px] text-zinc-500">Checks</div>
          <div class="text-sm text-white font-semibold">${checks.length}</div>
        </div>
        <div class="bg-surface-700 rounded p-2 border border-surface-600/40">
          <div class="text-[10px] text-zinc-500">Healthy</div>
          <div class="text-sm text-emerald-400 font-semibold">${healthy}</div>
        </div>
        <div class="bg-surface-700 rounded p-2 border border-surface-600/40">
          <div class="text-[10px] text-zinc-500">Blockers</div>
          <div class="text-sm text-red-400 font-semibold">${blockers}</div>
        </div>
      </div>

      <div class="flex gap-2 mb-3">
        <button id="doctor-run-dry" class="btn btn-secondary btn-sm">Run dry scan</button>
        <button id="doctor-fix-all" class="btn btn-primary btn-sm">Apply safe fixes</button>
      </div>

      <div class="space-y-1 max-h-44 overflow-y-auto pr-1">
        ${checks.length === 0 ? '<div class="text-xs text-zinc-500">No checks reported yet.</div>' : checks.map(c => `
          <div class="bg-surface-700 border border-surface-600/40 rounded p-2">
            <div class="flex items-center justify-between">
              <div class="text-xs text-zinc-200">${c?.title || c?.id || 'Check'}</div>
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
        <h1 class="text-3xl font-bold text-white mt-4">Welcome to Ghost</h1>
        <p class="text-zinc-400 mt-2">Let's connect your AI providers.</p>
      </div>

      <div class="flex items-center justify-center gap-2 mb-8" id="step-indicator">
        ${[1,2,3,4].map(s => `
          <div class="step-dot ${s === 1 ? 'active' : ''}" data-step="${s}">
            <div class="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold
              ${s === 1 ? 'bg-ghost-600 text-white' : 'bg-surface-800 text-zinc-500 border border-surface-600/30'}">${s}</div>
            <div class="text-[10px] mt-1 ${s === 1 ? 'text-ghost-400' : 'text-zinc-600'}">${['Choose','Configure','Confirm','Done'][s-1]}</div>
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
        doctorLastResult = (res && (res.summary || res.message)) ? (res.summary || res.message) : 'Dry run completed.';
      } catch {
        doctorLastResult = 'Dry run failed.';
      }
      await render(container);
      dryBtn.disabled = false;
    });
  }

  if (fixBtn) {
    fixBtn.addEventListener('click', async () => {
      if (!confirm('Apply all safe setup fixes now?')) return;
      fixBtn.disabled = true;
      try {
        const res = await api.post('/api/setup/doctor/fix-all', { confirm: true });
        doctorLastResult = (res && (res.summary || res.message)) ? (res.summary || res.message) : 'Safe fixes applied.';
      } catch {
        doctorLastResult = 'Fix-all failed.';
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
      <h2 class="text-lg font-semibold text-white mb-1">Choose your AI providers</h2>
      <p class="text-sm text-zinc-400 mb-4">Select one or more. You can always add more later from the Models page.</p>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3" id="provider-cards"></div>
      <div class="flex justify-end mt-6">
        <button id="btn-step1-next" class="btn btn-primary" disabled>Continue</button>
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
      <button id="btn-step2-back" class="btn btn-ghost">Back</button>
      <button id="btn-step2-next" class="btn btn-primary" disabled>Continue</button>
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
            <h3 class="text-sm font-semibold text-white">OpenAI Codex</h3>
            <p class="text-xs text-zinc-500 mt-0.5">Sign in with your ChatGPT account</p>
          </div>
          <div class="config-status-${pid}"></div>
        </div>
        <button class="btn btn-primary w-full oauth-btn" data-provider="${pid}">
          <span class="oauth-text">Sign in with ChatGPT</span>
          <span class="oauth-spinner hidden">
            <svg class="animate-spin h-4 w-4 inline mr-1" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
            Waiting for login...
          </span>
        </button>
        <p class="text-[10px] text-zinc-600 mt-2">Opens your browser to sign in via auth.openai.com</p>
      `;
    } else if (meta.authType === 'none') {
      card.innerHTML = `
        <div class="flex items-start gap-3 mb-3">
          <span class="text-xl">${meta.icon}</span>
          <div class="flex-1">
            <h3 class="text-sm font-semibold text-white">Ollama (Local)</h3>
            <p class="text-xs text-zinc-500 mt-0.5">No API key needed — runs locally</p>
          </div>
          <div class="config-status-${pid}"></div>
        </div>
        <button class="btn btn-secondary w-full detect-btn" data-provider="${pid}">Detect Ollama</button>
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
            <button class="btn btn-secondary flex-1 test-btn" data-provider="${pid}">Test Connection</button>
            <button class="btn btn-primary flex-1 save-btn" data-provider="${pid}">Save</button>
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
        errorEl.textContent = 'API key is required';
        errorEl.classList.remove('hidden');
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Saving...';
      try {
        await api.post(`/api/setup/providers/${pid}/configure`, { api_key: key });
        markConfigured(pid, true);
        u.toast(`${pid} saved`);
      } catch (e) {
        errorEl.textContent = e.message || 'Save failed';
        errorEl.classList.remove('hidden');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Save';
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
      btn.textContent = 'Testing...';
      try {
        const result = await api.post(`/api/setup/providers/${pid}/test`, { api_key: key });
        if (result.ok) {
          u.toast(`${pid} connection OK`);
          markConfigured(pid, true);
        } else {
          errorEl.textContent = result.error || 'Connection failed';
          errorEl.classList.remove('hidden');
        }
      } catch (e) {
        errorEl.textContent = e.message;
        errorEl.classList.remove('hidden');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Test Connection';
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
              text.textContent = 'Connected!';
              text.classList.remove('hidden');
              spinner.classList.add('hidden');
              markConfigured('openai-codex', true);
              u.toast('Codex OAuth connected');
            }
          } catch {}
        }, 2000);

        setTimeout(() => clearInterval(poll), 300000);
      } catch (e) {
        text.classList.remove('hidden');
        spinner.classList.add('hidden');
        btn.disabled = false;
        u.toast('OAuth failed: ' + e.message, 'error');
      }
    });
  });

  // Ollama detect handler
  cards.querySelectorAll('.detect-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = 'Detecting...';
      try {
        const result = await api.post('/api/setup/providers/ollama/test');
        if (result.ok) {
          await api.post('/api/setup/providers/ollama/configure', {});
          markConfigured('ollama', true);
          u.toast(`Ollama detected (${result.count || 0} models)`);
        } else {
          u.toast('Ollama not running: ' + (result.error || ''), 'error');
        }
      } catch (e) {
        u.toast('Detection failed: ' + e.message, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Detect Ollama';
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
        <span class="text-emerald-400 text-xs">Connected</span>
      </label>
    `;
  }).join('');

  content.innerHTML = `
    <div class="stat-card">
      <h2 class="text-lg font-semibold text-white mb-1">You're all set!</h2>
      <p class="text-sm text-zinc-400 mb-4">${selectedProviders.length} provider${selectedProviders.length !== 1 ? 's' : ''} configured. Select your primary provider — Ghost will try it first and fall back to others if it fails.</p>
      <div class="text-xs text-zinc-500 mb-2">Primary provider (tried first):</div>
      <div class="space-y-2 mb-6">${provList}</div>
      <div class="grid grid-cols-2 gap-3 mb-6">
        <div class="p-3 rounded-lg bg-surface-800 border border-surface-600/30">
          <div class="text-sm font-medium text-white">Multi-Provider Fallback</div>
          <div class="text-xs text-zinc-500 mt-1">If one provider fails, Ghost falls through to the next</div>
        </div>
        <div class="p-3 rounded-lg bg-surface-800 border border-surface-600/30">
          <div class="text-sm font-medium text-white">Auto Token Refresh</div>
          <div class="text-xs text-zinc-500 mt-1">OAuth tokens are refreshed automatically before expiry</div>
        </div>
      </div>
      <button id="btn-launch" class="btn btn-primary w-full">Start Ghost</button>
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
