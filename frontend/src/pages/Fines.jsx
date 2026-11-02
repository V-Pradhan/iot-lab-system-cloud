import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { useAuth } from '../auth';
import { Badge, Empty, fmtDate, useMoney, useToast } from '../ui';

const STATUS = { pending: ['red', 'Unpaid'], paid: ['green', 'Paid'], waived: ['gray', 'Waived'], none: ['amber', 'Accruing'] };

export default function Fines() {
  const { user, settings } = useAuth();
  const toast = useToast();
  const money = useMoney();
  const [rows, setRows] = useState([]);
  const canSettle = user.role === 'admin' || user.role === 'teacher';

  const load = useCallback(() => api.get('/fines').then(setRows).catch((e) => toast(e.message, 'err')), [toast]);
  useEffect(() => { load(); }, [load]);

  const settle = async (id, status) => {
    try { await api.post(`/fines/${id}/settle`, { status }); toast(status === 'paid' ? 'Marked as paid' : 'Fine waived'); load(); }
    catch (e) { toast(e.message, 'err'); }
  };

  return (
    <>
      <h1>Fines</h1>
      <p className="muted">{money(settings.fine_per_day || 0)} per unit for each day after the due date. Fines are recorded when items are returned.</p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Student</th><th>Equipment</th><th>Due</th><th>Recorded</th><th>Still accruing</th><th>Status</th>{canSettle && <th />}</tr></thead>
          <tbody>
            {rows.map((r) => {
              const [kind, text] = r.fine_total > 0 ? STATUS[r.fine_status] : STATUS.none;
              return (
                <tr key={r.id}>
                  <td>{r.student.name}<br /><span className="muted small">{r.student.university_uid}</span></td>
                  <td>{r.equipment.name}</td><td>{fmtDate(r.due_date)}</td>
                  <td>{r.fine_total > 0 ? money(r.fine_total) : '–'}</td>
                  <td>{r.accrued_fine > 0 ? money(r.accrued_fine) : '–'}</td>
                  <td><Badge kind={kind}>{text}</Badge></td>
                  {canSettle && (
                    <td className="row-actions">
                      {r.fine_total > 0 && r.fine_status === 'pending' && (
                        <>
                          <button className="btn small" onClick={() => settle(r.id, 'paid')}>Mark paid</button>
                          {user.role === 'admin' && <button className="btn small ghost" onClick={() => settle(r.id, 'waived')}>Waive</button>}
                        </>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
        {rows.length === 0 && <Empty>No fines. Nothing is overdue.</Empty>}
      </div>
    </>
  );
}
