import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../auth';
import { Field, useToast } from '../ui';

export default function Account() {
  const { user, refreshUser } = useAuth();
  const toast = useToast();
  const nav = useNavigate();
  const [old, setOld] = useState('');
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');

  const save = async (e) => {
    e.preventDefault();
    if (pw !== pw2) return toast('The new passwords do not match', 'err');
    try {
      await api.post('/auth/change-password', { old_password: old, new_password: pw });
      await refreshUser();
      toast('Password changed');
      nav('/');
    } catch (err) { toast(err.message, 'err'); }
  };

  return (
    <>
      <h1>Account</h1>
      {user.must_change_password && <p className="notice">Choose a new password before you continue.</p>}
      <p className="muted">{user.full_name} · {user.username}{user.employee_id ? ` · employee ID ${user.employee_id}` : ''}</p>
      <form className="card form narrow" onSubmit={save}>
        <Field label="Current password"><input type="password" value={old} onChange={(e) => setOld(e.target.value)} required /></Field>
        <Field label="New password" hint="At least 8 characters"><input type="password" value={pw} onChange={(e) => setPw(e.target.value)} minLength={8} required /></Field>
        <Field label="Repeat new password"><input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} minLength={8} required /></Field>
        <button className="btn">Change password</button>
      </form>
    </>
  );
}
