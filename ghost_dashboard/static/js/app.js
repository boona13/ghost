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
import { render as langfuse } from './pages/langfuse.js';
import { render as browser_use } from './pages/browser_use.js';
import { render as pairing } from './pages/pairing.js';
import { render as nodes } from './pages/nodes.js';
import { render as gallery } from './pages/gallery.js';
import { render as audit } from './pages/audit.js';
const pages = { overview, chat, models, config, soul, user, skills, cron, memory, feed, evolve, integrations, autonomy, accounts, setup, security, console: console_page, channels, future_features, webhooks, projects, prs, langfuse, browser_use, pairing, nodes, gallery, audit };
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

  _ensureSectionVisible(page);
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

/* ── Collapsible nav sections ─────────────────────────────────── */
document.querySelectorAll('.nav-section-toggle').forEach(toggle => {
  const section = toggle.dataset.section;
  const body = document.querySelector(`[data-section-body="${section}"]`);
  if (!body) return;
  const storageKey = `ghost-nav-${section}`;
  const isExpanded = localStorage.getItem(storageKey) === '1';
  if (isExpanded) {
    body.style.display = '';
    toggle.classList.add('expanded');
    toggle.setAttribute('aria-expanded', 'true');
  }
  toggle.addEventListener('click', () => {
    const nowExpanded = body.style.display === 'none';
    body.style.display = nowExpanded ? '' : 'none';
    toggle.classList.toggle('expanded', nowExpanded);
    toggle.setAttribute('aria-expanded', String(nowExpanded));
    localStorage.setItem(storageKey, nowExpanded ? '1' : '0');
  });
});

/* When navigating to a page inside a collapsed section, expand it */
const _origNavigate = navigate;
function _ensureSectionVisible(page) {
  const link = document.querySelector(`.nav-link[data-page="${page}"]`);
  if (!link) return;
  const body = link.closest('.nav-section-body');
  if (body && body.style.display === 'none') {
    body.style.display = '';
    const section = body.dataset.sectionBody;
    const toggle = document.querySelector(`.nav-section-toggle[data-section="${section}"]`);
    if (toggle) toggle.classList.add('expanded');
    localStorage.setItem(`ghost-nav-${section}`, '1');
  }
}

const origNavLinks = document.querySelectorAll('.nav-link');
origNavLinks.forEach(el => {
  el.addEventListener('click', () => _ensureSectionVisible(el.dataset.page));
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

  const initPage = (window.location.hash || '#chat').slice(1);
  navigate(initPage);
  updateSidebarStatus();
  setInterval(updateSidebarStatus, 5000);
  
  // Start usage status polling
  updateUsageStatus();
  setInterval(updateUsageStatus, 3000);
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
  
  const tooltipEl = document.getElementById('status-provider-tooltip');
  try {
    const usage = await window.GhostAPI.get('/api/usage/live');

    const modelName = (usage.model || '—').split('/').pop();
    providerEl.textContent = usage.provider || '—';
    modelEl.textContent = modelName;
    tokensEl.textContent = usage.session_tokens?.toLocaleString() || '0';
    if (tooltipEl) tooltipEl.textContent = `${usage.provider || ''}/${usage.model || ''}`;

    if (usage.active) {
      activeDotEl?.classList.remove('hidden');
    } else {
      activeDotEl?.classList.add('hidden');
    }
  } catch (err) {
    providerEl.textContent = '—';
    modelEl.textContent = '—';
    activeDotEl?.classList.add('hidden');
  }
}
