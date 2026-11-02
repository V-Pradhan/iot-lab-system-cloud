import { useEffect, useState } from 'react';
import { Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { api } from './api';
import { useAuth } from './auth';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import Students from './pages/Students';
import Registrations from './pages/Registrations';
import Issue from './pages/Issue';
import Loans from './pages/Loans';
import Inventory from './pages/Inventory';
import Fines from './pages/Fines';
import Reports from './pages/Reports';
import Staff from './pages/Staff';
import Labs from './pages/Labs';
import Settings from './pages/Settings';
import Account from './pages/Account';
import Logo from './components/Logo';

const ALL = ['admin', 'teacher', 'lab_assistant'];
const NAV = [
  ['/', 'Dashboard', ALL],
  ['/issue', 'Issue equipment', ALL],
  ['/loans', 'Loans and returns', ALL],
  ['/registrations', 'Registrations', ALL],
  ['/students', 'Students', ALL],
  ['/inventory', 'Inventory', ALL],
  ['/fines', 'Fines', ALL],
  ['/reports', 'Reports', ALL],
  ['/staff', 'Staff', ['admin']],
  ['/labs', 'Labs and readers', ['admin']],
  ['/settings', 'Settings', ['admin']],
];

const ROLE = { admin: 'Administrator', teacher: 'Teacher', lab_assistant: 'Lab assistant' };

export default function App() {
  const { user, ready, logout, labs, lab, selectLab } = useAuth();
  const loc = useLocation();
  const [pending, setPending] = useState(0);

  // number of student registrations waiting for approval in the current lab
  useEffect(() => {
    if (!user || !lab) return undefined;
    const load = () => api.get('/registrations/count').then((r) => setPending(r.pending)).catch(() => {});
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [user, lab]);

  // the QR registration page is public: students are not logged in
  if (loc.pathname.startsWith('/register/')) {
    return <Routes><Route path="/register/:code" element={<Register />} /></Routes>;
  }
  if (!ready) return <div className="center-note">Loading…</div>;
  if (!user) return <Login />;
  if (user.must_change_password && loc.pathname !== '/account') return <Navigate to="/account" replace />;
  if (!lab) {
    return (
      <div className="center-note">
        <p>No laboratory is assigned to your account. Ask the administrator.</p>
        <button className="btn ghost" onClick={logout}>Sign out</button>
      </div>
    );
  }

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand"><Logo size={42} /> <span><b>Electronics Department</b><small>University Institute of Computing</small></span></div>
        <div className="labbox">
          <span>Laboratory</span>
          {labs.length > 1 ? (
            <select value={lab.id} onChange={(e) => selectLab(e.target.value)} aria-label="Choose laboratory">
              {labs.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          ) : <strong>{lab.name}</strong>}
        </div>
        <nav>
          {NAV.filter(([, , roles]) => roles.includes(user.role)).map(([to, label]) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>
              {label}{to === '/registrations' && pending > 0 && <em className="pill">{pending}</em>}
            </NavLink>
          ))}
        </nav>
        <div className="who">
          <strong>{user.full_name}</strong>
          <span>{ROLE[user.role]}</span>
          <NavLink to="/account">Account</NavLink>
          <button className="link" onClick={logout}>Sign out</button>
        </div>
      </aside>
      <main className="main" key={lab.id}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/issue" element={<Issue />} />
          <Route path="/loans" element={<Loans />} />
          <Route path="/registrations" element={<Registrations />} />
          <Route path="/students" element={<Students />} />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/fines" element={<Fines />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/staff" element={user.role === 'admin' ? <Staff /> : <Navigate to="/" />} />
          <Route path="/labs" element={user.role === 'admin' ? <Labs /> : <Navigate to="/" />} />
          <Route path="/settings" element={user.role === 'admin' ? <Settings /> : <Navigate to="/" />} />
          <Route path="/account" element={<Account />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  );
}
