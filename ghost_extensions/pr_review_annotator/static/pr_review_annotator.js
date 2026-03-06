const state = {
  rules: null,
  loading: false,
  message: ''
};

function esc(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function statusBadge(level) {
  if (level === 'error') return 'badge badge-red';
  if (level === 'warning') return 'badge badge-yellow';
  return 'badge badge-blue';
}

function renderChecks() {
  const checks = Array.isArray(state.rules?.checks) ? state.rules.checks : [];
  if (!checks.length) {
    return '<div class="text-[11px] text-zinc-500">No review checks configured.</div>';
  }
  return checks
    .map((check) => {
      const id = esc(check.id || 'rule');
      const regex = esc(check.regex || '');
      const severity = esc(check.severity || 'warning');
      return `<div class="stat-card p-3">
        <div class="flex items-center justify-between gap-2">
          <code class="text-[11px] text-zinc-200">${id}</code>
          <span class="${statusBadge(severity)}">${severity}</span>
        </div>
        <div class="mt-2 text-[11px] text-zinc-400 break-all">${regex}</div>
      </div>`;
    })
    .join('');
}

function renderLayout(container) {
  container.innerHTML = `<div class="space-y-4">
    <div>
      <h1 class="page-header">PR Review Annotator</h1>
      <p class="page-desc">Configure and inspect PR review checks for the annotator extension.</p>
    </div>

    <div class="stat-card p-4 space-y-3">
      <div class="flex items-center justify-between">
        <h2 class="text-sm text-white font-semibold">Ruleset</h2>
        <button id="prra-reload" class="btn btn-secondary btn-sm">Reload</button>
      </div>
      <div id="prra-status" class="text-[11px] text-zinc-500"></div>
      <div id="prra-checks" class="grid gap-2"></div>
    </div>
  </div>`;
}

async function loadRules(container) {
  const statusEl = container.querySelector('#prra-status');
  const checksEl = container.querySelector('#prra-checks');
  state.loading = true;
  statusEl.textContent = 'Loading rules…';
  try {
    const payload = await window.GhostAPI.get('/extensions/pr_review_annotator/ruleset');
    const rules = payload?.ruleset;
    if (!rules || !Array.isArray(rules.checks)) {
      throw new Error('Malformed ruleset response');
    }
    state.rules = rules;
    statusEl.textContent = `Loaded ${rules.checks.length} checks.`;
    checksEl.innerHTML = renderChecks();
  } catch (err) {
    statusEl.textContent = `Failed to load ruleset: ${err?.message || err}`;
    checksEl.innerHTML = '<div class="text-[11px] text-red-400">Unable to load checks.</div>';
  } finally {
    state.loading = false;
  }
}

export async function render(container) {
  renderLayout(container);
  const reloadBtn = container.querySelector('#prra-reload');
  reloadBtn.addEventListener('click', async () => {
    if (state.loading) return;
    await loadRules(container);
  });
  await loadRules(container);
}
