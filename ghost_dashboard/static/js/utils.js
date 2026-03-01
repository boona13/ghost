/** Shared utilities */

export function toast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

export function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

export function timeAgo(iso) {
  const d = new Date(iso);
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function formatTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

export const TYPE_ICONS = {
  url: '🔗', error: '🔧', code: '💻', long_text: '📝',
  foreign: '🌍', json: '📊', image: '📸', ask: '💬', cron: '⏰',
};

export const TYPE_COLORS = {
  url: 'blue', error: 'red', code: 'purple', long_text: 'zinc',
  foreign: 'green', json: 'yellow', image: 'purple', ask: 'purple', cron: 'yellow',
};

window.GhostUtils = { toast, escapeHtml, timeAgo, formatTime, TYPE_ICONS, TYPE_COLORS };
