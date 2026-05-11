import { useState } from 'react';
import { apiFetch } from '../hooks/useApi';

export default function LoginScreen({ onLogin }) {
  const [password, setPassword] = useState('');
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const data = await apiFetch('/auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      localStorage.setItem('erp_token', data.access_token);
      onLogin();
    } catch {
      setError('Senha incorreta ou servidor indisponível.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center">
      <form
        onSubmit={handleSubmit}
        className="bg-card border border-card_border rounded-xl p-8 w-80 shadow-xl"
      >
        <h1 className="text-text_main text-xl font-bold mb-1">ERP Analytics</h1>
        <p className="text-subtext text-xs mb-6">Dashboard Web</p>

        <label className="block text-subtext text-[10px] uppercase tracking-wider mb-1.5">
          Senha de acesso
        </label>
        <input
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          className="w-full bg-bg border border-card_border rounded-lg px-3 py-2 text-text_main text-sm mb-4 focus:outline-none focus:border-accent"
          autoFocus
          autoComplete="current-password"
        />
        {error && <p className="text-accent_red text-xs mb-3">{error}</p>}
        <button
          type="submit"
          disabled={loading || !password}
          className="w-full bg-accent text-white rounded-lg py-2 text-sm font-medium hover:opacity-90 disabled:opacity-40 transition-opacity"
        >
          {loading ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </div>
  );
}
