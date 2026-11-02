import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { Badge, Empty, Field, Modal, fmtDateTime, useToast } from '../ui';

const BLANK = { name: '', category: '', total_qty: 0, damaged_qty: 0, missing_qty: 0, maintenance_qty: 0, notes: '', reason: '' };

export default function Inventory() {
  const toast = useToast();
  const canEdit = true;                       // administrator, teacher and lab assistant may all update stock
  const [history, setHistory] = useState(null);
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState('');
  const [editing, setEditing] = useState(null);

  const load = useCallback(() => api.get('/inventory?q=' + encodeURIComponent(q)).then(setRows).catch((e) => toast(e.message, 'err')), [q, toast]);
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t); }, [load]);

  return (
    <>
      <div className="head">
        <h1>Inventory</h1>
        <div className="row-actions">
          <button className="btn ghost" onClick={() => api.get('/inventory/log').then(setHistory).catch((e) => toast(e.message, 'err'))}>Change history</button>
          {canEdit && <button className="btn" onClick={() => setEditing('new')}>Add equipment</button>}
        </div>
      </div>
      <input className="search" placeholder="Search equipment or category" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="table-wrap">
        <table>
          <thead><tr><th>Equipment</th><th>Category</th><th>Total</th><th>Available</th><th>Issued</th><th>Damaged</th><th>Missing</th><th>Maintenance</th>{canEdit && <th />}</tr></thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id}>
                <td>{e.name}</td><td>{e.category}</td><td>{e.total_qty}</td>
                <td>{e.available_qty === 0 ? <Badge kind="red">0</Badge> : e.available_qty <= 2 ? <Badge kind="amber">{e.available_qty}</Badge> : e.available_qty}</td>
                <td>{e.issued_qty}</td><td>{e.damaged_qty}</td><td>{e.missing_qty}</td><td>{e.maintenance_qty}</td>
                {canEdit && <td><button className="btn small ghost" onClick={() => setEditing(e)}>Edit</button></td>}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <Empty>No equipment yet.{canEdit ? ' Add the first item with the button above.' : ''}</Empty>}
      </div>
      {history && (
        <Modal title="Stock change history" onClose={() => setHistory(null)} wide>
          {history.length === 0 ? <Empty>No changes yet.</Empty> : (
            <div className="table-wrap flat"><table>
              <thead><tr><th>When</th><th>Who</th><th>Item</th><th>Change</th><th>Reason</th></tr></thead>
              <tbody>{history.map((h) => <tr key={h.id}><td>{fmtDateTime(h.at)}</td><td>{h.user}</td><td>{h.equipment}</td><td>{h.change}</td><td>{h.reason}</td></tr>)}</tbody>
            </table></div>
          )}
        </Modal>
      )}
      {editing && <EquipmentForm item={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
    </>
  );
}

function EquipmentForm({ item, onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState(item ? { ...item, reason: '' } : BLANK);
  const num = (k) => (e) => setF({ ...f, [k]: e.target.value === '' ? '' : Number(e.target.value) });
  const txt = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const avail = (Number(f.total_qty) || 0) - (item ? item.issued_qty : 0) - (Number(f.damaged_qty) || 0) - (Number(f.missing_qty) || 0) - (Number(f.maintenance_qty) || 0);

  const save = async (e) => {
    e.preventDefault();
    const body = { name: f.name, category: f.category, total_qty: Number(f.total_qty) || 0, damaged_qty: Number(f.damaged_qty) || 0,
      missing_qty: Number(f.missing_qty) || 0, maintenance_qty: Number(f.maintenance_qty) || 0, notes: f.notes, reason: f.reason };
    try {
      if (item) await api.patch('/inventory/' + item.id, body); else await api.post('/inventory', body);
      toast('Inventory saved');
      onSaved();
    } catch (err) { toast(err.message, 'err'); }
  };

  return (
    <Modal title={item ? `Edit ${item.name}` : 'Add equipment'} onClose={onClose}>
      <form className="form" onSubmit={save}>
        <div className="grid2">
          <Field label="Name"><input value={f.name} onChange={txt('name')} required minLength={2} /></Field>
          <Field label="Category"><input value={f.category} onChange={txt('category')} /></Field>
          <Field label="Total units"><input type="number" min="0" value={f.total_qty} onChange={num('total_qty')} /></Field>
          <Field label="Damaged"><input type="number" min="0" value={f.damaged_qty} onChange={num('damaged_qty')} /></Field>
          <Field label="Missing"><input type="number" min="0" value={f.missing_qty} onChange={num('missing_qty')} /></Field>
          <Field label="In maintenance"><input type="number" min="0" value={f.maintenance_qty} onChange={num('maintenance_qty')} /></Field>
        </div>
        <Field label="Notes"><input value={f.notes} onChange={txt('notes')} /></Field>
        <Field label="Reason for this change" hint="Saved in the change history, e.g. new purchase, recount, broken"><input value={f.reason} onChange={txt('reason')} maxLength={200} /></Field>
        <p className={avail < 0 ? 'error' : 'muted'}>
          Available after saving: <strong>{avail}</strong>{item && item.issued_qty > 0 ? ` (${item.issued_qty} currently issued)` : ''}
        </p>
        <div className="actions"><button type="button" className="btn ghost" onClick={onClose}>Cancel</button><button className="btn" disabled={avail < 0}>Save</button></div>
      </form>
    </Modal>
  );
}
