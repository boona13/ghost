/** Ghost Dashboard — Main app router */

import { toast } from './utils.js';
import { render as overview } from './pages/overview.js';
import { render as models } from './pages/models.js';
import { render as config } from './pages/config.js';
import { render as soul } from './pages/soul.js';
import { render as user } from './pages/user.js';
import { render as skills } from './pages/skills.js';
import { render as cron } from './pages/cron.js';
import { render as memory } from './pages/memory.js';
import { render as feed } from './pages/feed.js';
import { render as evolve } from './pages/evolve.js';
import { render as chat } from './pages/chat.js';
import { render as integrations } from './pages/integrations.js';
import { render as autonomy } from './pages/autonomy.js';
import { render as accounts } from './pages/accounts.js';
import { render as setup } from './pages/setup.js';
import { render as security } from './pages/security.js';
import { render as console_page } from './pages/console.js';
import { render as channels } from './pages/channels.js';
import { render as future_features } from './pages/future_features.js';
import { render as webhooks } from './pages/webhooks.js';
import { render as projects } from './pages/projects.js';
import { render as prs } from './pages/prs.js';
import { render as mcp } from './pages/mcp.js';
const pages = { overview, chat, models, config, soul, user, skills, cron, memory, feed, evolve, integrations, autonomy, accounts, setup, security, console: console_page, channels, future_features, webhooks, projects, prs, mcp };
const container = document.getElementById('page-content');
let currentPage = null;
let pollTimer = null;
let needsSetup = false;
let _prevConnected = true;

function navigate(page) {
  page = page.split('?')[0];
  if (needsSetup && page !== 'setup') page = 'setup';
  if (!pages[page]) page = 'overview';
  currentPage = page;

  document.querySelectorAll('.nav-link').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
  });

  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }

  if (page === 'chat') {
    container.classList.add('chat-active');
  } else {
    container.classList.remove('chat-active');
  }

  container.innerHTML = '<div class="flex items-center justify-center h-32 text-zinc-600"><div class="animate-pulse">Loading...</div></div>';

  pages[page](container).catch(err => {
    container.innerHTML = `<div class="text-red-400 p-4">Error loading page: ${err.message}</div>`;
  });

  if (page === 'feed') {
    pollTimer = setInterval(() => pages.feed(container), 5000);
  }
}

document.querySelectorAll('.nav-link').forEach(el => {
  el.addEventListener('click', (e) => {
    e.preventDefault();
    const page = el.dataset.page;
    window.location.hash = page;
    navigate(page);
  });
});

/* ── Sidebar collapse/expand ─────────────────────────────────── */
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebar-toggle');

if (localStorage.getItem('ghost-sidebar-collapsed') === '1') {
  sidebar.classList.add('collapsed');
}

sidebarToggle.addEventListener('click', () => {
  sidebar.classList.toggle('collapsed');
  const isCollapsed = sidebar.classList.contains('collapsed');
  localStorage.setItem('ghost-sidebar-collapsed', isCollapsed ? '1' : '0');
  sidebarToggle.title = isCollapsed ? 'Expand sidebar' : 'Collapse sidebar';
});

async function updateSidebarStatus() {
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  try {
    const s = await window.GhostAPI.get('/api/status');
    if (s.running && !s.paused) {
      dot.className = 'w-2 h-2 rounded-full bg-emerald-500 animate-pulse';
      text.textContent = `Running (PID ${s.pid})`;
    } else if (s.paused) {
      dot.className = 'w-2 h-2 rounded-full bg-amber-500';
      text.textContent = 'Paused';
    } else {
      dot.className = 'w-2 h-2 rounded-full bg-zinc-600';
      text.textContent = 'Stopped';
    }
    if (!_prevConnected) {
      _prevConnected = true;
      window.dispatchEvent(new CustomEvent('ghost:restarted'));
      toast('Ghost restarted successfully');
    }
  } catch {
    if (_prevConnected) {
      _prevConnected = false;
      dot.className = 'w-2 h-2 rounded-full bg-amber-500 ghost-restart-pulse';
      text.textContent = 'Restarting...';
    }
  }
  try {
    const a = await window.GhostAPI.get('/api/autonomy/actions');
    const badge = document.getElementById('action-items-count');
    if (badge && a.pending_count > 0) {
      badge.textContent = a.pending_count;
      badge.classList.remove('hidden');
    } else if (badge) {
      badge.classList.add('hidden');
    }
  } catch {}
}

async function init() {
  try {
    const setupStatus = await window.GhostAPI.get('/api/setup/status');
    if (setupStatus.needs_setup) {
      needsSetup = true;
      document.getElementById('sidebar').classList.add('hidden');
      navigate('setup');
      return;
    }
  } catch {}

  const initPage = (window.location.hash || '#chat').slice(1);
  navigate(initPage);
  updateSidebarStatus();
  setInterval(updateSidebarStatus, 5000);
  
  // Start usage status polling
  updateUsageStatus();
  setInterval(updateUsageStatus, 3000);
}

init();

window.addEventListener('hashchange', () => {
  navigate(window.location.hash.slice(1));
});

/* ── Usage Status Bar ─────────────────────────────────────────── */
async function updateUsageStatus() {
  const providerEl = document.getElementById('status-provider');
  const modelEl = document.getElementById('status-model');
  const activeDotEl = document.getElementById('status-active-dot');
  const tokensEl = document.getElementById('status-tokens');
  
  if (!providerEl || !modelEl || !tokensEl) return;
  
  try {
    const usage = await window.GhostAPI.get('/api/usage/live');
    
    providerEl.textContent = usage.provider || '—';
    modelEl.textContent = usage.model || '—';
    tokensEl.textContent = usage.session_tokens?.toLocaleString() || '0';
    
    if (usage.active) {
      activeDotEl?.classList.remove('hidden');
    } else {
      activeDotEl?.classList.add('hidden');
    }
  } catch (err) {
    // Silent fail - status bar is non-critical
    providerEl.textContent = '—';
    modelEl.textContent = '—';
    activeDotEl?.classList.add('hidden');
  }
}
