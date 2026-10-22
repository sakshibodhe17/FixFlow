import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity, Bell, Boxes, ClipboardList, Cpu, DatabaseBackup, FileDown, Gauge, LayoutDashboard,
  LogOut, Menu, PlusCircle, ScrollText, Settings2, ShieldAlert, Tags, UserCircle, Users, Wrench, X,
} from 'lucide-react';
import api from '../lib/api';
import { useAuth } from '../lib/auth';
import { useApi } from '../lib/hooks';
import { fmt } from '../lib/format';
import { cx } from './ui';

const NAV = {
  Reporter: [
    { group: 'Requests', items: [
      { to: '/report', label: 'Report a problem', icon: PlusCircle },
      { to: '/my-requests', label: 'My requests', icon: ClipboardList },
    ] },
  ],
  Technician: [
    { group: 'Work', items: [
      { to: '/tasks', label: 'My jobs', icon: Wrench },
      { to: '/report', label: 'Report a problem', icon: PlusCircle },
      { to: '/tech/profile', label: 'Skills & availability', icon: UserCircle },
    ] },
  ],
  Manager: [
    { group: 'Operations', items: [
      { to: '/manager', label: 'Overview', icon: LayoutDashboard, end: true },
      { to: '/manager/requests', label: 'All requests', icon: ClipboardList },
      { to: '/manager/sla', label: 'SLA & escalations', icon: ShieldAlert, badge: 'esc' },
      { to: '/manager/technicians', label: 'Technicians', icon: Users },
    ] },
    { group: 'Assets', items: [
      { to: '/manager/assets', label: 'Assets & QR codes', icon: Boxes },
      { to: '/manager/risk', label: 'Failure risk', icon: Gauge },
      { to: '/manager/reports', label: 'Reports', icon: FileDown },
    ] },
  ],
};
NAV.Admin = [
  ...NAV.Manager,
  { group: 'Administration', items: [
    { to: '/admin/users', label: 'Users & roles', icon: Users },
    { to: '/admin/catalog', label: 'Locations & skills', icon: Tags },
    { to: '/admin/settings', label: 'Notifications & SLA', icon: Settings2 },
    { to: '/admin/model', label: 'Prediction model', icon: Cpu },
    { to: '/admin/logs', label: 'Logs & usage', icon: ScrollText },
    { to: '/admin/backups', label: 'Backup & restore', icon: DatabaseBackup },
  ] },
];

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5 text-white">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect width="32" height="32" rx="6" fill="#10304A" stroke="rgba(255,255,255,.25)" />
        <path d="M9 23V9h12M9 16h8" stroke="#E8A317" strokeWidth="3.2" fill="none" strokeLinecap="round" />
      </svg>
      <span className="font-narrow text-xl font-bold tracking-tight">FixFlow</span>
    </Link>
  );
}

function Sidebar({ onNavigate }) {
  const { user, logout } = useAuth();
  const isStaff = user.role === 'Manager' || user.role === 'Admin';
  const { data: esc } = useApi('/sla/escalations/count', { pollMs: 60000, enabled: isStaff });
  const groups = NAV[user.role] || [];
  return (
    <div className="blueprint-grid flex h-full flex-col text-white/85">
      <div className="px-5 py-5"><Logo /></div>
      <nav className="flex-1 space-y-6 overflow-y-auto px-3 pb-4" aria-label="Main">
        {groups.map((g) => (
          <div key={g.group}>
            <div className="px-2 pb-1.5 text-xs font-medium text-white/50">{g.group}</div>
            <ul className="space-y-0.5">
              {g.items.map(({ to, label, icon: Icon, end, badge }) => (
                <li key={to}>
                  <NavLink to={to} end={end} onClick={onNavigate}
                    className={({ isActive }) => cx('flex items-center gap-3 rounded px-2.5 py-2 text-sm transition-colors',
                      isActive ? 'bg-white text-blueprint-deep font-semibold' : 'hover:bg-white/10')}>
                    <Icon className="h-4 w-4 shrink-0" aria-hidden />
                    <span className="flex-1">{label}</span>
                    {badge === 'esc' && esc?.unacknowledged > 0 && (
                      <span className="rounded-sm bg-signal px-1.5 text-xs font-bold text-ink">{esc.unacknowledged}</span>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      <div className="border-t border-white/10 px-3 py-3">
        <NavLink to="/profile" onClick={onNavigate} className="flex items-center gap-3 rounded px-2.5 py-2 hover:bg-white/10">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/15 text-sm font-semibold">
            {user.full_name.split(' ').map((p) => p[0]).slice(0, 2).join('')}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-white">{user.full_name}</span>
            <span className="block text-xs text-white/60">{user.role === 'Manager' ? 'Facility manager' : user.role}</span>
          </span>
        </NavLink>
        <button type="button" onClick={logout} className="mt-1 flex w-full items-center gap-3 rounded px-2.5 py-2 text-sm hover:bg-white/10">
          <LogOut className="h-4 w-4" /> Sign out
        </button>
      </div>
    </div>
  );
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const { data, reload } = useApi('/notifications', { pollMs: 20000 });
  const navigate = useNavigate();
  const ref = useRef(null);

  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const openItem = async (n) => {
    if (!n.is_read) await api.post(`/notifications/${n.notification_id}/read`).catch(() => {});
    setOpen(false);
    reload(true);
    if (n.link) navigate(n.link);
  };
  const readAll = async () => { await api.post('/notifications/read-all'); reload(true); };
  const unread = data?.unread || 0;

  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen((o) => !o)} className="relative rounded p-2 text-ink-soft hover:bg-white"
        aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`} aria-expanded={open}>
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute right-0.5 top-0.5 min-w-[18px] rounded-full bg-breach px-1 text-center text-[11px] font-bold leading-[18px] text-white">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-[min(92vw,380px)] overflow-hidden rounded-md border border-line bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <span className="font-semibold">Notifications</span>
            {unread > 0 && <button type="button" onClick={readAll} className="text-xs font-medium text-blueprint hover:underline">Mark all read</button>}
          </div>
          <ul className="max-h-[60vh] overflow-y-auto">
            {(data?.items || []).length === 0 && <li className="px-4 py-8 text-center text-sm text-ink-soft">You're all caught up.</li>}
            {(data?.items || []).map((n) => (
              <li key={n.notification_id}>
                <button type="button" onClick={() => openItem(n)}
                  className={cx('block w-full border-b border-line/60 px-4 py-3 text-left hover:bg-paper', !n.is_read && 'bg-blueprint-light/50')}>
                  <div className="flex items-start gap-2">
                    {!n.is_read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-blueprint" aria-label="Unread" />}
                    <div className="min-w-0">
                      <div className="text-sm font-medium">{n.title}</div>
                      {n.message && <div className="mt-0.5 line-clamp-2 text-xs text-ink-soft">{n.message}</div>}
                      <div className="mt-1 text-xs text-ink-faint">{fmt.relative(n.created_at)}</div>
                    </div>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMobileOpen(false), [location.pathname]);

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 lg:block"><Sidebar /></aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink/50" onClick={() => setMobileOpen(false)} />
          <aside className="relative h-full w-72 max-w-[85vw]">
            <button type="button" onClick={() => setMobileOpen(false)} className="absolute right-3 top-5 z-10 rounded p-1 text-white hover:bg-white/10" aria-label="Close menu"><X className="h-5 w-5" /></button>
            <Sidebar onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-paper/95 px-4 backdrop-blur lg:px-8">
          <button type="button" onClick={() => setMobileOpen(true)} className="rounded p-2 hover:bg-white lg:hidden" aria-label="Open menu"><Menu className="h-5 w-5" /></button>
          <div className="flex-1" />
          <Link to="/report" className="hidden items-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium text-blueprint hover:bg-white sm:inline-flex">
            <Activity className="h-4 w-4" /> Report a problem
          </Link>
          <Notifications />
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-8 lg:py-8"><Outlet /></main>
      </div>
    </div>
  );
}

