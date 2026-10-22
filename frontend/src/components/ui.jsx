import { forwardRef, useEffect, useRef } from 'react';
import { AlertTriangle, Loader2, X } from 'lucide-react';
import { fmt } from '../lib/format';
import { useTicker } from '../lib/hooks';

export const cx = (...c) => c.filter(Boolean).join(' ');

// ---- Buttons & inputs --------------------------------------------------------
const VARIANTS = {
  primary: 'bg-blueprint text-white hover:bg-blueprint-dark disabled:bg-blueprint/50',
  secondary: 'bg-white text-ink border border-line hover:border-ink-faint disabled:text-ink-faint',
  ghost: 'text-blueprint hover:bg-blueprint-light',
  danger: 'bg-breach text-white hover:bg-breach/90 disabled:bg-breach/50',
  success: 'bg-moss text-white hover:bg-moss/90 disabled:bg-moss/50',
  amber: 'bg-signal text-ink hover:bg-signal/90',
};
const SIZES = { sm: 'h-8 px-3 text-xs', md: 'h-10 px-4 text-sm', lg: 'h-12 px-5 text-base' };

export function Button({ variant = 'primary', size = 'md', busy, icon: Icon, className, children, ...props }) {
  return (
    <button
      type="button"
      {...props}
      disabled={busy || props.disabled}
      className={cx('inline-flex items-center justify-center gap-2 rounded font-medium transition-colors disabled:cursor-not-allowed',
        VARIANTS[variant], SIZES[size], className)}
    >
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : Icon ? <Icon className="h-4 w-4" aria-hidden /> : null}
      {children}
    </button>
  );
}

export function Field({ label, hint, error, children, className }) {
  return (
    <label className={cx('block', className)}>
      {label && <span className="mb-1 block text-sm font-medium text-ink">{label}</span>}
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-ink-soft">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-breach">{error}</span>}
    </label>
  );
}

export const Input = forwardRef((props, ref) => <input ref={ref} {...props} className={cx('field', props.className)} />);
export const Textarea = forwardRef((props, ref) => <textarea ref={ref} rows={4} {...props} className={cx('field', props.className)} />);
export const Select = forwardRef(({ children, ...props }, ref) => (
  <select ref={ref} {...props} className={cx('field pr-8', props.className)}>{children}</select>
));

// ---- Layout pieces -----------------------------------------------------------
export function PageHeader({ title, subtitle, actions, children }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-bold text-ink sm:text-[28px] sm:leading-9">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-ink-soft">{subtitle}</p>}
        {children}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ title, actions, children, className, bodyClass, note }) {
  return (
    <section className={cx('rounded-md border border-line bg-white', className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
          <div>
            <h2 className="text-base font-semibold">{title}</h2>
            {note && <p className="text-xs text-ink-soft">{note}</p>}
          </div>
          {actions && <div className="flex gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx('p-4', bodyClass)}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub, tone = 'default' }) {
  const tones = {
    default: 'border-l-blueprint', amber: 'border-l-signal', red: 'border-l-breach', green: 'border-l-moss',
  };
  return (
    <div className={cx('rounded-sm border border-line border-l-4 bg-white px-4 py-3', tones[tone])}>
      <div className="text-xs text-ink-soft">{label}</div>
      <div className="mt-1 font-narrow text-3xl font-semibold leading-none text-ink">{value}</div>
      {sub && <div className="mt-1.5 text-xs text-ink-soft">{sub}</div>}
    </div>
  );
}

export function Spinner({ label = 'Loading…' }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-ink-soft" role="status">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}

export function ErrorNote({ children }) {
  if (!children) return null;
  return (
    <div className="flex items-start gap-2 rounded border border-breach/30 bg-breach-light px-3 py-2 text-sm text-breach" role="alert">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> <span>{children}</span>
    </div>
  );
}

export function Empty({ title, children, action }) {
  return (
    <div className="rounded border border-dashed border-line px-6 py-10 text-center">
      <p className="font-medium text-ink">{title}</p>
      {children && <p className="mx-auto mt-1 max-w-md text-sm text-ink-soft">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// ---- Status vocabulary -------------------------------------------------------
const STATUS_STYLE = {
  Open: 'bg-white text-ink border-ink-faint',
  Assigned: 'bg-blueprint-light text-blueprint-dark border-blueprint/30',
  'In Progress': 'bg-blueprint text-white border-blueprint',
  'On Hold': 'bg-paper text-ink-soft border-line',
  Resolved: 'bg-moss-light text-moss border-moss/30',
  Closed: 'bg-paper text-ink-soft border-line',
  Reopened: 'bg-signal-light text-signal-dark border-signal/40',
};
export function StatusPill({ status }) {
  return (
    <span className={cx('inline-flex items-center whitespace-nowrap rounded-sm border px-2 py-0.5 text-xs font-medium', STATUS_STYLE[status])}>
      {status}
    </span>
  );
}

const SEV_BARS = { Low: 1, Medium: 2, High: 3, Critical: 4 };
/** Severity as a 4-step meter — readable without colour. */
export function SeverityPill({ severity }) {
  const n = SEV_BARS[severity] || 0;
  const color = n >= 4 ? 'bg-breach' : n === 3 ? 'bg-signal' : 'bg-ink-soft';
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium text-ink" title={`${severity} severity`}>
      <span className="flex items-end gap-[2px]" aria-hidden>
        {[1, 2, 3, 4].map((i) => (
          <span key={i} className={cx('w-[3px] rounded-[1px]', i <= n ? color : 'bg-line')} style={{ height: 4 + i * 2.5 }} />
        ))}
      </span>
      {severity}
    </span>
  );
}

export function RiskPill({ level, score }) {
  const style = { High: 'bg-breach text-white', Medium: 'bg-signal-light text-signal-dark', Low: 'bg-moss-light text-moss' }[level];
  return (
    <span className={cx('inline-flex items-center gap-1 whitespace-nowrap rounded-sm px-2 py-0.5 text-xs font-semibold', style)}>
      {level}{score != null && <span className="font-normal opacity-80">{Math.round(score * 100)}%</span>}
    </span>
  );
}

/**
 * The SLA gauge — FixFlow's signature element.
 * The bar fills as the SLA window is consumed; amber once it crosses the warning line,
 * red when the deadline has passed. The tick marks the warning threshold.
 */
export function SlaBar({ sla, warnPct = 75, compact = false }) {
  useTicker(30000);
  if (!sla) return <span className="text-xs text-ink-faint">No SLA</span>;
  const { state } = sla;
  const due = new Date(sla.resolution_due);
  const start = new Date(sla.window_start);
  const live = state === 'on_track' || state === 'at_risk' || state === 'breached';
  const pct = live ? ((Date.now() - start) / Math.max(due - start, 1)) * 100 : sla.pct_elapsed;
  const liveState = live ? (Date.now() > due ? 'breached' : pct >= warnPct ? 'at_risk' : 'on_track') : state;
  const fill = { on_track: 'bg-blueprint', at_risk: 'bg-signal', breached: 'bg-breach', met: 'bg-moss', missed: 'bg-breach/60' }[liveState];
  const secs = (due - Date.now()) / 1000;
  const text = {
    on_track: `${fmt.hours(secs / 3600)} left`,
    at_risk: `${fmt.hours(secs / 3600)} left`,
    breached: `${fmt.hours(-secs / 3600)} late`,
    met: 'Met SLA',
    missed: 'Missed SLA',
  }[liveState];
  const textColor = liveState === 'breached' || liveState === 'missed' ? 'text-breach' : liveState === 'at_risk' ? 'text-signal-dark' : liveState === 'met' ? 'text-moss' : 'text-ink-soft';

  return (
    <div className={cx(compact ? 'w-28' : 'w-full max-w-xs')} title={`Due ${fmt.dateTime(sla.resolution_due)}`}>
      <div className={cx('mb-1 flex justify-between gap-2 text-xs', textColor)}>
        <span className="font-medium">{text}</span>
        {!compact && <span className="text-ink-faint">due {fmt.dateTime(sla.resolution_due)}</span>}
      </div>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="SLA time used">
        <div className={cx('h-full rounded-full transition-[width] duration-700', fill)} style={{ width: `${Math.min(100, Math.max(2, pct))}%` }} />
        <div className="absolute top-0 h-full w-px bg-ink/30" style={{ left: `${warnPct}%` }} />
      </div>
    </div>
  );
}

// ---- Modal -------------------------------------------------------------------
export function Modal({ open, onClose, title, children, footer, wide }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const prev = document.activeElement;
    const onKey = (e) => e.key === 'Escape' && onClose?.();
    document.addEventListener('keydown', onKey);
    ref.current?.querySelector('input, select, textarea, button')?.focus();
    return () => { document.removeEventListener('keydown', onKey); prev?.focus?.(); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-0 sm:items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title}
        className={cx('max-h-[92vh] w-full overflow-y-auto rounded-t-lg bg-white shadow-xl sm:rounded-lg', wide ? 'sm:max-w-3xl' : 'sm:max-w-lg')}>
        <header className="sticky top-0 flex items-center justify-between border-b border-line bg-white px-5 py-3">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button type="button" onClick={onClose} className="rounded p-1 text-ink-soft hover:bg-paper" aria-label="Close"><X className="h-5 w-5" /></button>
        </header>
        <div className="px-5 py-4">{children}</div>
        {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">{footer}</footer>}
      </div>
    </div>
  );
}

export function Stars({ value, onChange, size = 'h-6 w-6' }) {
  return (
    <div className="flex gap-1" role={onChange ? 'radiogroup' : undefined} aria-label="Rating">
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" disabled={!onChange} onClick={() => onChange?.(n)}
          role={onChange ? 'radio' : undefined} aria-checked={value === n} aria-label={`${n} star${n > 1 ? 's' : ''}`}
          className={cx('disabled:cursor-default', n <= value ? 'text-signal' : 'text-line')}>
          <svg viewBox="0 0 24 24" className={size} fill="currentColor"><path d="M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3l-5.9 3.3 1.3-6.6L2.5 9.4l6.6-.8z" /></svg>
        </button>
      ))}
    </div>
  );
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="mb-4 flex gap-1 overflow-x-auto border-b border-line" role="tablist">
      {tabs.map((t) => (
        <button key={t.value} type="button" role="tab" aria-selected={value === t.value} onClick={() => onChange(t.value)}
          className={cx('-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium',
            value === t.value ? 'border-blueprint text-blueprint' : 'border-transparent text-ink-soft hover:text-ink')}>
          {t.label}{t.count != null && <span className="ml-1.5 rounded-sm bg-paper px-1.5 text-xs">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}
