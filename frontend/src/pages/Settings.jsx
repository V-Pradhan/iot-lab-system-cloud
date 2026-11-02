import { useEffect, useState } from 'react';
import { api } from '../api';
import { useAuth } from '../auth';
import { Badge, Empty, Field, fmtDateTime, useToast } from '../ui';

export default function Settings() {
  const toast = useToast();
  const { loadSettings } = useAuth();
  const [s, setS] = useState(null);
  const [mail, setMail] = useState('');
  const [log, setLog] = useState([]);
  const [audit, setAudit] = useState(null);

  const loadLog = () => api.get('/notifications').then(setLog).catch(() => {});
  useEffect(() => { api.get('/settings').then(setS).catch((e) => toast(e.message, 'err')); loadLog(); }, [toast]);
  if (!s) return <p className="muted">Loading…</p>;
  const set = (k) => (e) => setS({ ...s, [k]: e.target.value });

  const save = async (e) => {
    e.preventDefault();
    try { setS(await api.put('/settings', s)); loadSettings(); toast('Settings saved'); } catch (err) { toast(err.message, 'err'); }
  };

  return (
    <>
      <h1>Settings</h1>
      <form className="card form" onSubmit={save}>
        <h2>Loan rules</h2>
        <div className="grid3">
          <Field label="Loan period (days)"><input type="number" min="1" value={s.loan_days} onChange={set('loan_days')} /></Field>
          <Field label="Renewal period (days)"><input type="number" min="1" value={s.renew_days} onChange={set('renew_days')} /></Field>
          <Field label="Fine per unit per day"><input type="number" min="0" step="0.5" value={s.fine_per_day} onChange={set('fine_per_day')} /></Field>
          <Field label="Currency symbol"><input value={s.currency} onChange={set('currency')} /></Field>
          <Field label="Reminder days before due" hint="Comma separated, e.g. 7,1"><input value={s.reminder_days} onChange={set('reminder_days')} /></Field>
          <Field label="Renew overdue loans?">
            <select value={s.renew_after_due} onChange={set('renew_after_due')}><option value="false">No</option><option value="true">Yes</option></select>
          </Field>
        </div>
        <div className="actions"><button className="btn">Save settings</button></div>
      </form>

      <section className="card">
        <h2>Email reminders</h2>
        <p className="muted">Reminders go out automatically before the due date and weekly once a loan is overdue. Configure SMTP in the backend .env file.</p>
        <div className="adder">
          <input type="email" placeholder="your@email.com" value={mail} onChange={(e) => setMail(e.target.value)} />
          <button className="btn ghost" onClick={() => api.post('/notifications/test', { to: mail }).then(() => toast('Test email sent')).catch((e) => toast(e.message, 'err'))}>Send test email</button>
          <button className="btn" onClick={() => api.post('/notifications/run').then((r) => { toast(`Sent ${r.sent}, failed ${r.failed}`); loadLog(); }).catch((e) => toast(e.message, 'err'))}>Check reminders now</button>
        </div>
        <div className="table-wrap flat">
          <table>
            <thead><tr><th>When</th><th>To</th><th>Type</th><th>Status</th></tr></thead>
            <tbody>
              {log.map((n) => (
                <tr key={n.id}><td>{fmtDateTime(n.at)}</td><td>{n.to}</td><td>{n.kind.split('_').slice(0, 2).join(' ')}</td>
                  <td><Badge kind={n.status === 'sent' ? 'green' : 'red'}>{n.status}</Badge> {n.error && <span className="muted small">{n.error}</span>}</td></tr>
              ))}
            </tbody>
          </table>
          {log.length === 0 && <Empty>No reminders sent yet.</Empty>}
        </div>
      </section>

      <section className="card">
        <div className="head"><h2>Activity log</h2>
          <button className="btn ghost" onClick={() => api.get('/audit').then(setAudit).catch((e) => toast(e.message, 'err'))}>{audit ? 'Refresh' : 'Show latest 200'}</button></div>
        {audit && (
          <div className="table-wrap flat"><table>
            <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Detail</th></tr></thead>
            <tbody>{audit.map((a) => <tr key={a.id}><td>{fmtDateTime(a.at)}</td><td>{a.user}</td><td>{a.action}</td><td>{a.detail}</td></tr>)}</tbody>
          </table></div>
        )}
      </section>
    </>
  );
}
