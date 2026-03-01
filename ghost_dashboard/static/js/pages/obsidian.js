/** Obsidian Vault Integration Page */

let vaults = [];
let selectedVault = null;

export async function render(container) {
  const { GhostAPI: api, GhostUtils: u } = window;

  container.innerHTML = `
    <div class="page-header">Obsidian Vaults</div>
    <div class="page-desc">Manage Obsidian vaults and configure note workflows</div>

    <div class="stat-card" style="margin-top: 1rem;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
        <h3 style="margin:0; font-size:0.9rem; color:var(--text-white);">Vault Configuration</h3>
        <button id="add-vault-btn" class="btn btn-primary">+ Add Vault</button>
      </div>

      <div id="vaults-list" class="vaults-list"></div>

      <div id="add-vault-form" style="display:none; margin-top:1rem; padding:1rem; background:rgba(0,0,0,0.2); border-radius:8px;">
        <div class="form-group">
          <label class="form-label">Vault Path</label>
          <input type="text" id="vault-path-input" class="form-input" placeholder="/Users/name/Documents/Obsidian/Vault">
          <div style="font-size:0.75rem; color:var(--text-secondary); margin-top:0.25rem;">
            Absolute path to your Obsidian vault folder
          </div>
        </div>
        <div style="display:flex; gap:0.5rem; margin-top:0.75rem;">
          <button id="save-vault-btn" class="btn btn-primary">Save</button>
          <button id="cancel-add-btn" class="btn btn-secondary">Cancel</button>
          <button id="discover-btn" class="btn btn-ghost">Discover from Obsidian</button>
        </div>
        <div id="discover-results" style="margin-top:0.75rem;"></div>
      </div>
    </div>

    <div class="stat-card" style="margin-top:1rem;">
      <h3 style="margin:0 0 1rem 0; font-size:0.9rem; color:var(--text-white);">Settings</h3>

      <div class="form-group">
        <label class="form-label">Default Vault</label>
        <select id="default-vault-select" class="form-input">
          <option value="">-- Select default --</option>
        </select>
      </div>

      <div class="form-group" style="margin-top:0.75rem;">
        <label class="form-label">Daily Notes Folder</label>
        <input type="text" id="daily-folder-input" class="form-input" placeholder="Daily">
      </div>

      <div class="form-group" style="margin-top:0.75rem;">
        <label class="form-label">Capture Folder</label>
        <input type="text" id="capture-folder-input" class="form-input" placeholder="Clippings">
      </div>

      <div style="margin-top:1rem;">
        <button id="save-settings-btn" class="btn btn-primary">Save Settings</button>
      </div>
    </div>

    <div class="stat-card" style="margin-top:1rem;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
        <h3 style="margin:0; font-size:0.9rem; color:var(--text-white);">Quick Actions</h3>
      </div>
      <div style="display:flex; gap:0.5rem; flex-wrap:wrap;">
        <button id="daily-note-btn" class="btn btn-secondary" ${!selectedVault ? 'disabled' : ''}>Create Daily Note</button>
        <button id="capture-btn" class="btn btn-secondary" ${!selectedVault ? 'disabled' : ''}>Capture Knowledge</button>
      </div>
    </div>
  `;

  // Load data
  await loadVaults();
  await loadSettings();

  // Event handlers
  document.getElementById('add-vault-btn').addEventListener('click', () => {
    document.getElementById('add-vault-form').style.display = 'block';
  });

  document.getElementById('cancel-add-btn').addEventListener('click', () => {
    document.getElementById('add-vault-form').style.display = 'none';
    document.getElementById('vault-path-input').value = '';
    document.getElementById('discover-results').innerHTML = '';
  });

  document.getElementById('save-vault-btn').addEventListener('click', async () => {
    const path = document.getElementById('vault-path-input').value.trim();
    if (!path) return;

    try {
      const result = await api.post('/api/obsidian/vaults', { path });
      if (result.success) {
        u.toast('Vault added successfully');
        document.getElementById('add-vault-form').style.display = 'none';
        document.getElementById('vault-path-input').value = '';
        await loadVaults();
      } else {
        u.toast(result.error || 'Failed to add vault', 'error');
      }
    } catch (e) {
      u.toast(e.message, 'error');
    }
  });

  document.getElementById('discover-btn').addEventListener('click', async () => {
    const resultsDiv = document.getElementById('discover-results');
    resultsDiv.innerHTML = '<div style="color:var(--text-secondary);">Discovering...</div>';

    try {
      const result = await api.get('/api/obsidian/discover');
      if (result.vaults && result.vaults.length > 0) {
        let html = '<div style="margin-top:0.5rem;"><strong>Found vaults:</strong></div>';
        result.vaults.forEach(v => {
          html += `
            <div style="display:flex; justify-content:space-between; align-items:center; padding:0.5rem; background:rgba(255,255,255,0.05); margin-top:0.25rem; border-radius:4px;">
              <span>${v.name}</span>
              <button class="btn btn-sm btn-primary" onclick="document.getElementById('vault-path-input').value = '${v.path}'">Select</button>
            </div>
          `;
        });
        resultsDiv.innerHTML = html;
      } else {
        resultsDiv.innerHTML = '<div style="color:var(--text-secondary);">No vaults found in obsidian.json</div>';
      }
    } catch (e) {
      resultsDiv.innerHTML = `<div style="color:var(--danger);">Error: ${e.message}</div>`;
    }
  });

  document.getElementById('save-settings-btn').addEventListener('click', async () => {
    const config = {
      default_vault: document.getElementById('default-vault-select').value,
      daily_notes_folder: document.getElementById('daily-folder-input').value,
      capture_folder: document.getElementById('capture-folder-input').value,
    };

    try {
      await api.post('/api/obsidian/config', config);
      u.toast('Settings saved');
    } catch (e) {
      u.toast(e.message, 'error');
    }
  });

  document.getElementById('daily-note-btn').addEventListener('click', async () => {
    if (!selectedVault) return;
    u.toast('Use obsidian_daily_note tool to create daily notes');
  });

  document.getElementById('capture-btn').addEventListener('click', async () => {
    if (!selectedVault) return;
    u.toast('Use obsidian_knowledge_capture tool to capture knowledge');
  });
}

async function loadVaults() {
  const { GhostAPI: api } = window;
  const listDiv = document.getElementById('vaults-list');
  const defaultSelect = document.getElementById('default-vault-select');

  try {
    const result = await api.get('/api/obsidian/vaults');
    vaults = result.vaults || [];

    if (vaults.length === 0) {
      listDiv.innerHTML = '<div style="color:var(--text-secondary); padding:1rem; text-align:center;">No vaults configured</div>';
    } else {
      listDiv.innerHTML = vaults.map(v => `
        <div class="vault-item" style="display:flex; justify-content:space-between; align-items:center; padding:0.75rem; background:rgba(255,255,255,0.03); border-radius:8px; margin-bottom:0.5rem; ${v.path === selectedVault ? 'border:1px solid var(--primary);' : ''}">
          <div>
            <div style="font-weight:500;">${v.name}</div>
            <div style="font-size:0.75rem; color:var(--text-secondary);">${v.path}</div>
            ${v.exists ? '<span class="badge badge-green">✓</span>' : '<span class="badge badge-red">✗</span>'}
          </div>
          <div style="display:flex; gap:0.5rem;">
            <button class="btn btn-sm btn-secondary" onclick="window.selectVault('${v.path}')">Select</button>
            <button class="btn btn-sm btn-danger" onclick="window.removeVault('${encodeURIComponent(v.path)}')">Remove</button>
          </div>
        </div>
      `).join('');
    }

    // Update default select
    defaultSelect.innerHTML = '<option value="">-- Select default --</option>' +
      vaults.map(v => `<option value="${v.path}">${v.name}</option>`).join('');

    if (result.default_vault) {
      defaultSelect.value = result.default_vault;
    }

  } catch (e) {
    listDiv.innerHTML = `<div style="color:var(--danger);">Error loading vaults: ${e.message}</div>`;
  }
}

async function loadSettings() {
  const { GhostAPI: api } = window;

  try {
    const config = await api.get('/api/obsidian/config');
    document.getElementById('daily-folder-input').value = config.daily_notes_folder || '';
    document.getElementById('capture-folder-input').value = config.capture_folder || '';
  } catch (e) {
    console.error('Failed to load settings:', e);
  }
}

// Global functions for onclick handlers
window.selectVault = (path) => {
  selectedVault = path;
  loadVaults();
  document.getElementById('daily-note-btn').disabled = false;
  document.getElementById('capture-btn').disabled = false;
};

window.removeVault = async (encodedPath) => {
  const { GhostAPI: api, GhostUtils: u } = window;
  const path = decodeURIComponent(encodedPath);

  if (!confirm('Remove this vault from configuration?')) return;

  try {
    await api.delete(`/api/obsidian/vaults/${encodedPath}`);
    u.toast('Vault removed');
    if (selectedVault === path) {
      selectedVault = null;
      document.getElementById('daily-note-btn').disabled = true;
      document.getElementById('capture-btn').disabled = true;
    }
    await loadVaults();
  } catch (e) {
    u.toast(e.message, 'error');
  }
};
