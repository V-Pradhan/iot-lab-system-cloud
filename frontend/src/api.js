let token = localStorage.getItem('token');
let labId = localStorage.getItem('labId');

export function setToken(t) {
  token = t;
  if (t) localStorage.setItem('token', t);
  else localStorage.removeItem('token');
}
export const hasToken = () => !!token;

export function setLabId(id) {
  labId = id ? String(id) : null;
  if (labId) localStorage.setItem('labId', labId);
  else localStorage.removeItem('labId');
}

function errorText(j, fallback) {
  if (!j || !j.detail) return fallback;
  if (typeof j.detail === 'string') return j.detail;
  if (Array.isArray(j.detail)) {
    return j.detail.map((d) => `${(d.loc || []).slice(1).join(' ')}: ${d.msg}`).join('; ');
  }
  return fallback;
}

async function request(method, path, body, asBlob) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = 'Bearer ' + token;
  if (labId) headers['X-Lab-Id'] = labId;
  let res;
  try {
    res = await fetch('/api' + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error('Cannot reach the server. Check that the backend is running.');
  }
  if (res.status === 401 && token) {
    setToken(null);
    window.dispatchEvent(new Event('auth-expired'));
  }
  if (!res.ok) {
    let j = null;
    try { j = await res.json(); } catch { /* not json */ }
    throw new Error(errorText(j, res.statusText || 'Request failed'));
  }
  return asBlob ? res.blob() : res.json();
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b = {}) => request('POST', p, b),
  patch: (p, b) => request('PATCH', p, b),
  put: (p, b) => request('PUT', p, b),
  del: (p) => request('DELETE', p),
  async download(path, filename) {
    const blob = await request('GET', path, undefined, true);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
};
