import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Cpu, RefreshCw } from 'lucide-react';
import { Button, ErrorNote, PageHeader, Panel, Spinner, Stat } from '../../components/ui';
import api from '../../lib/api';
import { fmt } from '../../lib/format';
import { useAction, useApi } from '../../lib/hooks';
import { C } from '../manager/Overview';

export default function ModelCenter() {
  const { data, loading, reload } = useApi('/predictions/model');
  const action = useAction();
  const train = () => action.run(async () => { await api.post('/predictions/train'); await api.post('/predictions/run'); reload(true); }).catch(() => {});
  const score = () => action.run(async () => { await api.post('/predictions/run'); reload(true); }).catch(() => {});
  if (loading || !data) return <Spinner />;

  const a = data.active;
  const m = a?.metrics;
  const labels = data.feature_labels;
  const importance = a ? Object.entries(a.feature_importance)
    .map(([k, v]) => ({ name: labels[k] || k.replace('cat_', 'Category: '), value: Number((v * 100).toFixed(1)) }))
    .sort((x, y) => y.value - x.value).slice(0, 10) : [];

  return (
    <>
      <PageHeader title="Prediction model" subtitle={`Predicts which assets will fail in the next ${data.horizon_days} days. Retrain after significant new maintenance history.`}
        actions={<>
          <Button variant="secondary" icon={Cpu} busy={action.busy} onClick={score}>Score assets</Button>
          <Button icon={RefreshCw} busy={action.busy} onClick={train}>Retrain model</Button>
        </>} />
      <ErrorNote>{action.error}</ErrorNote>
      {!a ? (
        <Panel><p className="text-sm">No trained model yet, so a simple rule-based score (<strong>heuristic-v1</strong>) is used. Training needs about 3 months of maintenance history with some failures in it.</p></Panel>
      ) : (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="ROC-AUC" value={m.roc_auc} sub="0.5 = guessing, 1 = perfect" tone={m.roc_auc >= 0.7 ? 'green' : 'amber'} />
            <Stat label="Precision" value={fmt.pct(m.precision * 100)} sub="flagged assets that did fail" />
            <Stat label="Recall" value={fmt.pct(m.recall * 100)} sub="failures that were flagged" />
            <Stat label="Accuracy" value={fmt.pct(m.accuracy * 100)} />
            <Stat label="Training samples" value={fmt.num(a.n_samples)} sub={`${fmt.pct(a.positive_rate * 100)} had a failure`} />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Panel title="What drives the prediction" note="Feature importance of the active model">
              <div style={{ height: Math.max(240, importance.length * 30) }}>
                <ResponsiveContainer>
                  <BarChart data={importance} layout="vertical" margin={{ top: 0, right: 20, left: 10, bottom: 0 }}>
                    <CartesianGrid stroke={C.grid} horizontal={false} />
                    <XAxis type="number" unit="%" tick={{ fontSize: 11, fill: '#5D6B75' }} tickLine={false} axisLine={false} />
                    <YAxis type="category" dataKey="name" width={160} tick={{ fontSize: 11, fill: '#5D6B75' }} tickLine={false} axisLine={false} />
                    <Tooltip formatter={(v) => [`${v}%`, 'Importance']} />
                    <Bar dataKey="value" fill={C.blue} radius={[0, 2, 2, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title="Active model">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div><dt className="text-xs text-ink-soft">Version</dt><dd className="font-medium">{a.version}</dd></div>
                <div><dt className="text-xs text-ink-soft">Algorithm</dt><dd>{a.algorithm === 'xgboost' ? 'XGBoost' : 'Random forest'}</dd></div>
                <div><dt className="text-xs text-ink-soft">Trained</dt><dd>{fmt.dateTime(a.trained_at)}</dd></div>
                <div><dt className="text-xs text-ink-soft">Validation</dt><dd>{m.split}</dd></div>
                <div><dt className="text-xs text-ink-soft">Train / test rows</dt><dd>{m.train_samples} / {m.test_samples}</dd></div>
                <div><dt className="text-xs text-ink-soft">XGBoost installed</dt><dd>{data.xgboost_available ? 'Yes' : 'No (using random forest)'}</dd></div>
              </dl>
              <p className="mt-4 text-xs text-ink-soft">Training takes snapshots of every asset every 14 days and asks whether it failed in the following {data.horizon_days} days, so the model only ever learns from information that existed at the time.</p>
            </Panel>
          </div>
        </>
      )}
      <Panel title="Training history" className="mt-6" bodyClass="p-0">
        <div className="overflow-x-auto">
          <table className="table-base">
            <thead><tr><th>Version</th><th>Trained</th><th>Samples</th><th>ROC-AUC</th><th>Precision</th><th>Recall</th><th>F1</th><th /></tr></thead>
            <tbody>
              {data.runs.map((r) => (
                <tr key={r.run_id}>
                  <td className="font-medium">{r.model_version}</td><td>{fmt.dateTime(r.trained_at)}</td><td>{fmt.num(r.n_samples)}</td>
                  <td>{r.metrics?.roc_auc}</td><td>{r.metrics?.precision}</td><td>{r.metrics?.recall}</td><td>{r.metrics?.f1}</td>
                  <td>{r.is_active && <span className="rounded-sm bg-moss-light px-1.5 text-xs text-moss">active</span>}</td>
                </tr>
              ))}
              {data.runs.length === 0 && <tr><td colSpan={8} className="text-center text-ink-soft">No training runs yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
