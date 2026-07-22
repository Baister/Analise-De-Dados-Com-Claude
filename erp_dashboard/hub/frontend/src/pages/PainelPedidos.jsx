import { useState, useEffect, useMemo } from 'react';
import { apiFetch } from '../hooks/useApi';
import { brl } from '../utils/format';

const AMBAR = '#d29922', AZUL = '#1f6feb', VERDE = '#238636';

// Fila viva da view (pré-faturamento). Quem fatura SOME da view → coluna Saiu
// vem das NFs do dia (endpoint envia separado em `saiu`).
const CHIP = {
  5: { txt: 'CONFERÊNCIA', cor: AMBAR },
  3: { txt: 'FATURAMENTO', cor: AZUL },
};

const hora = d => (d ? String(d).slice(11, 16) : '');

function Linha({ razao, sub, chipTxt, chipCor, brilho }) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-lg bg-bg border border-card_border min-w-0"
      style={{ borderLeft: `4px solid ${chipCor}`, boxShadow: brilho ? `0 0 12px ${VERDE}44` : 'none' }}>
      <div className="min-w-0">
        <p className="text-text_main font-extrabold leading-tight truncate"
          style={{ fontSize: 'clamp(15px, 1.4vw, 20px)', letterSpacing: '0.3px' }}>
          {razao}
        </p>
        <p className="text-subtext text-[11px] mt-0.5 truncate">{sub}</p>
      </div>
      <span className="text-[10px] font-bold px-2.5 py-1 rounded-full whitespace-nowrap"
        style={{ background: `${chipCor}22`, color: chipCor, border: `1px solid ${chipCor}55` }}>
        {chipTxt}
      </span>
    </div>
  );
}

function Coluna({ titulo, cor, children, qtd, vazio }) {
  return (
    <div className="bg-card border border-card_border rounded-xl p-4 flex-1 min-w-0 w-full"
      style={{ borderTop: `3px solid ${cor}` }}>
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-extrabold uppercase" style={{ color: cor, fontSize: 'clamp(16px, 1.6vw, 22px)', letterSpacing: '1.5px' }}>
          {titulo}
        </h2>
        <span className="text-2xl font-extrabold" style={{ color: cor }}>{qtd}</span>
      </div>
      <div className="flex flex-col gap-2">
        {qtd === 0 ? <p className="text-subtext text-sm text-center py-8">{vazio}</p> : children}
      </div>
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

  const filtra = (lista, q) => !q ? lista : lista.filter(p =>
    String(p.razao ?? '').toLowerCase().includes(q) ||
    String(p.cliente ?? '').toLowerCase().includes(q) ||
    String(p.pedido ?? '').toLowerCase().includes(q));
  const porPedido = (a, b) => (Number(a.pedido) || 0) - (Number(b.pedido) || 0);

  const [aguardando, saiu] = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return [
      filtra(data?.pedidos ?? [], q).sort(porPedido),
      filtra(data?.saiu ?? [], q).sort(porPedido),
    ];
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
            Fila pendente + NFs emitidas hoje · nº crescente · atualiza a cada 30s
            {data?.ts && <> · última consulta {data.ts}</>}
          </p>
        </div>
        <input type="text" placeholder="Buscar razão social ou nº do pedido…" value={busca}
          onChange={e => setBusca(e.target.value)}
          className="w-64 px-3 py-2 text-xs bg-card border border-card_border rounded-lg text-text_main placeholder-subtext focus:outline-none focus:border-accent" />
      </div>

      {erro && <p className="text-accent_red text-xs mb-2">Erro ao consultar: {erro}</p>}

      <div className="flex flex-col lg:flex-row gap-3 items-start w-full">
        <Coluna titulo="⏳ Aguardando" cor={AMBAR} qtd={aguardando.length}
          vazio="Nenhum pedido aguardando — esteira limpa!">
          {aguardando.map(p => {
            const chip = CHIP[p.status] ?? { txt: p.status_descr ?? '—', cor: '#8b949e' };
            return <Linha key={`a-${p.pedido}`} chipTxt={chip.txt} chipCor={chip.cor}
              razao={String(p.razao ?? p.cliente ?? '—').trim().toUpperCase()}
              sub={<>pedido <b className="text-text_main">{String(p.pedido).trim()}</b>
                {p.vendedor && <> · {String(p.vendedor).trim()}</>}
                {p.emissao && <> · emitido {String(p.emissao).slice(8, 10)}/{String(p.emissao).slice(5, 7)}</>}</>} />;
          })}
        </Coluna>
        <Coluna titulo="✓ Saiu Hoje" cor={VERDE} qtd={saiu.length}
          vazio="Nenhuma NF emitida hoje ainda.">
          {saiu.map(p => (
            <Linha key={`s-${p.pedido}-${p.nf}`} chipTxt="✓ SAIU" chipCor={VERDE} brilho
              razao={String(p.razao ?? p.cliente ?? '—').trim().toUpperCase()}
              sub={<>pedido <b className="text-text_main">{String(p.pedido).trim()}</b>
                {p.nf && <> · NF {String(p.nf).trim()}</>}
                {p.emissao && <> · {hora(p.emissao)}</>}
                {p.valor != null && <> · {brl(p.valor)}</>}</>} />
          ))}
        </Coluna>
      </div>

      <p className="text-subtext text-[10px] mt-3 opacity-70">
        Aguardando = fila viva do painel do ERP (conferência → faturamento; inclui pendências de dias anteriores) ·
        Saiu = pedidos com NF emitida HOJE (Fat=1, não cancelada) — ao faturar, o pedido sai da fila e aparece aqui.
      </p>
    </div>
  );
}
