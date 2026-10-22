import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search } from 'lucide-react';
import RequestTable from '../../components/RequestTable';
import { Button, ErrorNote, Input, PageHeader, Panel, Select, Spinner } from '../../components/ui';
import { SEVERITIES, STATUSES } from '../../lib/format';
import { useApi } from '../../lib/hooks';

const PAGE = 50;

export default function AllRequests() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') || '');
  const [page, setPage] = useState(0);
  const filters = {
    status: params.get('status') || undefined,
    severity: params.get('severity') || undefined,
    technician_id: params.get('technician_id') || undefined,
    overdue: params.get('overdue') === 'true' || undefined,
    preventive: params.get('preventive') || undefined,
    q: params.get('q') || undefined,
  };
  const { data: techs } = useApi('/technicians');
  const { data, loading, error } = useApi('/requests', { params: { ...filters, limit: PAGE, offset: page * PAGE }, pollMs: 30000 });

  const set = (k, v) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    setParams(next);
    setPage(0);
  };
  const total = data?.total || 0;

  return (
    <>
      <PageHeader title="All requests" subtitle={`${total} matching request${total === 1 ? '' : 's'}. Updates every 30 seconds.`} />
      <Panel bodyClass="p-0">
        <div className="grid gap-2 border-b border-line p-3 sm:grid-cols-2 lg:grid-cols-6">
          <form className="relative lg:col-span-2" onSubmit={(e) => { e.preventDefault(); set('q', q.trim()); }}>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
            <Input className="pl-9" placeholder="Search title or asset, then Enter" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" />
          </form>
          <Select value={filters.status || ''} onChange={(e) => set('status', e.target.value)} aria-label="Status">
            <option value="">Any status</option>
            <option value="Open,Assigned,In Progress,On Hold,Reopened">Not yet resolved</option>
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </Select>
          <Select value={filters.severity || ''} onChange={(e) => set('severity', e.target.value)} aria-label="Severity">
            <option value="">Any severity</option>{SEVERITIES.map((s) => <option key={s}>{s}</option>)}
          </Select>
          <Select value={filters.technician_id || ''} onChange={(e) => set('technician_id', e.target.value)} aria-label="Technician">
            <option value="">Any technician</option>
            {(techs || []).map((t) => <option key={t.technician_id} value={t.technician_id}>{t.full_name}</option>)}
          </Select>
          <Select value={filters.overdue ? 'overdue' : filters.preventive === 'true' ? 'pm' : ''} aria-label="Type"
            onChange={(e) => { const n = new URLSearchParams(params); n.delete('overdue'); n.delete('preventive');
              if (e.target.value === 'overdue') n.set('overdue', 'true'); if (e.target.value === 'pm') n.set('preventive', 'true'); setParams(n); setPage(0); }}>
            <option value="">All types</option><option value="overdue">Past SLA only</option><option value="pm">Preventive only</option>
          </Select>
        </div>
        <div className="px-3 pb-3">
          <ErrorNote>{error}</ErrorNote>
          {loading && !data ? <Spinner /> : <RequestTable items={data?.items} showReporter />}
          {total > PAGE && (
            <div className="mt-3 flex items-center justify-between text-sm">
              <span className="text-ink-soft">{page * PAGE + 1}–{Math.min(total, (page + 1) * PAGE)} of {total}</span>
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
                <Button size="sm" variant="secondary" disabled={(page + 1) * PAGE >= total} onClick={() => setPage(page + 1)}>Next</Button>
              </div>
            </div>
          )}
        </div>
      </Panel>
    </>
  );
}
