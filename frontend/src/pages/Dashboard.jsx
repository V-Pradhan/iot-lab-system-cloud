import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { Badge, Empty, fmtDateTime, useMoney, useToast } from '../ui';

const RESULT = {
  recognised: ['green', 'Student card'],
  unregistered: ['red', 'Unregistered card'],
  inactive: ['gray', 'Inactive student'],
  captured: ['blue', 'Card captured for registration'],
  in_use: ['gray', 'Card already assigned'],
};

export default function Dashboard() {
  const [d, setD] = useState(null);
  const money = useMoney();
  const toast = useToast();

  useEffect(() => {
    const load = () => api.get('/dashboard').then(setD).catch((e) => toast(e.message, 'err'));
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [toast]);

  if (!d) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Dashboard <span className="lab-tag">{d.lab ? d.lab.name : ''}</span></h1>
      {d.pending_registrations > 0 && (
        <Link to="/registrations" className="notice banner">{d.pending_registrations} student registration{d.pending_registrations === 1 ? ' is' : 's are'} waiting for approval. Review now</Link>
      )}
      <div className="stats">
        <Link to="/loans" className="stat"><b>{d.active_loans}</b><span>Loans out</span></Link>
        <Link to="/loans?tab=overdue" className={`stat ${d.overdue_loans ? 'alert' : ''}`}><b>{d.overdue_loans}</b><span>Overdue</span></Link>
        <Link to="/loans" className="stat"><b>{d.due_soon}</b><span>Due in the next 3 days</span></Link>
        <Link to="/fines" className="stat"><b>{money(d.pending_fines)}</b><span>Fines owed</span></Link>
        <Link to="/inventory" className="stat"><b>{d.units_available}<small> / {d.units_total}</small></b><span>Units on the shelf</span></Link>
        <Link to="/students" className="stat"><b>{d.students}</b><span>Active students</span></Link>
      </div>

      <div className="two">
        <section className="card">
          <h2>Latest card scans</h2>
          {d.recent_scans.length === 0 ? <Empty>No scans yet. Tap a card on the reader to test it.</Empty> : (
            <ul className="plain">
              {d.recent_scans.map((s) => {
                const [kind, text] = RESULT[s.result] || ['gray', s.result];
                return (
                  <li key={s.id}>
                    <div><strong>{s.student ? s.student.name : s.uid}</strong><br /><span className="muted">{fmtDateTime(s.at)} · {s.device_id}</span></div>
                    <Badge kind={kind}>{text}</Badge>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
        <section className="card">
          <h2>Running low</h2>
          {d.low_stock.length === 0 ? <Empty>Every item has more than 2 units available.</Empty> : (
            <ul className="plain">
              {d.low_stock.map((e) => (
                <li key={e.id}><span>{e.name}</span><Badge kind={e.available === 0 ? 'red' : 'amber'}>{e.available} of {e.total} left</Badge></li>
              ))}
            </ul>
          )}
          <p className="muted small">Today: {d.issued_today} issued, {d.returned_today} returned.</p>
        </section>
      </div>
    </>
  );
}
