import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api';
import Logo from '../components/Logo';

const BLANK = { name: '', university_uid: '', course: '', department: '', class_section: '', mobile: '', email: '', consent: false, website: '' };

/** Public page opened from the QR code. No login. Works on a phone. */
export default function Register() {
  const { code } = useParams();
  const [lab, setLab] = useState(null);
  const [bad, setBad] = useState('');
  const [f, setF] = useState(BLANK);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  useEffect(() => {
    api.get('/public/labs/' + encodeURIComponent(code)).then(setLab).catch((e) => setBad(e.message));
  }, [code]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const r = await api.post('/public/register', { ...f, lab_code: code });
      setDone(r.message);
    } catch (err) { setError(err.message); }
    setBusy(false);
  };

  return (
    <div className="reg-wrap">
      <div className="reg-card">
        <div className="reg-head">
          <Logo size={56} />
          <div>
            <h1>Student registration</h1>
            <p>{lab ? lab.name : 'Electronics Department'}<br /><small>University Institute of Computing, Chandigarh University</small></p>
          </div>
        </div>

        {bad && <p className="error">{bad}</p>}
        {done ? (
          <div className="reg-done">
            <h2>Thank you</h2>
            <p>{done}</p>
            <p className="muted">A lab staff member will check your details and link your ID card. You will receive an e-mail when it is approved.</p>
          </div>
        ) : (
          lab && (
            <form className="form" onSubmit={submit}>
              <p className="muted">Fill this form once. Use your own details, exactly as on your ID card.</p>
              <label className="field"><span>Full name</span><input value={f.name} onChange={set('name')} required minLength={2} autoComplete="name" /></label>
              <label className="field"><span>University ID (UID)</span><input value={f.university_uid} onChange={set('university_uid')} required minLength={3} autoCapitalize="characters" /></label>
              <div className="grid2">
                <label className="field"><span>Course</span><input value={f.course} onChange={set('course')} required placeholder="e.g. MCA" /></label>
                <label className="field"><span>Department</span><input value={f.department} onChange={set('department')} required placeholder="e.g. UIC" /></label>
              </div>
              <label className="field"><span>Class / section</span><input value={f.class_section} onChange={set('class_section')} required /></label>
              <label className="field"><span>Mobile number</span><input type="tel" inputMode="numeric" value={f.mobile} onChange={set('mobile')} required placeholder="10 digits" autoComplete="tel" /></label>
              <label className="field"><span>E-mail address</span><input type="email" value={f.email} onChange={set('email')} required autoComplete="email" />
                <small>Codes and receipts for the equipment you borrow are sent here.</small></label>
              <input className="hp" tabIndex={-1} autoComplete="off" aria-hidden="true" value={f.website} onChange={set('website')} />
              <label className="check"><input type="checkbox" checked={f.consent} onChange={(e) => setF({ ...f, consent: e.target.checked })} />
                <span>I agree that these details are stored by the laboratory to record the equipment I borrow.</span></label>
              {error && <p className="error">{error}</p>}
              <button className="btn wide" disabled={busy || !f.consent}>{busy ? 'Sending…' : 'Submit registration'}</button>
            </form>
          )
        )}
      </div>
    </div>
  );
}
