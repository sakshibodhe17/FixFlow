import axios from 'axios';

export const API_ORIGIN = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const TOKEN_KEY = 'fixflow_token';

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

const api = axios.create({ baseURL: `${API_ORIGIN}/api`, timeout: 60000 });

api.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && !err.config.url.includes('/auth/login')) {
      tokenStore.clear();
      if (!window.location.pathname.startsWith('/login')) window.location.assign('/login?expired=1');
    }
    return Promise.reject(err);
  },
);

export default api;

/** Human-readable message from an API error (FastAPI `detail` can be a string or a list). */
export function errorMessage(err) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d.length) {
    return d.map((e) => `${(e.loc || []).slice(1).join(' ') || 'Field'}: ${e.msg}`).join('. ');
  }
  if (err?.code === 'ERR_NETWORK') return `Can't reach the server at ${API_ORIGIN}. Check that the backend is running.`;
  return err?.message || 'Something went wrong.';
}

export const fileUrl = (path) => (path?.startsWith('http') ? path : `${API_ORIGIN}${path}`);

/** Download a file from an authenticated endpoint. */
export async function download(url, params, fallbackName) {
  const res = await api.get(url, { params, responseType: 'blob' });
  const cd = res.headers['content-disposition'] || '';
  const name = /filename="?([^"]+)"?/.exec(cd)?.[1] || fallbackName;
  const href = URL.createObjectURL(res.data);
  const a = document.createElement('a');
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
