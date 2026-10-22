import { useState } from 'react';
import { Button, ErrorNote, Field, Input, PageHeader, Panel } from '../components/ui';
import api from '../lib/api';
import { useAuth } from '../lib/auth';
import { useAction } from '../lib/hooks';

export default function Profile() {
  const { user, setUser } = useAuth();
  const [form, setForm] = useState({ full_name: user.full_name, phone: user.phone || '' });
  const [pw, setPw] = useState({ current_password: '', new_password: '' });
  const [saved, setSaved] = useState(null);
  const profile = useAction();
  const password = useAction();

  const saveProfile = (e) => {
    e.preventDefault();
    profile.run(async () => {
      const { data } = await api.put('/auth/me', form);
      setUser(data);
      setSaved('Profile saved.');
    }).catch(() => {});
  };
  const savePassword = (e) => {
    e.preventDefault();
    password.run(async () => {
      await api.post('/auth/me/password', pw);
      setPw({ current_password: '', new_password: '' });
      setSaved('Password changed.');
    }).catch(() => {});
  };

  return (
    <>
      <PageHeader title="Your profile" subtitle={`${user.email} · ${user.role === 'Manager' ? 'Facility manager' : user.role}`} />
      {saved && <p className="mb-4 rounded border border-moss/30 bg-moss-light px-3 py-2 text-sm text-moss" role="status">{saved}</p>}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Details">
          <form onSubmit={saveProfile} className="space-y-4">
            <Field label="Full name"><Input required minLength={2} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
            <Field label="Phone"><Input maxLength={15} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
            <ErrorNote>{profile.error}</ErrorNote>
            <Button type="submit" busy={profile.busy}>Save profile</Button>
          </form>
        </Panel>
        <Panel title="Password">
          <form onSubmit={savePassword} className="space-y-4">
            <Field label="Current password"><Input type="password" required autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></Field>
            <Field label="New password" hint="At least 8 characters."><Input type="password" required minLength={8} maxLength={72} autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></Field>
            <ErrorNote>{password.error}</ErrorNote>
            <Button type="submit" busy={password.busy}>Change password</Button>
          </form>
        </Panel>
      </div>
    </>
  );
}
