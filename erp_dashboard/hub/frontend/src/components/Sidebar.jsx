import { useState, useEffect } from 'react';
import { apiFetch } from '../hooks/useApi';

const STATUS_COLOR = {
  ok:         '#238636',
  executando: '#d29922',
  erro:       '#da3633',
};

function BotDot({ status }) {
  const color = STATUS_COLOR[status] || '#8b949e';
  return (
    <span
      className="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0"
      style={{ background: color }}
    />
  );
}

function BotStatusBar({ bots }) {
  const entries = Object.entries(bots);
  if (!entries.length) return null;
  return (
    <div className="px-4 py-3 border-t border-card_border">
      <p className="text-subtext text-[9px] uppercase tracking-wider mb-2">Bots</p>
      <div className="flex flex-col gap-1.5">
        {entries.map(([name, info]) => (
          <div key={name} className="flex items-center gap-2">
            <BotDot status={info.status} />
            <span className="text-subtext text-[10px] capitalize">{name}</span>
            {info.ultimo_update && (
              <span className="text-[9px] text-subtext ml-auto opacity-60">
                {info.ultimo_update}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Sidebar({ routes, activePage, onNavigate }) {
  const [bots, setBots] = useState({});

  useEffect(() => {
    function fetchStatus() {
      apiFetch('/status')
        .then(d => setBots(d.bots || {}))
        .catch(() => {});
    }
    fetchStatus();
    const id = setInterval(fetchStatus, 30_000);
    return () => clearInterval(id);
  }, []);

  return (
    <aside className="w-[200px] bg-sidebar border-r border-card_border flex flex-col flex-shrink-0 overflow-hidden">
      <div className="px-4 py-5 border-b border-card_border">
        <h1 className="text-text_main font-bold text-sm leading-tight">ERP Analytics</h1>
        <p className="text-subtext text-[10px] mt-0.5">Dashboard</p>
      </div>

      <nav className="flex-1 py-2 overflow-y-auto">
        {routes.map(route => {
          const isActive = activePage === route.key;
          return (
            <button
              key={route.key}
              onClick={() => onNavigate(route.key)}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors text-left ${
                isActive
                  ? 'bg-accent text-white font-medium'
                  : 'text-subtext hover:text-text_main hover:bg-card'
              }`}
            >
              <span className="text-base leading-none">{route.icon}</span>
              <span>{route.label}</span>
            </button>
          );
        })}
      </nav>

      <BotStatusBar bots={bots} />
    </aside>
  );
}
