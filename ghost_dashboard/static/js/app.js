/** Ghost Dashboard — Main app router */

import { toast } from './utils.js';
import { i18n } from './i18n/index.js';
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
import { render as langfuse } from './pages/langfuse.js';
import { render as browser_use } from './pages/browser_use.js';
import { render as pairing } from './pages/pairing.js';
import { render as nodes } from './pages/nodes.js';
import { render as gallery } from './pages/gallery.js';
import { render as extensions } from './pages/extensions.js';
import { render as audit } from './pages/audit.js';
const pages = { overview, chat, models, config, soul, user, skills, cron, memory, feed, evolve, integrations, autonomy, accounts, setup, security, console: console_page, channels, future_features, webhooks, projects, prs, mcp, langfuse, browser_use, pairing, nodes, gallery, extensions, audit };
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

  container.innerHTML = `<div class="flex items-center justify-center h-32 text-zinc-600"><div class="animate-pulse">${i18n.t('common.loading')}</div></div>`;

  pages[page](container).catch(err => {
    container.innerHTML = `<div class="text-red-400 p-4">${i18n.t('common.error')}: ${err.message}</div>`;
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
  sidebarToggle.title = isCollapsed ? i18n.t('sidebar.expand') : i18n.t('sidebar.collapse');
});

async function updateSidebarStatus() {
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  try {
    const s = await window.GhostAPI.get('/api/status');
    if (s.running && !s.paused) {
      dot.className = 'w-2 h-2 rounded-full bg-emerald-500 animate-pulse';
      text.textContent = i18n.t('status.runningPid', {pid: s.pid});
    } else if (s.paused) {
      dot.className = 'w-2 h-2 rounded-full bg-amber-500';
      text.textContent = i18n.t('status.paused');
    } else {
      dot.className = 'w-2 h-2 rounded-full bg-zinc-600';
      text.textContent = i18n.t('status.stopped');
    }
    if (!_prevConnected) {
      _prevConnected = true;
      window.dispatchEvent(new CustomEvent('ghost:restarted'));
      toast(i18n.t('status.ghostRestartedSuccess'));
    }
  } catch {
    if (_prevConnected) {
      _prevConnected = false;
      dot.className = 'w-2 h-2 rounded-full bg-amber-500 ghost-restart-pulse';
      text.textContent = i18n.t('status.restarting');
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
  await i18n.init();

  const langSelector = document.getElementById('lang-selector');
  if (langSelector) {
    langSelector.value = i18n.getLocale();
    langSelector.addEventListener('change', () => {
      i18n.setLocale(langSelector.value);
    });
  }

  i18n.onChange(() => {
    if (currentPage && pages[currentPage]) {
      pages[currentPage](container).catch(() => {});
    }
  });

  try {
    const setupStatus = await window.GhostAPI.get('/api/setup/status');
    if (setupStatus.needs_setup) {
      needsSetup = true;
      document.getElementById('sidebar').classList.add('hidden');
      navigate('setup');
      return;
    }
  } catch {}

  await loadExtensionPages();

  const initPage = (window.location.hash || '#chat').slice(1);
  navigate(initPage);
  updateSidebarStatus();
  setInterval(updateSidebarStatus, 5000);
  
  // Start usage status polling
  updateUsageStatus();
  setInterval(updateUsageStatus, 3000);
}

async function loadExtensionPages() {
  try {
    const data = await window.GhostAPI.get('/api/extensions/pages');
    const extPages = (data && data.pages) || [];
    const navContainer = document.getElementById('extension-nav-items');
    const navSection = document.getElementById('extension-nav-section');
    let addedCount = 0;

    for (const page of extPages) {
      if (!page.id || !page.js_url || pages[page.id]) continue;
      const jsUrl = page.js_url;
      if (!jsUrl.startsWith('/extensions/') && !jsUrl.startsWith('/static/')) continue;
      try {
        const mod = await import(jsUrl);
        if (mod.render) {
          pages[page.id] = mod.render;
          if (navContainer) {
            const link = document.createElement('a');
            link.href = `#${page.id}`;
            link.className = 'nav-link';
            link.dataset.page = page.id;
            const label = (page.label || page.id).replace(/[<>&"']/g, '');
            link.title = label;
            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('class', 'nav-icon w-4 h-4');
            svg.setAttribute('fill', 'none');
            svg.setAttribute('viewBox', '0 0 24 24');
            svg.setAttribute('stroke', 'currentColor');
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('stroke-linecap', 'round');
            path.setAttribute('stroke-linejoin', 'round');
            path.setAttribute('stroke-width', '2');
            path.setAttribute('d', 'M11 4a2 2 0 114 0v1a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-1a2 2 0 100 4h1a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-1a2 2 0 10-4 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-3a1 1 0 00-1-1H4a2 2 0 110-4h1a1 1 0 001-1V7a1 1 0 011-1h3a1 1 0 001-1V4z');
            svg.appendChild(path);
            link.appendChild(svg);
            const span = document.createElement('span');
            span.className = 'nav-label';
            span.textContent = label;
            link.appendChild(span);
            link.addEventListener('click', (e) => {
              e.preventDefault();
              window.location.hash = page.id;
              navigate(page.id);
            });
            navContainer.appendChild(link);
            addedCount++;
          }
        }
      } catch (err) {
        console.warn(`Failed to load extension page ${page.id}:`, err);
      }
    }
    if (addedCount > 0 && navSection) navSection.classList.remove('hidden');
  } catch {
    // Extension system not available — silent fail
  }
}

window.GhostI18n = i18n;

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
