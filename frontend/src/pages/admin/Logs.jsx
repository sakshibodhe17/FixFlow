import { useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ErrorNote, Input, PageHeader, Panel, Spinner, Stat, Tabs } from '../../components/ui';
import { fmt } from '../../lib/format';
import { useApi } from '../../lib/hooks';
import { C } from '../manager/Overview';

export default function Logs() {
  const [tab, setTab] = useState('usage');
  const [action, setAction] = useState('');
  const usage = useApi('/admin/usage', { enabled: tab === 'usage' });
  const audit = useApi('/admin/audit-logs', { params: { action: action || undefined, limit: 300 }, enabled: tab === 'audit' });
  const sys = useApi('/admin/system-log', { params: { lines: 300 }, enabled: tab === 'system', pollMs: tab === 'system' ? 10000 : undefined });
  const u = usage.data;

  return (
    <>
      <PageHeader title="Logs & usage" subtitle="Who did what, what the server is doing, and how much the system is used." />
      <Tabs value={tab} onChange={setTab} tabs={[{ value: 'usage', label: 'Usage' }, { value: 'audit', label: 'Audit trail' }, { value: 'system', label: 'Server log' }]} />

      {tab === 'usage' && (!u ? <Spinner /> : (
        <>
          <ErrorNote>{usage.error}</ErrorNote>
          <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-6">
            {['Reporter', 'Technician', 'Manager', 'Admin'].map((r) => <Stat key={r} label={`${r === 'Manager' ? 'Managers' : `${r}s`}`} value={u.users_by_role[r] || 0} />)}
            <Stat label="Active, last 7 days" value={u.active_users_7d} tone="green" />
            <Stat label="Database size" value={u.database_size} />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            {[['Sign-ins per day', u.logins_30d], ['Requests per day', u.requests_30d]].map(([title, rows]) => (
              <Panel key={title} title={title} note="Last 30 days">
                <div style={{ height: 200 }}>
                  <ResponsiveContainer>
                    <BarChart data={rows} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                      <CartesianGrid stroke={C.grid} vertical={false} />
                      <XAxis dataKey="day" tick={{ fontSize: 10, fill: '#5D6B75' }} tickFormatter={(d) => d.slice(5)} tickLine={false} axisLine={false} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#5D6B75' }} tickLine={false} axisLine={false} />
                      <Tooltip /><Bar dataKey="count" fill={C.blue} radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Panel>
            ))}
            <Panel title="Background jobs">
              <table className="table-base"><thead><tr><th>Job</th><th>Schedule</th><th>Next run</th></tr></thead>
                <tbody>{u.scheduler_jobs.map((j) => <tr key={j.id}><td className="font-medium">{j.id}</td><td className="text-xs">{j.trigger}</td><td>{fmt.dateTime(j.next_run)}</td></tr>)}
                  {u.scheduler_jobs.length === 0 && <tr><td colSpan={3} className="text-ink-soft">Scheduler is not running in this process.</td></tr>}</tbody>
              </table>
            </Panel>
          </div>
        </>
      ))}

      {tab === 'audit' && (
        <Panel bodyClass="p-0">
          <div className="border-b border-line p-3"><Input className="max-w-xs" placeholder="Filter by action, e.g. request. or user.login" value={action} onChange={(e) => setAction(e.target.value)} aria-label="Filter actions" /></div>
          {!audit.data ? <Spinner /> : (
            <div className="max-h-[70vh] overflow-auto">
              <table className="table-base">
                <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
                <tbody>{audit.data.map((l) => (
                  <tr key={l.log_id}><td className="whitespace-nowrap text-xs">{fmt.dateTime(l.created_at)}</td><td className="whitespace-nowrap text-sm">{l.user}</td>
                    <td className="whitespace-nowrap text-xs font-medium">{l.action}</td><td className="text-xs">{l.entity ? `${l.entity} #${l.entity_id ?? ''}` : '—'}</td>
                    <td className="max-w-md truncate text-xs text-ink-soft" title={l.details || ''}>{l.details}</td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Panel>
      )}

      {tab === 'system' && (
        <Panel title="Server log" note="Last 300 lines of logs/fixflow.log. Refreshes every 10 seconds.">
          {!sys.data ? <Spinner /> : (
            <pre className="max-h-[65vh] overflow-auto rounded bg-blueprint-deep p-3 text-xs leading-relaxed text-white/85">
              {sys.data.lines.length ? sys.data.lines.join('') : 'The log is empty.'}
            </pre>
          )}
        </Panel>
      )}
    </>
  );
}
