import { useState, useEffect, useMemo } from 'react';
import { apiFetch } from '../hooks/useApi';

const AMBAR = '#d29922', AZUL = '#1f6feb', ROXO = '#a371f7', VERDE = '#238636';

// status do ERP → coluna do telão (estilo fast-food: Em Preparo | Pronto)
const CHIP = {
  5: { txt: 'CONFERÊNCIA', cor: AMBAR },
  3: { txt: 'FATURAMENTO', cor: AZUL },
  6: { txt: 'NF EMITIDA', cor: ROXO },
  1: { txt: 'SAIU', cor: VERDE },
};
const PREPARO = [5, 3], PRONTO = [6, 1];

function Linha({ p, lado }) {
  const chip = CHIP[p.status] ?? { txt: p.status_descr ?? '—', cor: '#8b949e' };
  const razao = String(p.razao ?? p.cliente ?? '—').trim().toUpperCase();
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-lg bg-bg border border-card_border"
      style={{ borderLeft: `4px solid ${chip.cor}`, boxShadow: lado === 'pronto' && p.status === 1 ? `0 0 12px ${VERDE}44` : 'none' }}>
      <div className="min-w-0">
        <p className="text-text_main font-extrabold leading-tight truncate"
          style={{ fontSize: 'clamp(15px, 1.4vw, 20px)', letterSpacing: '0.3px' }}>
          {razao}
        </p>
        <p className="text-subtext text-[11px] mt-0.5">
          pedido <b className="text-text_main" style={{ fontFamily: 'monospace', fontSize: 13 }}>{String(p.pedido).trim()}</b>
          {p.vendedor && <> · {String(p.vendedor).trim()}</>}
        </p>
      </div>
      <span className="text-[10px] font-bold px-2.5 py-1 rounded-full whitespace-nowrap"
        style={{ background: `${chip.cor}22`, color: chip.cor, border: `1px solid ${chip.cor}55` }}>
        {p.status === 1 ? '✓ SAIU' : chip.txt}
      </span>
    </div>
  );
}

function Coluna({ titulo, cor, itens, lado, vazio }) {
  return (
    <div className="bg-card border border-card_border rounded-xl p-4 flex-1"
      style={{ borderTop: `3px solid ${cor}` }}>
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-extrabold uppercase" style={{ color: cor, fontSize: 'clamp(16px, 1.6vw, 22px)', letterSpacing: '1.5px' }}>
          {titulo}
        </h2>
        <span className="text-2xl font-extrabold" style={{ color: cor }}>{itens.length}</span>
      </div>
      <div className="flex flex-col gap-2">
        {itens.length === 0
          ? <p className="text-subtext text-sm text-center py-8">{vazio}</p>
          : itens.map(p => <Linha key={`${p.pedido}-${p.status}`} p={p} lado={lado} />)}
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

  const [preparo, pronto] = useMemo(() => {
    const q = busca.trim().toLowerCase();
    const lista = (data?.pedidos ?? []).filter(p => !q ||
      String(p.razao ?? '').toLowerCase().includes(q) ||
      String(p.cliente ?? '').toLowerCase().includes(q) ||
      String(p.pedido ?? '').toLowerCase().includes(q));
    const prep = lista.filter(p => PREPARO.includes(p.status))
      .sort((a, b) => String(a.emissao ?? '').localeCompare(String(b.emissao ?? '')));       // fila: mais antigo no topo
    const pron = lista.filter(p => PRONTO.includes(p.status))
      .sort((a, b) => String(b.editado ?? '').localeCompare(String(a.editado ?? '')));       // recém-prontos no topo
    return [prep, pron];
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
            Atualiza a cada 30s{data?.ts && <> · última consulta {data.ts}</>}
          </p>
        </div>
        <input type="text" placeholder="Buscar razão social ou nº do pedido…" value={busca}
          onChange={e => setBusca(e.target.value)}
          className="w-64 px-3 py-2 text-xs bg-card border border-card_border rounded-lg text-text_main placeholder-subtext focus:outline-none focus:border-accent" />
      </div>

      {erro && <p className="text-accent_red text-xs mb-2">Erro ao consultar: {erro}</p>}

      <div className="flex flex-col lg:flex-row gap-3 items-start">
        <Coluna titulo="⏳ Em Preparo" cor={AMBAR} itens={preparo} lado="preparo"
          vazio="Nenhum pedido em preparo — esteira limpa!" />
        <Coluna titulo="✓ Pronto · Saiu" cor={VERDE} itens={pronto} lado="pronto"
          vazio="Nenhum pedido pronto ainda." />
      </div>

      <p className="text-subtext text-[10px] mt-3 opacity-70">
        Em Preparo = aguardando conferência/faturamento (mais antigos no topo) · Pronto = NF emitida ou concluído
        (recentes no topo) · consulta direta ao ERP, sem cache.
      </p>
    </div>
  );
}
