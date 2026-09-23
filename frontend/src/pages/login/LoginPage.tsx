import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import './LoginPage.css';

export function LoginPage() {
  const { user, signIn } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to='/live' replace />;
  return <main className='login-page'><form className='login-card' onSubmit={async event => {
    event.preventDefault(); setBusy(true); setError('');
    try { await signIn(username, password); }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Нэвтрэхэд алдаа гарлаа.'); }
    finally { setBusy(false); }
  }}>
    <h1>Vehicle AI</h1><p>Танилтын системд нэвтрэх</p>
    <label htmlFor='username'>Username</label>
    <input id='username' autoComplete='username' required value={username}
      onChange={event => setUsername(event.target.value)} disabled={busy} />
    <label htmlFor='password'>Password</label>
    <input id='password' type='password' autoComplete='current-password' required
      value={password} onChange={event => setPassword(event.target.value)} disabled={busy} />
    {error && <p role='alert'>{error}</p>}
    <button type='submit' disabled={busy}>{busy ? 'Нэвтэрч байна…' : 'Нэвтрэх'}</button>
  </form></main>;
}
