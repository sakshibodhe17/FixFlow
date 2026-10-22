import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Pencil, RefreshCw } from 'lucide-react';
import RequestTable from '../../components/RequestTable';
import { Button, Empty, ErrorNote, Field, Input, Modal, PageHeader, Panel, Spinner, Stat, Tabs, cx } from '../../components/ui';
import api from '../../lib/api';
import { fmt } from '../../lib/format';
import { useAction, useApi } from '../../lib/hooks';

const LEVEL_STYLE = { Breach: 'bg-breach text-white', Warning: 'bg-signal-light text-signal-dark', Response: 'bg-blueprint-light text-blueprint-dark' };

export default function SlaCenter() {
  const [tab, setTab] = useState('risk');
  const monitor = useApi('/sla/monitor', { pollMs: 30000 });
  const esc = useApi('/sla/escalations', { params: { acknowledged: false, limit: 300 }, pollMs: 30000 });
  const policies = useApi('/sla/policies');
  const [edit, setEdit] = useState(null);
  const action = useAction();
  const [checkResult, setCheckResult] = useState(null);

  const m = monitor.data;
  const items = (m?.items || []).filter((r) => (tab === 'risk' ? ['breached', 'at_risk'].includes(r.sla?.state) : true));
  // one row per request+level (each manager gets their own escalation record)
  const escalations = [...new Map((esc.data || []).map((e) => [`${e.request_id}-${e.level}`, e])).values()];

  const ack = (id) => action.run(async () => { await api.post(`/sla/escalations/${id}/acknowledge`); esc.reload(true); }).catch(() => {});
  const checkNow = () => action.run(async () => {
    const { data } = await api.post('/sla/check-now');
    setCheckResult(data);
    monitor.reload(true); esc.reload(true);
  }).catch(() => {});
  const savePolicy = () => action.run(async () => {
    await api.put(`/sla/policies/${edit.sla_id}`, { response_hours: Number(edit.response_hours), resolution_hours: Number(edit.resolution_hours) });
    setEdit(null); policies.reload(true);
  }).catch(() => {});

  return (
    <>
      <PageHeader title="SLA & escalations" subtitle="Deadlines are checked automatically every few minutes. Managers are alerted when a request nears or passes its deadline."
        actions={<Button variant="secondary" icon={RefreshCw} busy={action.busy} onClick={checkNow}>Check deadlines now</Button>} />
      {checkResult && <p className="mb-4 text-sm text-ink-soft" role="status">Checked {checkResult.checked} open requests: {checkResult.breaches} new breach, {checkResult.warnings} new warning, {checkResult.response_breaches} missed response alerts.</p>}
      <ErrorNote>{action.error}</ErrorNote>

      <div className="mb-6 grid grid-cols-3 gap-3">
        <Stat label="Past deadline" value={m?.counts.breached ?? '—'} tone="red" />
        <Stat label={`Over ${m?.warning_pct ?? 75}% of time used`} value={m?.counts.at_risk ?? '—'} tone="amber" />
        <Stat label="On track" value={m?.counts.on_track ?? '—'} tone="green" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <Panel title="Live SLA monitor">
          <Tabs value={tab} onChange={setTab} tabs={[
            { value: 'risk', label: 'Needs attention', count: (m?.counts.breached || 0) + (m?.counts.at_risk || 0) },
            { value: 'all', label: 'All open', count: m?.items.length },
          ]} />
          {!m ? <Spinner /> : <RequestTable items={items} warnPct={m.warning_pct} empty={<Empty title="Nothing at risk right now.">Every open request is comfortably inside its deadline.</Empty>} />}
        </Panel>

        <div className="space-y-6">
          <Panel title="Unacknowledged alerts" note="Acknowledging clears the alert for every manager.">
            {!esc.data ? <Spinner /> : escalations.length === 0 ? <p className="text-sm text-ink-soft">No open alerts.</p> : (
              <ul className="divide-y divide-line">
                {escalations.map((e) => (
                  <li key={e.escalation_id} className="py-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className={cx('rounded-sm px-1.5 py-0.5 text-xs font-semibold', LEVEL_STYLE[e.level])}>{e.level === 'Response' ? 'No response' : e.level}</span>
                      <span className="text-xs text-ink-faint">{fmt.relative(e.escalated_at)}</span>
                    </div>
                    <Link to={`/requests/${e.request_id}`} className="mt-1 block text-sm font-medium hover:text-blueprint hover:underline">#{e.request_id} {e.request?.title}</Link>
                    <p className="mt-0.5 text-xs text-ink-soft">{e.reason}</p>
                    <Button size="sm" variant="ghost" className="-ml-3 mt-1" onClick={() => ack(e.escalation_id)}>Acknowledge</Button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="SLA rules" note="Changes apply to new requests only.">
            <table className="table-base">
              <thead><tr><th>Severity</th><th>Respond</th><th>Resolve</th><th /></tr></thead>
              <tbody>
                {(policies.data || []).map((p) => (
                  <tr key={p.sla_id}>
                    <td className="font-medium">{p.severity}</td><td>{fmt.hours(p.response_hours)}</td><td>{fmt.hours(p.resolution_hours)}</td>
                    <td className="text-right"><button type="button" className="rounded p-1 text-ink-soft hover:bg-paper" aria-label={`Edit ${p.severity}`} onClick={() => setEdit({ ...p })}><Pencil className="h-4 w-4" /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </div>
      </div>

      <Modal open={!!edit} onClose={() => setEdit(null)} title={`${edit?.severity} severity SLA`}
        footer={<><Button variant="secondary" onClick={() => setEdit(null)}>Cancel</Button><Button busy={action.busy} onClick={savePolicy}>Save rule</Button></>}>
        {edit && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Respond within (hours)"><Input type="number" min="1" value={edit.response_hours} onChange={(e) => setEdit({ ...edit, response_hours: e.target.value })} /></Field>
            <Field label="Resolve within (hours)"><Input type="number" min="1" value={edit.resolution_hours} onChange={(e) => setEdit({ ...edit, resolution_hours: e.target.value })} /></Field>
          </div>
        )}
        <div className="mt-3"><ErrorNote>{action.error}</ErrorNote></div>
      </Modal>
    </>
  );
}
