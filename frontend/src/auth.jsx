import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api, hasToken, setLabId, setToken } from './api';

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [settings, setSettings] = useState({ currency: 'Rs ' });
  const [ready, setReady] = useState(!hasToken());
  const [labId, setLab] = useState(localStorage.getItem('labId'));

  const labs = user?.labs || [];
  // the laboratory the staff member is working in (falls back to the first one allowed)
  const lab = useMemo(() => labs.find((l) => String(l.id) === String(labId)) || labs[0] || null, [labs, labId]);
  useEffect(() => { setLabId(lab ? lab.id : null); }, [lab]);

  const loadSettings = useCallback(() => api.get('/settings').then(setSettings).catch(() => {}), []);

  useEffect(() => {
    if (hasToken()) {
      api.get('/auth/me').then((u) => { setUser(u); loadSettings(); }).catch(() => setToken(null)).finally(() => setReady(true));
    }
    const expired = () => setUser(null);
    window.addEventListener('auth-expired', expired);
    return () => window.removeEventListener('auth-expired', expired);
  }, [loadSettings]);

  const login = async (username, password) => {
    const r = await api.post('/auth/login', { username, password });
    setToken(r.token);
    setUser(r.user);
    loadSettings();
    return r.user;
  };
  const logout = () => { setToken(null); setUser(null); };
  const refreshUser = () => api.get('/auth/me').then(setUser);
  const selectLab = (id) => { setLab(String(id)); };

  return (
    <AuthCtx.Provider value={{ user, ready, login, logout, refreshUser, settings, loadSettings, labs, lab, selectLab }}>
      {children}
    </AuthCtx.Provider>
  );
}
