import { useState } from 'react';
import { useAuth } from '../auth';
import Logo from '../components/Logo';

const FEATURES = [
  ['RFID card based issue and return', <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 10h18M7 15h4" /></>],
  ['Email one-time code verification', <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 7l9 6 9-6" /></>],
  ['Live inventory and stock alerts', <path d="M21 8l-9-5-9 5 9 5 9-5zM3 8v8l9 5 9-5V8M12 13v8" />],
  ['Due date reminders and fines', <path d="M6 16v-5a6 6 0 0112 0v5l2 2H4l2-2zM10 21h4" />],
  ['Secure, role based access', <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z" />],
];

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try { await login(username, password); } catch (err) { setError(err.message); }
    setBusy(false);
  };

  return (
    <div className="auth-bg">
      <div className="auth-card">
        <section className="auth-left">
          <Logo size={96} />
          <h1>Electronics Department</h1>
          <p>University Institute of Computing</p>
          <p>Chandigarh University</p>
          <ul className="feat">
            {FEATURES.map(([text, icon]) => (
              <li key={text}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{icon}</svg>
                {text}
              </li>
            ))}
          </ul>
        </section>

        <form className="auth-right" onSubmit={submit}>
          <h2>Welcome Back</h2>
          <p className="muted">Please sign in to your account to continue</p>

          <label className="auth-label" htmlFor="u">Username</label>
          <input id="u" className="soft" value={username} onChange={(e) => setUsername(e.target.value)}
            autoFocus autoComplete="username" required />

          <label className="auth-label" htmlFor="p">Password</label>
          <div className="pw">
            <input id="p" className="soft" type={show ? 'text' : 'password'} value={password}
              onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
            <button type="button" className="eye" onClick={() => setShow(!show)} aria-label={show ? 'Hide password' : 'Show password'}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" />
                {show && <path d="M3 3l18 18" />}
              </svg>
            </button>
          </div>

          {error && <p className="error">{error}</p>}
          <button className="btn wide" disabled={busy}>{busy ? 'Signing in…' : 'Sign In'}</button>
          <p className="muted center small">Accounts are created by the department administrator.</p>
        </form>
      </div>
    </div>
  );
}
