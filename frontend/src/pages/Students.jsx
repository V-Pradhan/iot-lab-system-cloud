import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import ScanPanel from '../components/ScanPanel';
import { Badge, Empty, Field, Modal, useToast } from '../ui';

const BLANK = { name: '', university_uid: '', class_section: '', course: '', department: '', mobile: '', email: '', rfid_uid: '' };

export default function Students() {
  const toast = useToast();
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState('');
  const [editing, setEditing] = useState(null); // null | 'new' | student

  const load = useCallback(() => {
    api.get('/students?q=' + encodeURIComponent(q)).then(setRows).catch((e) => toast(e.message, 'err'));
  }, [q, toast]);
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t); }, [load]);

  return (
    <>
      <div className="head">
        <h1>Students</h1>
        <button className="btn" onClick={() => setEditing('new')}>Register student</button>
      </div>
      <input className="search" placeholder="Search by name, university UID, class or mobile" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="table-wrap">
        <table>
          <thead><tr><th>Name</th><th>University UID</th><th>Course / class</th><th>Mobile</th><th>Email</th><th>Card</th><th /></tr></thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id}>
                <td>{s.name} {!s.is_active && <Badge>Inactive</Badge>}</td>
                <td>{s.university_uid}</td><td>{s.course ? `${s.course} · ` : ''}{s.class_section}</td><td>{s.mobile}</td><td>{s.email}</td>
                <td>{s.rfid_uid ? <code>{s.rfid_uid}</code> : <Badge kind="amber">No card</Badge>}</td>
                <td><button className="btn small ghost" onClick={() => setEditing(s)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <Empty>No students found. Register the first student with the button above.</Empty>}
      </div>
      {editing && <StudentForm student={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
    </>
  );
}

function StudentForm({ student, onClose, onSaved }) {
  const toast = useToast();
  const isNew = !student;
  const [f, setF] = useState(isNew ? BLANK : { ...student, rfid_uid: student.rfid_uid || '' });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const onScan = (scan) => {
    if (scan.result === 'captured') { setF((p) => ({ ...p, rfid_uid: scan.uid })); toast('Card captured'); }
    else if (scan.result === 'in_use') toast(`That card already belongs to ${scan.student ? scan.student.name : 'another student'}`, 'err');
  };

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (isNew) {
        await api.post('/students', { ...f, rfid_uid: f.rfid_uid || null });
        toast('Student registered');
      } else {
        const body = { name: f.name, class_section: f.class_section, course: f.course || '', department: f.department || '', mobile: f.mobile, email: f.email, is_active: f.is_active };
        if (f.rfid_uid && f.rfid_uid !== student.rfid_uid) body.rfid_uid = f.rfid_uid;
        if (!f.rfid_uid && student.rfid_uid) body.clear_rfid = true;
        await api.patch('/students/' + student.id, body);
        toast('Student updated');
      }
      onSaved();
    } catch (err) { toast(err.message, 'err'); setBusy(false); }
  };

  return (
    <Modal title={isNew ? 'Register student' : 'Edit student'} onClose={onClose}>
      <form className="form" onSubmit={save}>
        <ScanPanel mode="register" label={f.rfid_uid ? 'Replace ID card' : 'Scan the ID card'} onScan={onScan}
          hint="Tap the student's college ID card on the reader to link it." />
        <Field label="Card UID">
          <input value={f.rfid_uid} readOnly placeholder="Scan a card to fill this in" />
        </Field>
        {f.rfid_uid && <button type="button" className="link" onClick={() => setF({ ...f, rfid_uid: '' })}>Remove card</button>}
        <div className="grid2">
          <Field label="Full name"><input value={f.name} onChange={set('name')} required minLength={2} /></Field>
          <Field label="University UID"><input value={f.university_uid} onChange={set('university_uid')} required disabled={!isNew} /></Field>
          <Field label="Class / section"><input value={f.class_section} onChange={set('class_section')} required /></Field>
          <Field label="Course"><input value={f.course || ''} onChange={set('course')} /></Field>
          <Field label="Department"><input value={f.department || ''} onChange={set('department')} /></Field>
          <Field label="Mobile"><input value={f.mobile} onChange={set('mobile')} required placeholder="10 digits" /></Field>
        </div>
        <Field label="Email" hint="Reminders go to this address"><input type="email" value={f.email} onChange={set('email')} required /></Field>
        {!isNew && (
          <label className="check"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> Active student</label>
        )}
        <div className="actions"><button type="button" className="btn ghost" onClick={onClose}>Cancel</button><button className="btn" disabled={busy}>Save student</button></div>
      </form>
    </Modal>
  );
}
