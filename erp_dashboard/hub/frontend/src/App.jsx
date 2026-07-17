import { useState, useCallback, useMemo, Suspense, lazy } from 'react';
import { ROUTES } from './routes';

// lazy() UMA vez por rota (escopo de módulo) — recriar a cada render força
// unmount/remount da página ativa a cada evento SSE, perdendo filtros/estado.
const LAZY_PAGES = Object.fromEntries(ROUTES.map(r => [r.key, lazy(r.component)]));
import LoginScreen from './components/LoginScreen';
import Sidebar from './components/Sidebar';
import { useSSE } from './hooks/useSSE';

function LoadingFallback() {
  return (
    <div className="flex items-center justify-center h-40">
      <p className="text-subtext text-sm">Carregando…</p>
    </div>
  );
}

export default function App() {
  const [token, setToken]           = useState(() => localStorage.getItem('erp_token'));
  const [activePage, setActivePage] = useState(ROUTES[0].key);
  const [lastUpdate, setLastUpdate] = useState({});

  const handleBotUpdate = useCallback((botKey) => {
    setLastUpdate(prev => ({ ...prev, [botKey]: Date.now() }));
  }, []);

  useSSE(handleBotUpdate, token);

  // Abas permitidas pelo perfil (senha). "*" = todas. Filtra ROUTES.
  const allowedTabs = useMemo(() => {
    try { return JSON.parse(localStorage.getItem('erp_tabs') || '["*"]'); }
    catch { return ['*']; }
  }, [token]);

  const visibleRoutes = useMemo(() =>
    allowedTabs.includes('*') ? ROUTES : ROUTES.filter(r => allowedTabs.includes(r.key)),
  [allowedTabs]);

  if (!token) {
    return <LoginScreen onLogin={() => setToken(localStorage.getItem('erp_token'))} />;
  }

  // Aba ativa precisa ser uma das visíveis (fallback p/ a primeira permitida)
  const activeRoute = visibleRoutes.find(r => r.key === activePage) || visibleRoutes[0];
  const PageComponent = LAZY_PAGES[activeRoute.key];

  return (
    <div className="flex h-screen bg-bg overflow-hidden">
      <Sidebar routes={visibleRoutes} activePage={activeRoute.key} onNavigate={setActivePage} />
      <main className="flex-1 overflow-y-auto p-6">
        <Suspense fallback={<LoadingFallback />}>
          <PageComponent
            refreshTrigger={lastUpdate[activeRoute.botKey]}
            botKey={activeRoute.botKey}
          />
        </Suspense>
      </main>
    </div>
  );
}
