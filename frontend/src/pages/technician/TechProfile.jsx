import { useEffect, useState } from 'react';
import { Button, ErrorNote, PageHeader, Panel, Spinner, Stat, cx } from '../../components/ui';
import api from '../../lib/api';
import { useAction, useApi } from '../../lib/hooks';

export default function TechProfile() {
  const { data: me, loading, setData } = useApi('/technicians/me');
  const { data: skills } = useApi('/skills');
  const [selected, setSelected] = useState([]);
  const [saved, setSaved] = useState(false);
  const { busy, error, run } = useAction();

  useEffect(() => { if (me) setSelected(me.skills.map((s) => s.skill_id)); }, [me]);
  if (loading || !me) return <Spinner />;

  const save = (body) => run(async () => {
    const { data } = await api.put('/technicians/me', body);
    setData(data);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  }).catch(() => {});
  const toggle = (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const dirty = JSON.stringify([...selected].sort()) !== JSON.stringify(me.skills.map((s) => s.skill_id).sort());

  return (
    <>
      <PageHeader title="Skills & availability" subtitle="New jobs are matched to your skills and only sent while you're available." />
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Open jobs" value={me.current_workload} />
        <Stat label="Resolved, last 30 days" value={me.resolved_30d} tone="green" />
        <Stat label="Labour hours, 30 days" value={me.labour_hours_30d} />
        <Stat label="Average rating" value={me.avg_rating ?? '—'} tone="amber" />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Availability">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="font-medium">{me.is_available ? 'Available for new jobs' : 'Not taking new jobs'}</div>
              <p className="text-sm text-ink-soft">{me.is_available ? 'The assignment engine can send you work.' : 'Your current jobs stay with you.'}</p>
            </div>
            <button type="button" role="switch" aria-checked={me.is_available} aria-label="Available for new jobs" disabled={busy}
              onClick={() => save({ is_available: !me.is_available })}
              className={cx('relative h-7 w-12 shrink-0 rounded-full transition-colors', me.is_available ? 'bg-moss' : 'bg-ink-faint')}>
              <span className={cx('absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition-all', me.is_available ? 'left-[22px]' : 'left-0.5')} />
            </button>
          </div>
        </Panel>
        <Panel title="Skills" note="Pick everything you're qualified to repair.">
          <div className="flex flex-wrap gap-2">
            {(skills || []).map((s) => (
              <button key={s.skill_id} type="button" onClick={() => toggle(s.skill_id)} aria-pressed={selected.includes(s.skill_id)}
                className={cx('rounded border px-3 py-1.5 text-sm', selected.includes(s.skill_id) ? 'border-blueprint bg-blueprint text-white' : 'border-line bg-white hover:border-ink-faint')}>
                {s.skill_name}
              </button>
            ))}
          </div>
          <div className="mt-4 flex items-center gap-3">
            <Button disabled={!dirty} busy={busy} onClick={() => save({ skill_ids: selected })}>Save skills</Button>
            {saved && <span className="text-sm text-moss" role="status">Saved</span>}
          </div>
          <div className="mt-3"><ErrorNote>{error}</ErrorNote></div>
        </Panel>
      </div>
    </>
  );
}
