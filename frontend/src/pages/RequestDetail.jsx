import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, CalendarClock, Camera, CheckCircle2, ClipboardPlus, MapPin, Pause, Play, RotateCcw, ShieldAlert,
  ThumbsUp, UserCog, Wand2,
} from 'lucide-react';
import {
  Button, ErrorNote, Field, Input, Modal, PageHeader, Panel, Select, SeverityPill, SlaBar, Spinner, Stars,
  StatusPill, Textarea, cx,
} from '../components/ui';
import api, { fileUrl } from '../lib/api';
import { useAuth } from '../lib/auth';
import { fmt, STATUSES } from '../lib/format';
import { useAction, useApi } from '../lib/hooks';

const ACTION_LABEL = {
  'request.created': 'Reported', 'request.assigned': 'Assigned', 'request.accepted': 'Accepted by technician',
  'request.started': 'Work started', 'request.resumed': 'Work resumed', 'request.paused': 'Paused',
  'request.resolved': 'Marked resolved', 'request.rated': 'Rated', 'request.closed': 'Closed',
  'request.reopened': 'Reopened', 'request.status_override': 'Status changed by manager',
  'request.photos_added': 'Photos added', 'request.log_added': 'Progress logged',
  'request.assign_failed': 'No matching technician available', 'request.preventive_scheduled': 'Preventive job scheduled',
  'sla.warning': 'SLA warning sent to managers', 'sla.breach': 'SLA breached, escalated', 'sla.response': 'Response time missed, escalated',
  'escalation.acknowledged': 'Escalation acknowledged',
};

function describe(t) {
  const d = t.details;
  if (!d || typeof d !== 'object') return null;
  if (t.action === 'request.assigned') return `${d.technician}${d.mode === 'manual' ? ' (manual override)' : d.mode === 'reopen' ? ' (after reopen)' : ''}`;
  if (t.action === 'request.reopened') return d.reason;
  if (t.action === 'request.rated') return `${d.rating} ★`;
  if (t.action === 'request.status_override') return `${d.from} → ${d.to}${d.note ? `: ${d.note}` : ''}`;
  if (t.action === 'request.resolved') return `${d.labour_hours} h labour, ${fmt.money(d.repair_cost)}`;
  if (t.action === 'request.photos_added') return `${d.count} ${d.type.toLowerCase()} photo(s)`;
  if (t.action === 'request.assign_failed') return d.required_skill ? `Needs ${d.required_skill}` : null;
  return null;
}

function WorkTimer({ req }) {
  const [, tick] = useState(0);
  const running = !!req.work_started_at;
  useEffect(() => {
    if (!running) return undefined;
    const id = setInterval(() => tick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [running]);
  const secs = (req.work_seconds || 0) + (running ? (Date.now() - new Date(req.work_started_at)) / 1000 : 0);
  return (
    <div className="flex items-center gap-3">
      <span className={cx('h-2.5 w-2.5 rounded-full', running ? 'animate-pulse bg-moss' : 'bg-ink-faint')} aria-hidden />
      <span className="font-narrow text-3xl font-semibold tabular-nums">{fmt.duration(secs)}</span>
      <span className="text-xs text-ink-soft">{running ? 'timer running' : 'timer paused'}</span>
    </div>
  );
}

function PhotoUpload({ requestId, type, onDone, label }) {
  const { busy, error, run } = useAction();
  const upload = (files) => run(async () => {
    const fd = new FormData();
    Array.from(files).slice(0, 6).forEach((f) => fd.append('files', f));
    fd.append('photo_type', type);
    await api.post(`/requests/${requestId}/photos`, fd);
    onDone();
  }).catch(() => {});
  return (
    <div>
      <label className={cx('inline-flex h-8 cursor-pointer items-center gap-2 rounded border border-line bg-white px-3 text-xs font-medium hover:border-ink-faint', busy && 'opacity-60')}>
        <Camera className="h-4 w-4" /> {busy ? 'Uploading…' : label}
        <input type="file" accept="image/*" multiple className="sr-only" disabled={busy} onChange={(e) => { upload(e.target.files); e.target.value = ''; }} />
      </label>
      {error && <div className="mt-2"><ErrorNote>{error}</ErrorNote></div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
function TechnicianActions({ req, reload }) {
  const { busy, error, run } = useAction();
  const [modal, setModal] = useState(null);
  const liveHours = ((req.work_seconds || 0) + (req.work_started_at ? (Date.now() - new Date(req.work_started_at)) / 1000 : 0)) / 3600;
  const [form, setForm] = useState({ work_notes: '', parts_used: '', labour_hours: '', repair_cost: '' });
  const act = (path, body) => run(async () => { await api.post(`/requests/${req.request_id}/${path}`, body); setModal(null); reload(); }).catch(() => {});

  const openComplete = () => { setForm({ work_notes: '', parts_used: '', labour_hours: liveHours.toFixed(2), repair_cost: '' }); setModal('complete'); };
  const openLog = () => { setForm({ work_notes: '', parts_used: '', labour_hours: '', repair_cost: '' }); setModal('log'); };
  const num = (v) => (v === '' ? null : Number(v));

  const active = ['Assigned', 'In Progress', 'On Hold'].includes(req.status);
  return (
    <Panel title="Your job">
      {active && <WorkTimer req={req} />}
      <div className="mt-4 flex flex-wrap gap-2">
        {req.status === 'Assigned' && !req.accepted_at && <Button variant="secondary" icon={ThumbsUp} busy={busy} onClick={() => act('accept')}>Accept job</Button>}
        {req.status === 'Assigned' && <Button icon={Play} busy={busy} onClick={() => act('start')}>Start work</Button>}
        {req.status === 'On Hold' && <Button icon={Play} busy={busy} onClick={() => act('start')}>Resume work</Button>}
        {req.status === 'In Progress' && <Button variant="secondary" icon={Pause} busy={busy} onClick={() => act('pause')}>Pause</Button>}
        {active && req.status !== 'Assigned' && <Button variant="secondary" icon={ClipboardPlus} onClick={openLog}>Log progress</Button>}
        {['In Progress', 'On Hold'].includes(req.status) && <Button variant="success" icon={CheckCircle2} onClick={openComplete}>Complete job</Button>}
      </div>
      {active && <div className="mt-3"><PhotoUpload requestId={req.request_id} type="After" label="Add after-repair photos" onDone={reload} /></div>}
      {!active && <p className="text-sm text-ink-soft">This job is {req.status.toLowerCase()}. Nothing more to do here.</p>}
      <div className="mt-3"><ErrorNote>{error}</ErrorNote></div>

      <Modal open={!!modal} onClose={() => setModal(null)} title={modal === 'complete' ? 'Complete job' : 'Log progress'}
        footer={<>
          <Button variant="secondary" onClick={() => setModal(null)}>Cancel</Button>
          <Button variant={modal === 'complete' ? 'success' : 'primary'} busy={busy}
            onClick={() => (modal === 'complete'
              ? act('complete', { work_notes: form.work_notes, parts_used: form.parts_used || null, labour_hours: num(form.labour_hours), repair_cost: num(form.repair_cost) ?? 0 })
              : act('repair-logs', { work_notes: form.work_notes, parts_used: form.parts_used || null, labour_hours: num(form.labour_hours), repair_cost: num(form.repair_cost) }))}>
            {modal === 'complete' ? 'Mark as resolved' : 'Save log'}
          </Button>
        </>}>
        <div className="space-y-4">
          <Field label="Work notes" hint="What you found and what you did."><Textarea required value={form.work_notes} onChange={(e) => setForm({ ...form, work_notes: e.target.value })} /></Field>
          <Field label="Spare parts used" hint="Comma separated, with quantities."><Input value={form.parts_used} onChange={(e) => setForm({ ...form, parts_used: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Labour hours" hint={modal === 'complete' ? 'Pre-filled from the timer.' : undefined}><Input type="number" min="0" step="0.25" value={form.labour_hours} onChange={(e) => setForm({ ...form, labour_hours: e.target.value })} /></Field>
            <Field label="Repair cost (₹)"><Input type="number" min="0" step="1" value={form.repair_cost} onChange={(e) => setForm({ ...form, repair_cost: e.target.value })} /></Field>
          </div>
          {modal === 'complete' && <p className="text-xs text-ink-soft">Downtime is calculated automatically from when the fault was reported.</p>}
          <ErrorNote>{error}</ErrorNote>
        </div>
      </Modal>
    </Panel>
  );
}

function ReporterActions({ req, reload }) {
  const { busy, error, run } = useAction();
  const [rating, setRating] = useState(req.feedback?.rating || 0);
  const [comment, setComment] = useState(req.feedback?.comment || '');
  const [reopenOpen, setReopenOpen] = useState(false);
  const [reason, setReason] = useState('');

  const rate = () => run(async () => { await api.post(`/requests/${req.request_id}/feedback`, { rating, comment: comment || null }); reload(); }).catch(() => {});
  const reopen = () => run(async () => { await api.post(`/requests/${req.request_id}/reopen`, { reason }); setReopenOpen(false); setReason(''); reload(); }).catch(() => {});
  const done = ['Resolved', 'Closed'].includes(req.status);

  if (!done) {
    return (
      <Panel title="Your request">
        <p className="text-sm text-ink-soft">
          {req.technician ? `${req.technician.full_name} is on it.` : 'Waiting for a technician to be assigned.'} You'll get a notification when it's fixed.
        </p>
        <div className="mt-3"><PhotoUpload requestId={req.request_id} type="Before" label="Add more photos" onDone={reload} /></div>
      </Panel>
    );
  }
  return (
    <Panel title={req.status === 'Resolved' ? 'Is it fixed?' : 'Your rating'}>
      <div className="space-y-3">
        <Stars value={rating} onChange={setRating} size="h-8 w-8" />
        <Textarea rows={2} placeholder="Anything to add? (optional)" value={comment} onChange={(e) => setComment(e.target.value)} />
        <ErrorNote>{error}</ErrorNote>
        <div className="flex flex-wrap gap-2">
          <Button disabled={!rating} busy={busy} onClick={rate}>{req.status === 'Resolved' ? 'Confirm fix and rate' : 'Update rating'}</Button>
          <Button variant="secondary" icon={RotateCcw} onClick={() => setReopenOpen(true)}>Still broken? Reopen</Button>
        </div>
      </div>
      <Modal open={reopenOpen} onClose={() => setReopenOpen(false)} title="Reopen request"
        footer={<><Button variant="secondary" onClick={() => setReopenOpen(false)}>Cancel</Button><Button variant="amber" busy={busy} disabled={reason.trim().length < 3} onClick={reopen}>Reopen request</Button></>}>
        <Field label="What's still wrong?" hint="This goes to the technician and the facility manager. The SLA clock restarts."><Textarea value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <div className="mt-3"><ErrorNote>{error}</ErrorNote></div>
      </Modal>
    </Panel>
  );
}

function ManagerActions({ req, reload }) {
  const { busy, error, run } = useAction();
  const [assignOpen, setAssignOpen] = useState(false);
  const [status, setStatus] = useState(req.status);
  const [note, setNote] = useState('');
  const { data: cands, loading } = useApi(`/requests/${req.request_id}/candidates`, { enabled: assignOpen });
  const closed = ['Resolved', 'Closed'].includes(req.status);

  const assign = (id) => run(async () => { await api.put(`/requests/${req.request_id}/assign`, { technician_id: id }); setAssignOpen(false); reload(); }).catch(() => {});
  const auto = () => run(async () => { await api.post(`/requests/${req.request_id}/auto-assign`); reload(); }).catch(() => {});
  const override = () => run(async () => { await api.patch(`/requests/${req.request_id}/status`, { status, note: note || null }); setNote(''); reload(); }).catch(() => {});

  return (
    <Panel title="Manage">
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" icon={UserCog} disabled={closed} onClick={() => setAssignOpen(true)}>{req.technician ? 'Reassign' : 'Assign'}</Button>
          <Button variant="ghost" icon={Wand2} disabled={closed} busy={busy} onClick={auto}>Auto-assign</Button>
        </div>
        <div className="border-t border-line pt-4">
          <Field label="Override status">
            <div className="flex gap-2">
              <Select value={status} onChange={(e) => setStatus(e.target.value)}>{STATUSES.map((s) => <option key={s}>{s}</option>)}</Select>
              <Button variant="secondary" disabled={status === req.status} busy={busy} onClick={override}>Apply</Button>
            </div>
          </Field>
          {status !== req.status && <Input className="mt-2" placeholder="Note to the reporter (optional)" value={note} onChange={(e) => setNote(e.target.value)} />}
        </div>
        <ErrorNote>{error}</ErrorNote>
      </div>

      <Modal open={assignOpen} onClose={() => setAssignOpen(false)} title="Choose a technician" wide>
        {loading || !cands ? <Spinner /> : (
          <>
            <p className="mb-3 text-sm text-ink-soft">
              {cands.required_skill ? <>This asset needs <strong className="text-ink">{cands.required_skill}</strong>. Matching technicians are listed first.</> : 'No skill is mapped to this asset category.'}
            </p>
            <div className="overflow-x-auto">
              <table className="table-base">
                <thead><tr><th>Technician</th><th>Skills</th><th>Workload</th><th>Status</th><th /></tr></thead>
                <tbody>
                  {cands.technicians.map((t) => (
                    <tr key={t.technician_id}>
                      <td className="font-medium">{t.full_name}{t.skill_match && <span className="ml-2 rounded-sm bg-moss-light px-1.5 text-xs text-moss">skill match</span>}</td>
                      <td className="text-xs text-ink-soft">{t.skills.map((s) => s.skill_name).join(', ') || '—'}</td>
                      <td>{t.current_workload} open</td>
                      <td>{t.is_available ? <span className="text-moss">Available</span> : <span className="text-ink-faint">Unavailable</span>}</td>
                      <td className="text-right">
                        <Button size="sm" variant={t.technician_id === req.technician?.technician_id ? 'secondary' : 'primary'}
                          disabled={t.technician_id === req.technician?.technician_id} busy={busy} onClick={() => assign(t.technician_id)}>
                          {t.technician_id === req.technician?.technician_id ? 'Current' : 'Assign'}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Modal>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
export default function RequestDetail() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const { user } = useAuth();
  const { data: req, loading, error, reload } = useApi(`/requests/${id}`, { pollMs: 15000 });
  const [lightbox, setLightbox] = useState(null);

  if (loading && !req) return <Spinner />;
  if (error) return <ErrorNote>{error}</ErrorNote>;
  if (!req) return null;

  const isStaff = user.role === 'Manager' || user.role === 'Admin';
  const isAssignedTech = user.role === 'Technician' && user.technician_id === req.technician?.technician_id;
  const isOwner = req.reporter?.user_id === user.user_id;
  const before = req.photos.filter((p) => p.photo_type === 'Before');
  const after = req.photos.filter((p) => p.photo_type === 'After');
  const totals = req.repair_logs.reduce((a, l) => ({ cost: a.cost + (l.repair_cost || 0), hours: a.hours + (l.labour_hours || 0) }), { cost: 0, hours: 0 });
  const back = isStaff ? '/manager/requests' : user.role === 'Technician' ? '/tasks' : '/my-requests';

  return (
    <>
      <Link to={back} className="mb-3 inline-flex items-center gap-1 text-sm text-ink-soft hover:text-ink"><ArrowLeft className="h-4 w-4" /> Back</Link>
      {params.get('new') && (
        <div className="mb-4 rounded border border-moss/30 bg-moss-light px-4 py-3 text-sm text-moss" role="status">
          Request submitted. {req.technician ? `${req.technician.full_name} has been assigned.` : 'A manager will assign a technician shortly.'}
        </div>
      )}
      <PageHeader title={req.title}>
        <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
          <span className="text-ink-soft">#{req.request_id}</span>
          <StatusPill status={req.status} />
          <SeverityPill severity={req.severity} />
          {req.is_preventive && <span className="inline-flex items-center gap-1 text-xs font-medium text-blueprint"><CalendarClock className="h-3.5 w-3.5" />Preventive</span>}
          {req.reopen_count > 0 && <span className="text-xs text-signal-dark">Reopened {req.reopen_count}×</span>}
        </div>
      </PageHeader>

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <Panel title="Details">
            <p className="whitespace-pre-line text-sm leading-relaxed">{req.description || <span className="text-ink-soft">No description given.</span>}</p>
            {[['Before', before], ['After repair', after]].map(([label, list]) => list.length > 0 && (
              <div key={label} className="mt-5">
                <h3 className="mb-2 text-sm font-semibold">{label}</h3>
                <div className="flex flex-wrap gap-2">
                  {list.map((p) => (
                    <button key={p.photo_id} type="button" onClick={() => setLightbox(fileUrl(p.photo_url))} className="h-24 w-24 overflow-hidden rounded border border-line">
                      <img src={fileUrl(p.photo_url)} alt={`${label} photo`} className="h-full w-full object-cover" loading="lazy" />
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </Panel>

          {(req.repair_logs.length > 0 || isAssignedTech || isStaff) && (
            <Panel title="Repair log" note={req.repair_logs.length ? `${fmt.num(totals.hours, 2)} h labour · ${fmt.money(totals.cost)} total` : undefined}>
              {req.repair_logs.length === 0 ? <p className="text-sm text-ink-soft">No work logged yet.</p> : (
                <ul className="space-y-4">
                  {req.repair_logs.map((l) => (
                    <li key={l.log_id} className="border-l-2 border-blueprint pl-3">
                      <div className="text-xs text-ink-soft">{l.technician_name} · {fmt.dateTime(l.completed_at)}</div>
                      <p className="mt-1 text-sm">{l.work_notes}</p>
                      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-soft">
                        {l.parts_used && <span>Parts: {l.parts_used}</span>}
                        {l.labour_hours != null && <span>Labour: {l.labour_hours} h</span>}
                        {l.repair_cost != null && <span>Cost: {fmt.money(l.repair_cost)}</span>}
                        {l.downtime_hours != null && <span>Downtime: {fmt.hours(l.downtime_hours)}</span>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}

          {req.feedback && !isOwner && (
            <Panel title="Reporter feedback">
              <Stars value={req.feedback.rating} />
              {req.feedback.comment && <p className="mt-2 text-sm">“{req.feedback.comment}”</p>}
            </Panel>
          )}

          <Panel title="Timeline">
            <ol className="relative space-y-4 border-l border-line pl-5">
              {req.timeline.map((t, i) => (
                <li key={i} className="relative">
                  <span className={cx('absolute -left-[25px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white',
                    t.action.startsWith('sla.') ? 'bg-breach' : t.action === 'request.resolved' ? 'bg-moss' : 'bg-blueprint')} />
                  <div className="text-sm font-medium">{ACTION_LABEL[t.action] || t.action}</div>
                  {describe(t) && <div className="text-sm text-ink-soft">{describe(t)}</div>}
                  <div className="text-xs text-ink-faint">{fmt.dateTime(t.at)} · {t.by}</div>
                </li>
              ))}
            </ol>
          </Panel>
        </div>

        <aside className="space-y-6">
          {isAssignedTech && <TechnicianActions req={req} reload={() => reload(true)} />}
          {isOwner && !isStaff && <ReporterActions req={req} reload={() => reload(true)} />}
          {isStaff && <ManagerActions key={req.status} req={req} reload={() => reload(true)} />}

          <Panel title="SLA">
            <SlaBar sla={req.sla} />
            {req.sla_policy && (
              <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div><dt className="text-xs text-ink-soft">Respond within</dt><dd>{fmt.hours(req.sla_policy.response_hours)}</dd></div>
                <div><dt className="text-xs text-ink-soft">Resolve within</dt><dd>{fmt.hours(req.sla_policy.resolution_hours)}</dd></div>
                <div><dt className="text-xs text-ink-soft">Reported</dt><dd>{fmt.dateTime(req.reported_at)}</dd></div>
                <div><dt className="text-xs text-ink-soft">{req.resolved_at ? 'Resolved' : 'Accepted'}</dt><dd>{fmt.dateTime(req.resolved_at || req.accepted_at)}</dd></div>
              </dl>
            )}
            {isStaff && req.escalations?.length > 0 && (
              <div className="mt-4 border-t border-line pt-3">
                <div className="mb-1 flex items-center gap-1.5 text-sm font-medium text-breach"><ShieldAlert className="h-4 w-4" />Escalations</div>
                <ul className="space-y-1 text-xs text-ink-soft">
                  {[...new Map(req.escalations.map((e) => [e.level, e])).values()].map((e) => (
                    <li key={e.escalation_id}>{e.level} · {fmt.dateTime(e.escalated_at)}{e.is_acknowledged && ' · acknowledged'}</li>
                  ))}
                </ul>
              </div>
            )}
          </Panel>

          <Panel title="Asset">
            <div className="font-medium">{req.asset.asset_name}</div>
            <div className="mt-1 flex items-center gap-1 text-sm text-ink-soft"><MapPin className="h-3.5 w-3.5" />{req.asset.location?.label || 'No location'}</div>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-xs text-ink-soft">Category</dt><dd>{req.asset.category}</dd></div>
              <div><dt className="text-xs text-ink-soft">QR code</dt><dd className="truncate">{req.asset.qr_code}</dd></div>
              <div><dt className="text-xs text-ink-soft">Reported by</dt><dd>{req.reporter?.full_name}</dd></div>
              <div><dt className="text-xs text-ink-soft">Technician</dt><dd>{req.technician?.full_name || '—'}{req.technician?.phone && <a className="block text-xs text-blueprint" href={`tel:${req.technician.phone}`}>{req.technician.phone}</a>}</dd></div>
            </dl>
            {req.asset_history && (
              <div className="mt-4 border-t border-line pt-3">
                <div className="mb-2 text-sm font-medium">Repair history on this asset</div>
                {req.asset_history.length === 0 ? <p className="text-xs text-ink-soft">No earlier requests.</p> : (
                  <ul className="space-y-2">
                    {req.asset_history.map((h) => (
                      <li key={h.request_id} className="text-sm">
                        <Link to={`/requests/${h.request_id}`} className="hover:text-blueprint hover:underline">{h.title}</Link>
                        <div className="text-xs text-ink-soft">{fmt.date(h.reported_at)} · {h.status}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </Panel>
        </aside>
      </div>

      <Modal open={!!lightbox} onClose={() => setLightbox(null)} title="Photo" wide>
        {lightbox && <img src={lightbox} alt="Full size" className="mx-auto max-h-[70vh] rounded" />}
      </Modal>
    </>
  );
}
