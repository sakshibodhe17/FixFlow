import { useEffect, useState } from 'react';
import { Button, ErrorNote, Input, PageHeader, Panel, Spinner, cx } from '../../components/ui';
import api from '../../lib/api';
import { useAction, useApi } from '../../lib/hooks';

const GROUPS = [
  { title: 'Notifications', keys: ['email_notifications', 'notify_reporter_on_status'] },
  { title: 'SLA escalation', keys: ['sla_warning_pct', 'escalate_to_admins'] },
  { title: 'Failure prediction', keys: ['risk_medium_threshold', 'risk_high_threshold', 'nightly_predictions', 'auto_retrain_weekly'] },
];

export default function Settings() {
  const { data, loading, setData } = useApi('/admin/settings');
  const [values, setValues] = useState({});
  const [saved, setSaved] = useState(false);
  const action = useAction();

  useEffect(() => { if (data) setValues(Object.fromEntries(data.settings.map((s) => [s.key, s.value]))); }, [data]);
  if (loading || !data) return <Spinner />;
  const meta = Object.fromEntries(data.settings.map((s) => [s.key, s]));

  const save = () => action.run(async () => {
    const res = await api.put('/admin/settings', { values });
    setData({ ...data, settings: res.data.settings });
    setSaved(true); setTimeout(() => setSaved(false), 2500);
  }).catch(() => {});

  return (
    <>
      <PageHeader title="Notifications & SLA settings" subtitle="System-wide behaviour for alerts, escalations and risk scoring."
        actions={<Button busy={action.busy} onClick={save}>Save settings</Button>} />
      {saved && <p className="mb-4 rounded border border-moss/30 bg-moss-light px-3 py-2 text-sm text-moss" role="status">Settings saved.</p>}
      <ErrorNote>{action.error}</ErrorNote>
      <div className="grid gap-6 lg:grid-cols-2">
        {GROUPS.map((g) => (
          <Panel key={g.title} title={g.title}>
            <ul className="divide-y divide-line">
              {g.keys.map((k) => (
                <li key={k} className="flex items-center justify-between gap-4 py-3">
                  <span className="text-sm">{meta[k]?.description}</span>
                  {meta[k]?.type === 'bool' ? (
                    <button type="button" role="switch" aria-checked={!!values[k]} aria-label={meta[k].description} onClick={() => setValues({ ...values, [k]: !values[k] })}
                      className={cx('relative h-6 w-10 shrink-0 rounded-full', values[k] ? 'bg-moss' : 'bg-ink-faint')}>
                      <span className={cx('absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all', values[k] ? 'left-[18px]' : 'left-0.5')} />
                    </button>
                  ) : (
                    <Input type="number" className="w-24 shrink-0" step={meta[k]?.type === 'float' ? '0.05' : '1'} min="0" max={meta[k]?.type === 'float' ? '1' : '100'}
                      value={values[k] ?? ''} onChange={(e) => setValues({ ...values, [k]: e.target.value })} aria-label={meta[k]?.description} />
                  )}
                </li>
              ))}
            </ul>
          </Panel>
        ))}
        <Panel title="Email delivery">
          <p className="text-sm">{data.smtp_enabled ? <>Emails are sent through <strong>{data.smtp_host}</strong>.</> : 'SMTP is off. Emails are written to the server log instead of being sent.'}</p>
          <p className="mt-2 text-xs text-ink-soft">SMTP credentials live in the backend <code>.env</code> file (SMTP_ENABLED, SMTP_HOST, SMTP_USER, SMTP_PASSWORD). Deadlines are checked every {data.sla_check_interval_minutes} minutes.</p>
        </Panel>
      </div>
    </>
  );
}
