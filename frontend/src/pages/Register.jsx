import { useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { Button, ErrorNote, Field, Input } from '../components/ui';
import { errorMessage } from '../lib/api';
import { useAuth } from '../lib/auth';
import { AuthShell } from './Login';

export default function Register() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: '', email: '', phone: '', password: '', confirm: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  if (user) return <Navigate to="/" replace />;
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    if (form.password !== form.confirm) { setError("The passwords don't match."); return; }
    setBusy(true);
    setError(null);
    try {
      await register({ full_name: form.full_name, email: form.email, phone: form.phone || null, password: form.password });
      navigate('/report', { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell>
      <div className="w-full max-w-sm">
        <h1 className="text-3xl font-bold">Create your account</h1>
        <p className="mt-1 text-sm text-ink-soft">For students, staff and employees reporting problems. Already registered? <Link to="/login" className="font-medium text-blueprint hover:underline">Sign in</Link></p>
        <form onSubmit={submit} className="mt-8 space-y-4">
          <Field label="Full name"><Input required minLength={2} autoComplete="name" value={form.full_name} onChange={set('full_name')} /></Field>
          <Field label="Email"><Input type="email" required autoComplete="email" value={form.email} onChange={set('email')} /></Field>
          <Field label="Phone" hint="Optional. Technicians may call if they can't find the asset."><Input type="tel" maxLength={15} autoComplete="tel" value={form.phone} onChange={set('phone')} /></Field>
          <Field label="Password" hint="At least 8 characters."><Input type="password" required minLength={8} maxLength={72} autoComplete="new-password" value={form.password} onChange={set('password')} /></Field>
          <Field label="Confirm password"><Input type="password" required autoComplete="new-password" value={form.confirm} onChange={set('confirm')} /></Field>
          <ErrorNote>{error}</ErrorNote>
          <Button type="submit" busy={busy} className="w-full">Create account</Button>
        </form>
      </div>
    </AuthShell>
  );
}
