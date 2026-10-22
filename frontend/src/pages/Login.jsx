import { useState } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { Button, ErrorNote, Field, Input } from '../components/ui';
import { errorMessage } from '../lib/api';
import { HOME_BY_ROLE, useAuth } from '../lib/auth';

const DEMO = [
  ['Reporter', 'student@fixflow.dev', 'Reporter@123'],
  ['Technician', 'ravi@fixflow.dev', 'Tech@123'],
  ['Manager', 'manager@fixflow.dev', 'Manager@123'],
  ['Admin', 'admin@fixflow.dev', 'Admin@123'],
];

export function AuthShell({ children }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_minmax(420px,520px)]">
      <div className="blueprint-grid relative hidden flex-col justify-between p-10 text-white lg:flex">
        <div className="flex items-center gap-2.5">
          <svg viewBox="0 0 32 32" className="h-9 w-9" aria-hidden><rect width="32" height="32" rx="6" fill="#10304A" stroke="rgba(255,255,255,.25)" /><path d="M9 23V9h12M9 16h8" stroke="#E8A317" strokeWidth="3.2" fill="none" strokeLinecap="round" /></svg>
          <span className="font-narrow text-2xl font-bold">FixFlow</span>
        </div>
        <div className="max-w-lg">
          <p className="font-narrow text-[44px] font-bold leading-[1.05]">
            Every fault reported, routed, and fixed before the clock runs out.
          </p>
          <div className="mt-10 space-y-3">
            {[['Projector – Room 204', 82, 'bg-signal', '2.1 h left'], ['Water cooler – Hostel A', 34, 'bg-white', '31 h left'], ['Split AC – Lab 2', 100, 'bg-breach', '3 h late']].map(([n, p, c, t]) => (
              <div key={n} className="max-w-sm">
                <div className="mb-1 flex justify-between text-sm text-white/80"><span>{n}</span><span>{t}</span></div>
                <div className="h-1.5 rounded-full bg-white/15"><div className={`h-full rounded-full ${c}`} style={{ width: `${p}%` }} /></div>
              </div>
            ))}
          </div>
        </div>
        <p className="text-sm text-white/50">Maintenance requests, SLA tracking and 30-day failure risk in one place.</p>
      </div>
      <div className="flex items-center justify-center px-5 py-10">{children}</div>
    </div>
  );
}

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(params.get('expired') ? 'Your session expired. Sign in again.' : null);

  if (user) return <Navigate to={params.get('next') || HOME_BY_ROLE[user.role]} replace />;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await login(email, password);
      navigate(params.get('next') || HOME_BY_ROLE[u.role], { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell>
      <div className="w-full max-w-sm">
        <h1 className="text-3xl font-bold">Sign in</h1>
        <p className="mt-1 text-sm text-ink-soft">New here? <Link to="/register" className="font-medium text-blueprint hover:underline">Create an account</Link> to report problems.</p>
        <form onSubmit={submit} className="mt-8 space-y-4">
          <Field label="Email"><Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Field label="Password"><Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <ErrorNote>{error}</ErrorNote>
          <Button type="submit" busy={busy} className="w-full">Sign in</Button>
        </form>
        <div className="mt-10 rounded border border-line bg-white p-4">
          <p className="text-sm font-medium">Demo accounts</p>
          <p className="text-xs text-ink-soft">Available after running the seed script. Click to fill in.</p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {DEMO.map(([role, e, p]) => (
              <button key={role} type="button" onClick={() => { setEmail(e); setPassword(p); }}
                className="rounded border border-line px-2 py-1.5 text-left text-xs hover:border-blueprint hover:bg-blueprint-light">
                <span className="block font-semibold">{role}</span><span className="text-ink-soft">{e}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </AuthShell>
  );
}
