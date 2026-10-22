import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, ErrorNote, Modal, PageHeader, Panel, Spinner, cx } from '../../components/ui';
import api from '../../lib/api';
import { useAction, useApi } from '../../lib/hooks';

export default function Technicians() {
  const { data, loading, error, reload } = useApi('/technicians', { pollMs: 60000 });
  const { data: skills } = useApi('/skills');
  const [edit, setEdit] = useState(null);
  const action = useAction();

  const update = (t, body) => action.run(async () => { await api.put(`/technicians/${t.technician_id}`, body); setEdit(null); reload(true); }).catch(() => {});

  return (
    <>
      <PageHeader title="Technicians" subtitle="Availability and skills decide who the assignment engine picks. Lowest workload wins among matches." />
      <ErrorNote>{error || action.error}</ErrorNote>
      <Panel bodyClass="p-0">
        {loading ? <Spinner /> : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead><tr><th>Name</th><th>Skills</th><th>Open jobs</th><th>Resolved, 30 days</th><th>Rating</th><th>Available</th><th /></tr></thead>
              <tbody>
                {(data || []).map((t) => (
                  <tr key={t.technician_id} className={cx(!t.is_active && 'opacity-50')}>
                    <td><div className="font-medium">{t.full_name}</div><div className="text-xs text-ink-soft">{t.phone || t.email}</div></td>
                    <td className="max-w-xs text-xs">{t.skills.map((s) => s.skill_name).join(', ') || <span className="text-breach">No skills</span>}</td>
                    <td>
                      <Link to={`/manager/requests?technician_id=${t.technician_id}&status=Assigned,In Progress,On Hold`} className="hover:underline">{t.current_workload}</Link>
                      <div className="mt-1 h-1 w-16 rounded bg-paper"><div className={cx('h-full rounded', t.current_workload > 6 ? 'bg-breach' : t.current_workload > 3 ? 'bg-signal' : 'bg-blueprint')} style={{ width: `${Math.min(100, t.current_workload * 12)}%` }} /></div>
                    </td>
                    <td>{t.resolved_30d}</td>
                    <td>{t.avg_rating ? `${t.avg_rating} ★` : '—'}</td>
                    <td>
                      <button type="button" role="switch" aria-checked={t.is_available} aria-label={`${t.full_name} available`} onClick={() => update(t, { is_available: !t.is_available })}
                        className={cx('relative h-6 w-10 rounded-full', t.is_available ? 'bg-moss' : 'bg-ink-faint')}>
                        <span className={cx('absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all', t.is_available ? 'left-[18px]' : 'left-0.5')} />
                      </button>
                    </td>
                    <td className="text-right"><Button size="sm" variant="ghost" onClick={() => setEdit({ ...t, skill_ids: t.skills.map((s) => s.skill_id) })}>Edit skills</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <Modal open={!!edit} onClose={() => setEdit(null)} title={`Skills: ${edit?.full_name}`}
        footer={<><Button variant="secondary" onClick={() => setEdit(null)}>Cancel</Button><Button busy={action.busy} onClick={() => update(edit, { skill_ids: edit.skill_ids })}>Save skills</Button></>}>
        <div className="flex flex-wrap gap-2">
          {(skills || []).map((s) => {
            const on = edit?.skill_ids.includes(s.skill_id);
            return (
              <button key={s.skill_id} type="button" aria-pressed={on}
                onClick={() => setEdit({ ...edit, skill_ids: on ? edit.skill_ids.filter((x) => x !== s.skill_id) : [...edit.skill_ids, s.skill_id] })}
                className={cx('rounded border px-3 py-1.5 text-sm', on ? 'border-blueprint bg-blueprint text-white' : 'border-line bg-white')}>{s.skill_name}</button>
            );
          })}
        </div>
      </Modal>
    </>
  );
}
