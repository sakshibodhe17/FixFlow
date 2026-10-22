import { useState } from 'react';
import { CalendarPlus, Cpu } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Button, Empty, ErrorNote, Field, Input, Modal, PageHeader, Panel, RiskPill, Select, Spinner, Stat, Tabs, Textarea } from '../../components/ui';
import api from '../../lib/api';
import { fmt, SEVERITIES } from '../../lib/format';
import { useAction, useApi } from '../../lib/hooks';
import { C } from './Overview';

function defaultDate() {
  const d = new Date(Date.now() + 3 * 86400000);
  d.setHours(10, 0, 0, 0);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
}

export default function RiskScores() {
  const [tab, setTab] = useState('High');
  const { data, loading, error, reload } = useApi('/predictions/latest');
  const { data: model } = useApi('/predictions/model');
  const { data: dist, reload: reloadDist } = useApi('/analytics/risk-distribution');
  const [plan, setPlan] = useState(null);
  const [result, setResult] = useState(null);
  const action = useAction();

  const items = data || [];
  const shown = tab === 'all' ? items : items.filter((p) => p.risk_level === tab);
  const counts = { High: 0, Medium: 0, Low: 0 };
  items.forEach((p) => { counts[p.risk_level] += 1; });

  const run = () => action.run(async () => { setResult((await api.post('/predictions/run')).data); reload(true); reloadDist(true); }).catch(() => {});
  const schedule = () => action.run(async () => {
    await api.post('/predictions/preventive', { asset_id: plan.asset.asset_id, scheduled_for: new Date(plan.when).toISOString(), notes: plan.notes || null, severity: plan.severity });
    setPlan(null); reload(true);
  }).catch(() => {});

  return (
    <>
      <PageHeader title="Failure risk" subtitle={`Each asset's predicted chance of failing in the next ${model?.horizon_days ?? 30} days, from its age, failure history, repair costs and warranty.`}
        actions={<Button variant="secondary" icon={Cpu} busy={action.busy} onClick={run}>Score all assets now</Button>} />
      {result && <p className="mb-4 text-sm text-ink-soft" role="status">Scored {result.scored} assets with {result.model_version}: {result.high} high, {result.medium} medium, {result.low} low risk.</p>}
      <ErrorNote>{error || action.error}</ErrorNote>

      <div className="mb-6 grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        <div className="grid grid-cols-3 gap-3 self-start">
          <Stat label="High risk" value={counts.High} tone="red" sub="act now" />
          <Stat label="Medium risk" value={counts.Medium} tone="amber" sub="inspect soon" />
          <Stat label="Low risk" value={counts.Low} tone="green" sub="no action" />
          <div className="col-span-3 text-xs text-ink-soft">
            Model: <span className="font-medium text-ink">{model?.active_version || '—'}</span>
            {model?.active?.metrics && <> · ROC-AUC {model.active.metrics.roc_auc} · scored {fmt.relative(items[0]?.predicted_at)}</>}
          </div>
        </div>
        <Panel title="Risk distribution" bodyClass="p-2">
          <div style={{ height: 160 }}>
            <ResponsiveContainer>
              <BarChart data={dist?.histogram || []} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="range" tick={{ fontSize: 10, fill: '#5D6B75' }} tickLine={false} axisLine={false} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#5D6B75' }} tickLine={false} axisLine={false} />
                <Tooltip formatter={(v) => [`${v} assets`, 'Count']} />
                <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                  {(dist?.histogram || []).map((h, i) => <Cell key={h.range} fill={i >= 7 ? C.red : i >= 4 ? C.amber : C.green} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <Panel>
        <Tabs value={tab} onChange={setTab} tabs={[
          { value: 'High', label: 'High', count: counts.High }, { value: 'Medium', label: 'Medium', count: counts.Medium },
          { value: 'Low', label: 'Low', count: counts.Low }, { value: 'all', label: 'All', count: items.length },
        ]} />
        {loading ? <Spinner /> : shown.length === 0 ? (
          <Empty title={items.length ? 'No assets at this level.' : 'No scores yet.'} action={!items.length && <Button onClick={run}>Score all assets</Button>} />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead><tr><th>Asset</th><th>Risk</th><th>Why</th><th>Recommendation</th><th /></tr></thead>
              <tbody>
                {shown.map((p) => (
                  <tr key={p.asset_id}>
                    <td><div className="font-medium">{p.asset.asset_name}</div><div className="text-xs text-ink-soft">{p.asset.category} · {p.asset.location?.label}</div></td>
                    <td>
                      <RiskPill level={p.risk_level} score={p.risk_score} />
                      <div className="mt-1.5 h-1 w-24 rounded bg-paper"><div className="h-full rounded" style={{ width: `${p.risk_score * 100}%`, background: p.risk_level === 'High' ? C.red : p.risk_level === 'Medium' ? C.amber : C.green }} /></div>
                    </td>
                    <td className="max-w-xs"><ul className="list-disc space-y-0.5 pl-4 text-xs text-ink-soft">{p.reasons.map((r) => <li key={r}>{r}</li>)}</ul></td>
                    <td className="text-sm">{p.preventive_scheduled ? <span className="text-moss">Preventive job scheduled</span> : p.recommendation}</td>
                    <td className="text-right">
                      {p.risk_level !== 'Low' && !p.preventive_scheduled && (
                        <Button size="sm" variant={p.risk_level === 'High' ? 'primary' : 'secondary'} icon={CalendarPlus}
                          onClick={() => setPlan({ asset: p.asset, when: defaultDate(), severity: p.risk_level === 'High' ? 'High' : 'Medium', notes: '' })}>Schedule</Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Modal open={!!plan} onClose={() => setPlan(null)} title="Schedule preventive maintenance"
        footer={<><Button variant="secondary" onClick={() => setPlan(null)}>Cancel</Button><Button busy={action.busy} onClick={schedule}>Schedule job</Button></>}>
        {plan && (
          <div className="space-y-4">
            <p className="text-sm">A preventive job for <strong>{plan.asset.asset_name}</strong> will be created and assigned to a technician with the right skill.</p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Complete by"><Input type="datetime-local" value={plan.when} onChange={(e) => setPlan({ ...plan, when: e.target.value })} /></Field>
              <Field label="Priority"><Select value={plan.severity} onChange={(e) => setPlan({ ...plan, severity: e.target.value })}>{SEVERITIES.map((s) => <option key={s}>{s}</option>)}</Select></Field>
            </div>
            <Field label="Instructions for the technician"><Textarea rows={3} value={plan.notes} onChange={(e) => setPlan({ ...plan, notes: e.target.value })} placeholder="e.g. Clean filters, check refrigerant pressure, inspect wiring." /></Field>
            <ErrorNote>{action.error}</ErrorNote>
          </div>
        )}
      </Modal>
    </>
  );
}
