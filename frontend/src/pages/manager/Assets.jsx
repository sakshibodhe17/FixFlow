import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Archive, History, Pencil, Plus, Printer, QrCode, RefreshCw, Search } from 'lucide-react';
import {
  Button, Empty, ErrorNote, Field, Input, Modal, PageHeader, Panel, RiskPill, Select, Spinner, StatusPill, cx,
} from '../../components/ui';
import api from '../../lib/api';
import { fmt } from '../../lib/format';
import { useAction, useApi } from '../../lib/hooks';

const ASSET_STATUS = { Working: 'text-moss', Faulty: 'text-breach', 'Under Repair': 'text-signal-dark', Retired: 'text-ink-faint' };
const EMPTY = { asset_name: '', category: '', location_id: '', purchase_date: '', warranty_expiry: '', status: 'Working' };

function printLabels(labels) {
  const w = window.open('', '_blank', 'width=800,height=900');
  if (!w) return;
  const cards = labels.map((l) => `
    <div class="card"><img src="${l.image}" alt=""/><div class="name">${l.asset_name}</div>
    <div class="code">${l.qr_code}</div><div class="hint">Scan to report a problem</div></div>`).join('');
  w.document.write(`<!doctype html><html><head><title>FixFlow QR labels</title><style>
    body{font-family:Arial,sans-serif;margin:16px} .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
    .card{border:1px dashed #999;padding:10px;text-align:center;break-inside:avoid} img{width:150px;height:150px}
    .name{font-weight:bold;font-size:13px;margin-top:4px} .code{font-family:monospace;font-size:12px} .hint{font-size:11px;color:#555}
  </style></head><body><div class="grid">${cards}</div><script>window.onload=()=>window.print()<\/script></body></html>`);
  w.document.close();
}

function HistoryModal({ asset, onClose }) {
  const { data, loading } = useApi(asset ? `/assets/${asset.asset_id}/history` : null, { enabled: !!asset });
  return (
    <Modal open={!!asset} onClose={onClose} title={`Repair history: ${asset?.asset_name || ''}`} wide>
      {loading || !data ? <Spinner /> : (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div><div className="text-xs text-ink-soft">Failures</div><div className="text-lg font-semibold">{data.summary.failures}</div></div>
            <div><div className="text-xs text-ink-soft">Total cost</div><div className="text-lg font-semibold">{fmt.money(data.summary.total_repair_cost)}</div></div>
            <div><div className="text-xs text-ink-soft">Downtime</div><div className="text-lg font-semibold">{fmt.hours(data.summary.total_downtime_hours)}</div></div>
            <div><div className="text-xs text-ink-soft">Last failure</div><div className="text-lg font-semibold">{fmt.date(data.summary.last_failure_at)}</div></div>
          </div>
          {data.history.length === 0 ? <Empty title="No maintenance on record." /> : (
            <ul className="divide-y divide-line">
              {data.history.map((h) => (
                <li key={h.request_id} className="py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link to={`/requests/${h.request_id}`} className="font-medium hover:text-blueprint hover:underline">#{h.request_id} {h.title}</Link>
                    <StatusPill status={h.status} />{h.is_preventive && <span className="text-xs text-blueprint">Preventive</span>}
                  </div>
                  <div className="text-xs text-ink-soft">{fmt.date(h.reported_at)} · {h.severity}{h.resolved_at && ` · resolved ${fmt.date(h.resolved_at)}`}</div>
                  {h.repair_logs.map((l) => (
                    <div key={l.log_id} className="mt-1 text-xs text-ink-soft">{l.technician_name}: {l.work_notes} {l.parts_used && `(parts: ${l.parts_used})`} · {fmt.money(l.repair_cost)}</div>
                  ))}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Modal>
  );
}

export default function Assets() {
  const [filters, setFilters] = useState({ q: '', category: '', building: '', status: '' });
  const [query, setQuery] = useState({});
  const { data, loading, error, reload } = useApi('/assets', { params: { ...query, include_retired: query.status === 'Retired' } });
  const { data: locations } = useApi('/locations');
  const { data: categories } = useApi('/categories');
  const [form, setForm] = useState(null);
  const [qr, setQr] = useState(null);
  const [history, setHistory] = useState(null);
  const [selected, setSelected] = useState([]);
  const action = useAction();
  const buildings = [...new Set((locations || []).map((l) => l.building))];

  const apply = (next) => {
    const f = { ...filters, ...next };
    setFilters(f);
    setQuery(Object.fromEntries(Object.entries(f).filter(([, v]) => v)));
  };
  const save = () => action.run(async () => {
    const body = { ...form, location_id: form.location_id ? Number(form.location_id) : null,
      purchase_date: form.purchase_date || null, warranty_expiry: form.warranty_expiry || null };
    if (form.asset_id) await api.put(`/assets/${form.asset_id}`, body);
    else { const { data: created } = await api.post('/assets', body); setQr((await api.get(`/assets/${created.asset_id}/qr`)).data); }
    setForm(null);
    reload(true);
  }).catch(() => {});
  const showQr = (a) => action.run(async () => setQr((await api.get(`/assets/${a.asset_id}/qr`)).data)).catch(() => {});
  const regenerate = () => action.run(async () => { setQr((await api.post(`/assets/${qr.asset_id}/qr/regenerate`)).data); reload(true); }).catch(() => {});
  const retire = (a) => {
    if (!window.confirm(`Retire “${a.asset_name}”? Assets with history are kept but hidden from reporters.`)) return;
    action.run(async () => { await api.delete(`/assets/${a.asset_id}`); reload(true); }).catch(() => {});
  };
  const printSelected = () => action.run(async () => {
    const labels = await Promise.all(selected.map((id) => api.get(`/assets/${id}/qr`).then((r) => r.data)));
    printLabels(labels);
  }).catch(() => {});

  const items = data || [];
  return (
    <>
      <PageHeader title="Assets & QR codes" subtitle="Every asset gets a unique QR sticker. Scanning it opens the report form with the asset filled in."
        actions={<>
          {selected.length > 0 && <Button variant="secondary" icon={Printer} busy={action.busy} onClick={printSelected}>Print {selected.length} label{selected.length > 1 ? 's' : ''}</Button>}
          <Button icon={Plus} onClick={() => setForm({ ...EMPTY })}>Add asset</Button>
        </>} />
      <ErrorNote>{error || action.error}</ErrorNote>
      <Panel bodyClass="p-0">
        <div className="grid gap-2 border-b border-line p-3 sm:grid-cols-2 lg:grid-cols-4">
          <form className="relative" onSubmit={(e) => { e.preventDefault(); apply({}); }}>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
            <Input className="pl-9" placeholder="Name or QR code, then Enter" value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} aria-label="Search assets" />
          </form>
          <Select value={filters.category} onChange={(e) => apply({ category: e.target.value })} aria-label="Category"><option value="">All categories</option>{(categories || []).map((c) => <option key={c.category_id}>{c.name}</option>)}</Select>
          <Select value={filters.building} onChange={(e) => apply({ building: e.target.value })} aria-label="Building"><option value="">All buildings</option>{buildings.map((b) => <option key={b}>{b}</option>)}</Select>
          <Select value={filters.status} onChange={(e) => apply({ status: e.target.value })} aria-label="Status"><option value="">Active assets</option>{Object.keys(ASSET_STATUS).map((s) => <option key={s}>{s}</option>)}</Select>
        </div>
        {loading ? <Spinner /> : items.length === 0 ? <div className="p-4"><Empty title="No assets match.">Add your first asset to generate its QR code.</Empty></div> : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead><tr>
                <th><input type="checkbox" aria-label="Select all" checked={selected.length === items.length} onChange={(e) => setSelected(e.target.checked ? items.map((a) => a.asset_id) : [])} /></th>
                <th>Asset</th><th>Location</th><th>Status</th><th>Warranty</th><th>Failure risk</th><th className="text-right">Actions</th>
              </tr></thead>
              <tbody>
                {items.map((a) => (
                  <tr key={a.asset_id}>
                    <td><input type="checkbox" aria-label={`Select ${a.asset_name}`} checked={selected.includes(a.asset_id)} onChange={(e) => setSelected(e.target.checked ? [...selected, a.asset_id] : selected.filter((x) => x !== a.asset_id))} /></td>
                    <td><div className="font-medium">{a.asset_name}</div><div className="text-xs text-ink-soft">{a.category} · {a.qr_code}</div></td>
                    <td className="text-sm">{a.location?.label || '—'}</td>
                    <td className={cx('text-sm font-medium', ASSET_STATUS[a.status])}>{a.status}</td>
                    <td className="text-sm">{a.warranty_expiry ? (new Date(a.warranty_expiry) < new Date() ? <span className="text-ink-faint">Ended {fmt.date(a.warranty_expiry)}</span> : `Until ${fmt.date(a.warranty_expiry)}`) : '—'}</td>
                    <td>{a.risk ? <RiskPill level={a.risk.risk_level} score={a.risk.risk_score} /> : <span className="text-xs text-ink-faint">Not scored</span>}</td>
                    <td>
                      <div className="flex justify-end gap-1">
                        {[[QrCode, 'QR code', () => showQr(a)], [History, 'Repair history', () => setHistory(a)],
                          [Pencil, 'Edit', () => setForm({ ...EMPTY, ...a, location_id: a.location_id ? String(a.location_id) : '', purchase_date: a.purchase_date || '', warranty_expiry: a.warranty_expiry || '' })],
                          ...(a.status !== 'Retired' ? [[Archive, 'Retire', () => retire(a)]] : [])].map(([Icon, label, fn]) => (
                          <button key={label} type="button" onClick={fn} title={label} aria-label={`${label}: ${a.asset_name}`} className="rounded p-1.5 text-ink-soft hover:bg-paper hover:text-ink"><Icon className="h-4 w-4" /></button>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Modal open={!!form} onClose={() => setForm(null)} title={form?.asset_id ? 'Edit asset' : 'Add asset'}
        footer={<><Button variant="secondary" onClick={() => setForm(null)}>Cancel</Button><Button busy={action.busy} onClick={save}>{form?.asset_id ? 'Save changes' : 'Add asset and create QR'}</Button></>}>
        {form && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" className="sm:col-span-2"><Input required value={form.asset_name} onChange={(e) => setForm({ ...form, asset_name: e.target.value })} placeholder="Split AC 1.5T – Room 204" /></Field>
            <Field label="Category" hint="Decides which technician skill is needed.">
              <Select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}><option value="">Choose…</option>{(categories || []).map((c) => <option key={c.category_id}>{c.name}</option>)}</Select>
            </Field>
            <Field label="Location">
              <Select value={form.location_id} onChange={(e) => setForm({ ...form, location_id: e.target.value })}><option value="">None</option>{(locations || []).map((l) => <option key={l.location_id} value={l.location_id}>{l.label}</option>)}</Select>
            </Field>
            <Field label="Purchase date"><Input type="date" value={form.purchase_date} onChange={(e) => setForm({ ...form, purchase_date: e.target.value })} /></Field>
            <Field label="Warranty until"><Input type="date" value={form.warranty_expiry} onChange={(e) => setForm({ ...form, warranty_expiry: e.target.value })} /></Field>
            {form.asset_id && <Field label="Status"><Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>{Object.keys(ASSET_STATUS).map((s) => <option key={s}>{s}</option>)}</Select></Field>}
            <div className="sm:col-span-2"><ErrorNote>{action.error}</ErrorNote></div>
          </div>
        )}
      </Modal>

      <Modal open={!!qr} onClose={() => setQr(null)} title="QR code"
        footer={<>
          <Button variant="ghost" icon={RefreshCw} busy={action.busy} onClick={() => window.confirm('Generate a new code? Printed stickers with the old code will stop working.') && regenerate()}>New code</Button>
          {qr && <a href={qr.image} download={`${qr.qr_code}.png`}><Button variant="secondary">Download PNG</Button></a>}
          <Button icon={Printer} onClick={() => printLabels([qr])}>Print label</Button>
        </>}>
        {qr && (
          <div className="text-center">
            <img src={qr.image} alt={`QR code for ${qr.asset_name}`} className="mx-auto h-56 w-56" />
            <div className="mt-2 font-semibold">{qr.asset_name}</div>
            <div className="text-sm text-ink-soft">{qr.qr_code}</div>
            <p className="mt-2 break-all text-xs text-ink-faint">Opens {qr.scan_url}</p>
          </div>
        )}
      </Modal>
      <HistoryModal asset={history} onClose={() => setHistory(null)} />
    </>
  );
}
