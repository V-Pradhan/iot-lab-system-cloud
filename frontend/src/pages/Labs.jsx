import { useCallback, useEffect, useState } from 'react';
import QRCode from 'qrcode';
import { api } from '../api';
import { Badge, Empty, Field, Modal, fmtDateTime, useToast } from '../ui';

export default function Labs() {
  const toast = useToast();
  const [labs, setLabs] = useState([]);
  const [devices, setDevices] = useState([]);
  const [qr, setQr] = useState(null);
  const [newLab, setNewLab] = useState({ name: '', code: '' });
  const [newDev, setNewDev] = useState({ device_id: '', name: '', lab_id: '' });
  const [secret, setSecret] = useState(null);

  const load = useCallback(() => {
    api.get('/labs').then(setLabs).catch((e) => toast(e.message, 'err'));
    api.get('/devices').then(setDevices).catch(() => {});
  }, [toast]);
  useEffect(() => { load(); }, [load]);

  const addLab = async (e) => {
    e.preventDefault();
    try { await api.post('/labs', newLab); setNewLab({ name: '', code: '' }); toast('Laboratory added'); load(); } catch (err) { toast(err.message, 'err'); }
  };
  const toggleLab = (l) => api.patch('/labs/' + l.id, { is_active: !l.is_active }).then(load).catch((e) => toast(e.message, 'err'));
  const addDevice = async (e) => {
    e.preventDefault();
    try { setSecret(await api.post('/devices', { ...newDev, lab_id: Number(newDev.lab_id) })); setNewDev({ device_id: '', name: '', lab_id: '' }); load(); } catch (err) { toast(err.message, 'err'); }
  };
  const rotate = async (d) => {
    if (!window.confirm(`Make a new key for ${d.device_id}? The reader stops working until you put the new key in its program.`)) return;
    try { setSecret(await api.post(`/devices/${d.id}/rotate-key`)); load(); } catch (err) { toast(err.message, 'err'); }
  };
  const toggleDev = (d) => api.patch('/devices/' + d.id, { is_active: !d.is_active }).then(load).catch((e) => toast(e.message, 'err'));

  const link = (l) => `${window.location.origin}/#/register/${l.code}`;
  const showQr = async (l) => setQr({ lab: l, url: link(l), img: await QRCode.toDataURL(link(l), { width: 420, margin: 2 }) });

  return (
    <>
      <h1>Labs and readers</h1>
      <section className="card">
        <h2>Laboratories</h2>
        <div className="table-wrap flat">
          <table>
            <thead><tr><th>Name</th><th>Code</th><th>Status</th><th /></tr></thead>
            <tbody>
              {labs.map((l) => (
                <tr key={l.id}>
                  <td>{l.name}</td><td><code>{l.code}</code></td>
                  <td>{l.is_active ? <Badge kind="green">Active</Badge> : <Badge>Inactive</Badge>}</td>
                  <td className="row-actions">
                    <button className="btn small" onClick={() => showQr(l)}>Registration QR</button>
                    <button className="btn small ghost" onClick={() => toggleLab(l)}>{l.is_active ? 'Deactivate' : 'Activate'}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <form className="adder lab-form" onSubmit={addLab}>
          <input placeholder="New laboratory name" value={newLab.name} onChange={(e) => setNewLab({ ...newLab, name: e.target.value })} required minLength={2} />
          <input placeholder="Short code (e.g. EMB)" value={newLab.code} onChange={(e) => setNewLab({ ...newLab, code: e.target.value })} required pattern="[A-Za-z0-9_-]{2,20}" />
          <button className="btn">Add laboratory</button>
        </form>
        <p className="muted small">Staff see only the laboratories you assign to them on the Staff page. Each laboratory has its own stock, loans, readers and registration QR code.</p>
      </section>

      <section className="card">
        <h2>RFID readers</h2>
        <p className="muted small">Every reader belongs to one laboratory and has its own key. Put its ID and key in the reader's program.</p>
        <div className="table-wrap flat">
          <table>
            <thead><tr><th>Reader ID</th><th>Name</th><th>Laboratory</th><th>Last seen</th><th /></tr></thead>
            <tbody>
              {devices.map((d) => (
                <tr key={d.id}>
                  <td><code>{d.device_id}</code></td><td>{d.name}</td><td>{d.lab_name}</td>
                  <td>{d.last_seen ? fmtDateTime(d.last_seen) : <span className="muted">never</span>} {!d.is_active && <Badge>Disabled</Badge>}</td>
                  <td className="row-actions">
                    <button className="btn small ghost" onClick={() => rotate(d)}>New key</button>
                    <button className="btn small ghost" onClick={() => toggleDev(d)}>{d.is_active ? 'Disable' : 'Enable'}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {devices.length === 0 && <Empty>No readers yet.</Empty>}
        </div>
        <form className="adder dev-form" onSubmit={addDevice}>
          <input placeholder="Reader ID (e.g. EMB-READER-1)" value={newDev.device_id} onChange={(e) => setNewDev({ ...newDev, device_id: e.target.value })} required pattern="[A-Za-z0-9_-]{3,40}" />
          <input placeholder="Name (optional)" value={newDev.name} onChange={(e) => setNewDev({ ...newDev, name: e.target.value })} />
          <select value={newDev.lab_id} onChange={(e) => setNewDev({ ...newDev, lab_id: e.target.value })} required>
            <option value="">Laboratory…</option>
            {labs.filter((l) => l.is_active).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
          <button className="btn">Add reader</button>
        </form>
      </section>

      {qr && (
        <Modal title={`Registration QR: ${qr.lab.name}`} onClose={() => setQr(null)}>
          <div className="qr-box">
            <img src={qr.img} alt={`QR code to register for ${qr.lab.name}`} />
            <p className="muted small">Students scan this with their phone camera. Print it and put it on the lab door or counter.</p>
            <p><code className="break">{qr.url}</code></p>
            <div className="actions">
              <button className="btn ghost" onClick={() => navigator.clipboard?.writeText(qr.url).then(() => toast('Link copied'))}>Copy link</button>
              <button className="btn" onClick={() => window.print()}>Print</button>
            </div>
          </div>
        </Modal>
      )}

      {secret && (
        <Modal title={`Key for ${secret.device_id}`} onClose={() => setSecret(null)}>
          <p><strong>Copy this key now. It is shown only once.</strong> Only a scrambled copy is stored, so it cannot be shown again (you can make a new one).</p>
          <Field label="Device key"><input readOnly value={secret.key} onFocus={(e) => e.target.select()} /></Field>
          <pre className="snippet">{`const char* DEVICE_ID  = "${secret.device_id}";\nconst char* DEVICE_KEY = "${secret.key}";`}</pre>
          <div className="actions"><button className="btn" onClick={() => setSecret(null)}>I have copied it</button></div>
        </Modal>
      )}
    </>
  );
}
