import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import ScanPanel from '../components/ScanPanel';
import { Badge, Empty, Field, Modal, fmtDateTime, useToast } from '../ui';

const TABS = [['PENDING', 'Pending'], ['NEEDS_CORRECTION', 'Sent back'], ['APPROVED', 'Approved'], ['REJECTED', 'Rejected']];
const KIND = { PENDING: 'amber', NEEDS_CORRECTION: 'blue', APPROVED: 'green', REJECTED: 'red' };

export default function Registrations() {
  const toast = useToast();
  const [tab, setTab] = useState('PENDING');
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(null);

  const load = useCallback(() => {
    api.get('/registrations?status=' + tab).then(setRows).catch((e) => toast(e.message, 'err'));
  }, [tab, toast]);
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);

  return (
    <>
      <h1>Student registrations</h1>
      <p className="muted">Students fill the form on their phone after scanning the lab's QR code. Check the details, tap the student's ID card on the reader, then approve.</p>
      <div className="tabs">
        {TABS.map(([k, label]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{label}</button>)}
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Student</th><th>University ID</th><th>Course / class</th><th>Contact</th><th>Submitted</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.name} <Badge kind={KIND[r.status]}>{r.status === 'NEEDS_CORRECTION' ? 'Sent back' : r.status.toLowerCase()}</Badge></td>
                <td>{r.university_uid}</td>
                <td>{r.course} {r.department && `· ${r.department}`}<br /><span className="muted small">{r.class_section}</span></td>
                <td>{r.mobile}<br /><span className="muted small">{r.email}</span></td>
                <td>{fmtDateTime(r.created_at)}</td>
                <td>{r.status === 'PENDING' && <button className="btn small" onClick={() => setOpen(r)}>Review</button>}
                  {r.note && r.status !== 'PENDING' && <span className="muted small">{r.note}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <Empty>{tab === 'PENDING' ? 'No registrations are waiting. New ones appear here by themselves.' : 'Nothing here.'}</Empty>}
      </div>
      {open && <Review reg={open} onClose={() => setOpen(null)} onDone={() => { setOpen(null); load(); }} />}
    </>
  );
}

function Review({ reg, onClose, onDone }) {
  const toast = useToast();
  const [f, setF] = useState({ name: reg.name, course: reg.course, department: reg.department, class_section: reg.class_section, mobile: reg.mobile, email: reg.email });
  const [uid, setUid] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const onScan = (scan) => {
    if (scan.result === 'captured') { setUid(scan.uid); toast('Card captured'); }
    else if (scan.result === 'in_use') toast(`That card already belongs to ${scan.student ? scan.student.name : 'another student'}`, 'err');
  };

  const act = async (kind) => {
    setBusy(true);
    try {
      await api.patch(`/registrations/${reg.id}`, f);
      if (kind === 'approve') await api.post(`/registrations/${reg.id}/approve`, { rfid_uid: uid });
      else await api.post(`/registrations/${reg.id}/${kind}`, { note });
      toast({ approve: 'Student approved and registered', reject: 'Registration rejected', correction: 'Sent back to the student' }[kind]);
      onDone();
    } catch (e) { toast(e.message, 'err'); setBusy(false); }
  };

  return (
    <Modal title={`Review: ${reg.name}`} onClose={onClose} wide>
      <div className="form">
        <p className="muted small">University ID <strong>{reg.university_uid}</strong>. You can fix typing mistakes before approving.</p>
        <div className="grid2">
          <Field label="Full name"><input value={f.name} onChange={set('name')} /></Field>
          <Field label="Class / section"><input value={f.class_section} onChange={set('class_section')} /></Field>
          <Field label="Course"><input value={f.course} onChange={set('course')} /></Field>
          <Field label="Department"><input value={f.department} onChange={set('department')} /></Field>
          <Field label="Mobile"><input value={f.mobile} onChange={set('mobile')} /></Field>
          <Field label="E-mail"><input value={f.email} onChange={set('email')} /></Field>
        </div>
        <ScanPanel mode="register" label={uid ? 'Replace the card' : 'Tap the student\u2019s ID card'} onScan={onScan}
          hint="Press Start scan, then the student taps the ID card on this lab's reader." />
        <Field label="Card UID"><input value={uid} readOnly placeholder="Scan the card to fill this in" /></Field>
        <Field label="Message to the student (needed to send back, optional to reject)"><input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Section is wrong" /></Field>
        <div className="actions">
          <button className="btn ghost" disabled={busy} onClick={() => act('reject')}>Reject</button>
          <button className="btn ghost" disabled={busy || note.trim().length < 3} onClick={() => act('correction')}>Send back to correct</button>
          <button className="btn" disabled={busy || !uid} onClick={() => act('approve')}>Approve and register</button>
        </div>
      </div>
    </Modal>
  );
}
