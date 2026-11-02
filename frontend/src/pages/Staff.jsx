import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { Badge, Field, Modal, useToast } from '../ui';

const ROLES = [['admin', 'Administrator'], ['teacher', 'Teacher'], ['lab_assistant', 'Lab assistant']];
const label = (r) => (ROLES.find(([k]) => k === r) || [])[1] || r;

export default function Staff() {
  const toast = useToast();
  const [rows, setRows] = useState([]);
  const [labs, setLabs] = useState([]);
  const [editing, setEditing] = useState(null);
  const load = useCallback(() => api.get('/staff').then(setRows).catch((e) => toast(e.message, 'err')), [toast]);
  useEffect(() => { load(); api.get('/labs').then(setLabs).catch(() => {}); }, [load]);

  return (
    <>
      <div className="head"><h1>Staff</h1><button className="btn" onClick={() => setEditing('new')}>Add staff member</button></div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Laboratories</th><th>Email</th><th>Status</th><th /></tr></thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id}>
                <td>{u.full_name}</td><td>{u.username}</td><td>{label(u.role)}{u.employee_id ? ` · ${u.employee_id}` : ''}</td><td>{u.role === 'admin' ? 'All' : (u.lab_ids.map((id) => (labs.find((l) => l.id === id) || {}).name).filter(Boolean).join(', ') || '–')}</td><td>{u.email || '–'}</td>
                <td>{u.is_active ? <Badge kind="green">Active</Badge> : <Badge>Disabled</Badge>}</td>
                <td><button className="btn small ghost" onClick={() => setEditing(u)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && <StaffForm labs={labs} user={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
    </>
  );
}

function StaffForm({ user, labs, onClose, onSaved }) {
  const toast = useToast();
  const isNew = !user;
  const [f, setF] = useState(user ? { ...user, password: '' } : { username: '', full_name: '', email: '', employee_id: '', role: 'teacher', password: '', lab_ids: [] });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const save = async (e) => {
    e.preventDefault();
    try {
      if (isNew) {
        await api.post('/staff', { ...f, employee_id: f.employee_id || null });
      } else {
        const body = { full_name: f.full_name, email: f.email, employee_id: f.employee_id || '', role: f.role, is_active: f.is_active, lab_ids: f.lab_ids };
        if (f.password) body.password = f.password;
        await api.patch('/staff/' + user.id, body);
      }
      toast('Staff member saved');
      onSaved();
    } catch (err) { toast(err.message, 'err'); }
  };

  return (
    <Modal title={isNew ? 'Add staff member' : `Edit ${user.full_name}`} onClose={onClose}>
      <form className="form" onSubmit={save}>
        <div className="grid2">
          <Field label="Full name"><input value={f.full_name} onChange={set('full_name')} required /></Field>
          <Field label="Username"><input value={f.username} onChange={set('username')} required minLength={3} disabled={!isNew} /></Field>
          <Field label="Role"><select value={f.role} onChange={set('role')}>{ROLES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Employee ID" hint={f.role === 'teacher' ? 'Required for teachers' : ''}><input value={f.employee_id || ''} onChange={set('employee_id')} required={f.role === 'teacher'} /></Field>
        </div>
        <Field label="Email"><input type="email" value={f.email} onChange={set('email')} /></Field>
        {f.role !== 'admin' && (
          <fieldset className="labs-pick">
            <legend>Laboratories this person can work in</legend>
            {labs.filter((l) => l.is_active).map((l) => (
              <label key={l.id} className="check"><input type="checkbox" checked={(f.lab_ids || []).includes(l.id)}
                onChange={(e) => setF({ ...f, lab_ids: e.target.checked ? [...(f.lab_ids || []), l.id] : (f.lab_ids || []).filter((x) => x !== l.id) })} /> {l.name}</label>
            ))}
          </fieldset>
        )}
        <Field label={isNew ? 'Temporary password' : 'Reset password (optional)'} hint="At least 8 characters. They must change it at first sign-in.">
          <input type="password" value={f.password} onChange={set('password')} minLength={8} required={isNew} autoComplete="new-password" />
        </Field>
        {!isNew && <label className="check"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> Account active</label>}
        <div className="actions"><button type="button" className="btn ghost" onClick={onClose}>Cancel</button><button className="btn">Save</button></div>
      </form>
    </Modal>
  );
}
