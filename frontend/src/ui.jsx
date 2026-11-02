import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useAuth } from './auth';

const ToastCtx = createContext(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }) {
  const [t, setT] = useState(null);
  const show = useCallback((msg, type = 'ok') => {
    setT({ msg, type });
    setTimeout(() => setT(null), 4500);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {t && <div className={`toast ${t.type}`} role="status">{t.msg}</div>}
    </ToastCtx.Provider>
  );
}

export function Modal({ title, onClose, children, wide }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">×</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export const Badge = ({ kind = 'gray', children }) => <span className={`badge ${kind}`}>{children}</span>;
export const Empty = ({ children }) => <p className="empty">{children}</p>;

export const fmtDate = (s) =>
  s ? new Date(s).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '';
export const fmtDateTime = (s) =>
  s ? new Date(s).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';

export function useMoney() {
  const { settings } = useAuth();
  return (n) => `${settings.currency || ''}${Number(n || 0).toFixed(2)}`;
}

export function Field({ label, children, hint }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
