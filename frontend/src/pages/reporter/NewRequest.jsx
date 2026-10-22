import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ImagePlus, MapPin, QrCode, X } from 'lucide-react';
import QrScannerModal from '../../components/QrScanner';
import { Button, ErrorNote, Field, Input, PageHeader, Panel, Select, Textarea, cx } from '../../components/ui';
import api, { errorMessage } from '../../lib/api';
import { fmt, SEVERITIES } from '../../lib/format';
import { useApi } from '../../lib/hooks';

const SEVERITY_HELP = {
  Low: 'Cosmetic or minor; nothing is blocked.',
  Medium: 'Works partly, or is inconvenient.',
  High: 'Not working and people are affected.',
  Critical: 'Safety risk or a whole space is unusable.',
};

export default function NewRequest() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { data: locations } = useApi('/locations');
  const { data: assets } = useApi('/assets');
  const { data: policies } = useApi('/sla/policies');

  const [scanOpen, setScanOpen] = useState(false);
  const [scanned, setScanned] = useState(null);
  const [building, setBuilding] = useState('');
  const [locationId, setLocationId] = useState('');
  const [assetId, setAssetId] = useState('');
  const [form, setForm] = useState({ title: '', description: '', severity: 'Medium' });
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const lookupQr = async (code) => {
    setError(null);
    try {
      const { data } = await api.get(`/assets/by-qr/${encodeURIComponent(code)}`);
      setScanned(data);
      setAssetId(String(data.asset_id));
      setLocationId(data.location_id ? String(data.location_id) : '');
      setBuilding(data.location?.building || '');
    } catch (e) {
      setScanned(null);
      setError(errorMessage(e));
    }
  };

  useEffect(() => {
    const qr = params.get('qr');
    if (qr) lookupQr(qr);
  }, [params]); // eslint-disable-line react-hooks/exhaustive-deps

  const buildings = useMemo(() => [...new Set((locations || []).map((l) => l.building))], [locations]);
  const rooms = (locations || []).filter((l) => l.building === building);
  const roomAssets = (assets || []).filter((a) => String(a.location_id) === locationId);
  const selectedAsset = (assets || []).find((a) => String(a.asset_id) === assetId) || scanned;

  const addPhotos = (files) => {
    const next = [...photos, ...Array.from(files).filter((f) => f.type.startsWith('image/'))].slice(0, 6);
    setPhotos(next);
  };
  const previews = useMemo(() => photos.map((f) => URL.createObjectURL(f)), [photos]);
  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews]);

  const submit = async (e) => {
    e.preventDefault();
    if (!assetId) { setError('Choose the asset that has the problem, or scan its QR code.'); return; }
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.post('/requests', { asset_id: Number(assetId), ...form });
      if (photos.length) {
        const fd = new FormData();
        photos.forEach((p) => fd.append('files', p));
        fd.append('photo_type', 'Before');
        await api.post(`/requests/${data.request_id}/photos`, fd);
      }
      navigate(`/requests/${data.request_id}?new=1`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };

  const policyFor = (sev) => (policies || []).find((p) => p.severity === sev);

  return (
    <>
      <PageHeader title="Report a problem" subtitle="Tell us what's broken and where. We'll assign a technician straight away." />
      <form onSubmit={submit} className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Panel title="Which asset?" note="Scanning the sticker is fastest. Otherwise pick the location.">
            <div className="flex flex-col gap-4">
              <Button variant="secondary" icon={QrCode} onClick={() => setScanOpen(true)} className="self-start">Scan QR code</Button>
              {scanned && (
                <div className="flex items-start justify-between gap-3 rounded border border-blueprint/30 bg-blueprint-light px-3 py-2.5">
                  <div>
                    <div className="font-medium">{scanned.asset_name}</div>
                    <div className="text-xs text-ink-soft">{scanned.category} · {scanned.location?.label || 'No location'} · {scanned.qr_code}</div>
                  </div>
                  <button type="button" className="text-ink-soft hover:text-ink" onClick={() => { setScanned(null); setAssetId(''); }} aria-label="Clear scanned asset"><X className="h-4 w-4" /></button>
                </div>
              )}
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Building">
                  <Select value={building} onChange={(e) => { setBuilding(e.target.value); setLocationId(''); setAssetId(''); setScanned(null); }}>
                    <option value="">Choose…</option>
                    {buildings.map((b) => <option key={b}>{b}</option>)}
                  </Select>
                </Field>
                <Field label="Floor / room">
                  <Select value={locationId} disabled={!building} onChange={(e) => { setLocationId(e.target.value); setAssetId(''); setScanned(null); }}>
                    <option value="">Choose…</option>
                    {rooms.map((l) => <option key={l.location_id} value={l.location_id}>{[l.floor && `Floor ${l.floor}`, l.room].filter(Boolean).join(' · ')}</option>)}
                  </Select>
                </Field>
                <Field label="Asset">
                  <Select value={assetId} disabled={!locationId && !scanned} onChange={(e) => setAssetId(e.target.value)} required>
                    <option value="">Choose…</option>
                    {scanned && !roomAssets.some((a) => a.asset_id === scanned.asset_id) && <option value={scanned.asset_id}>{scanned.asset_name}</option>}
                    {roomAssets.map((a) => <option key={a.asset_id} value={a.asset_id}>{a.asset_name}</option>)}
                  </Select>
                </Field>
              </div>
              {locationId && roomAssets.length === 0 && !scanned && (
                <p className="text-sm text-ink-soft">No registered assets in this room. Ask your facility manager to add it, or pick a nearby asset and describe the problem.</p>
              )}
            </div>
          </Panel>

          <Panel title="What's wrong?">
            <div className="space-y-4">
              <Field label="Short title" hint="e.g. “AC leaking water onto desks”">
                <Input required minLength={3} maxLength={200} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              </Field>
              <Field label="Details" hint="What happened, since when, and anything the technician should know.">
                <Textarea maxLength={5000} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </Field>
              <fieldset>
                <legend className="mb-2 text-sm font-medium">How urgent is it?</legend>
                <div className="grid gap-2 sm:grid-cols-2">
                  {SEVERITIES.map((s) => {
                    const p = policyFor(s);
                    const active = form.severity === s;
                    return (
                      <label key={s} className={cx('cursor-pointer rounded border px-3 py-2.5 transition-colors',
                        active ? (s === 'Critical' ? 'border-breach bg-breach-light' : 'border-blueprint bg-blueprint-light') : 'border-line bg-white hover:border-ink-faint')}>
                        <input type="radio" name="severity" value={s} checked={active} onChange={() => setForm({ ...form, severity: s })} className="sr-only" />
                        <span className="flex items-baseline justify-between gap-2">
                          <span className="font-semibold">{s}</span>
                          {p && <span className="text-xs text-ink-soft">fixed within {fmt.hours(p.resolution_hours)}</span>}
                        </span>
                        <span className="mt-0.5 block text-xs text-ink-soft">{SEVERITY_HELP[s]}</span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>
            </div>
          </Panel>

          <Panel title="Photos" note="Optional, up to 6. A clear photo saves the technician a trip.">
            <div className="flex flex-wrap gap-3">
              {previews.map((u, i) => (
                <div key={u} className="relative h-24 w-24 overflow-hidden rounded border border-line">
                  <img src={u} alt={`Photo ${i + 1}`} className="h-full w-full object-cover" />
                  <button type="button" onClick={() => setPhotos(photos.filter((_, j) => j !== i))} className="absolute right-1 top-1 rounded-full bg-ink/70 p-0.5 text-white" aria-label="Remove photo"><X className="h-3.5 w-3.5" /></button>
                </div>
              ))}
              {photos.length < 6 && (
                <label className="flex h-24 w-24 cursor-pointer flex-col items-center justify-center gap-1 rounded border border-dashed border-ink-faint text-xs text-ink-soft hover:border-blueprint hover:text-blueprint">
                  <ImagePlus className="h-5 w-5" /> Add photo
                  <input type="file" accept="image/*" multiple className="sr-only" onChange={(e) => { addPhotos(e.target.files); e.target.value = ''; }} />
                </label>
              )}
            </div>
          </Panel>
        </div>

        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <Panel title="Summary">
            <dl className="space-y-3 text-sm">
              <div><dt className="text-xs text-ink-soft">Asset</dt><dd className="font-medium">{selectedAsset?.asset_name || 'Not chosen yet'}</dd></div>
              <div><dt className="text-xs text-ink-soft">Location</dt><dd className="flex items-center gap-1"><MapPin className="h-3.5 w-3.5 text-ink-soft" />{selectedAsset?.location?.label || '—'}</dd></div>
              <div><dt className="text-xs text-ink-soft">Severity</dt><dd>{form.severity}{policyFor(form.severity) && `, resolution due within ${fmt.hours(policyFor(form.severity).resolution_hours)}`}</dd></div>
            </dl>
            <div className="mt-4 space-y-3">
              <ErrorNote>{error}</ErrorNote>
              <Button type="submit" busy={busy} className="w-full" size="lg">Submit request</Button>
            </div>
          </Panel>
        </aside>
      </form>
      <QrScannerModal open={scanOpen} onClose={() => setScanOpen(false)} onScan={lookupQr} assets={assets} />
    </>
  );
}
