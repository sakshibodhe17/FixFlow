import { useState } from 'react';
import { Link } from 'react-router-dom';
import { MapPin, Play, ThumbsUp } from 'lucide-react';
import { Button, Empty, ErrorNote, PageHeader, Panel, SeverityPill, SlaBar, Spinner, Stat, StatusPill, Tabs } from '../../components/ui';
import api, { errorMessage } from '../../lib/api';
import { fmt } from '../../lib/format';
import { useApi } from '../../lib/hooks';

const URGENCY = { breached: 0, at_risk: 1, on_track: 2 };

export default function TaskQueue() {
  const [tab, setTab] = useState('active');
  const { data, loading, error, reload } = useApi('/requests', { params: { limit: 300 }, pollMs: 15000 });
  const [actionError, setActionError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const items = data?.items || [];
  const active = items
    .filter((r) => ['Assigned', 'In Progress', 'On Hold'].includes(r.status))
    .sort((a, b) => (URGENCY[a.sla?.state] ?? 3) - (URGENCY[b.sla?.state] ?? 3) || new Date(a.resolution_due) - new Date(b.resolution_due));
  const done = items.filter((r) => ['Resolved', 'Closed'].includes(r.status));
  const list = tab === 'active' ? active : done;

  const quick = async (r, action) => {
    setBusyId(r.request_id);
    setActionError(null);
    try { await api.post(`/requests/${r.request_id}/${action}`); await reload(true); } catch (e) { setActionError(errorMessage(e)); }
    setBusyId(null);
  };

  return (
    <>
      <PageHeader title="My jobs" subtitle="Most urgent first. Open a job to log parts, labour and photos." />
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Active jobs" value={active.length} />
        <Stat label="Past SLA" value={active.filter((r) => r.sla?.state === 'breached').length} tone="red" />
        <Stat label="Close to SLA" value={active.filter((r) => r.sla?.state === 'at_risk').length} tone="amber" />
        <Stat label="Resolved in total" value={done.length} tone="green" />
      </div>
      <Panel>
        <Tabs value={tab} onChange={setTab} tabs={[{ value: 'active', label: 'To do', count: active.length }, { value: 'done', label: 'Completed', count: done.length }]} />
        <ErrorNote>{error || actionError}</ErrorNote>
        {loading ? <Spinner /> : list.length === 0 ? (
          <Empty title={tab === 'active' ? 'No jobs assigned right now.' : 'No completed jobs yet.'}>
            {tab === 'active' && 'New jobs appear here automatically. Make sure you are marked available.'}
          </Empty>
        ) : (
          <ul className="divide-y divide-line">
            {list.map((r) => (
              <li key={r.request_id} className="flex flex-col gap-3 py-4 md:flex-row md:items-center">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link to={`/requests/${r.request_id}`} className="font-medium hover:text-blueprint hover:underline">{r.title}</Link>
                    <StatusPill status={r.status} />
                    {r.status === 'Assigned' && !r.accepted_at && <span className="text-xs font-medium text-signal-dark">New</span>}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-soft">
                    <SeverityPill severity={r.severity} />
                    <span>{r.asset?.asset_name}</span>
                    <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" />{r.asset?.location?.label}</span>
                    <span>reported {fmt.relative(r.reported_at)}</span>
                  </div>
                </div>
                <div className="w-full md:w-56"><SlaBar sla={r.sla} compact={false} /></div>
                {tab === 'active' && (
                  <div className="flex gap-2 md:w-48 md:justify-end">
                    {r.status === 'Assigned' && !r.accepted_at && <Button size="sm" variant="secondary" icon={ThumbsUp} busy={busyId === r.request_id} onClick={() => quick(r, 'accept')}>Accept</Button>}
                    {['Assigned', 'On Hold'].includes(r.status) && <Button size="sm" icon={Play} busy={busyId === r.request_id} onClick={() => quick(r, 'start')}>{r.status === 'On Hold' ? 'Resume' : 'Start'}</Button>}
                    {r.status === 'In Progress' && <Link to={`/requests/${r.request_id}`}><Button size="sm" variant="secondary">Open</Button></Link>}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}
