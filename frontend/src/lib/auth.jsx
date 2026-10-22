import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import api, { tokenStore } from './api';

const AuthContext = createContext(null);

export const HOME_BY_ROLE = {
  Reporter: '/my-requests',
  Technician: '/tasks',
  Manager: '/manager',
  Admin: '/manager',
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(!!tokenStore.get());

  const loadMe = useCallback(async () => {
    if (!tokenStore.get()) { setLoading(false); return; }
    try {
      const { data } = await api.get('/auth/me');
      setUser(data);
    } catch {
      tokenStore.clear();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadMe(); }, [loadMe]);

  const finish = (data) => { tokenStore.set(data.access_token); setUser(data.user); return data.user; };

  const value = useMemo(() => ({
    user,
    loading,
    login: async (email, password) => finish((await api.post('/auth/login', { email, password })).data),
    register: async (payload) => finish((await api.post('/auth/register', payload)).data),
    logout: () => { tokenStore.clear(); setUser(null); },
    refresh: loadMe,
    setUser,
  }), [user, loading, loadMe]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
