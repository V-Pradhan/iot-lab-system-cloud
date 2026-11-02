import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api';
import ScanPanel from '../components/ScanPanel';
import { Badge, Empty, Field, Modal, fmtDate, useMoney, useToast } from '../ui';

const TABS = [['active', 'Active'], ['overdue', 'Overdue'], ['returned', 'Returned'], ['all', 'All']];

export default function Loans() {
  const toast = useToast();
  const money = useMoney();
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') || 'active';
  const [q, setQ] = useState('');
  const [rows, setRows] = useState([]);
  const [returning, setReturning] = useState(null);

  const load = useCallback(() => {
    api.get(`/issues?status=${tab}&q=${encodeURIComponent(q)}`).then(setRows).catch((e) => toast(e.message, 'err'));
  }, [tab, q, toast]);
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t); }, [load]);

  const onScan = (scan) => {
    if (scan.student) { setQ(scan.student.university_uid); toast(`Showing loans for ${scan.student.name}`); }
    else toast('That card is not registered to a student', 'err');
  };

  const renew = async (l) => {
    try { await api.post(`/issues/${l.id}/renew`); toast('Renewed for another period'); load(); }
    catch (e) { toast(e.message, 'err'); }
  };

  return (
    <>
      <h1>Loans and returns</h1>
      <ScanPanel mode="lookup" label="Scan a student's card" onScan={onScan} hint="Shows that student's loans so you can return or renew them." />
      <div className="tabs">
        {TABS.map(([k, label]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setParams(k === 'active' ? {} : { tab: k })}>{label}</button>)}
        <input className="search inline" placeholder="Search student name or UID" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Student</th><th>Equipment</th><th>Qty out</th><th>Issued</th><th>Due</th><th>Fine</th><th /></tr></thead>
          <tbody>
            {rows.map((l) => (
              <tr key={l.id}>
                <td>{l.student.name}<br /><span className="muted small">{l.student.university_uid}</span></td>
                <td>{l.equipment.name}</td>
                <td>{l.outstanding}{l.returned_qty > 0 && <span className="muted small"> of {l.quantity}</span>}</td>
                <td>{fmtDate(l.issue_date)}</td>
                <td>{fmtDate(l.due_date)} {l.renewed && <Badge kind="blue">Renewed</Badge>} {l.overdue_days > 0 && <Badge kind="red">{l.overdue_days} days late</Badge>}</td>
                <td>{l.accrued_fine + l.fine_total > 0 ? money(l.accrued_fine + l.fine_total) : '–'}</td>
                <td className="row-actions">
                  {l.status === 'issued' ? (
                    <>
                      <button className="btn small" onClick={() => setReturning(l)}>Return</button>
                      {!l.renewed && <button className="btn small ghost" onClick={() => renew(l)}>Renew</button>}
                    </>
                  ) : <Badge kind="green">Returned</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <Empty>No loans in this view.</Empty>}
      </div>
      {returning && <ReturnForm loan={returning} onClose={() => setReturning(null)} onDone={() => { setReturning(null); load(); }} />}
    </>
  );
}

function ReturnForm({ loan, onClose, onDone }) {
  const toast = useToast();
  const money = useMoney();
  const [qty, setQty] = useState(loan.outstanding);
  const [condition, setCondition] = useState('good');
  const [busy, setBusy] = useState(false);
  const fine = loan.overdue_days * (loan.accrued_fine / (loan.outstanding * loan.overdue_days || 1)) * qty;

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api.post('/returns', { items: [{ issue_id: loan.id, quantity: Number(qty), condition }] });
      const f = r.results[0].fine;
      toast(f > 0 ? `Returned. Fine recorded: ${money(f)}` : 'Returned');
      onDone();
    } catch (err) { toast(err.message, 'err'); setBusy(false); }
  };

  return (
    <Modal title="Return equipment" onClose={onClose}>
      <form className="form" onSubmit={save}>
        <p><strong>{loan.student.name}</strong> · {loan.equipment.name}<br /><span className="muted">{loan.outstanding} unit(s) still out, due {fmtDate(loan.due_date)}</span></p>
        <div className="grid2">
          <Field label="Quantity returning"><input type="number" min="1" max={loan.outstanding} value={qty} onChange={(e) => setQty(e.target.value)} required /></Field>
          <Field label="Condition">
            <select value={condition} onChange={(e) => setCondition(e.target.value)}>
              <option value="good">Good, back on the shelf</option>
              <option value="damaged">Damaged</option>
              <option value="missing">Missing or lost</option>
            </select>
          </Field>
        </div>
        {loan.overdue_days > 0 && <p className="notice">{loan.overdue_days} days late. Fine for this return: {money(fine)}</p>}
        <div className="actions"><button type="button" className="btn ghost" onClick={onClose}>Cancel</button><button className="btn" disabled={busy}>Confirm return</button></div>
      </form>
    </Modal>
  );
}
