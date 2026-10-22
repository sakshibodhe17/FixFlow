import { Link } from 'react-router-dom';
import { CalendarClock } from 'lucide-react';
import { fmt } from '../lib/format';
import { Empty, SeverityPill, SlaBar, StatusPill } from './ui';

/** Requests as a table on wide screens and stacked rows on phones. */
export default function RequestTable({ items, showTechnician = true, showReporter = false, warnPct = 75, empty }) {
  if (!items?.length) return empty || <Empty title="No requests here." />;
  return (
    <>
      <div className="hidden overflow-x-auto md:block">
        <table className="table-base">
          <thead>
            <tr>
              <th>#</th><th>Problem</th><th>Severity</th><th>Status</th>
              {showTechnician && <th>Technician</th>}
              {showReporter && <th>Reported by</th>}
              <th className="w-56">SLA</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.request_id}>
                <td className="text-ink-soft">{r.request_id}</td>
                <td className="max-w-sm">
                  <Link to={`/requests/${r.request_id}`} className="font-medium text-ink hover:text-blueprint hover:underline">
                    {r.is_preventive && <CalendarClock className="mr-1 inline h-3.5 w-3.5 text-blueprint" aria-label="Preventive" />}
                    {r.title}
                  </Link>
                  <div className="text-xs text-ink-soft">{r.asset?.asset_name} · {r.asset?.location?.label} · {fmt.relative(r.reported_at)}</div>
                </td>
                <td><SeverityPill severity={r.severity} /></td>
                <td><StatusPill status={r.status} />{r.reopen_count > 0 && <span className="ml-1 text-xs text-signal-dark">↺{r.reopen_count}</span>}</td>
                {showTechnician && <td className="whitespace-nowrap text-sm">{r.technician?.full_name || <span className="text-breach">Unassigned</span>}</td>}
                {showReporter && <td className="whitespace-nowrap text-sm">{r.reporter?.full_name}</td>}
                <td><SlaBar sla={r.sla} warnPct={warnPct} compact /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="divide-y divide-line md:hidden">
        {items.map((r) => (
          <li key={r.request_id}>
            <Link to={`/requests/${r.request_id}`} className="block py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-medium">{r.title}</div>
                  <div className="truncate text-xs text-ink-soft">#{r.request_id} · {r.asset?.asset_name}</div>
                </div>
                <StatusPill status={r.status} />
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <SeverityPill severity={r.severity} />
                <SlaBar sla={r.sla} warnPct={warnPct} compact />
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
