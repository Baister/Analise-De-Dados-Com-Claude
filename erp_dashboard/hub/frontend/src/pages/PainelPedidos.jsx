import { useState, useEffect, useMemo } from 'react';
import { apiFetch } from '../hooks/useApi';
import DataTable from '../components/DataTable';
import { brl, fmtDate } from '../utils/format';

const AMBAR = '#d29922', AZUL = '#1f6feb', VERDE = '#238636', VERM = '#da3633', ROXO = '#a371f7';

// Cores por status (catálogo TbStatusOrcPedConsig); desconhecidos caem no cinza
const COR_STATUS = { 5: AMBAR, 3: AZUL, 2: ROXO, 44: ROXO, 45: ROXO, 46: ROXO, 47: ROXO, 48: ROXO, 49: ROXO, 50: ROXO };
// Fluxo REAL (comprovado no TbOrcPedVndLog): o pedido espera dias em
// FATURAMENTO (3); a CONFERÊNCIA (5) é a última parada — minutos antes de
// concluir (5→1 direto, nunca 5→3). Tabelas na ordem do fluxo:
const ORDEM_STATUS = { 3: 0, 5: 1 };

const hora = d => (d ? String(d).slice(11, 16) : '—');
const razaoDe = p => String(p.razao ?? p.cliente ?? '—').trim().toUpperCase();

const agingBadge = h => {
  if (h == null) return '—';
  const [c, bg] = h <= 24 ? ['#4ade80', 'rgba(35,134,54,0.15)']
    : h <= 72 ? ['#fbbf24', 'rgba(210,153,34,0.15)'] : ['#f87171', 'rgba(218,54,51,0.15)'];
  const txt = h < 24 ? `${h}h` : `${Math.floor(h / 24)}d ${h % 24}h`;
  return <span style={{ fontSize: 10, fontWeight: 700, padding: '1px 8px', borderRadius: 9999, background: bg, color: c }}>{txt}</span>;
};

const COLS_FILA = [
  { key: 'pedido', label: 'Pedido', render: v => <b style={{ fontFamily: 'monospace' }}>{String(v).trim()}</b> },
  { key: 'razao', label: 'Razão Social', render: (v, r) => <span className="font-semibold">{razaoDe(r)}</span> },
  { key: 'vendedor', label: 'Vendedor', render: v => String(v ?? '—').trim() },
  { key: 'emissao', label: 'Emitido', render: v => fmtDate(v) },
  { key: 'entrega', label: 'Entrega', render: (v, r) => v
      ? <span style={{ color: new Date(v) < new Date() ? '#f87171' : undefined }}>{fmtDate(v)}</span> : '—' },
  { key: 'tp_entrega', label: 'Logística', render: (v, r) => {
      const tipo = String(v ?? '').replace(/^\d+-/, '').trim();
      const rota = String(r.rota ?? '').trim();
      if (!tipo && !rota) return '—';
      const retira = /retira/i.test(tipo);
      return <span style={{ fontSize: 10, fontWeight: 600, padding: '1px 8px', borderRadius: 9999,
        background: retira ? 'rgba(163,113,247,0.15)' : 'rgba(31,111,235,0.15)',
        color: retira ? '#c4a7f7' : '#79c0ff' }}>{retira ? '🏬 Retira na Loja' : `🚚 ${rota || tipo || 'Entrega'}`}</span>;
    } },
  { key: 'valor', label: 'Valor', align: 'right', render: v => (v != null ? brl(v) : '—') },
  { key: 'horas_fila', label: 'Na fila', render: v => agingBadge(v) },
];

const COLS_SAIU = [
  { key: 'pedido', label: 'Pedido', render: v => <b style={{ fontFamily: 'monospace' }}>{String(v).trim()}</b> },
  { key: 'razao', label: 'Razão Social', render: (v, r) => <span className="font-semibold">{razaoDe(r)}</span> },
  { key: 'nf', label: 'NF', render: v => <span style={{ fontFamily: 'monospace' }}>{String(v ?? '—').trim()}</span> },
  { key: 'emissao', label: 'Hora', render: v => hora(v) },
  { key: 'valor', label: 'Valor', align: 'right', render: v => (v != null ? brl(v) : '—') },
];

function Secao({ titulo, cor, qtd, children, right }) {
  return (
    <div className="bg-card border border-card_border rounded-xl p-4 min-w-0 w-full mb-3"
      style={{ borderTop: `3px solid ${cor}` }}>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-1">
        <h2 className="font-extrabold uppercase" style={{ color: cor, fontSize: 15, letterSpacing: '1.2px' }}>
          {titulo} <span className="ml-1">({qtd})</span>
        </h2>
        {right && <span className="text-[10px] text-subtext">{right}</span>}
      </div>
      {children}
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

  const [grupos, saiu, totalFila] = useMemo(() => {
    const q = busca.trim().toLowerCase();
    const casa = p => !q || razaoDe(p).toLowerCase().includes(q) || String(p.pedido ?? '').toLowerCase().includes(q);
    const fila = (data?.pedidos ?? []).filter(casa);
    const porStatus = new Map();
    for (const p of fila) {
      if (!porStatus.has(p.status)) porStatus.set(p.status, { descr: String(p.status_descr ?? p.status).trim(), rows: [] });
      porStatus.get(p.status).rows.push(p);
    }
    const ordenados = [...porStatus.entries()]
      .sort((a, b) => (ORDEM_STATUS[a[0]] ?? a[0] + 10) - (ORDEM_STATUS[b[0]] ?? b[0] + 10));
    return [ordenados, (data?.saiu ?? []).filter(casa), fila.length];
  }, [data, busca]);

  if (!data && !erro) return (
    <div className="flex items-center justify-center h-64 text-subtext text-sm">Consultando o painel ao vivo…</div>
  );

  return (
    <div className="p-4">
      <div className="flex items-end justify-between flex-wrap gap-2 mb-3">
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
            Uma tabela por status (catálogo do ERP) · nº decrescente · atualiza a cada 30s
            {data?.ts && <> · última consulta {data.ts}</>}
          </p>
        </div>
        <input type="text" placeholder="Buscar razão social ou nº do pedido…" value={busca}
          onChange={e => setBusca(e.target.value)}
          className="w-64 px-3 py-2 text-xs bg-card border border-card_border rounded-lg text-text_main placeholder-subtext focus:outline-none focus:border-accent" />
      </div>

      {erro && <p className="text-accent_red text-xs mb-2">Erro ao consultar: {erro}</p>}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 mb-4">
        <div className="bg-card border border-card_border rounded-lg px-4 py-3" style={{ borderTop: `2px solid ${AMBAR}` }}>
          <p className="text-[10px] text-subtext uppercase" style={{ letterSpacing: '0.8px' }}>Na fila</p>
          <p className="text-2xl font-bold mt-1" style={{ color: AMBAR }}>{totalFila}</p>
        </div>
        {grupos.slice(0, 2).map(([st, g]) => (
          <div key={st} className="bg-card border border-card_border rounded-lg px-4 py-3"
            style={{ borderTop: `2px solid ${COR_STATUS[st] ?? '#8b949e'}` }}>
            <p className="text-[10px] text-subtext uppercase truncate" style={{ letterSpacing: '0.8px' }}>{g.descr}</p>
            <p className="text-2xl font-bold mt-1" style={{ color: COR_STATUS[st] ?? '#8b949e' }}>{g.rows.length}</p>
          </div>
        ))}
        <div className="bg-card border border-card_border rounded-lg px-4 py-3" style={{ borderTop: `2px solid ${VERDE}` }}>
          <p className="text-[10px] text-subtext uppercase" style={{ letterSpacing: '0.8px' }}>Saíram hoje (NF)</p>
          <p className="text-2xl font-bold mt-1" style={{ color: VERDE }}>{saiu.length}</p>
        </div>
      </div>

      {grupos.map(([st, g]) => (
        <Secao key={st} titulo={`⏳ ${g.descr}`} cor={COR_STATUS[st] ?? '#8b949e'} qtd={g.rows.length}
          right="entrega em vermelho = data vencida">
          <DataTable columns={COLS_FILA} rows={g.rows} />
        </Secao>
      ))}
      {grupos.length === 0 && (
        <Secao titulo="⏳ Fila" cor={AMBAR} qtd={0}><p className="text-subtext text-sm text-center py-6">Nenhum pedido aguardando — esteira limpa!</p></Secao>
      )}

      <Secao titulo="✓ Saiu Hoje — NF emitida" cor={VERDE} qtd={saiu.length} right="Fat=1, não canceladas">
        {saiu.length === 0
          ? <p className="text-subtext text-sm text-center py-6">Nenhuma NF emitida hoje ainda.</p>
          : <DataTable columns={COLS_SAIU} rows={saiu} />}
      </Secao>

      <p className="text-subtext text-[10px] mt-1 opacity-70">
        Status conforme catálogo oficial (TbStatusOrcPedConsig) · valor via TbOrcPedVnd · "Na fila" = tempo desde a
        emissão · ao faturar, o pedido sai da fila e entra em "Saiu Hoje".
      </p>
    </div>
  );
}
