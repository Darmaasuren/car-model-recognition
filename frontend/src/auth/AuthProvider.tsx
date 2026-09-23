import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { getMe, login, logout } from '../api/auth';
import type { User } from '../api/auth';
import { AuthContext } from './AuthContext';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  async function refresh() {
    setLoading(true);
    setError('');
    try { setUser(await getMe()); }
    catch { setError('Сервертэй холбогдож чадсангүй.'); }
    finally { setLoading(false); }
  }
  useEffect(() => {
    let active = true;
    getMe().then(value => { if (active) setUser(value); })
      .catch(() => { if (active) setError('Сервертэй холбогдож чадсангүй.'); })
      .finally(() => { if (active) setLoading(false); });
    const expired = () => setUser(null);
    window.addEventListener('auth-expired', expired);
    // Also checks idle sessions and logout from another browser tab.
    const interval = window.setInterval(() => {
      getMe().then(value => { if (active) setUser(value); }).catch(() => {});
    }, 60000);
    return () => { active = false; clearInterval(interval); window.removeEventListener('auth-expired', expired); };
  }, []);
  return <AuthContext.Provider value={{ user, loading, error, refresh,
    signIn: async (username, password) => { setUser(await login(username, password)); setError(''); },
    signOut: async () => { await logout(); setUser(null); },
  }}>{children}</AuthContext.Provider>;
}
