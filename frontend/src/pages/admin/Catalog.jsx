import { useState } from 'react';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { Button, ErrorNote, Field, Input, Modal, PageHeader, Panel, Select, Spinner, Tabs } from '../../components/ui';
import api from '../../lib/api';
import { useAction, useApi } from '../../lib/hooks';

function IconBtn({ icon: Icon, label, onClick }) {
  return <button type="button" onClick={onClick} aria-label={label} title={label} className="rounded p-1.5 text-ink-soft hover:bg-paper hover:text-ink"><Icon className="h-4 w-4" /></button>;
}

export default function Catalog() {
  const [tab, setTab] = useState('locations');
  const locations = useApi('/locations');
  const skills = useApi('/skills');
  const categories = useApi('/categories');
  const [edit, setEdit] = useState(null); // { kind, ...values }
  const action = useAction();

  const endpoints = { location: '/locations', skill: '/skills', category: '/categories' };
  const idKey = { location: 'location_id', skill: 'skill_id', category: 'category_id' };
  const reloadAll = () => { locations.reload(true); skills.reload(true); categories.reload(true); };

  const save = () => action.run(async () => {
    const { kind, ...v } = edit;
    const body = kind === 'location' ? { building: v.building, floor: v.floor || null, room: v.room || null }
      : kind === 'skill' ? { skill_name: v.skill_name }
        : { name: v.name, skill_id: v.skill_id ? Number(v.skill_id) : null, description: v.description || null };
    const id = v[idKey[kind]];
    if (id) await api.put(`${endpoints[kind]}/${id}`, body); else await api.post(endpoints[kind], body);
    setEdit(null); reloadAll();
  }).catch(() => {});
  const remove = (kind, row, name) => {
    if (!window.confirm(`Delete ${name}?`)) return;
    action.run(async () => { await api.delete(`${endpoints[kind]}/${row[idKey[kind]]}`); reloadAll(); }).catch(() => {});
  };

  return (
    <>
      <PageHeader title="Locations & skills" subtitle="Buildings and rooms, asset categories, and the technician skills each category needs." />
      <ErrorNote>{action.error && !edit ? action.error : null}</ErrorNote>
      <Tabs value={tab} onChange={setTab} tabs={[
        { value: 'locations', label: 'Locations', count: locations.data?.length },
        { value: 'categories', label: 'Asset categories', count: categories.data?.length },
        { value: 'skills', label: 'Skill types', count: skills.data?.length },
      ]} />

      {tab === 'locations' && (
        <Panel title="Locations" actions={<Button size="sm" icon={Plus} onClick={() => setEdit({ kind: 'location', building: '', floor: '', room: '' })}>Add location</Button>} bodyClass="p-0">
          {!locations.data ? <Spinner /> : (
            <div className="overflow-x-auto"><table className="table-base">
              <thead><tr><th>Building</th><th>Floor</th><th>Room</th><th>Assets</th><th /></tr></thead>
              <tbody>{locations.data.map((l) => (
                <tr key={l.location_id}><td className="font-medium">{l.building}</td><td>{l.floor || '—'}</td><td>{l.room || '—'}</td><td>{l.asset_count}</td>
                  <td><div className="flex justify-end"><IconBtn icon={Pencil} label="Edit" onClick={() => setEdit({ kind: 'location', ...l, floor: l.floor || '', room: l.room || '' })} /><IconBtn icon={Trash2} label="Delete" onClick={() => remove('location', l, l.label)} /></div></td></tr>
              ))}</tbody>
            </table></div>
          )}
        </Panel>
      )}

      {tab === 'categories' && (
        <Panel title="Asset categories" note="The required skill is what the auto-assignment engine matches on."
          actions={<Button size="sm" icon={Plus} onClick={() => setEdit({ kind: 'category', name: '', skill_id: '', description: '' })}>Add category</Button>} bodyClass="p-0">
          {!categories.data ? <Spinner /> : (
            <div className="overflow-x-auto"><table className="table-base">
              <thead><tr><th>Category</th><th>Required skill</th><th>Assets</th><th /></tr></thead>
              <tbody>{categories.data.map((c) => (
                <tr key={c.category_id}><td><div className="font-medium">{c.name}</div>{c.description && <div className="text-xs text-ink-soft">{c.description}</div>}</td>
                  <td>{c.skill_name || <span className="text-breach">None, can't auto-assign</span>}</td><td>{c.asset_count}</td>
                  <td><div className="flex justify-end"><IconBtn icon={Pencil} label="Edit" onClick={() => setEdit({ kind: 'category', ...c, skill_id: c.skill_id || '', description: c.description || '' })} /><IconBtn icon={Trash2} label="Delete" onClick={() => remove('category', c, c.name)} /></div></td></tr>
              ))}</tbody>
            </table></div>
          )}
        </Panel>
      )}

      {tab === 'skills' && (
        <Panel title="Technician skill types" actions={<Button size="sm" icon={Plus} onClick={() => setEdit({ kind: 'skill', skill_name: '' })}>Add skill</Button>} bodyClass="p-0">
          {!skills.data ? <Spinner /> : (
            <div className="overflow-x-auto"><table className="table-base">
              <thead><tr><th>Skill</th><th>Technicians</th><th /></tr></thead>
              <tbody>{skills.data.map((s) => (
                <tr key={s.skill_id}><td className="font-medium">{s.skill_name}</td><td>{s.technician_count}</td>
                  <td><div className="flex justify-end"><IconBtn icon={Pencil} label="Rename" onClick={() => setEdit({ kind: 'skill', ...s })} /><IconBtn icon={Trash2} label="Delete" onClick={() => remove('skill', s, s.skill_name)} /></div></td></tr>
              ))}</tbody>
            </table></div>
          )}
        </Panel>
      )}

      <Modal open={!!edit} onClose={() => setEdit(null)} title={edit ? `${edit[idKey[edit.kind]] ? 'Edit' : 'Add'} ${edit.kind}` : ''}
        footer={<><Button variant="secondary" onClick={() => setEdit(null)}>Cancel</Button><Button busy={action.busy} onClick={save}>Save</Button></>}>
        {edit?.kind === 'location' && (
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Building" className="sm:col-span-3"><Input value={edit.building} onChange={(e) => setEdit({ ...edit, building: e.target.value })} /></Field>
            <Field label="Floor"><Input value={edit.floor} onChange={(e) => setEdit({ ...edit, floor: e.target.value })} /></Field>
            <Field label="Room" className="sm:col-span-2"><Input value={edit.room} onChange={(e) => setEdit({ ...edit, room: e.target.value })} /></Field>
          </div>
        )}
        {edit?.kind === 'skill' && <Field label="Skill name"><Input value={edit.skill_name} onChange={(e) => setEdit({ ...edit, skill_name: e.target.value })} /></Field>}
        {edit?.kind === 'category' && (
          <div className="space-y-3">
            <Field label="Category name"><Input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="Required skill"><Select value={edit.skill_id} onChange={(e) => setEdit({ ...edit, skill_id: e.target.value })}><option value="">None</option>{(skills.data || []).map((s) => <option key={s.skill_id} value={s.skill_id}>{s.skill_name}</option>)}</Select></Field>
            <Field label="Description"><Input value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></Field>
          </div>
        )}
        <div className="mt-3"><ErrorNote>{action.error}</ErrorNote></div>
      </Modal>
    </>
  );
}
