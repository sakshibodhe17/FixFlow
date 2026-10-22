import { useState } from 'react';
import { FileSpreadsheet, FileText } from 'lucide-react';
import { Button, ErrorNote, Field, Input, PageHeader, Panel, Select } from '../../components/ui';
import { download } from '../../lib/api';
import { useAction } from '../../lib/hooks';

const iso = (d) => d.toISOString().slice(0, 10);

export default function Reports() {
  const [range, setRange] = useState({ date_from: iso(new Date(Date.now() - 30 * 86400000)), date_to: iso(new Date()), status: '' });
  const action = useAction();
  const params = { date_from: range.date_from, date_to: range.date_to, ...(range.status && { status: range.status }) };
  const get = (format) => action.run(() => download('/reports/requests', { ...params, format }, `fixflow_requests.${format}`)).catch(() => {});

  return (
    <>
      <PageHeader title="Reports" subtitle="Export maintenance data for audits, budget reviews and handovers." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Maintenance requests" note="One row per request with SLA result, labour, cost, downtime and rating.">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="From"><Input type="date" value={range.date_from} onChange={(e) => setRange({ ...range, date_from: e.target.value })} /></Field>
            <Field label="To"><Input type="date" value={range.date_to} onChange={(e) => setRange({ ...range, date_to: e.target.value })} /></Field>
            <Field label="Status">
              <Select value={range.status} onChange={(e) => setRange({ ...range, status: e.target.value })}>
                <option value="">Any</option><option value="Resolved,Closed">Completed</option><option value="Open,Assigned,In Progress,On Hold,Reopened">Not yet resolved</option>
              </Select>
            </Field>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button icon={FileText} busy={action.busy} onClick={() => get('pdf')}>Download PDF</Button>
            <Button variant="secondary" icon={FileSpreadsheet} busy={action.busy} onClick={() => get('csv')}>Download CSV</Button>
          </div>
          <div className="mt-3"><ErrorNote>{action.error}</ErrorNote></div>
        </Panel>
        <Panel title="Asset register" note="All assets with location, QR code, warranty and latest failure risk.">
          <Button variant="secondary" icon={FileSpreadsheet} busy={action.busy} onClick={() => action.run(() => download('/reports/assets', {}, 'fixflow_assets.csv')).catch(() => {})}>Download CSV</Button>
        </Panel>
      </div>
    </>
  );
}
