const CURRENCY = 'INR';
const LOCALE = 'en-IN';

const toDate = (v) => (v ? new Date(v) : null);

export const fmt = {
  date: (v) => (v ? toDate(v).toLocaleDateString(LOCALE, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'),
  dateTime: (v) => (v ? toDate(v).toLocaleString(LOCALE, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'),
  money: (v) => (v == null ? '—' : new Intl.NumberFormat(LOCALE, { style: 'currency', currency: CURRENCY, maximumFractionDigits: 0 }).format(v)),
  num: (v, d = 0) => (v == null ? '—' : Number(v).toLocaleString(LOCALE, { maximumFractionDigits: d })),
  pct: (v) => (v == null ? '—' : `${Number(v).toFixed(v >= 99.95 || v === 0 ? 0 : 1)}%`),
  hours: (v) => {
    if (v == null) return '—';
    if (v < 1) return `${Math.round(v * 60)} min`;
    if (v < 48) return `${Number(v).toFixed(1)} h`;
    return `${(v / 24).toFixed(1)} days`;
  },
  /** "in 3 h", "2 days ago" */
  relative: (v) => {
    if (!v) return '—';
    const diff = (toDate(v) - Date.now()) / 1000;
    const abs = Math.abs(diff);
    const rtf = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' });
    if (abs < 60) return rtf.format(Math.round(diff), 'second');
    if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute');
    if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour');
    return rtf.format(Math.round(diff / 86400), 'day');
  },
  duration: (seconds) => {
    const s = Math.max(0, Math.floor(seconds));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  },
};

export const SEVERITIES = ['Low', 'Medium', 'High', 'Critical'];
export const STATUSES = ['Open', 'Assigned', 'In Progress', 'On Hold', 'Resolved', 'Closed', 'Reopened'];
