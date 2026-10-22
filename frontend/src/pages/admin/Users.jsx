import { useState } from 'react';
import { KeyRound, Pencil, Plus, Search } from 'lucide-react';
import { Button, ErrorNote, Field, Input, Modal, PageHeader, Panel, Select, Spinner, cx } from '../../components/ui';
import api from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { fmt } from '../../lib/format';
import { useAction, useApi } from '../../lib/hooks';

const ROLES = ['Reporter', 'Technician', 'Manager', 'Admin'];
const ROLE_LABEL = { Manager: 'Facility manager' };

export default function Users() {
  const { user: me } = useAuth();
  const [filter, setFilter] = useState({ role: '', q: '' });
  const [query, setQuery] = useState({});
  const { data, loading, error, reload } = useApi('/users', { params: query });
  const [form, setForm] = useState(null);
  const [reset, setReset] = useState(null);
  const action = useAction();

  const save = () => action.run(async () => {
    if (form.user_id) {
      await api.put(`/users/${form.user_id}`, { full_name: form.full_name, phone: form.phone || null, role: form.role, is_active: form.is_active });
    } else {
      await api.post('/users', { full_name: form.full_name, email: form.email, phone: form.phone || null, role: form.role, password: form.password });
    }
    setForm(null); reload(true);
  }).catch(() => {});
  const doReset = () => action.run(async () => { await api.post(`/users/${reset.user_id}/reset-password`, { new_password: reset.password }); setReset(null); }).catch(() => {});

  return (
    <>
      <PageHeader title="Users & roles" subtitle="People register themselves as reporters. Give technician, manager or admin access here."
        actions={<Button icon={Plus} onClick={() => setForm({ full_name: '', email: '', phone: '', role: 'Technician', password: '', is_active: true })}>Add user</Button>} />
      <ErrorNote>{error}</ErrorNote>
      <Panel bodyClass="p-0">
        <form className="grid gap-2 border-b border-line p-3 sm:grid-cols-[1fr_200px_auto]" onSubmit={(e) => { e.preventDefault(); setQuery(Object.fromEntries(Object.entries(filter).filter(([, v]) => v))); }}>
          <div className="relative"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
            <Input className="pl-9" placeholder="Name or email" value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })} aria-label="Search users" /></div>
          <Select value={filter.role} onChange={(e) => setFilter({ ...filter, role: e.target.value })} aria-label="Role"><option value="">All roles</option>{ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r] || r}</option>)}</Select>
          <Button type="submit" variant="secondary">Filter</Button>
        </form>
        {loading ? <Spinner /> : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead><tr><th>Name</th><th>Role</th><th>Phone</th><th>Joined</th><th>Status</th><th /></tr></thead>
              <tbody>
                {(data || []).map((u) => (
                  <tr key={u.user_id} className={cx(!u.is_active && 'opacity-50')}>
                    <td><div className="font-medium">{u.full_name}{u.user_id === me.user_id && <span className="ml-1 text-xs text-ink-faint">(you)</span>}</div><div className="text-xs text-ink-soft">{u.email}</div></td>
                    <td>{ROLE_LABEL[u.role] || u.role}</td><td className="text-sm">{u.phone || '—'}</td><td className="text-sm">{fmt.date(u.created_at)}</td>
                    <td className={u.is_active ? 'text-moss' : 'text-ink-faint'}>{u.is_active ? 'Active' : 'Deactivated'}</td>
                    <td><div className="flex justify-end gap-1">
                      <button type="button" className="rounded p-1.5 text-ink-soft hover:bg-paper" aria-label={`Edit ${u.full_name}`} onClick={() => setForm({ ...u, phone: u.phone || '' })}><Pencil className="h-4 w-4" /></button>
                      <button type="button" className="rounded p-1.5 text-ink-soft hover:bg-paper" aria-label={`Reset password for ${u.full_name}`} onClick={() => setReset({ ...u, password: '' })}><KeyRound className="h-4 w-4" /></button>
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Modal open={!!form} onClose={() => setForm(null)} title={form?.user_id ? `Edit ${form.full_name}` : 'Add user'}
        footer={<><Button variant="secondary" onClick={() => setForm(null)}>Cancel</Button><Button busy={action.busy} onClick={save}>{form?.user_id ? 'Save changes' : 'Create user'}</Button></>}>
        {form && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Full name" className="sm:col-span-2"><Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
            <Field label="Email"><Input type="email" disabled={!!form.user_id} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Phone"><Input value={form.phone} maxLength={15} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
            <Field label="Role" hint={form.role === 'Technician' ? 'Set their skills on the Technicians page.' : undefined}>
              <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>{ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r] || r}</option>)}</Select>
            </Field>
            {form.user_id ? (
              <Field label="Account"><Select value={form.is_active ? '1' : '0'} onChange={(e) => setForm({ ...form, is_active: e.target.value === '1' })}><option value="1">Active</option><option value="0">Deactivated</option></Select></Field>
            ) : (
              <Field label="Temporary password" hint="At least 8 characters."><Input type="text" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
            )}
            <div className="sm:col-span-2"><ErrorNote>{action.error}</ErrorNote></div>
          </div>
        )}
      </Modal>
      <Modal open={!!reset} onClose={() => setReset(null)} title={`Reset password: ${reset?.full_name}`}
        footer={<><Button variant="secondary" onClick={() => setReset(null)}>Cancel</Button><Button busy={action.busy} disabled={(reset?.password || '').length < 8} onClick={doReset}>Set password</Button></>}>
        <Field label="New password" hint="Share it securely; they can change it from their profile."><Input value={reset?.password || ''} onChange={(e) => setReset({ ...reset, password: e.target.value })} /></Field>
        <div className="mt-3"><ErrorNote>{action.error}</ErrorNote></div>
      </Modal>
    </>
  );
}
