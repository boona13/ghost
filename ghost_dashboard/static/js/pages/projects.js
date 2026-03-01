/** Projects page — manage Ghost project workspaces */

let allProjects = [];
let allSkills = [];
let editingProject = null;

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  const [projectsData, skillsData] = await Promise.all([
    api.get('/api/projects'),
    api.get('/api/skills').catch(() => ({ groups: {} })),
  ]);

  allProjects = projectsData.projects || [];
  const groups = skillsData.groups || {};
  const skillSet = new Set();
  for (const groupList of Object.values(groups)) {
    for (const s of groupList) {
      if (s.name) skillSet.add(s.name);
    }
  }
  allSkills = Array.from(skillSet).sort();

  container.innerHTML = `
    <div class="flex items-center justify-between mb-1">
      <h1 class="page-header">Projects</h1>
      <button id="btn-new-project" class="btn btn-primary">+ New Project</button>
    </div>
    <p class="page-desc">${projectsData.count} project workspace${projectsData.count === 1 ? '' : 's'} configured</p>

    <div class="flex gap-3 mb-6">
      <input id="projects-search" type="text" class="form-input flex-1" placeholder="Search projects by name or path...">
      <select id="projects-filter" class="form-input" style="width:150px">
        <option value="all">All Projects</option>
        <option value="active">Active</option>
        <option value="isolated">Isolated Memory</option>
        <option value="shared">Shared Memory</option>
      </select>
    </div>

    <div id="projects-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"></div>

    <div id="project-modal" class="modal-overlay" style="display:none;">
      <div class="stat-card" style="width:100%;max-width:520px;border-color:rgba(139,92,246,0.3);max-height:85vh;overflow-y:auto;">
        <div class="flex items-center justify-between mb-4">
          <h3 id="modal-title" class="text-sm font-semibold text-white">New Project</h3>
          <button id="modal-close" class="text-zinc-500 hover:text-zinc-300 text-xl leading-none">&times;</button>
        </div>
        <div class="space-y-4">
          <div>
            <label class="form-label">Name</label>
            <input id="inp-name" type="text" class="form-input w-full" placeholder="My Project">
          </div>
          <div>
            <label class="form-label">Folder</label>
            <div class="flex gap-2">
              <input id="inp-path" type="text" class="form-input flex-1" placeholder="/path/to/project">
              <button id="btn-browse" class="btn btn-secondary text-xs" style="white-space:nowrap">Browse...</button>
            </div>
            <div id="folder-browser" style="display:none" class="mt-2">
              <div id="folder-breadcrumb" class="text-[10px] text-zinc-500 mb-1 font-mono truncate"></div>
              <div id="folder-list" class="folder-browser-list"></div>
            </div>
          </div>
          <div>
            <label class="form-label">Description</label>
            <textarea id="inp-desc" class="form-input w-full" rows="2" placeholder="Optional description"></textarea>
          </div>
          <div>
            <label class="form-label">Memory Scope</label>
            <select id="inp-memory" class="form-input w-full">
              <option value="inherit">Inherit (default)</option>
              <option value="isolated">Isolated</option>
              <option value="shared">Shared</option>
            </select>
          </div>
          <div>
            <button id="toggle-advanced" type="button" class="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors mt-1">
              <svg id="advanced-arrow" class="w-3 h-3 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" style="transform:rotate(0deg)">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
              </svg>
              Advanced: Skill Restrictions (optional)
            </button>
            <div id="advanced-section" style="display:none" class="mt-3 space-y-4">
              <p class="text-[10px] text-zinc-600">By default Ghost has access to all skills. Use these options only if you want to restrict what Ghost can do within this project.</p>
              <div>
                <label class="form-label">Restrict to these skills only</label>
                <p class="text-[10px] text-zinc-500 mb-2">If any are selected, Ghost will ONLY use these skills in this project. Leave empty for full access.</p>
                <div id="skills-enabled-list" class="skill-picker"></div>
              </div>
              <div>
                <label class="form-label">Block these skills</label>
                <p class="text-[10px] text-zinc-500 mb-2">Ghost will never use these skills in this project, even if requested.</p>
                <div id="skills-disabled-list" class="skill-picker"></div>
              </div>
            </div>
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button id="btn-cancel" class="btn btn-secondary">Cancel</button>
          <button id="btn-save" class="btn btn-primary">Save</button>
        </div>
      </div>
    </div>
  `;

  renderProjects(allProjects, container, u);

  document.getElementById('projects-search')?.addEventListener('input', () => applyFilters(container, u));
  document.getElementById('projects-filter')?.addEventListener('change', () => applyFilters(container, u));

  document.getElementById('btn-new-project')?.addEventListener('click', () => openModal(container, null));
  document.getElementById('modal-close')?.addEventListener('click', closeModal);
  document.getElementById('btn-cancel')?.addEventListener('click', closeModal);
  document.getElementById('btn-save')?.addEventListener('click', () => saveProject(container, api, u));

  const overlay = document.getElementById('project-modal');
  overlay?.addEventListener('click', (e) => {
    if (e.target === overlay) closeModal();
  });

  document.getElementById('toggle-advanced')?.addEventListener('click', () => {
    const section = document.getElementById('advanced-section');
    const arrow = document.getElementById('advanced-arrow');
    const visible = section.style.display !== 'none';
    section.style.display = visible ? 'none' : 'block';
    arrow.style.transform = visible ? 'rotate(0deg)' : 'rotate(90deg)';
  });

  document.getElementById('btn-browse')?.addEventListener('click', () => {
    const browser = document.getElementById('folder-browser');
    if (browser.style.display !== 'none') {
      browser.style.display = 'none';
      return;
    }
    browser.style.display = 'block';
    const currentPath = document.getElementById('inp-path').value;
    _loadDirectory(api, currentPath || '');
  });
}

function renderSkillPicker(containerId, selectedSkills) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const selected = new Set(selectedSkills || []);

  if (allSkills.length === 0) {
    el.innerHTML = '<span class="text-xs text-zinc-600">No skills found</span>';
    return;
  }

  el.innerHTML = `
    <div class="flex flex-wrap gap-1.5" style="max-height:120px;overflow-y:auto;padding:6px 0;">
      ${allSkills.map(name => {
        const checked = selected.has(name);
        return `<label class="skill-chip ${checked ? 'active' : ''}" data-skill="${name}">
          <input type="checkbox" value="${name}" ${checked ? 'checked' : ''} style="display:none;">
          <span>${name}</span>
        </label>`;
      }).join('')}
    </div>
  `;

  el.querySelectorAll('.skill-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const cb = chip.querySelector('input');
      cb.checked = !cb.checked;
      chip.classList.toggle('active', cb.checked);
    });
  });
}

function getSelectedSkills(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return [];
  return Array.from(el.querySelectorAll('input:checked')).map(cb => cb.value);
}

function renderProjects(projects, container, u) {
  const grid = document.getElementById('projects-grid');
  if (!grid) return;

  if (projects.length === 0) {
    grid.innerHTML = `
      <div class="col-span-full text-center py-12">
        <svg class="w-10 h-10 mx-auto mb-3 text-zinc-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
        </svg>
        <div class="text-zinc-400 text-sm">No projects yet</div>
        <div class="text-zinc-600 text-xs mt-1">Create a project to give Ghost workspace context</div>
      </div>
    `;
    return;
  }

  grid.innerHTML = projects.map(p => {
    const memoryScope = p.memory_scope || p.config?.memory_scope || 'inherit';
    const skills = p.skills || p.config?.skills || [];
    const disabled = p.disabled_skills || p.config?.disabled_skills || [];
    const isActive = p.is_active ? '<span class="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-medium ml-2">active</span>' : '';

    return `
      <div class="stat-card project-card" data-project-id="${u.escapeHtml(p.id)}">
        <div class="flex items-start justify-between mb-2">
          <div class="flex items-center">
            <svg class="w-4 h-4 mr-2 text-ghost-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
            </svg>
            <span class="font-semibold text-white text-sm">${u.escapeHtml(p.name)}</span>
            ${isActive}
          </div>
          <div class="flex gap-1">
            <button class="text-zinc-500 hover:text-white text-xs px-1" data-edit="${u.escapeHtml(p.id)}" title="Edit">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
            </button>
            <button class="text-zinc-500 hover:text-red-400 text-xs px-1" data-delete="${u.escapeHtml(p.id)}" title="Delete">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
            </button>
          </div>
        </div>
        <div class="text-xs text-zinc-500 mb-3 font-mono truncate">${u.escapeHtml(p.path)}</div>
        ${p.description || p.config?.description ? `<div class="text-xs text-zinc-400 mb-3">${u.escapeHtml(p.description || p.config.description)}</div>` : ''}
        <div class="flex flex-wrap gap-1 mb-2">
          <span class="text-[9px] px-1.5 py-0.5 rounded-full font-medium ${memoryScope === 'isolated' ? 'bg-purple-500/20 text-purple-400' : memoryScope === 'shared' ? 'bg-blue-500/20 text-blue-400' : 'bg-zinc-600/30 text-zinc-400'}">memory: ${memoryScope}</span>
          ${skills.length ? `<span class="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-medium">${skills.length} skill${skills.length > 1 ? 's' : ''}</span>` : ''}
          ${disabled.length ? `<span class="text-[9px] px-1.5 py-0.5 rounded-full bg-red-500/20 text-red-400 font-medium">${disabled.length} disabled</span>` : ''}
        </div>
      </div>
    `;
  }).join('');

  grid.querySelectorAll('[data-edit]').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.edit;
      const project = allProjects.find(p => p.id === id);
      if (project) openModal(container, project);
    });
  });

  grid.querySelectorAll('[data-delete]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.delete;
      const project = allProjects.find(p => p.id === id);
      if (!project) return;
      if (!confirm(`Delete project "${project.name}"?\n\nThis removes it from the registry but does NOT delete any files.`)) return;
      const { GhostAPI: api, GhostUtils: u } = window;
      await api.del(`/api/projects/${id}`);
      u.toast('Project deleted');
      render(container);
    });
  });
}

function applyFilters(container, u) {
  const q = document.getElementById('projects-search').value.toLowerCase().trim();
  const filter = document.getElementById('projects-filter').value;

  const filtered = allProjects.filter(p => {
    const memScope = p.memory_scope || p.config?.memory_scope || 'inherit';
    if (filter === 'active' && !p.is_active) return false;
    if (filter === 'isolated' && memScope !== 'isolated') return false;
    if (filter === 'shared' && memScope !== 'shared') return false;
    if (q) {
      const hay = (p.name + ' ' + p.path + ' ' + (p.description || p.config?.description || '')).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  renderProjects(filtered, container, u);
}

function openModal(container, project) {
  editingProject = project;
  document.getElementById('modal-title').textContent = project ? 'Edit Project' : 'New Project';
  document.getElementById('inp-name').value = project?.name || '';
  document.getElementById('inp-path').value = project?.path || '';
  document.getElementById('inp-desc').value = project?.description || project?.config?.description || '';
  document.getElementById('inp-memory').value = project?.memory_scope || project?.config?.memory_scope || 'inherit';

  document.getElementById('inp-path').disabled = !!project;

  const enabledSkills = project?.skills || project?.config?.skills || [];
  const disabledSkills = project?.disabled_skills || project?.config?.disabled_skills || [];
  renderSkillPicker('skills-enabled-list', enabledSkills);
  renderSkillPicker('skills-disabled-list', disabledSkills);

  const hasSkillConfig = enabledSkills.length > 0 || disabledSkills.length > 0;
  const advSection = document.getElementById('advanced-section');
  const advArrow = document.getElementById('advanced-arrow');
  if (advSection) advSection.style.display = hasSkillConfig ? 'block' : 'none';
  if (advArrow) advArrow.style.transform = hasSkillConfig ? 'rotate(90deg)' : 'rotate(0deg)';

  document.getElementById('folder-browser').style.display = 'none';
  document.getElementById('project-modal').style.display = 'flex';
}

function closeModal() {
  document.getElementById('project-modal').style.display = 'none';
  editingProject = null;
}

async function saveProject(container, api, u) {
  const name = document.getElementById('inp-name').value.trim();
  const path = document.getElementById('inp-path').value.trim();
  const description = document.getElementById('inp-desc').value.trim();
  const memory_scope = document.getElementById('inp-memory').value;
  const skills = getSelectedSkills('skills-enabled-list');
  const disabled = getSelectedSkills('skills-disabled-list');

  if (!name) {
    u.toast('Name is required', 'error');
    return;
  }

  try {
    if (editingProject) {
      await api.put(`/api/projects/${editingProject.id}`, {
        name,
        description,
        memory_scope,
        skills,
        disabled_skills: disabled,
      });
      u.toast('Project updated');
    } else {
      if (!path) {
        u.toast('Path is required', 'error');
        return;
      }
      const body = { path, name, description, memory_scope };
      if (skills.length) body.skills = skills;
      if (disabled.length) body.disabled_skills = disabled;
      await api.post('/api/projects', body);
      u.toast('Project created');
    }
    closeModal();
    render(container);
  } catch (e) {
    u.toast(e.message || 'Failed to save project', 'error');
  }
}

async function _loadDirectory(api, pathStr) {
  const list = document.getElementById('folder-list');
  const breadcrumb = document.getElementById('folder-breadcrumb');
  if (!list) return;

  list.innerHTML = '<div class="text-[10px] text-zinc-500 p-2">Loading...</div>';

  try {
    const params = pathStr ? `?path=${encodeURIComponent(pathStr)}` : '';
    const data = await api.get(`/api/projects/browse${params}`);

    breadcrumb.textContent = data.current;

    let html = '';

    if (data.parent) {
      html += `<div class="folder-item folder-parent" data-path="${data.parent}">
        <svg class="w-3 h-3 text-zinc-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
        </svg>
        <span>..</span>
      </div>`;
    }

    html += `<div class="folder-item folder-select" data-path="${data.current}">
      <svg class="w-3 h-3 text-emerald-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
      </svg>
      <span class="text-emerald-400 font-medium">Select this folder</span>
    </div>`;

    for (const dir of data.directories) {
      html += `<div class="folder-item" data-path="${dir.path}">
        <svg class="w-3 h-3 text-zinc-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
        </svg>
        <span>${dir.name}</span>
        ${dir.has_children ? '<svg class="w-2.5 h-2.5 text-zinc-600 ml-auto flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>' : ''}
      </div>`;
    }

    if (data.directories.length === 0) {
      html += '<div class="text-[10px] text-zinc-600 p-2">No subdirectories</div>';
    }

    list.innerHTML = html;

    list.querySelectorAll('.folder-item:not(.folder-select)').forEach(item => {
      item.addEventListener('click', () => _loadDirectory(api, item.dataset.path));
    });

    list.querySelector('.folder-select')?.addEventListener('click', () => {
      document.getElementById('inp-path').value = data.current;
      document.getElementById('folder-browser').style.display = 'none';
      if (!document.getElementById('inp-name').value) {
        const name = data.current.split('/').pop() || data.current.split('\\').pop() || '';
        document.getElementById('inp-name').value = name;
      }
    });
  } catch (e) {
    list.innerHTML = `<div class="text-[10px] text-red-400 p-2">${e.message || 'Failed to browse'}</div>`;
  }
}
