import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Empty, ErrorNote, PageHeader, Panel, Select, Spinner, Stat } from '../../components/ui';
import { fmt } from '../../lib/format';
import { useApi } from '../../lib/hooks';

export const C = { blue: '#22577A', blueLight: '#8DB3CC', amber: '#E8A317', red: '#C8372D', green: '#3A7D44', grey: '#8A969E', grid: '#E4E8EA' };
const axis = { fontSize: 12, fill: '#5D6B75' };
const tooltipStyle = { contentStyle: { borderRadius: 5, border: '1px solid #D6DCDF', fontSize: 12 } };

function ChartBox({ height = 260, children }) {
  return <div style={{ height }} className="w-full"><ResponsiveContainer>{children}</ResponsiveContainer></div>;
}

export default function Overview() {
  const [days, setDays] = useState(30);
  const ov = useApi('/analytics/overview', { params: { days }, pollMs: 60000 });
  const trends = useApi('/analytics/trends', { params: { months: 12 } });
  const recurring = useApi('/analytics/recurring-faults', { params: { days: Math.max(days, 90) } });
  const techs = useApi('/analytics/technicians', { params: { days: Math.max(days, 30) } });
  const sla = useApi('/analytics/sla', { params: { days: Math.max(days, 30) } });
  const o = ov.data;

  return (
    <>
      <PageHeader title="Maintenance overview" subtitle="Live status of requests, SLA performance, costs and recurring faults."
        actions={(
          <Select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Period" className="w-40">
            <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option><option value={180}>Last 6 months</option><option value={365}>Last 12 months</option>
          </Select>
        )} />
      <ErrorNote>{ov.error}</ErrorNote>
      {!o ? <Spinner /> : (
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          <Link to="/manager/requests?status=Open,Assigned,In Progress,On Hold,Reopened" className="contents"><Stat label="Open requests" value={o.open_requests} sub={`${o.unassigned_requests} unassigned`} /></Link>
          <Link to="/manager/sla" className="contents"><Stat label="Past SLA now" value={o.overdue_requests} sub={`${o.unacknowledged_escalations} unacknowledged alerts`} tone={o.overdue_requests ? 'red' : 'green'} /></Link>
          <Stat label="SLA compliance" value={fmt.pct(o.sla_compliance_pct)} sub={`${o.resolved_requests} resolved`} tone={o.sla_compliance_pct != null && o.sla_compliance_pct < 85 ? 'amber' : 'green'} />
          <Stat label="Avg resolution" value={fmt.hours(o.avg_resolution_hours)} sub={`${o.new_requests} new requests`} />
          <Stat label="Repair cost" value={fmt.money(o.total_repair_cost)} sub={`${fmt.num(o.total_labour_hours)} labour h`} />
          <Stat label="Downtime" value={fmt.hours(o.total_downtime_hours)} sub="across all assets" tone="amber" />
          <Link to="/manager/risk" className="contents"><Stat label="High-risk assets" value={o.high_risk_assets} sub={o.avg_rating ? `Avg rating ${o.avg_rating} ★` : 'next 30 days'} tone={o.high_risk_assets ? 'red' : 'green'} /></Link>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Requests and SLA compliance" note="Last 12 months">
          {!trends.data ? <Spinner /> : (
            <ChartBox>
              <ComposedChart data={trends.data} margin={{ top: 5, right: 5, left: -10, bottom: 0 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="label" tick={axis} tickLine={false} axisLine={false} />
                <YAxis yAxisId="l" tick={axis} tickLine={false} axisLine={false} allowDecimals={false} />
                <YAxis yAxisId="r" orientation="right" domain={[0, 100]} tick={axis} tickLine={false} axisLine={false} unit="%" />
                <Tooltip {...tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar yAxisId="l" dataKey="requests" name="Reported" fill={C.blueLight} radius={[2, 2, 0, 0]} />
                <Bar yAxisId="l" dataKey="resolved" name="Resolved" fill={C.blue} radius={[2, 2, 0, 0]} />
                <Line yAxisId="r" dataKey="sla_compliance_pct" name="SLA met %" stroke={C.amber} strokeWidth={2.5} dot={false} connectNulls />
              </ComposedChart>
            </ChartBox>
          )}
        </Panel>

        <Panel title="Repair cost and downtime" note="Monthly totals">
          {!trends.data ? <Spinner /> : (
            <ChartBox>
              <LineChart data={trends.data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="label" tick={axis} tickLine={false} axisLine={false} />
                <YAxis yAxisId="l" tick={axis} tickLine={false} axisLine={false} tickFormatter={(v) => `₹${v >= 1000 ? `${Math.round(v / 1000)}k` : v}`} />
                <YAxis yAxisId="r" orientation="right" tick={axis} tickLine={false} axisLine={false} unit=" h" />
                <Tooltip {...tooltipStyle} formatter={(v, n) => (n === 'Repair cost' ? fmt.money(v) : `${fmt.num(v, 1)} h`)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line yAxisId="l" dataKey="repair_cost" name="Repair cost" stroke={C.blue} strokeWidth={2.5} dot={false} />
                <Line yAxisId="r" dataKey="downtime_hours" name="Downtime" stroke={C.red} strokeWidth={2} strokeDasharray="5 4" dot={false} />
              </LineChart>
            </ChartBox>
          )}
        </Panel>

        <Panel title="Recurring faults by asset" note={`Assets with the most failures, last ${Math.max(days, 90)} days`}>
          {!recurring.data ? <Spinner /> : recurring.data.assets.length === 0 ? <Empty title="No failures in this period." /> : (
            <ChartBox height={Math.max(220, recurring.data.assets.slice(0, 8).length * 34)}>
              <BarChart data={recurring.data.assets.slice(0, 8)} layout="vertical" margin={{ top: 0, right: 20, left: 10, bottom: 0 }}>
                <CartesianGrid stroke={C.grid} horizontal={false} />
                <XAxis type="number" tick={axis} allowDecimals={false} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="asset_name" width={170} tick={{ ...axis, fontSize: 11 }} tickLine={false} axisLine={false} />
                <Tooltip {...tooltipStyle} formatter={(v, n) => (n === 'Failures' ? v : fmt.money(v))}
                  labelFormatter={(l, p) => `${l} — most often “${p?.[0]?.payload?.most_common_issue ?? ''}”`} />
                <Bar dataKey="count" name="Failures" radius={[0, 2, 2, 0]}>
                  {recurring.data.assets.slice(0, 8).map((a) => <Cell key={a.asset_id} fill={a.is_recurring ? C.red : C.blue} />)}
                </Bar>
              </BarChart>
            </ChartBox>
          )}
          <p className="mt-2 text-xs text-ink-soft">Red bars: {recurring.data?.min_count ?? 3}+ failures in the period.</p>
        </Panel>

        <Panel title="Faults and cost by category">
          {!recurring.data ? <Spinner /> : (
            <ChartBox>
              <BarChart data={recurring.data.categories} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="category" tick={{ ...axis, fontSize: 11 }} tickLine={false} axisLine={false} interval={0} angle={-20} textAnchor="end" height={50} />
                <YAxis yAxisId="l" tick={axis} tickLine={false} axisLine={false} allowDecimals={false} />
                <YAxis yAxisId="r" orientation="right" tick={axis} tickLine={false} axisLine={false} tickFormatter={(v) => `₹${Math.round(v / 1000)}k`} />
                <Tooltip {...tooltipStyle} formatter={(v, n) => (n === 'Cost' ? fmt.money(v) : v)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar yAxisId="l" dataKey="count" name="Failures" fill={C.blue} radius={[2, 2, 0, 0]} />
                <Bar yAxisId="r" dataKey="cost" name="Cost" fill={C.amber} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ChartBox>
          )}
        </Panel>

        <Panel title="SLA compliance by severity" note={`Resolved in the last ${Math.max(days, 30)} days`}>
          {!sla.data ? <Spinner /> : (
            <ChartBox height={220}>
              <BarChart data={sla.data} margin={{ top: 5, right: 5, left: -10, bottom: 0 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="severity" tick={axis} tickLine={false} axisLine={false} />
                <YAxis domain={[0, 100]} unit="%" tick={axis} tickLine={false} axisLine={false} />
                <Tooltip {...tooltipStyle} formatter={(v, n, p) => [`${v ?? '—'}% (${p.payload.resolved} resolved, avg ${fmt.hours(p.payload.avg_resolution_hours)})`, 'SLA met']} />
                <Bar dataKey="compliance_pct" name="SLA met" radius={[2, 2, 0, 0]}>
                  {sla.data.map((d) => <Cell key={d.severity} fill={d.compliance_pct != null && d.compliance_pct < 85 ? C.amber : C.green} />)}
                </Bar>
              </BarChart>
            </ChartBox>
          )}
        </Panel>

        <Panel title="Recurring faults by building">
          {!recurring.data ? <Spinner /> : (
            <ul className="space-y-2.5">
              {recurring.data.locations.map((l) => {
                const max = recurring.data.locations[0]?.count || 1;
                return (
                  <li key={l.building}>
                    <div className="flex justify-between text-sm"><span>{l.building}</span><span className="text-ink-soft">{l.count} faults · {fmt.money(l.cost)}</span></div>
                    <div className="mt-1 h-2 rounded-sm bg-paper"><div className="h-full rounded-sm bg-blueprint" style={{ width: `${(l.count / max) * 100}%` }} /></div>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title="Technician performance" note={`Last ${Math.max(days, 30)} days`} className="mt-6" bodyClass="p-0">
        {!techs.data ? <Spinner /> : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead><tr><th>Technician</th><th>Open now</th><th>Assigned</th><th>Resolved</th><th>Avg resolution</th><th>SLA met</th><th>Reopened</th><th>Rating</th><th>Labour</th><th>Parts & cost</th></tr></thead>
              <tbody>
                {techs.data.map((t) => (
                  <tr key={t.technician_id}>
                    <td className="font-medium">{t.full_name}{!t.is_available && <span className="ml-2 text-xs text-ink-faint">unavailable</span>}</td>
                    <td>{t.current_workload}</td><td>{t.assigned}</td><td>{t.resolved}</td>
                    <td>{fmt.hours(t.avg_resolution_hours)}</td>
                    <td className={t.sla_compliance_pct != null && t.sla_compliance_pct < 85 ? 'text-signal-dark' : ''}>{fmt.pct(t.sla_compliance_pct)}</td>
                    <td>{t.reopened}</td><td>{t.avg_rating ? `${t.avg_rating} ★` : '—'}</td>
                    <td>{fmt.num(t.labour_hours, 1)} h</td><td>{fmt.money(t.repair_cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
