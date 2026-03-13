/** Goals page — persistent multi-step user goals with autonomous execution */

let currentGoals = [];
let currentFilter = 'all';

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  const [listData, statsData] = await Promise.all([
    api.get('/api/goals/list'),
    api.get('/api/goals/stats'),
  ]);

  currentGoals = listData.goals || [];
  const stats = statsData || {};

  container.innerHTML = `
    <div class="flex items-center justify-between mb-1">
      <h1 class="page-header">Goals</h1>
      <button id="goal-add-btn" class="btn btn-primary btn-sm flex items-center gap-1.5">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
        New Goal
      </button>
    </div>
    <p class="page-desc">Persistent multi-step goals executed autonomously — recurring tasks, long-horizon projects, weekly reports.</p>

    <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
      ${statCard('Total', stats.total || 0, 'text-zinc-300')}
      ${statCard('Active', stats.active || 0, 'text-emerald-400')}
      ${statCard('Needs Plan', stats.pending_plan || 0, 'text-amber-400')}
      ${statCard('Paused', stats.paused || 0, 'text-zinc-500')}
      ${statCard('Completed', stats.completed || 0, 'text-ghost-400')}
    </div>

    <div class="border-b border-surface-600/30 mb-4">
      <nav class="flex gap-1">
        ${tab('all', 'All', currentGoals.length)}
        ${tab('active', 'Active', stats.active || 0)}
        ${tab('pending_plan', 'Needs Plan', stats.pending_plan || 0)}
        ${tab('paused', 'Paused', stats.paused || 0)}
        ${tab('completed', 'Completed', stats.completed || 0)}
        ${tab('abandoned', 'Abandoned', stats.abandoned || 0)}
      </nav>
    </div>

    <div id="goal-list" class="space-y-3">
      ${renderList(currentGoals, currentFilter)}
    </div>

    <!-- Add Goal Modal -->
    <div id="goal-modal" class="hidden fixed inset-0 z-50 flex items-center justify-center" style="background:rgba(0,0,0,0.7)">
      <div class="stat-card w-full max-w-lg mx-4" style="border-color:rgba(139,92,246,0.3);max-height:90vh;overflow-y:auto">
        <h3 class="text-sm font-bold text-white mb-4">New Goal</h3>
        <form id="goal-form" class="space-y-3">
          <div>
            <label class="form-label">Title</label>
            <input type="text" id="goal-title" required placeholder="e.g. Weekly AI News Digest" class="form-input w-full">
          </div>
          <div>
            <label class="form-label">Goal Description</label>
            <textarea id="goal-text" rows="3" required placeholder="Describe what Ghost should do — be specific about steps and output." class="form-input w-full" style="resize:vertical"></textarea>
          </div>
          <div>
            <label class="form-label">Recurrence <span class="text-zinc-500 font-normal">(optional cron expression)</span></label>
            <input type="text" id="goal-recurrence" placeholder="e.g. 0 9 * * 1  (every Monday 9am)" class="form-input w-full font-mono text-xs">
            <div class="flex flex-wrap gap-1.5 mt-1.5" id="recurrence-presets">
              ${['0 9 * * 1|Every Mon 9am','0 9 * * *|Every day 9am','0 9 * * 1-5|Weekdays 9am','0 9 1 * *|Monthly'].map(p => {
                const [val, label] = p.split('|');
                return `<button type="button" class="recurrence-preset text-[10px] px-2 py-0.5 rounded-full border border-zinc-700 text-zinc-400 hover:border-ghost-500 hover:text-ghost-400 transition-colors" data-val="${val}">${label}</button>`;
              }).join('')}
            </div>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button type="button" id="goal-cancel" class="btn btn-secondary btn-sm">Cancel</button>
            <button type="submit" class="btn btn-primary btn-sm">Create Goal</button>
          </div>
        </form>
      </div>
    </div>

    <!-- Detail Drawer -->
    <div id="goal-drawer" class="hidden fixed inset-y-0 right-0 z-50 w-full max-w-lg flex flex-col" style="background:#18181b;border-left:1px solid rgba(63,63,70,0.5)">
      <div id="goal-drawer-content" class="flex-1 overflow-y-auto p-5"></div>
      <div class="p-4 border-t border-zinc-800">
        <button id="goal-drawer-close" class="btn btn-secondary btn-sm w-full">Close</button>
      </div>
    </div>
    <div id="goal-drawer-backdrop" class="hidden fixed inset-0 z-40" style="background:rgba(0,0,0,0.4)"></div>
  `;

  bindEvents(container, api, u);
}

// ─── render helpers ──────────────────────────────────────────────────────────

function statCard(label, value, colorClass) {
  return `
    <div class="stat-card">
      <div class="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">${label}</div>
      <div class="text-xl font-bold ${colorClass}">${value}</div>
    </div>`;
}

function tab(filter, label, count) {
  const active = filter === currentFilter ? 'border-b-2 border-ghost-500 text-white' : 'text-zinc-500 hover:text-zinc-300';
  return `<button class="goal-tab px-3 py-2 text-xs font-medium transition-colors ${active}" data-filter="${filter}">
    ${label} <span class="text-[10px] text-zinc-600">${count}</span>
  </button>`;
}

function statusBadge(status) {
  const map = {
    active:       ['bg-emerald-500/15 text-emerald-400', 'Active'],
    pending_plan: ['bg-amber-500/15 text-amber-400',    'Needs Plan'],
    paused:       ['bg-zinc-500/15 text-zinc-400',       'Paused'],
    completed:    ['bg-ghost-500/15 text-ghost-400',     'Completed'],
    abandoned:    ['bg-red-500/15 text-red-400',         'Abandoned'],
  };
  const [cls, lbl] = map[status] || ['bg-zinc-700 text-zinc-400', status];
  return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium ${cls}">${lbl}</span>`;
}

function progressBar(plan) {
  if (!plan || plan.length === 0) return '';
  const done = plan.filter(s => s.status === 'completed').length;
  const pct = Math.round((done / plan.length) * 100);
  return `
    <div class="mt-2">
      <div class="flex items-center justify-between text-[10px] text-zinc-500 mb-1">
        <span>${done}/${plan.length} steps</span><span>${pct}%</span>
      </div>
      <div class="h-1 bg-zinc-800 rounded-full overflow-hidden">
        <div class="h-full bg-ghost-500 rounded-full transition-all" style="width:${pct}%"></div>
      </div>
    </div>`;
}

function recurrenceLabel(recurrence) {
  if (!recurrence) return '';
  const presets = {
    '0 9 * * 1': 'Every Monday 9am',
    '0 9 * * *': 'Every day 9am',
    '0 8 * * *': 'Every day 8am',
    '0 9 * * 1-5': 'Weekdays 9am',
    '0 9 1 * *': '1st of month',
    '*/30 * * * *': 'Every 30 min',
    '0 */6 * * *': 'Every 6 hours',
  };
  const label = presets[recurrence] || recurrence;
  return `<span class="inline-flex items-center gap-1 text-[10px] text-zinc-500">
    <svg class="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
    ${label}
  </span>`;
}

function renderList(goals, filter) {
  const filtered = filter === 'all' ? goals : goals.filter(g => g.status === filter);
  if (filtered.length === 0) {
    return `<div class="text-center text-zinc-600 py-16 text-sm">
      ${filter === 'all' ? 'No goals yet. Create your first goal to get started.' : `No ${filter} goals.`}
    </div>`;
  }
  return filtered.map(g => `
    <div class="stat-card cursor-pointer hover:border-ghost-500/40 transition-colors goal-card" data-id="${g.id}" role="button" tabindex="0" aria-label="View goal: ${escHtml(g.title)}" style="border-color:rgba(63,63,70,0.4)">
      <div class="flex items-start justify-between gap-3">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            ${statusBadge(g.status)}
            ${recurrenceLabel(g.recurrence)}
          </div>
          <div class="text-sm font-semibold text-white truncate">${escHtml(g.title)}</div>
          <div class="text-xs text-zinc-500 mt-0.5 line-clamp-2">${escHtml(g.goal_text || '')}</div>
          ${progressBar(g.plan)}
        </div>
        <div class="flex items-center gap-1 shrink-0">
          ${g.status === 'active' ? `<button class="goal-action-btn btn btn-secondary btn-sm py-0.5 px-2 text-[11px]" data-action="pause" data-id="${g.id}">Pause</button>` : ''}
          ${g.status === 'paused' ? `<button class="goal-action-btn btn btn-primary btn-sm py-0.5 px-2 text-[11px]" data-action="resume" data-id="${g.id}">Resume</button>` : ''}
          <button class="goal-action-btn p-1.5 rounded hover:bg-zinc-700 text-zinc-500 hover:text-red-400 transition-colors" data-action="abandon" data-id="${g.id}" title="Abandon goal">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
      </div>
      ${g.last_output ? `
        <div class="mt-2 pt-2 border-t border-emerald-500/10 text-[10px]">
          <span class="text-emerald-600">Latest output:</span>
          <span class="text-zinc-500"> ${escHtml(g.last_output.slice(0, 140))}${g.last_output.length > 140 ? '…' : ''}</span>
        </div>` :
        (g.observations || []).length > 0 ? `
        <div class="mt-2 pt-2 border-t border-zinc-800/60 text-[10px] text-zinc-500">
          <span class="text-zinc-600">Last note:</span> ${escHtml((g.observations[g.observations.length - 1]?.text || '').slice(0, 120))}
        </div>` : ''}
    </div>
  `).join('');
}

function renderStepRow(step, i) {
  const stepIcon = s => {
    if (s === 'completed') return `<svg class="w-4 h-4 text-emerald-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>`;
    if (s === 'failed')    return `<svg class="w-4 h-4 text-red-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>`;
    if (s === 'running')   return `<div class="w-4 h-4 border-2 border-ghost-400 border-t-transparent rounded-full animate-spin shrink-0"></div>`;
    return `<div class="w-4 h-4 rounded-full border-2 border-zinc-600 shrink-0"></div>`;
  };
  return `
    <div class="flex gap-3 items-start p-2 rounded-lg ${step.status === 'completed' ? 'bg-emerald-500/5' : step.status === 'failed' ? 'bg-red-500/5' : 'bg-zinc-800/40'}">
      ${stepIcon(step.status)}
      <div class="flex-1 min-w-0">
        <div class="text-[10px] text-zinc-600 mb-0.5">Step ${i + 1}</div>
        <div class="text-xs text-zinc-300 leading-snug">${escHtml(step.description)}</div>
        ${step.result ? `<div class="text-[10px] text-zinc-500 mt-0.5 italic">${escHtml(step.result.slice(0, 150))}</div>` : ''}
        ${step.error  ? `<div class="text-[10px] text-red-400 mt-0.5">${escHtml(step.error.slice(0, 150))}</div>` : ''}
      </div>
    </div>`;
}

function renderPlanSection(goal) {
  const plan = goal.plan || [];
  const lastRun = goal.last_completed_plan || null;
  const isRecurring = !!goal.recurrence;
  const allPending = plan.length > 0 && plan.every(s => s.status === 'pending');

  // For a recurring goal where this cycle is pending, show last completed run first
  if (isRecurring && allPending && lastRun) {
    const lastSteps = lastRun.steps || [];
    const doneCount = lastSteps.filter(s => s.status === 'completed').length;
    const lastDate = (lastRun.completed_at || '').slice(0, 16).replace('T', ' ');
    return `
      <div class="mb-5">
        <div class="flex items-center justify-between mb-2">
          <div class="text-[10px] uppercase tracking-wider text-emerald-600 font-semibold">Last Run — All Steps Completed</div>
          <span class="text-[10px] text-zinc-500">${lastDate} · Run #${lastRun.run || ''}</span>
        </div>
        <div class="space-y-2">
          ${lastSteps.map((step, i) => renderStepRow(step, i)).join('')}
        </div>
      </div>
      <div class="mb-2">
        <div class="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">Next Cycle — Waiting to Run</div>
        <div class="space-y-2 mb-5">
          ${plan.map((step, i) => renderStepRow(step, i)).join('')}
        </div>
      </div>`;
  }

  // Normal case: show the current plan
  if (plan.length === 0) {
    return `<div class="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">Execution Plan</div>
      <div class="text-xs text-zinc-600 italic mb-4">No plan yet — the goal executor will create one on its next run.</div>`;
  }
  return `
    <div class="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">Execution Plan</div>
    <div class="space-y-2 mb-5">
      ${plan.map((step, i) => renderStepRow(step, i)).join('')}
    </div>`;
}

function renderDrawer(goal) {
  const observations = goal.observations || [];
  const outputHistory = goal.output_history || [];
  const lastOutput = goal.last_output || null;
  const delivery = goal.delivery || '';

  return `
    <div class="flex items-start justify-between mb-4">
      <div class="flex-1">
        <div class="flex items-center gap-2 mb-1">${statusBadge(goal.status)} ${recurrenceLabel(goal.recurrence)}</div>
        <h2 class="text-base font-bold text-white">${escHtml(goal.title)}</h2>
        <p class="text-xs text-zinc-500 mt-1">${escHtml(goal.goal_text || '')}</p>
        ${delivery ? `<div class="mt-1 text-[10px] text-zinc-500 flex items-center gap-1">
          <svg class="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/></svg>
          Delivers via: <span class="text-ghost-400">${escHtml(delivery)}</span>
        </div>` : ''}
      </div>
    </div>

    ${lastOutput ? `
      <div class="mb-5">
        <div class="flex items-center justify-between mb-2">
          <div class="text-[10px] uppercase tracking-wider text-emerald-500 font-semibold">Latest Output</div>
          ${outputHistory.length > 1 ? `<button id="toggle-history" class="text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors">${outputHistory.length - 1} previous run${outputHistory.length > 2 ? 's' : ''} ▾</button>` : ''}
        </div>
        <div class="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
          <div class="text-[10px] text-zinc-500 mb-2">
            ${goal.last_executed_at ? goal.last_executed_at.slice(0, 16).replace('T', ' ') : ''}
            ${goal.completion_count > 0 ? `· Run #${goal.completion_count}` : ''}
          </div>
          <div class="text-xs text-zinc-300 leading-relaxed whitespace-pre-wrap" style="max-height:320px;overflow-y:auto">${escHtml(lastOutput)}</div>
        </div>
        ${outputHistory.length > 1 ? `
          <div id="output-history" class="hidden mt-2 space-y-2">
            ${outputHistory.slice(0, -1).reverse().map((h, i) => `
              <div class="p-3 rounded-lg bg-zinc-800/40 border border-zinc-700/40">
                <div class="text-[10px] text-zinc-500 mb-1.5">${h.at ? h.at.slice(0, 16).replace('T', ' ') : ''} · Run #${h.run || (outputHistory.length - 1 - i)}</div>
                <div class="text-xs text-zinc-400 leading-relaxed whitespace-pre-wrap" style="max-height:200px;overflow-y:auto">${escHtml(h.output || '')}</div>
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>
    ` : `
      <div class="mb-5 p-3 rounded-lg bg-zinc-800/30 border border-zinc-700/30 text-xs text-zinc-500 italic">
        No output yet — Ghost will populate this after completing the first execution cycle.
      </div>
    `}

    ${renderPlanSection(goal)}

    ${observations.length > 0 ? `
      <div class="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">Working Memory</div>
      <div class="space-y-2 mb-5">
        ${observations.slice().reverse().slice(0, 8).map(o => `
          <div class="p-2 rounded bg-zinc-800/40 border-l-2 border-ghost-500/20">
            <div class="text-[10px] text-zinc-600 mb-0.5">${o.at ? o.at.slice(0, 16).replace('T', ' ') : ''}</div>
            <div class="text-xs text-zinc-400 leading-snug">${escHtml(o.text || '')}</div>
          </div>
        `).join('')}
      </div>
    ` : ''}

    <div class="text-[10px] text-zinc-600 mt-4 pt-4 border-t border-zinc-800">
      ID: <span class="font-mono">${goal.id}</span>
      &nbsp;·&nbsp; Created: ${(goal.created_at || '').slice(0, 16).replace('T', ' ')}
      ${goal.last_executed_at ? `&nbsp;·&nbsp; Last run: ${goal.last_executed_at.slice(0, 16).replace('T', ' ')}` : ''}
      ${goal.completion_count > 0 ? `&nbsp;·&nbsp; Completed ${goal.completion_count}× ` : ''}
    </div>
  `;
}

// ─── event binding ────────────────────────────────────────────────────────────

function bindEvents(container, api, u) {
  // New goal modal
  document.getElementById('goal-add-btn').addEventListener('click', () => {
    document.getElementById('goal-modal').classList.remove('hidden');
    document.getElementById('goal-title').focus();
  });

  document.getElementById('goal-cancel').addEventListener('click', closeModal);
  document.getElementById('goal-modal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeModal();
  });

  // Recurrence presets
  document.getElementById('recurrence-presets').addEventListener('click', e => {
    const btn = e.target.closest('.recurrence-preset');
    if (btn) document.getElementById('goal-recurrence').value = btn.dataset.val;
  });

  // Create goal form
  document.getElementById('goal-form').addEventListener('submit', async e => {
    e.preventDefault();
    const data = {
      title:      document.getElementById('goal-title').value.trim(),
      goal_text:  document.getElementById('goal-text').value.trim(),
      recurrence: document.getElementById('goal-recurrence').value.trim(),
    };
    const btn = e.target.querySelector('[type=submit]');
    btn.disabled = true; btn.textContent = 'Creating…';
    const res = await api.post('/api/goals/add', data);
    btn.disabled = false; btn.textContent = 'Create Goal';
    if (res.ok) {
      closeModal();
      u.toast('Goal created — Ghost will plan and execute it automatically.');
      await refresh(api);
    } else {
      u.toast(res.error || 'Failed to create goal', 'error');
    }
  });

  // Filter tabs
  container.querySelectorAll('.goal-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      currentFilter = tab.dataset.filter;
      document.getElementById('goal-list').innerHTML = renderList(currentGoals, currentFilter);
      rebindCards(api, u);
      container.querySelectorAll('.goal-tab').forEach(t => {
        t.classList.toggle('border-b-2', t.dataset.filter === currentFilter);
        t.classList.toggle('border-ghost-500', t.dataset.filter === currentFilter);
        t.classList.toggle('text-white', t.dataset.filter === currentFilter);
        t.classList.toggle('text-zinc-500', t.dataset.filter !== currentFilter);
      });
    });
  });

  rebindCards(api, u);

  // Drawer close
  document.getElementById('goal-drawer-close').addEventListener('click', closeDrawer);
  document.getElementById('goal-drawer-backdrop').addEventListener('click', closeDrawer);
}

function rebindCards(api, u) {
  // Card click/keyboard — open drawer
  document.querySelectorAll('.goal-card').forEach(card => {
    const openCard = async (e) => {
      if (e.target.closest('.goal-action-btn')) return;
      const id = card.dataset.id;
      const res = await api.get(`/api/goals/${id}`);
      if (res.ok) openDrawer(res.goal);
    };
    card.addEventListener('click', openCard);
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openCard(e); } });
  });

  // Action buttons (pause / resume / abandon)
  document.querySelectorAll('.goal-action-btn').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      const { action, id } = btn.dataset;
      if (action === 'abandon' && !confirm('Abandon this goal? This cannot be undone.')) return;
      const res = await api.post(`/api/goals/${id}/${action}`);
      if (res.ok) {
        u.toast(action === 'pause' ? 'Goal paused.' : action === 'resume' ? 'Goal resumed.' : 'Goal abandoned.');
        await refresh(api);
      } else {
        u.toast(res.error || 'Action failed', 'error');
      }
    });
  });
}

async function refresh(api) {
  const [listData, statsData] = await Promise.all([
    api.get('/api/goals/list'),
    api.get('/api/goals/stats'),
  ]);
  currentGoals = listData.goals || [];
  const stats = statsData || {};

  // Update stat cards
  const statValues = [
    stats.total || 0, stats.active || 0, stats.pending_plan || 0,
    stats.paused || 0, stats.completed || 0,
  ];
  document.querySelectorAll('.stat-card .text-xl').forEach((el, i) => {
    if (i < statValues.length) el.textContent = statValues[i];
  });

  // Update filter tab counts
  const tabCounts = {
    all: currentGoals.length,
    active: stats.active || 0,
    pending_plan: stats.pending_plan || 0,
    paused: stats.paused || 0,
    completed: stats.completed || 0,
    abandoned: stats.abandoned || 0,
  };
  document.querySelectorAll('.goal-tab').forEach(tab => {
    const filter = tab.dataset.filter;
    const countEl = tab.querySelector('span');
    if (countEl && tabCounts[filter] !== undefined) {
      countEl.textContent = tabCounts[filter];
    }
  });

  document.getElementById('goal-list').innerHTML = renderList(currentGoals, currentFilter);
  const { GhostAPI, GhostUtils } = window;
  rebindCards(GhostAPI, GhostUtils);
}

function openDrawer(goal) {
  document.getElementById('goal-drawer-content').innerHTML = renderDrawer(goal);
  document.getElementById('goal-drawer').classList.remove('hidden');
  document.getElementById('goal-drawer-backdrop').classList.remove('hidden');

  // Wire output history toggle
  const toggleBtn = document.getElementById('toggle-history');
  const historyEl = document.getElementById('output-history');
  if (toggleBtn && historyEl) {
    toggleBtn.addEventListener('click', () => {
      const hidden = historyEl.classList.toggle('hidden');
      toggleBtn.textContent = hidden
        ? `${(goal.output_history || []).length - 1} previous run${(goal.output_history || []).length > 2 ? 's' : ''} ▾`
        : 'Hide history ▴';
    });
  }
}

function closeDrawer() {
  document.getElementById('goal-drawer').classList.add('hidden');
  document.getElementById('goal-drawer-backdrop').classList.add('hidden');
}

function closeModal() {
  document.getElementById('goal-modal').classList.add('hidden');
  document.getElementById('goal-form').reset();
}

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
