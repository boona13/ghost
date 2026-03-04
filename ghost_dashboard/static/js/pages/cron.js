/** Cron Jobs page */

const t = (key, params) => window.GhostI18n?.t(key, params) ?? key;

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;
  const [jobsData, statusData] = await Promise.all([
    api.get('/api/cron/jobs'),
    api.get('/api/cron/status'),
  ]);

  const jobs = jobsData.jobs || [];

  container.innerHTML = `
    <h1 class="page-header">${t('cron.title')}</h1>
    <p class="page-desc">${t('cron.subtitle')}</p>

    <div class="grid grid-cols-3 gap-4 mb-6">
      <div class="stat-card">
        <div class="text-xs text-zinc-500">${t('cron.totalJobs')}</div>
        <div class="text-xl font-bold text-white">${statusData.total_jobs || 0}</div>
      </div>
      <div class="stat-card">
        <div class="text-xs text-zinc-500">${t('cron.enabledJobs')}</div>
        <div class="text-xl font-bold text-emerald-400">${statusData.enabled_jobs || 0}</div>
      </div>
      <div class="stat-card">
        <div class="text-xs text-zinc-500">${t('cron.nextWake')}</div>
        <div class="text-sm font-medium text-zinc-300">${statusData.next_wake || '—'}</div>
      </div>
    </div>

    <div class="stat-card mb-6">
      <h3 class="text-sm font-semibold text-white mb-3">${t('cron.addNewJob')}</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div>
          <label class="form-label">${t('cron.jobName')}</label>
          <input id="cron-name" type="text" class="form-input w-full" placeholder="${t('cron.jobNamePlaceholder')}">
        </div>
        <div>
          <label class="form-label">${t('cron.scheduleType')}</label>
          <select id="cron-stype" class="form-input w-full">
            <option value="every">${t('cron.everyInterval')}</option>
            <option value="cron">${t('cron.cronExpression')}</option>
            <option value="at">${t('cron.atOneShot')}</option>
          </select>
        </div>
      </div>
      <div id="sched-fields" class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div id="sf-every">
          <label class="form-label">${t('cron.intervalSeconds')}</label>
          <input id="cron-interval" type="number" class="form-input w-full" value="300" min="10">
        </div>
        <div id="sf-cron" class="hidden">
          <label class="form-label">${t('cron.cronExpressionLabel')}</label>
          <input id="cron-expr" type="text" class="form-input w-full" placeholder="${t('cron.cronPlaceholder')}">
        </div>
        <div id="sf-at" class="hidden">
          <label class="form-label">${t('cron.runAt')}</label>
          <input id="cron-at" type="datetime-local" class="form-input w-full">
        </div>
        <div>
          <label class="form-label">${t('cron.taskType')}</label>
          <select id="cron-ttype" class="form-input w-full">
            <option value="task">${t('cron.aiTask')}</option>
            <option value="notify">${t('cron.notification')}</option>
            <option value="shell">${t('cron.shellCommand')}</option>
          </select>
        </div>
      </div>
      <div class="mb-3">
        <label class="form-label">${t('cron.taskLabel')}</label>
        <textarea id="cron-task" class="form-input w-full h-20" placeholder="${t('cron.whatShouldGhostDo')}"></textarea>
      </div>
      <div class="mb-3">
        <label class="form-label">${t('cron.descriptionOptional')}</label>
        <input id="cron-desc" type="text" class="form-input w-full" placeholder="">
      </div>
      <button id="btn-add-cron" class="btn btn-primary">${t('cron.createJob')}</button>
    </div>

    <div class="space-y-3" id="cron-list">
      ${jobs.length === 0 ? `<div class="text-sm text-zinc-600">${t('cron.noCronJobs')}</div>` :
        jobs.map(j => `
          <div class="stat-card">
            <div class="flex items-center justify-between mb-2">
              <div class="flex items-center gap-3">
                <div class="toggle ${j.enabled ? 'on' : ''}" data-cron-toggle="${j.id}"><span class="toggle-dot"></span></div>
                <span class="font-semibold text-sm text-white">${u.escapeHtml(j.name)}</span>
                <span class="badge badge-${j.enabled ? 'green' : 'zinc'}">${j.enabled ? t('common.on') : t('common.off')}</span>
              </div>
              <div class="flex gap-2">
                <button class="btn btn-ghost btn-sm" data-cron-run="${j.id}">${t('cron.runNow')}</button>
                <button class="btn btn-danger btn-sm" data-cron-del="${j.id}">${t('common.delete')}</button>
              </div>
            </div>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-zinc-400">
              <div>${t('cron.scheduleLabel')} <span class="text-zinc-300">${u.escapeHtml(j.schedule_human)}</span></div>
              <div>${t('cron.nextLabel')} <span class="text-zinc-300">${j.next_run || '—'}</span></div>
              <div>${t('cron.lastLabel')} <span class="text-zinc-300">${j.last_status || t('common.never')}</span></div>
              <div>${t('cron.typeLabel')} <span class="text-zinc-300">${j.payload?.type || '?'}</span></div>
            </div>
            ${j.last_error ? `<div class="text-xs text-red-400 mt-1">${u.escapeHtml(j.last_error)}</div>` : ''}
            ${j.description ? `<div class="text-xs text-zinc-500 mt-1">${u.escapeHtml(j.description)}</div>` : ''}
          </div>
        `).join('')}
    </div>
  `;

  const stypeSelect = document.getElementById('cron-stype');
  const show = (id) => { document.getElementById(id).classList.remove('hidden'); };
  const hide = (id) => { document.getElementById(id).classList.add('hidden'); };

  stypeSelect?.addEventListener('change', () => {
    hide('sf-every'); hide('sf-cron'); hide('sf-at');
    show(`sf-${stypeSelect.value}`);
  });

  document.getElementById('btn-add-cron')?.addEventListener('click', async () => {
    const body = {
      name: document.getElementById('cron-name').value.trim(),
      schedule_type: stypeSelect.value,
      task_type: document.getElementById('cron-ttype').value,
      task: document.getElementById('cron-task').value,
      description: document.getElementById('cron-desc').value,
    };
    if (stypeSelect.value === 'every') body.interval_seconds = parseFloat(document.getElementById('cron-interval').value);
    if (stypeSelect.value === 'cron') body.cron_expr = document.getElementById('cron-expr').value;
    if (stypeSelect.value === 'at') body.run_at = document.getElementById('cron-at').value;

    if (!body.name) { u.toast(t('cron.nameRequired'), 'error'); return; }
    const r = await api.post('/api/cron/jobs', body);
    if (r.error) { u.toast(r.error, 'error'); return; }
    u.toast(t('cron.jobCreated', {name: body.name}));
    render(container);
  });

  container.querySelectorAll('[data-cron-toggle]').forEach(el => {
    el.addEventListener('click', async () => {
      const id = el.dataset.cronToggle;
      const on = el.classList.contains('on');
      await api.put(`/api/cron/jobs/${id}`, { enabled: !on });
      u.toast(!on ? t('common.enabled') : t('common.disabled'));
      render(container);
    });
  });

  container.querySelectorAll('[data-cron-run]').forEach(btn => {
    btn.addEventListener('click', async () => {
      await api.post(`/api/cron/jobs/${btn.dataset.cronRun}/run`);
      u.toast(t('cron.jobTriggered'));
    });
  });

  container.querySelectorAll('[data-cron-del]').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm(t('cron.deleteJob'))) return;
      await api.del(`/api/cron/jobs/${btn.dataset.cronDel}`);
      u.toast(t('cron.jobDeleted'));
      render(container);
    });
  });
}
