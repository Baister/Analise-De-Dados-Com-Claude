import { useState, useEffect, useRef } from 'react';
import { apiFetch } from '../hooks/useApi';

const STATUS_COLOR = {
  ok:         '#238636',
  executando: '#d29922',
  erro:       '#da3633',
};

function fmt_secs(s) {
  if (s === null || s === undefined) return '—';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return m > 0 ? `${m}m ${sec < 10 ? '0' : ''}${sec}s` : `${sec}s`;
}

function BotDot({ status }) {
  const color = STATUS_COLOR[status] || '#8b949e';
  return (
    <span
      className="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0"
      style={{ background: color }}
    />
  );
}

function BotStatusBar({ bots, fetchAge }) {
  const entries = Object.entries(bots);
  if (!entries.length) return null;
  return (
    <div className="px-3 py-3 border-t border-card_border">
      <p className="text-subtext text-[9px] uppercase tracking-wider mb-2">Bots · Próx. atualização</p>
      <div className="flex flex-col gap-2">
        {entries.map(([name, info]) => {
          const rawSecs = info.seconds_until_next;
          const remaining = rawSecs !== null && rawSecs !== undefined
            ? Math.max(0, rawSecs - fetchAge)
            : null;

          let countdown;
          if (info.status === 'executando') {
            countdown = <span style={{ color: STATUS_COLOR.executando }} className="text-[9px]">atualizando…</span>;
          } else if (remaining === null) {
            countdown = <span className="text-[9px] text-subtext opacity-50">aguardando</span>;
          } else if (remaining === 0) {
            countdown = <span style={{ color: STATUS_COLOR.executando }} className="text-[9px]">em breve</span>;
          } else {
            countdown = <span className="text-[9px] text-subtext">{fmt_secs(remaining)}</span>;
          }

          return (
            <div key={name} className="flex items-center gap-1.5">
              <BotDot status={info.status} />
              <span className="text-subtext text-[10px] capitalize flex-1">{name}</span>
              {countdown}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function Sidebar({ routes, activePage, onNavigate }) {
  const [bots, setBots] = useState({});
  const [fetchAge, setFetchAge] = useState(0);
  const fetchTimeRef = useRef(Date.now());

  useEffect(() => {
    function fetchStatus() {
      apiFetch('/status')
        .then(d => {
          if (d) {
            setBots(d.bots || {});
            fetchTimeRef.current = Date.now();
            setFetchAge(0);
          }
        })
        .catch(() => {});
    }
    fetchStatus();
    const pollId = setInterval(fetchStatus, 30_000);

    // tick every second to decrement countdown
    const tickId = setInterval(() => {
      setFetchAge(Math.floor((Date.now() - fetchTimeRef.current) / 1000));
    }, 1000);

    return () => { clearInterval(pollId); clearInterval(tickId); };
  }, []);

  return (
    <aside className="w-[200px] bg-sidebar border-r border-card_border flex flex-col flex-shrink-0 overflow-hidden">
      <div className="px-4 py-5 border-b border-card_border">
        <h1 className="text-text_main font-bold text-sm leading-tight">G2 Analytics</h1>
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

      <BotStatusBar bots={bots} fetchAge={fetchAge} />
    </aside>
  );
}
