/** Webhooks page — Event-driven triggers for Ghost autonomy */

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  let triggers, templates, history, configData;
  try {
    [triggers, templates, history, configData] = await Promise.all([
      api.get('/api/webhooks/triggers'),
      api.get('/api/webhooks/templates'),
      api.get('/api/webhooks/history'),
      api.get('/api/config'),
    ]);
  } catch (e) {
    container.innerHTML = `<h1 class="page-header">Webhooks</h1>
      <div class="stat-card"><p class="text-zinc-500 text-sm">Webhook system not available. Make sure Ghost is running.</p></div>`;
    return;
  }

  const triggerList = triggers.triggers || [];
  const templateMap = templates.templates || {};
  const events = (history.events || []).reverse();
  const secret = configData?.config?.webhook_secret || '';
  const hasSecret = secret.length > 0;

  const statusBadge = (enabled) => enabled
    ? '<span class="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-medium">enabled</span>'
    : '<span class="text-[9px] px-1.5 py-0.5 rounded-full bg-zinc-600/50 text-zinc-500 font-medium">disabled</span>';

  const eventStatusColor = (s) => ({
    dispatched: 'text-emerald-400', completed: 'text-emerald-400',
    auth_failed: 'text-red-400', hmac_failed: 'text-red-400',
    error: 'text-red-400', cooldown: 'text-amber-400',
    concurrency_limit: 'text-amber-400',
  }[s] || 'text-zinc-400');

  const eventStatusDot = (s) => {
    const c = {
      dispatched: 'bg-emerald-400', completed: 'bg-emerald-400',
      auth_failed: 'bg-red-400', hmac_failed: 'bg-red-400',
      error: 'bg-red-400', cooldown: 'bg-amber-400',
      concurrency_limit: 'bg-amber-400',
    }[s] || 'bg-zinc-600';
    return `<span class="inline-block w-1.5 h-1.5 rounded-full ${c}"></span>`;
  };

  container.innerHTML = `
    <h1 class="page-header">Webhooks</h1>
    <p class="page-desc">Event-driven triggers — external services fire Ghost actions in real-time via HTTP POST</p>

    ${!hasSecret ? `
    <div class="stat-card mb-6 border border-amber-500/30">
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/>
        </svg>
        <div>
          <div class="text-sm font-medium text-amber-400">Webhook secret not configured</div>
          <p class="text-xs text-zinc-400 mt-1">All webhook requests will be rejected until you set a <code class="text-xs bg-surface-700 px-1 py-0.5 rounded">webhook_secret</code> in <a href="#config" class="text-ghost-400 hover:underline">Configuration</a>.</p>
          <div class="mt-3 flex gap-2">
            <button id="wh-gen-secret" class="text-[10px] px-3 py-1.5 rounded bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 font-medium">Generate Secret</button>
          </div>
        </div>
      </div>
      <div id="wh-secret-result" class="text-xs mt-3 hidden"></div>
    </div>
    ` : ''}

    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
      <div class="stat-card">
        <div class="text-2xl font-bold text-white">${triggerList.length}</div>
        <div class="text-xs text-zinc-500">Triggers</div>
      </div>
      <div class="stat-card">
        <div class="text-2xl font-bold ${hasSecret ? 'text-emerald-400' : 'text-red-400'}">${hasSecret ? 'Active' : 'No Secret'}</div>
        <div class="text-xs text-zinc-500">Auth Status</div>
      </div>
      <div class="stat-card">
        <div class="text-2xl font-bold text-white">${events.length}</div>
        <div class="text-xs text-zinc-500">Recent Events</div>
      </div>
    </div>

    <div class="stat-card mb-6">
      <h3 class="text-sm font-semibold text-white mb-3">Create Trigger</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div>
          <label class="form-label">Name</label>
          <input id="wh-name" type="text" class="form-input w-full" placeholder="e.g. GitHub Push Review">
        </div>
        <div>
          <label class="form-label">Template</label>
          <select id="wh-template" class="form-input w-full">
            <option value="">Custom (write your own prompt)</option>
            ${Object.entries(templateMap).map(([id, t]) =>
              `<option value="${id}">${u.escapeHtml(t.name)}</option>`
            ).join('')}
          </select>
        </div>
      </div>

      <div id="wh-custom-fields">
        <div class="mb-3">
          <label class="form-label">Prompt Template</label>
          <textarea id="wh-prompt" class="form-input w-full h-24" placeholder="Use {field_name} placeholders that map to payload paths.\nExample: A push to {repository} on branch {branch} by {pusher}..."></textarea>
        </div>
        <div class="mb-3">
          <label class="form-label">Extract Fields <span class="text-zinc-600">(JSON: variable name → payload dot-path)</span></label>
          <textarea id="wh-fields" class="form-input w-full h-16 font-mono text-xs" placeholder='{"repository": "repository.full_name", "branch": "ref"}'></textarea>
        </div>
        <div class="mb-3">
          <label class="form-label">Event Type</label>
          <input id="wh-event-type" type="text" class="form-input w-full" placeholder="generic" value="generic">
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div>
          <label class="form-label">Cooldown (seconds)</label>
          <input id="wh-cooldown" type="number" class="form-input w-full" value="30" min="0">
        </div>
        <div>
          <label class="form-label">HMAC Header <span class="text-zinc-600">(optional)</span></label>
          <input id="wh-hmac-header" type="text" class="form-input w-full" placeholder="X-Hub-Signature-256">
        </div>
      </div>

      <button id="btn-create-wh" class="btn btn-primary">Create Trigger</button>
      <div id="wh-create-result" class="text-xs mt-2 hidden"></div>
    </div>

    ${triggerList.length > 0 ? `
    <h3 class="text-sm font-semibold text-white mb-3">Configured Triggers</h3>
    <div class="space-y-3 mb-6" id="wh-trigger-list">
      ${triggerList.map(t => `
        <div class="stat-card">
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-3">
              <div class="toggle ${t.enabled ? 'on' : ''}" data-wh-toggle="${t.id}"><span class="toggle-dot"></span></div>
              <span class="font-semibold text-sm text-white">${u.escapeHtml(t.name)}</span>
              ${statusBadge(t.enabled)}
              <span class="text-[9px] px-1.5 py-0.5 rounded bg-surface-600/50 text-zinc-500">${u.escapeHtml(t.event_type)}</span>
            </div>
            <div class="flex gap-2">
              <button class="btn-copy-url text-[10px] px-2 py-1 rounded bg-surface-600 text-zinc-400 hover:bg-surface-500" data-id="${t.id}">Copy URL</button>
              <button class="btn-test-wh text-[10px] px-2 py-1 rounded bg-blue-500/20 text-blue-400 hover:bg-blue-500/30" data-id="${t.id}">Test</button>
              <button class="btn-del-wh text-[10px] px-2 py-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20" data-id="${t.id}">Delete</button>
            </div>
          </div>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-zinc-400">
            <div>ID: <span class="text-zinc-300 font-mono">${u.escapeHtml(t.id)}</span></div>
            <div>Cooldown: <span class="text-zinc-300">${t.cooldown_seconds}s</span></div>
            <div>Created: <span class="text-zinc-300">${t.created_at ? u.timeAgo(t.created_at) : '—'}</span></div>
            <div>Last fired: <span class="text-zinc-300">${t.last_fired > 0 ? u.timeAgo(new Date(t.last_fired * 1000).toISOString()) : 'never'}</span></div>
          </div>
          <div class="mt-2">
            <div class="text-[10px] text-zinc-600 mb-1">Endpoint URL:</div>
            <code class="text-[11px] text-ghost-400 bg-surface-700 px-2 py-1 rounded block break-all">${window.location.origin}/api/webhooks/${u.escapeHtml(t.id)}</code>
          </div>
          <details class="mt-2">
            <summary class="text-[10px] text-zinc-600 cursor-pointer hover:text-zinc-400">Prompt template</summary>
            <pre class="text-[11px] text-zinc-400 bg-surface-700 rounded p-2 mt-1 whitespace-pre-wrap max-h-32 overflow-y-auto">${u.escapeHtml(t.prompt_template || '(none)')}</pre>
          </details>
        </div>
      `).join('')}
    </div>
    ` : ''}

    <h3 class="text-sm font-semibold text-zinc-400 mb-3">Recent Events</h3>
    <div id="wh-history" class="stat-card">
      ${events.length === 0
        ? '<div class="text-xs text-zinc-600 py-4 text-center">No webhook events yet</div>'
        : events.slice(0, 30).map(e => `
          <div class="flex items-center gap-2 py-2 border-b border-surface-600/30 last:border-0">
            ${eventStatusDot(e.status)}
            <span class="text-[10px] px-1.5 py-0.5 rounded bg-surface-600 text-zinc-400 font-mono">${u.escapeHtml(e.trigger_id)}</span>
            <span class="text-[11px] ${eventStatusColor(e.status)} font-medium">${u.escapeHtml(e.status)}</span>
            <span class="text-[11px] text-zinc-500 flex-1 truncate">${u.escapeHtml(e.detail || '')}</span>
            <span class="text-[10px] text-zinc-600">${e.timestamp ? u.timeAgo(e.timestamp) : ''}</span>
          </div>
        `).join('')
      }
    </div>

    <div class="mt-6 stat-card">
      <h3 class="text-sm font-semibold text-zinc-400 mb-3">Integration Guide</h3>
      <div class="text-xs text-zinc-500 space-y-2">
        <p>External services send a <code class="bg-surface-700 px-1 py-0.5 rounded text-zinc-400">POST</code> request to the trigger URL with a JSON payload.</p>
        <p>Every request must include the header: <code class="bg-surface-700 px-1 py-0.5 rounded text-zinc-400">Authorization: Bearer &lt;webhook_secret&gt;</code></p>
        <details>
          <summary class="cursor-pointer hover:text-zinc-300 font-medium">Example: cURL</summary>
          <pre class="bg-surface-700 rounded p-3 mt-2 text-[11px] text-zinc-400 whitespace-pre-wrap">curl -X POST ${window.location.origin}/api/webhooks/YOUR_TRIGGER_ID \\
  -H "Authorization: Bearer YOUR_SECRET" \\
  -H "Content-Type: application/json" \\
  -d '{"key": "value"}'</pre>
        </details>
        <details>
          <summary class="cursor-pointer hover:text-zinc-300 font-medium">Example: GitHub Webhook Setup</summary>
          <div class="bg-surface-700 rounded p-3 mt-2 text-[11px] text-zinc-400 space-y-1">
            <p>1. Create a trigger using the "GitHub Push" template above</p>
            <p>2. Go to your GitHub repo → Settings → Webhooks → Add webhook</p>
            <p>3. Set <strong>Payload URL</strong> to the trigger's endpoint URL</p>
            <p>4. Set <strong>Content type</strong> to <code>application/json</code></p>
            <p>5. Set <strong>Secret</strong> to your <code>webhook_secret</code> from Ghost config</p>
            <p>6. Select events: Pushes, Pull requests, Issues, etc.</p>
          </div>
        </details>
      </div>
    </div>
  `;

  // ── Generate secret ──
  container.querySelector('#wh-gen-secret')?.addEventListener('click', async () => {
    const btn = container.querySelector('#wh-gen-secret');
    btn.disabled = true;
    btn.textContent = 'Generating...';
    try {
      const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
      let secret = 'ghst_wh_';
      const arr = new Uint8Array(32);
      crypto.getRandomValues(arr);
      for (const b of arr) secret += chars[b % chars.length];

      await api.post('/api/config', { webhook_secret: secret });

      const resultDiv = container.querySelector('#wh-secret-result');
      resultDiv.classList.remove('hidden');
      resultDiv.className = 'text-xs mt-3 text-emerald-400';
      resultDiv.innerHTML = `Secret set! <code class="bg-surface-700 px-1.5 py-0.5 rounded text-ghost-400 select-all">${u.escapeHtml(secret)}</code> — save this, it won't be shown again.`;
      btn.textContent = 'Done!';
      setTimeout(() => render(container), 3000);
    } catch (e) {
      const resultDiv = container.querySelector('#wh-secret-result');
      resultDiv.classList.remove('hidden');
      resultDiv.className = 'text-xs mt-3 text-red-400';
      resultDiv.textContent = `Error: ${e.message}`;
      btn.disabled = false;
      btn.textContent = 'Generate Secret';
    }
  });

  // ── Template toggle ──
  const tmplSelect = container.querySelector('#wh-template');
  const customFields = container.querySelector('#wh-custom-fields');
  tmplSelect?.addEventListener('change', () => {
    if (tmplSelect.value) {
      customFields.classList.add('hidden');
    } else {
      customFields.classList.remove('hidden');
    }
  });

  // ── Create trigger ──
  container.querySelector('#btn-create-wh')?.addEventListener('click', async () => {
    const name = container.querySelector('#wh-name').value.trim();
    if (!name) { u.toast('Name is required', 'error'); return; }

    const templateId = container.querySelector('#wh-template').value;
    const resultDiv = container.querySelector('#wh-create-result');

    let body;
    if (templateId) {
      body = { name, template_id: templateId, cooldown_seconds: parseInt(container.querySelector('#wh-cooldown').value) || 30 };
    } else {
      const prompt = container.querySelector('#wh-prompt').value.trim();
      if (!prompt) { u.toast('Prompt template is required for custom triggers', 'error'); return; }

      let extractFields = {};
      const fieldsText = container.querySelector('#wh-fields').value.trim();
      if (fieldsText) {
        try {
          extractFields = JSON.parse(fieldsText);
        } catch (e) {
          u.toast('Extract fields must be valid JSON', 'error');
          return;
        }
      }

      body = {
        name,
        prompt_template: prompt,
        event_type: container.querySelector('#wh-event-type').value || 'generic',
        extract_fields: extractFields,
        cooldown_seconds: parseInt(container.querySelector('#wh-cooldown').value) || 30,
        hmac_header: container.querySelector('#wh-hmac-header').value.trim(),
      };
    }

    const btn = container.querySelector('#btn-create-wh');
    btn.disabled = true;
    btn.textContent = 'Creating...';

    try {
      const res = await api.post('/api/webhooks/triggers', body);
      if (res.ok) {
        u.toast(`Trigger "${name}" created`);
        render(container);
      } else {
        resultDiv.classList.remove('hidden');
        resultDiv.className = 'text-xs mt-2 text-red-400';
        resultDiv.textContent = res.error || 'Failed to create trigger';
        btn.disabled = false;
        btn.textContent = 'Create Trigger';
      }
    } catch (e) {
      resultDiv.classList.remove('hidden');
      resultDiv.className = 'text-xs mt-2 text-red-400';
      resultDiv.textContent = `Error: ${e.message}`;
      btn.disabled = false;
      btn.textContent = 'Create Trigger';
    }
  });

  // ── Toggle enable/disable ──
  container.querySelectorAll('[data-wh-toggle]').forEach(el => {
    el.addEventListener('click', async () => {
      const id = el.dataset.whToggle;
      const isOn = el.classList.contains('on');
      try {
        const res = await fetch(`/api/webhooks/triggers/${id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: !isOn }),
        });
        const data = await res.json();
        if (data.ok) {
          u.toast(isOn ? 'Trigger disabled' : 'Trigger enabled');
          render(container);
        }
      } catch (e) {
        u.toast(`Error: ${e.message}`, 'error');
      }
    });
  });

  // ── Copy URL ──
  container.querySelectorAll('.btn-copy-url').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.id;
      const url = `${window.location.origin}/api/webhooks/${id}`;
      navigator.clipboard.writeText(url).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy URL'; }, 1500);
      });
    });
  });

  // ── Test trigger ──
  container.querySelectorAll('.btn-test-wh').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.id;
      btn.textContent = 'Testing...';
      btn.disabled = true;
      try {
        const configRes = await api.get('/api/config');
        const sec = configRes?.config?.webhook_secret || '';
        const res = await fetch(`/api/webhooks/${id}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${sec}`,
          },
          body: JSON.stringify({ test: true, message: 'Dashboard test event', timestamp: new Date().toISOString() }),
        });
        const data = await res.json();
        btn.textContent = data.ok ? 'Fired!' : 'Failed';
        if (data.ok) u.toast('Test webhook fired');
        else u.toast(data.error || 'Test failed', 'error');
      } catch (e) {
        btn.textContent = 'Error';
        u.toast(`Error: ${e.message}`, 'error');
      }
      setTimeout(() => { btn.textContent = 'Test'; btn.disabled = false; }, 2000);
    });
  });

  // ── Delete trigger ──
  container.querySelectorAll('.btn-del-wh').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.id;
      if (!confirm(`Delete trigger "${id}"?`)) return;
      try {
        await api.del(`/api/webhooks/triggers/${id}`);
        u.toast('Trigger deleted');
        render(container);
      } catch (e) {
        u.toast(`Error: ${e.message}`, 'error');
      }
    });
  });
}
