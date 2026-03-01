/** Skills page — grouped, filterable, with enable/disable and requirements */

let allSkills = [];
let expandedSkill = null;

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;
  const data = await api.get('/api/skills');
  const stats = data.stats;
  const groups = data.groups;

  allSkills = [
    ...(groups.bundled || []),
    ...(groups.user || []),
    ...(groups.other || []),
  ];

  const countEl = document.getElementById('skills-count');
  if (countEl) countEl.textContent = stats.total;

  container.innerHTML = `
    <div class="flex items-center justify-between mb-1">
      <h1 class="page-header">Skills</h1>
      <div class="flex gap-2 items-center">
        <span class="badge badge-green">${stats.eligible} eligible</span>
        ${stats.disabled ? `<span class="badge badge-zinc">${stats.disabled} disabled</span>` : ''}
        ${stats.missing_reqs ? `<span class="badge badge-yellow">${stats.missing_reqs} missing reqs</span>` : ''}
      </div>
    </div>
    <p class="page-desc">${stats.total} skills loaded from bundled and user directories</p>

    <div class="flex gap-3 mb-6">
      <input id="skills-search" type="text" class="form-input flex-1" placeholder="Search skills by name, description, or trigger...">
      <select id="skills-filter" class="form-input" style="width:150px">
        <option value="all">All Skills</option>
        <option value="eligible">Eligible</option>
        <option value="disabled">Disabled</option>
        <option value="missing">Missing Reqs</option>
      </select>
    </div>

    <div id="skills-groups"></div>

    <div class="mt-6 stat-card">
      <div class="text-xs text-zinc-500">
        <div>Bundled: <span class="font-mono text-zinc-400">${u.escapeHtml(data.bundled_dir)}</span></div>
        <div>User: <span class="font-mono text-zinc-400">${u.escapeHtml(data.user_dir)}</span></div>
      </div>
    </div>
  `;

  renderGroups(groups, container, 'all', '', api, u);

  document.getElementById('skills-search')?.addEventListener('input', () => applyFilters(groups, container, api, u));
  document.getElementById('skills-filter')?.addEventListener('change', () => applyFilters(groups, container, api, u));
}

function applyFilters(groups, container, api, u) {
  const q = document.getElementById('skills-search').value.toLowerCase().trim();
  const filter = document.getElementById('skills-filter').value;
  renderGroups(groups, container, filter, q, api, u);
}

function filterSkills(skills, filter, query) {
  return skills.filter(s => {
    if (filter === 'eligible' && !s.eligible) return false;
    if (filter === 'disabled' && !s.disabled) return false;
    if (filter === 'missing' && !s.missing.bins.length && !s.missing.env.length) return false;
    if (query) {
      const hay = (s.name + ' ' + s.description + ' ' + (s.triggers || []).join(' ')).toLowerCase();
      if (!hay.includes(query)) return false;
    }
    return true;
  });
}

function renderGroups(groups, container, filter, query, api, u) {
  const target = document.getElementById('skills-groups');
  if (!target) return;

  const sections = [
    { key: 'bundled', label: 'Bundled Skills', icon: '📦', skills: groups.bundled || [] },
    { key: 'user', label: 'User Skills', icon: '👤', skills: groups.user || [] },
    { key: 'other', label: 'Other Skills', icon: '📂', skills: groups.other || [] },
  ];

  let html = '';
  for (const sec of sections) {
    const filtered = filterSkills(sec.skills, filter, query);
    if (filtered.length === 0 && filter !== 'all') continue;

    html += `
      <div class="mb-6">
        <button class="group-toggle flex items-center gap-2 mb-3 cursor-pointer w-full text-left" data-group="${sec.key}">
          <svg class="w-4 h-4 text-zinc-500 transition-transform group-chevron" style="transform:rotate(90deg)" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
          </svg>
          <span class="text-sm">${sec.icon}</span>
          <span class="text-sm font-semibold text-zinc-300">${sec.label}</span>
          <span class="text-[10px] text-zinc-600">(${filtered.length})</span>
        </button>
        <div class="skills-grid grid grid-cols-1 md:grid-cols-2 gap-3" data-group-body="${sec.key}">
          ${filtered.map(s => renderSkillCard(s, u)).join('')}
          ${filtered.length === 0 ? '<div class="text-xs text-zinc-600 col-span-2 py-2">No skills match filters</div>' : ''}
        </div>
      </div>
    `;
  }

  target.innerHTML = html;

  target.querySelectorAll('.group-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.group;
      const body = target.querySelector('[data-group-body="' + key + '"]');
      const chev = btn.querySelector('.group-chevron');
      if (body.style.display === 'none') {
        body.style.display = '';
        chev.style.transform = 'rotate(90deg)';
      } else {
        body.style.display = 'none';
        chev.style.transform = 'rotate(0deg)';
      }
    });
  });

  target.querySelectorAll('.toggle[data-skill-toggle]').forEach(el => {
    el.addEventListener('click', async (e) => {
      e.stopPropagation();
      const name = el.dataset.skillToggle;
      const isOn = el.classList.contains('on');
      await api.put('/api/skills/' + name, { enabled: !isOn });
      el.classList.toggle('on');
      u.toast(isOn ? name + ' disabled' : name + ' enabled');
    });
  });

  target.querySelectorAll('.skill-card[data-skill-name]').forEach(card => {
    card.addEventListener('click', async () => {
      const name = card.dataset.skillName;
      await openSkillDetail(name, api, u);
    });
  });
}

function renderSkillCard(s, u) {
  const hasMissing = s.missing.bins.length > 0 || s.missing.env.length > 0;

  let statusChips = '';
  statusChips += `<span class="badge badge-${s.source === 'bundled' ? 'blue' : 'purple'}">${s.source}</span>`;
  if (s.eligible) statusChips += '<span class="badge badge-green">eligible</span>';
  if (s.disabled) statusChips += '<span class="badge badge-zinc">disabled</span>';
  if (hasMissing) statusChips += '<span class="badge badge-yellow">missing reqs</span>';
  if (!s.os_ok) statusChips += '<span class="badge badge-red">wrong OS</span>';

  let reqsHtml = '';
  if (s.requirements.bins.length || s.requirements.env.length) {
    reqsHtml = '<div class="mt-2 flex flex-wrap gap-1">';
    for (const b of s.requirements.bins) {
      const ok = !s.missing.bins.includes(b);
      reqsHtml += '<span class="inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded '
        + (ok ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400') + '">'
        + (ok ? '✓' : '✗') + ' ' + u.escapeHtml(b) + '</span>';
    }
    for (const e of s.requirements.env) {
      const ok = !s.missing.env.includes(e);
      reqsHtml += '<span class="inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded '
        + (ok ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400') + '">'
        + (ok ? '✓' : '⚠') + ' $' + u.escapeHtml(e) + '</span>';
    }
    reqsHtml += '</div>';
  }

  return `
    <div class="skill-card ${s.disabled ? 'opacity-50' : ''} ${hasMissing ? 'border-l-2 border-l-amber-500/40' : ''}" data-skill-name="${s.name}">
      <div class="flex items-start justify-between mb-2">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <span class="font-semibold text-sm text-white truncate">${u.escapeHtml(s.name)}</span>
            <span class="text-[10px] text-zinc-600">pri:${s.priority}</span>
          </div>
          <div class="text-xs text-zinc-400 leading-relaxed">${u.escapeHtml(s.description || 'No description')}</div>
        </div>
        <div class="toggle ${s.disabled ? '' : 'on'} ml-3 flex-shrink-0" data-skill-toggle="${s.name}">
          <span class="toggle-dot"></span>
        </div>
      </div>

      <div class="flex flex-wrap gap-1 mb-2">${statusChips}</div>

      <div class="flex flex-wrap gap-1 mb-1">
        ${(s.triggers || []).slice(0, 6).map(t =>
          '<span class="inline-block text-[10px] px-1.5 py-0.5 rounded bg-ghost-500/10 text-ghost-400 border border-ghost-500/20">'
          + u.escapeHtml(t) + '</span>'
        ).join('')}
        ${s.triggers.length > 6 ? '<span class="text-[10px] text-zinc-600">+' + (s.triggers.length - 6) + ' more</span>' : ''}
      </div>

      ${s.tools.length ? `<div class="flex flex-wrap gap-1 mb-1">
        ${s.tools.map(t =>
          '<span class="inline-block text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">'
          + u.escapeHtml(t) + '</span>'
        ).join('')}
      </div>` : ''}

      ${reqsHtml}
    </div>
  `;
}

function closeSkillModal() {
  const overlay = document.getElementById('skill-modal-overlay');
  if (!overlay) return;
  overlay.classList.add('modal-closing');
  overlay.addEventListener('animationend', () => overlay.remove(), { once: true });
  expandedSkill = null;
}

async function openSkillDetail(name, api, u) {
  const data = await api.get('/api/skills/' + name);
  if (data.error) { u.toast(data.error, 'error'); return; }

  expandedSkill = name;

  const hasMissing = data.missing.bins.length > 0 || data.missing.env.length > 0;

  let metaHtml = '<div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">';
  metaHtml += '<div><span class="text-zinc-500">Source:</span> <span class="text-zinc-300">' + data.source + '</span></div>';
  metaHtml += '<div><span class="text-zinc-500">Priority:</span> <span class="text-zinc-300">' + data.priority + '</span></div>';
  metaHtml += '<div><span class="text-zinc-500">Status:</span> <span class="' + (data.eligible ? 'text-emerald-400' : 'text-amber-400') + '">' + (data.eligible ? 'Eligible' : 'Not Eligible') + '</span></div>';
  metaHtml += '<div><span class="text-zinc-500">Enabled:</span> <span class="' + (data.disabled ? 'text-red-400' : 'text-emerald-400') + '">' + (data.disabled ? 'No' : 'Yes') + '</span></div>';
  metaHtml += '</div>';

  if (data.triggers.length) {
    metaHtml += '<div class="mt-3"><span class="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider">Triggers</span><div class="flex flex-wrap gap-1 mt-1">'
      + data.triggers.map(t => '<span class="inline-block text-[10px] px-1.5 py-0.5 rounded bg-ghost-500/10 text-ghost-400 border border-ghost-500/20">' + u.escapeHtml(t) + '</span>').join('')
      + '</div></div>';
  }
  if (data.tools.length) {
    metaHtml += '<div class="mt-2"><span class="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider">Tools</span><div class="flex flex-wrap gap-1 mt-1">'
      + data.tools.map(t => '<span class="inline-block text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">' + u.escapeHtml(t) + '</span>').join('')
      + '</div></div>';
  }
  if (hasMissing) {
    metaHtml += '<div class="mt-3 p-2 rounded bg-amber-500/5 border border-amber-500/20">';
    metaHtml += '<span class="text-[10px] text-amber-400 font-semibold uppercase tracking-wider">Missing Requirements</span>';
    if (data.missing.bins.length) metaHtml += '<div class="text-xs text-amber-300 mt-1">Binaries: ' + data.missing.bins.map(b => '<code class="font-mono">' + u.escapeHtml(b) + '</code>').join(', ') + '</div>';
    if (data.missing.env.length) metaHtml += '<div class="text-xs text-amber-300 mt-1">Env vars: ' + data.missing.env.map(e => '<code class="font-mono">$' + u.escapeHtml(e) + '</code>').join(', ') + '</div>';
    metaHtml += '</div>';
  }

  metaHtml += '<div class="mt-2 text-[10px] text-zinc-600 font-mono">' + u.escapeHtml(data.path) + '</div>';

  const existing = document.getElementById('skill-modal-overlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'skill-modal-overlay';
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal-panel" style="max-width: 720px;">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-sm font-semibold text-white">${u.escapeHtml(name)}</h3>
        <button id="btn-close-skill-modal" class="btn btn-ghost btn-sm" title="Close">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>
      <div class="mb-4">${metaHtml}</div>
      <textarea id="detail-editor" class="editor-textarea" style="min-height:320px">${u.escapeHtml(data.content)}</textarea>
      <div class="flex gap-3 mt-4 justify-end">
        <button id="btn-cancel-skill-modal" class="btn btn-secondary btn-sm">Cancel</button>
        <button id="btn-save-skill" class="btn btn-primary btn-sm">Save Changes</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeSkillModal();
  });

  overlay.querySelector('#btn-close-skill-modal').addEventListener('click', closeSkillModal);
  overlay.querySelector('#btn-cancel-skill-modal').addEventListener('click', closeSkillModal);

  overlay.querySelector('#btn-save-skill').addEventListener('click', async () => {
    if (!expandedSkill) return;
    const content = overlay.querySelector('#detail-editor').value;
    await api.put('/api/skills/' + expandedSkill, { content });
    u.toast('Skill saved — reload to see changes');
    closeSkillModal();
  });

  document.addEventListener('keydown', function escHandler(e) {
    if (e.key === 'Escape') {
      closeSkillModal();
      document.removeEventListener('keydown', escHandler);
    }
  });
}
