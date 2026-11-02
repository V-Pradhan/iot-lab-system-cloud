import { useEffect, useState } from 'react';
import { api } from '../api';
import { Badge, Empty, fmtDateTime, useMoney, useToast } from '../ui';

export default function Reports() {
  const toast = useToast();
  const money = useMoney();
  const [inv, setInv] = useState(null);
  const [rows, setRows] = useState([]);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const qs = `?start=${start}&end=${end}`;

  useEffect(() => { api.get('/reports/inventory').then(setInv).catch((e) => toast(e.message, 'err')); }, [toast]);
  useEffect(() => { api.get('/reports/transactions' + qs).then(setRows).catch((e) => toast(e.message, 'err')); }, [qs, toast]);

  return (
    <>
      <h1>Reports</h1>
      {inv && (
        <section className="card">
          <h2>Stock summary</h2>
          <div className="mini-stats">
            {[['Total', 'total_qty'], ['Available', 'available_qty'], ['Issued', 'issued_qty'], ['Damaged', 'damaged_qty'], ['Missing', 'missing_qty'], ['Maintenance', 'maintenance_qty']]
              .map(([label, k]) => <div key={k}><b>{inv.totals[k]}</b><span>{label}</span></div>)}
          </div>
        </section>
      )}
      <section className="card">
        <div className="head">
          <h2>Issue and return history</h2>
          <button className="btn ghost" onClick={() => api.download('/reports/transactions' + qs + '&format=csv', 'transactions.csv').catch((e) => toast(e.message, 'err'))}>Download CSV</button>
        </div>
        <div className="filters">
          <label>From <input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
          <label>To <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
        </div>
        <div className="table-wrap flat">
          <table>
            <thead><tr><th>When</th><th></th><th>Student</th><th>Equipment</th><th>Qty</th><th>Detail</th><th>Fine</th><th>Staff</th></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td>{fmtDateTime(r.at)}</td>
                  <td><Badge kind={r.type === 'issued' ? 'blue' : 'green'}>{r.type === 'issued' ? 'Issued' : 'Returned'}</Badge></td>
                  <td>{r.student}<br /><span className="muted small">{r.uid}</span></td>
                  <td>{r.equipment}</td><td>{r.quantity}</td><td>{r.detail}</td>
                  <td>{r.fine > 0 ? money(r.fine) : '–'}</td><td>{r.staff}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <Empty>No activity in this period.</Empty>}
        </div>
      </section>
    </>
  );
}
