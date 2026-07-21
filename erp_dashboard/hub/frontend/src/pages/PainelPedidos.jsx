import { useState, useEffect, useMemo } from 'react';
import { apiFetch } from '../hooks/useApi';
import { fmtDate } from '../utils/format';

const AMBAR = '#d29922', AZUL = '#1f6feb', ROXO = '#a371f7', VERDE = '#238636', VERM = '#da3633';

// Fluxo do pedido: status do ERP → etapa do rastreador (1..4)
const FLOW = {
  5: { etapa: 1, rotulo: 'Aguardando Conferência', cor: AMBAR },
  3: { etapa: 2, rotulo: 'Aguardando Faturamento', cor: AZUL },
  6: { etapa: 3, rotulo: 'NF Emitida', cor: ROXO },
  1: { etapa: 4, rotulo: 'Concluído — Saiu', cor: VERDE },
};
const ETAPAS = ['Conferência', 'Faturamento', 'NF Emitida', 'Saiu'];

function Stepper({ etapa, cor }) {
  return (
    <div className="flex items-center gap-0 mt-3">
      {ETAPAS.map((nome, i) => {
        const n = i + 1, done = n < etapa, atual = n === etapa;
        const c = done || atual ? cor : '#30363d';
        return (
          <div key={nome} className="flex items-center" style={{ flex: n < 4 ? 1 : 'none' }}>
            <div className="flex flex-col items-center" style={{ minWidth: 64 }}>
              <div className="rounded-full flex items-center justify-center"
                style={{ width: 22, height: 22, background: done ? c : 'transparent',
                         border: `2px solid ${c}`, boxShadow: atual ? `0 0 10px ${c}` : 'none' }}>
                {done ? <span style={{ color: '#fff', fontSize: 11, fontWeight: 700 }}>✓</span>
                      : atual ? <span className="rounded-full animate-pulse" style={{ width: 8, height: 8, background: c }} />
                              : null}
              </div>
              <span className="text-[9px] mt-1" style={{ color: done || atual ? '#e6edf3' : '#8b949e' }}>{nome}</span>
            </div>
            {n < 4 && <div className="h-[2px] flex-1 mx-1 mb-4 rounded" style={{ background: done ? c : '#30363d' }} />}
          </div>
        );
      })}
    </div>
  );
}

export default function PainelPedidos() {
  const [data, setData] = useState(null);
  const [erro, setErro] = useState('');
  const [busca, setBusca] = useState('');

  useEffect(() => {
    let vivo = true;
    const carregar = async () => {
      try {
        const res = await apiFetch('/dados/painel_pedidos');
        if (vivo && res?.pedidos) { setData(res); setErro(''); }
      } catch (e) { if (vivo) setErro(String(e)); }
    };
    carregar();
    const t = setInterval(carregar, 30000);
    return () => { vivo = false; clearInterval(t); };
  }, []);

  const pedidos = useMemo(() => {
    const lista = data?.pedidos ?? [];
    const q = busca.trim().toLowerCase();
    const filtrada = q ? lista.filter(p =>
      String(p.cliente ?? '').toLowerCase().includes(q) ||
      String(p.pedido ?? '').toLowerCase().includes(q)) : lista;
    const ordem = { 5: 0, 3: 1, 6: 2, 1: 3 };
    return [...filtrada].sort((a, b) =>
      (ordem[a.status] ?? 9) - (ordem[b.status] ?? 9) || String(b.emissao).localeCompare(String(a.emissao)));
  }, [data, busca]);

  const resumo = data?.resumo ?? {};

  if (!data && !erro) return (
    <div className="flex items-center justify-center h-64 text-subtext text-sm">Consultando o painel ao vivo…</div>
  );

  return (
    <div className="p-4">
      <div className="flex items-end justify-between flex-wrap gap-2 mb-1">
        <div>
          <h1 className="text-text_main text-lg font-bold leading-tight flex items-center gap-2">
            Painel Pedido Conferência
            <span className="relative flex" style={{ width: 10, height: 10 }}>
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60" style={{ background: '#4ade80' }} />
              <span className="relative inline-flex rounded-full" style={{ width: 10, height: 10, background: '#4ade80' }} />
            </span>
            <span className="text-[10px] font-normal" style={{ color: '#4ade80' }}>AO VIVO</span>
          </h1>
          <p className="text-subtext text-[11px]">
            Esteira em tempo real (vmPainelPedidoVndConf) · atualiza a cada 30s
            {data?.ts && <> · consulta {data.ts}</>}
          </p>
        </div>
        <input type="text" placeholder="Buscar cliente ou nº do pedido…" value={busca}
          onChange={e => setBusca(e.target.value)}
          className="w-64 px-3 py-2 text-xs bg-card border border-card_border rounded-lg text-text_main placeholder-subtext focus:outline-none focus:border-accent" />
      </div>

      {erro && <p className="text-accent_red text-xs mb-2">Erro ao consultar: {erro}</p>}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 mt-3 mb-4">
        {[5, 3, 6, 1].map(s => (
          <div key={s} className="bg-card border border-card_border rounded-lg px-4 py-3"
            style={{ borderTop: `2px solid ${FLOW[s].cor}` }}>
            <p className="text-[10px] text-subtext uppercase" style={{ letterSpacing: '0.8px' }}>{FLOW[s].rotulo}</p>
            <p className="text-2xl font-bold mt-1" style={{ color: FLOW[s].cor }}>{resumo[s] ?? 0}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-2.5">
        {pedidos.length === 0 && (
          <p className="text-subtext text-sm text-center py-10">Nenhum pedido encontrado.</p>
        )}
        {pedidos.map(p => {
          const f = FLOW[p.status] ?? { etapa: 0, rotulo: p.status_descr || '—', cor: '#8b949e' };
          const saiu = p.status === 1, quase = p.status === 6;
          const atrasado = !saiu && p.entrega && new Date(p.entrega) < new Date();
          return (
            <div key={`${p.pedido}-${p.status}`} className="bg-card border border-card_border rounded-lg px-5 py-4"
              style={{ borderLeft: `3px solid ${f.cor}` }}>
              <div className="flex items-start justify-between flex-wrap gap-2">
                <div>
                  <p className="text-text_main text-[15px] font-bold leading-tight">{p.cliente || p.razao || '—'}</p>
                  <p className="text-subtext text-[11px] mt-0.5">
                    Pedido <b className="text-text_main">{String(p.pedido).trim()}</b>
                    {p.vendedor && <> · vend. {String(p.vendedor).trim()}</>}
                    {p.emissao && <> · emitido {fmtDate(p.emissao)}</>}
                    {p.entrega && <> · entrega {fmtDate(p.entrega)}</>}
                    {atrasado && <b style={{ color: VERM }}> · ENTREGA VENCIDA</b>}
                  </p>
                </div>
                <span className="text-[11px] font-bold px-3 py-1.5 rounded-full"
                  style={{ background: `${f.cor}22`, color: f.cor, border: `1px solid ${f.cor}55` }}>
                  {saiu ? '✓ SAIU' : quase ? 'NF EMITIDA — SAINDO' : `⏳ ${f.rotulo.toUpperCase()}`}
                </span>
              </div>
              <Stepper etapa={f.etapa} cor={f.cor} />
            </div>
          );
        })}
      </div>
      <p className="text-subtext text-[10px] mt-3 opacity-70">
        Consulta direta à view do ERP a cada acesso — sem cache. “Saiu” = pedido concluído no painel de conferência.
      </p>
    </div>
  );
}
