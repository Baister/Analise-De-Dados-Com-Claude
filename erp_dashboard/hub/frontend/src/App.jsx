import { useState, useCallback, Suspense, lazy } from 'react';
import { ROUTES } from './routes';
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

  useSSE(token ? handleBotUpdate : null);

  if (!token) {
    return <LoginScreen onLogin={() => setToken(localStorage.getItem('erp_token'))} />;
  }

  const activeRoute = ROUTES.find(r => r.key === activePage) || ROUTES[0];
  const PageComponent = lazy(activeRoute.component);

  return (
    <div className="flex h-screen bg-bg overflow-hidden">
      <Sidebar routes={ROUTES} activePage={activePage} onNavigate={setActivePage} />
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
