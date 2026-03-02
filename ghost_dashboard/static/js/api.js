/** Ghost Dashboard API client */

export const api = {
  async get(url) {
    const r = await fetch(url);
    return r.json();
  },

  async put(url, data) {
    const r = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return r.json();
  },

  async post(url, data = {}) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return r.json();
  },

  async postRaw(url, data = {}, extraHeaders = {}) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...extraHeaders },
      body: JSON.stringify(data),
    });
    return r.json();
  },

  async patch(url, data = {}) {
    const r = await fetch(url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return r.json();
  },

  async del(url) {
    const r = await fetch(url, { method: 'DELETE' });
    return r.json();
  },
};

window.GhostAPI = api;
