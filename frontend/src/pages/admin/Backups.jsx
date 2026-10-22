import { DatabaseBackup, Download, RotateCcw, Trash2 } from 'lucide-react';
import { Button, Empty, ErrorNote, PageHeader, Panel, Spinner } from '../../components/ui';
import api, { download } from '../../lib/api';
import { fmt } from '../../lib/format';
import { useAction, useApi } from '../../lib/hooks';

const size = (b) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`);

export default function Backups() {
  const { data, loading, reload } = useApi('/admin/backups');
  const action = useAction();

  const create = () => action.run(async () => { await api.post('/admin/backups'); reload(true); }).catch(() => {});
  const restore = (f) => {
    if (!window.confirm(`Restore ${f.file}? This replaces ALL current data with the backup. Make a fresh backup first if unsure.`)) return;
    action.run(async () => { await api.post(`/admin/backups/${f.file}/restore`); window.alert('Restore complete. You may need to sign in again.'); window.location.reload(); }).catch(() => {});
  };
  const remove = (f) => window.confirm(`Delete ${f.file}?`) && action.run(async () => { await api.delete(`/admin/backups/${f.file}`); reload(true); }).catch(() => {});

  return (
    <>
      <PageHeader title="Backup & restore" subtitle="Backups use pg_dump when it's installed on the server, otherwise a portable JSON export of every table."
        actions={<Button icon={DatabaseBackup} busy={action.busy} onClick={create}>Back up now</Button>} />
      <ErrorNote>{action.error}</ErrorNote>
      <Panel bodyClass="p-0">
        {loading ? <Spinner /> : !data?.length ? <div className="p-4"><Empty title="No backups yet.">Create one before making big changes, and download copies to keep off the server.</Empty></div> : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead><tr><th>File</th><th>Type</th><th>Size</th><th>Created</th><th className="text-right">Actions</th></tr></thead>
              <tbody>{data.map((f) => (
                <tr key={f.file}>
                  <td className="font-medium">{f.file}</td><td>{f.file.endsWith('.sql') ? 'SQL dump' : 'JSON export'}</td><td>{size(f.size_bytes)}</td><td>{fmt.dateTime(f.created_at)}</td>
                  <td><div className="flex justify-end gap-2">
                    <Button size="sm" variant="secondary" icon={Download} onClick={() => action.run(() => download(`/admin/backups/${f.file}`, {}, f.file)).catch(() => {})}>Download</Button>
                    <Button size="sm" variant="amber" icon={RotateCcw} busy={action.busy} onClick={() => restore(f)}>Restore</Button>
                    <button type="button" className="rounded p-1.5 text-ink-soft hover:bg-paper" aria-label={`Delete ${f.file}`} onClick={() => remove(f)}><Trash2 className="h-4 w-4" /></button>
                  </div></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
