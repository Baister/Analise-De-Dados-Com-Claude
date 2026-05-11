import { useState } from 'react';
import { apiFetch } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import { pct, shortBrl } from '../utils/format';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

function DataTable({ title, rows, cols }) {
  if (!rows?.length) return null;
  return (
    <div className="bg-card border border-card_border rounded-lg p-4">
      <h3 className="text-sm font-semibold text-text_main mb-3">{title}</h3>
      <table className="w-full text-xs text-subtext">
        <thead>
          <tr className="border-b border-card_border">
            {cols.map(c => (
              <th key={c.key}
                  className={`pb-2 font-medium text-subtext ${c.right ? 'text-right' : 'text-left'}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-card_border last:border-0">
              {cols.map(c => (
                <td key={c.key} className={`py-2 ${c.right ? 'text-right' : ''}`}>
                  {c.fmt ? c.fmt(row[c.key]) : (row[c.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ClienteComportamento() {
  const [busca,   setBusca]   = useState('');
  const [de,      setDe]      = useState('');
  const [ate,     setAte]     = useState('');
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);
  const [dados,   setDados]   = useState(null);

  async function handleAplicar(e) {
    e.preventDefault();
    if (!busca.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ cliente: busca.trim() });
      if (de)  params.set('de',  de);
      if (ate) params.set('ate', ate);
      const d = await apiFetch(`/dados/cliente_comportamento?${params}`);
      setDados(d);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const kpis        = dados?.kpis            ?? {};
  const info        = dados?.cliente_info    ?? {};
  const evolucao    = dados?.evolucao_mensal ?? [];
  const topMarcas   = dados?.top_marcas      ?? [];
  const topProdutos = dados?.top_produtos    ?? [];

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold text-text_main">Comportamento de Clientes</h1>

      {/* Busca */}
      <form
        onSubmit={handleAplicar}
        className="bg-card border border-card_border rounded-lg p-4 flex flex-wrap gap-3 items-end"
      >
        <div className="flex flex-col gap-1 flex-1 min-w-48">
          <label className="text-xs text-subtext font-medium">Buscar cliente</label>
          <input
            className="bg-bg border border-card_border rounded px-3 py-2 text-sm text-text_main
                       placeholder-subtext focus:outline-none focus:border-accent_blue"
            placeholder="Nome ou código..."
            value={busca}
            onChange={e => setBusca(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-subtext font-medium">De</label>
          <input
            type="date"
            className="bg-bg border border-card_border rounded px-3 py-2 text-sm text-text_main
                       focus:outline-none focus:border-accent_blue"
            value={de}
            onChange={e => setDe(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-subtext font-medium">Até</label>
          <input
            type="date"
            className="bg-bg border border-card_border rounded px-3 py-2 text-sm text-text_main
                       focus:outline-none focus:border-accent_blue"
            value={ate}
            onChange={e => setAte(e.target.value)}
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="bg-accent_blue hover:opacity-90 text-white font-semibold px-5 py-2 rounded
                     text-sm disabled:opacity-50 transition-opacity"
        >
          {loading ? 'Buscando…' : 'Aplicar'}
        </button>
      </form>

      {error && (
        <div className="bg-card border border-accent_red rounded-lg p-4 text-accent_red text-sm">
          Erro: {error}
        </div>
      )}

      {!dados && !loading && (
        <div className="flex items-center justify-center h-48 text-subtext text-sm">
          Busque um cliente acima para ver a análise de comportamento.
        </div>
      )}

      {loading && !dados && (
        <div className="flex items-center justify-center h-48 text-subtext text-sm">
          Buscando dados…
        </div>
      )}

      {dados && (
        <>
          {/* Banner do cliente */}
          {info.nome && (
            <div className="bg-gradient-to-r from-[#1f2f4d] to-card border border-accent_blue/30 rounded-lg p-5">
              <p className="text-xs text-subtext font-medium mb-1 uppercase tracking-wider">
                Cliente selecionado
              </p>
              <p className="text-2xl font-bold text-text_main">{info.nome}</p>
              <div className="flex gap-6 mt-2">
                {info.cod      && <span className="text-xs text-subtext">Cód: {info.cod}</span>}
                {info.vendedor && <span className="text-xs text-subtext">Vendedor: {info.vendedor}</span>}
              </div>
            </div>
          )}

          {/* 5 KPIs */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <KpiCard label="Venda Bruta"   value={shortBrl(kpis.venda_bruta   ?? 0)} variant="success" />
            <KpiCard label="Devolução"     value={shortBrl(kpis.devolucao     ?? 0)} variant="error"   />
            <KpiCard label="Venda Líquida" value={shortBrl(kpis.venda_liquida ?? 0)} variant="default" />
            <KpiCard label="Margem %"      value={pct(kpis.margem_pct         ?? 0)} variant="warning" />
            <KpiCard label="Ticket Médio"  value={shortBrl(kpis.ticket_medio  ?? 0)} variant="default" />
          </div>

          {/* Gráfico de área — evolução mensal */}
          {evolucao.length > 0 && (
            <div className="bg-card border border-card_border rounded-lg p-4">
              <h2 className="text-sm font-semibold text-text_main mb-4">Evolução Mensal de Vendas</h2>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={evolucao} margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
                  <defs>
                    <linearGradient id="gradCliVB" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#1f6feb" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#1f6feb" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
                  <XAxis dataKey="mes" tick={{ fill: '#8b949e', fontSize: 10 }} />
                  <YAxis tickFormatter={v => shortBrl(v)} tick={{ fill: '#8b949e', fontSize: 10 }} />
                  <Tooltip
                    formatter={(v, name) => [
                      shortBrl(v),
                      name === 'venda_bruta' ? 'Venda Bruta' : 'Devolução',
                    ]}
                    contentStyle={{ background: '#1c2128', border: '1px solid #30363d', borderRadius: 6 }}
                    labelStyle={{ color: '#e6edf3' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="venda_bruta"
                    stroke="#1f6feb"
                    fill="url(#gradCliVB)"
                    strokeWidth={2}
                    dot={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Tabelas lado a lado */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <DataTable
              title="Top Marcas Compradas"
              rows={topMarcas}
              cols={[
                { key: 'DescrMarca',  label: 'Marca' },
                { key: 'faturamento', label: 'Valor', right: true, fmt: shortBrl },
                { key: 'quantidade',  label: 'Qtd',   right: true },
              ]}
            />
            <DataTable
              title="Top Produtos Comprados"
              rows={topProdutos}
              cols={[
                { key: 'DescrItem',   label: 'Produto' },
                { key: 'faturamento', label: 'Valor',   right: true, fmt: shortBrl },
                { key: 'quantidade',  label: 'Qtd',     right: true },
              ]}
            />
          </div>
        </>
      )}
    </div>
  );
}
