import { useEffect, useId, useRef, useState } from 'react';
import { Html5Qrcode } from 'html5-qrcode';
import { Camera, ImageUp, Keyboard } from 'lucide-react';
import { Button, ErrorNote, Field, Input, Modal, Select, Tabs } from './ui';

/** Extract the asset code from either a bare code ("FF-…") or the scanned URL (".../report?qr=FF-…"). */
export function parseQr(text) {
  const t = (text || '').trim();
  const m = /[?&]qr=([^&\s]+)/.exec(t);
  return m ? decodeURIComponent(m[1]) : t;
}

function CameraScan({ onScan }) {
  const id = `qr-${useId().replace(/:/g, '')}`;
  const [error, setError] = useState(null);
  const done = useRef(false);
  const callback = useRef(onScan);
  callback.current = onScan;

  useEffect(() => {
    const scanner = new Html5Qrcode(id, { verbose: false });
    const started = scanner.start(
      { facingMode: 'environment' },
      { fps: 10, qrbox: { width: 220, height: 220 } },
      (text) => {
        if (done.current) return;
        done.current = true;
        scanner.stop().catch(() => {}).finally(() => callback.current(parseQr(text)));
      },
      () => {},
    ).catch(() => setError('Camera unavailable. Allow camera access, or upload a photo of the QR sticker instead.'));
    return () => {
      started.then(() => (scanner.isScanning ? scanner.stop() : null)).catch(() => {}).finally(() => {
        try { scanner.clear(); } catch { /* already cleared */ }
      });
    };
  }, [id]);

  return (
    <div>
      <div id={id} className="mx-auto aspect-square w-full max-w-xs overflow-hidden rounded bg-ink" />
      <p className="mt-2 text-center text-xs text-ink-soft">Point the camera at the FixFlow sticker on the asset.</p>
      <div className="mt-3"><ErrorNote>{error}</ErrorNote></div>
    </div>
  );
}

function FileScan({ onScan }) {
  const [error, setError] = useState(null);
  const id = `qrf-${useId().replace(/:/g, '')}`;
  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    const scanner = new Html5Qrcode(id, { verbose: false });
    try {
      onScan(parseQr(await scanner.scanFile(file, false)));
    } catch {
      setError("Couldn't find a QR code in that photo. Try a closer, sharper shot.");
    } finally {
      try { scanner.clear(); } catch { /* noop */ }
    }
  };
  return (
    <div className="space-y-3">
      <div id={id} className="hidden" />
      <Field label="Photo of the QR sticker"><Input type="file" accept="image/*" capture="environment" onChange={onFile} /></Field>
      <ErrorNote>{error}</ErrorNote>
    </div>
  );
}

function ManualEntry({ onScan, assets }) {
  const [code, setCode] = useState('');
  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); if (code.trim()) onScan(parseQr(code)); }} className="flex gap-2">
        <Input placeholder="FF-XXXXXXXXXX" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} aria-label="Asset code" />
        <Button type="submit">Look up</Button>
      </form>
      {assets?.length > 0 && (
        <Field label="Simulate a scan" hint="For testing without a printed sticker: pick an asset to scan its code.">
          <Select defaultValue="" onChange={(e) => e.target.value && onScan(e.target.value)}>
            <option value="">Choose an asset…</option>
            {assets.filter((a) => a.qr_code).slice(0, 200).map((a) => (
              <option key={a.asset_id} value={a.qr_code}>{a.asset_name} ({a.qr_code})</option>
            ))}
          </Select>
        </Field>
      )}
    </div>
  );
}

export default function QrScannerModal({ open, onClose, onScan, assets }) {
  const [mode, setMode] = useState('camera');
  const handle = (code) => { onScan(code); onClose(); };
  return (
    <Modal open={open} onClose={onClose} title="Scan asset QR code">
      <Tabs value={mode} onChange={setMode} tabs={[
        { value: 'camera', label: <span className="inline-flex items-center gap-1.5"><Camera className="h-4 w-4" />Camera</span> },
        { value: 'file', label: <span className="inline-flex items-center gap-1.5"><ImageUp className="h-4 w-4" />Photo</span> },
        { value: 'manual', label: <span className="inline-flex items-center gap-1.5"><Keyboard className="h-4 w-4" />Type code</span> },
      ]} />
      {open && mode === 'camera' && <CameraScan onScan={handle} />}
      {mode === 'file' && <FileScan onScan={handle} />}
      {mode === 'manual' && <ManualEntry onScan={handle} assets={assets} />}
    </Modal>
  );
}
