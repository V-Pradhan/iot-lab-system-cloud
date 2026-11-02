import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../auth';
import ScanPanel from '../components/ScanPanel';
import { Badge, Empty, Field, fmtDate, useToast } from '../ui';

export default function Issue() {
  const toast = useToast();
  const { user, settings } = useAuth();
  const isAdmin = user.role === 'admin';

  const [student, setStudent] = useState(null);
  const [viaOverride, setViaOverride] = useState(false);
  const [notice, setNotice] = useState('');
  const [q, setQ] = useState('');
  const [found, setFound] = useState([]);
  const [reason, setReason] = useState('');
  const [equipment, setEquipment] = useState([]);
  const [loans, setLoans] = useState([]);
  const [cart, setCart] = useState([]);
  const [pick, setPick] = useState('');
  const [qty, setQty] = useState(1);
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [done, setDone] = useState(null);
  const [busy, setBusy] = useState(false);

  // emailed one-time code
  const [code, setCode] = useState('');
  const [sentTo, setSentTo] = useState('');
  const [codeError, setCodeError] = useState('');
  const [sending, setSending] = useState(false);
  const [cool, setCool] = useState(0);
  const [sentFor, setSentFor] = useState('');   // the item list the emailed code was created for

  const loadEquipment = () => api.get('/inventory').then(setEquipment).catch((e) => toast(e.message, 'err'));
  useEffect(() => { loadEquipment(); }, []); // eslint-disable-line

  useEffect(() => {
    if (!isAdmin || !q.trim()) { setFound([]); return undefined; }
    const t = setTimeout(() => api.get('/students?q=' + encodeURIComponent(q)).then((r) => setFound(r.filter((s) => s.is_active).slice(0, 6))).catch(() => {}), 200);
    return () => clearTimeout(t);
  }, [q, isAdmin]);

  useEffect(() => {
    if (student) api.get(`/issues?status=active&student_id=${student.id}`).then(setLoans).catch(() => {});
    else setLoans([]);
  }, [student, done]);

  useEffect(() => {
    if (cool <= 0) return undefined;
    const t = setTimeout(() => setCool(cool - 1), 1000);
    return () => clearTimeout(t);
  }, [cool]);

  const mergedItems = () => {
    const merged = {};
    cart.forEach((c) => { merged[c.equipment.id] = (merged[c.equipment.id] || 0) + c.quantity; });
    return Object.entries(merged).map(([equipment_id, quantity]) => ({ equipment_id: Number(equipment_id), quantity }));
  };
  const fingerprint = () => mergedItems().sort((a, b) => a.equipment_id - b.equipment_id).map((i) => `${i.equipment_id}:${i.quantity}`).join(',');

  const sendCode = async () => {
    setSending(true);
    setCodeError('');
    try {
      const r = await api.post('/issue-codes', { student_id: student.id, items: mergedItems() });
      setSentTo(r.sent_to);
      setSentFor(fingerprint());
      setCool(r.cooldown);
      setCode('');
    } catch (e) {
      setCodeError(e.message);
      const m = /wait (\d+)/i.exec(e.message);
      if (m) setCool(Number(m[1]));
    }
    setSending(false);
  };

  const resetAll = () => {
    setStudent(null); setViaOverride(false); setCart([]); setDone(null); setNotice('');
    setCode(''); setSentTo(''); setSentFor(''); setCodeError(''); setReason(''); setCool(0);
  };

  // A card scan identifies the student and immediately emails a fresh code to them.
  const onScan = (scan) => {
    if (scan.result === 'recognised') {
      resetAll();
      setStudent(scan.student);
    } else if (scan.result === 'inactive') {
      setNotice(`${scan.student?.name || 'This student'} is inactive and cannot borrow equipment.`);
    } else {
      setNotice('unregistered');
    }
  };

  const chooseOverride = (s) => { resetAll(); setStudent(s); setViaOverride(true); setQ(''); setFound([]); };

  const eq = equipment.find((e) => String(e.id) === pick);
  const inCart = (id) => cart.filter((c) => c.equipment.id === id).reduce((a, c) => a + c.quantity, 0);
  const free = eq ? eq.available_qty - inCart(eq.id) : 0;

  const add = () => {
    if (!eq) return;
    if (qty < 1 || qty > free) return toast(`Only ${free} available`, 'err');
    setCart([...cart, { equipment: eq, quantity: Number(qty) }]);
    setPick(''); setQty(1);
  };

  const listChanged = !!sentFor && sentFor !== fingerprint();
  const ready = viaOverride ? reason.trim().length >= 5 : (/^\d{6}$/.test(code) && !!sentFor && !listChanged);

  const confirm = async () => {
    setBusy(true);
    try {
      const body = { student_id: student.id, request_id: requestId, items: mergedItems() };
      if (viaOverride) body.override_reason = reason.trim(); else body.code = code;
      const res = await api.post('/issues', body);
      setDone(res);
      setCart([]);
      setCode('');
      setSentFor('');
      setRequestId(crypto.randomUUID());
      loadEquipment();
      toast('Equipment issued');
    } catch (err) { toast(err.message, 'err'); }
    setBusy(false);
  };

  return (
    <>
      <h1>Issue equipment</h1>
      {!student ? (
        <section className="card">
          <h2>1. Student taps their card</h2>
          <ScanPanel mode="lookup" onScan={onScan} hint="After the scan, a one-time code is emailed to the student straight away." />
          {notice === 'unregistered' && <p className="notice">This card is not registered. <Link to="/students">Register the student first</Link>.</p>}
          {notice && notice !== 'unregistered' && <p className="notice">{notice}</p>}
          {isAdmin && (
            <>
              <div className="or">administrator only: no card</div>
              <input className="search" placeholder="Search name or university UID to issue without a card" value={q} onChange={(e) => setQ(e.target.value)} />
              {found.length > 0 && (
                <ul className="pick">
                  {found.map((s) => <li key={s.id}><button onClick={() => chooseOverride(s)}><strong>{s.name}</strong> <span className="muted">{s.university_uid} · {s.class_section}</span></button></li>)}
                </ul>
              )}
            </>
          )}
        </section>
      ) : (
        <>
          <section className="card who-card">
            <div>
              <h2>{student.name}</h2>
              <span className="muted">{student.university_uid} · {student.class_section}</span>
              {viaOverride && <> <Badge kind="amber">Override, no card</Badge></>}
            </div>
            <button className="btn ghost" onClick={resetAll}>Change student</button>
          </section>

          {loans.length > 0 && !done && (
            <section className="card">
              <h2>Already borrowed</h2>
              <ul className="plain">
                {loans.map((l) => (
                  <li key={l.id}><span>{l.outstanding} × {l.equipment.name}</span>
                    <span className="muted">due {fmtDate(l.due_date)} {l.overdue_days > 0 && <Badge kind="red">{l.overdue_days} days late</Badge>}</span></li>
                ))}
              </ul>
            </section>
          )}

          {done ? (
            <section className="card success">
              <h2>Issued</h2>
              <ul className="plain">{done.map((d) => <li key={d.id}><span>{d.quantity} × {d.equipment.name}</span><span>due {fmtDate(d.due_date)}</span></li>)}</ul>
              <p className="muted">A receipt with these details was emailed to the student and shown on the reader.</p>
              <div className="actions" style={{ justifyContent: 'flex-start' }}>
                <button className="btn" onClick={resetAll}>Next student</button>
                <button className="btn ghost" onClick={() => { setDone(null); setCart([]); setCode(''); setSentFor(''); setSentTo(''); setCodeError(''); }}>Issue more to this student</button>
              </div>
            </section>
          ) : (
            <>
              <section className="card">
                <h2>2. Choose equipment</h2>
                <div className="adder">
                  <select value={pick} onChange={(e) => { setPick(e.target.value); setQty(1); }}>
                    <option value="">Select equipment…</option>
                    {equipment.map((e) => <option key={e.id} value={e.id} disabled={e.available_qty - inCart(e.id) <= 0}>{e.name} ({e.available_qty - inCart(e.id)} available)</option>)}
                  </select>
                  <input type="number" min="1" max={free || 1} value={qty} onChange={(e) => setQty(e.target.value)} aria-label="Quantity" />
                  <button className="btn" onClick={add} disabled={!eq}>Add</button>
                </div>
                {cart.length === 0 ? <Empty>Nothing added yet.</Empty> : (
                  <ul className="plain">
                    {cart.map((c, i) => (
                      <li key={i}><span>{c.quantity} × {c.equipment.name}</span>
                        <button className="link" onClick={() => setCart(cart.filter((_, j) => j !== i))}>Remove</button></li>
                    ))}
                  </ul>
                )}
              </section>

              {cart.length > 0 && (
                <section className="card">
                  <h2>3. Confirm</h2>
                  {viaOverride ? (
                    <Field label="Reason for issuing without a card" hint="Saved in the activity log">
                      <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Card forgotten, ID checked" />
                    </Field>
                  ) : (
                    <>
                      <p className="muted">One email with the full list above and a single code is sent to the student. Add every item first, then send it.</p>
                      <div className="actions" style={{ justifyContent: 'flex-start', marginBottom: 12 }}>
                        <button className="btn ghost" disabled={sending || cool > 0} onClick={sendCode}>
                          {sending ? 'Sending…' : cool > 0 ? `Resend in ${cool}s` : sentFor ? 'Send a new code' : 'Email code to student'}
                        </button>
                      </div>
                      {codeError && <p className="error">{codeError}</p>}
                      {listChanged && <p className="notice">The list changed after the code was sent. Send a new code for the current list.</p>}
                      {sentFor && !listChanged && !codeError && <p className="notice">Code emailed to <strong>{sentTo}</strong> for the {cart.length} item(s) above. Ask the student to read it out and type it below.</p>}
                      <div className="adder code-row">
                        <input inputMode="numeric" maxLength={6} placeholder="6-digit code" value={code} disabled={!sentFor || listChanged}
                          onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} aria-label="Code from the student's email" autoComplete="one-time-code" />
                      </div>
                    </>
                  )}
                  <p className="muted">Due {settings.loan_days || 30} days from today. One renewal is allowed.</p>
                  <button className="btn" onClick={confirm} disabled={busy || !ready}>{busy ? 'Issuing…' : 'Issue equipment'}</button>
                </section>
              )}
            </>
          )}
        </>
      )}
    </>
  );
}
