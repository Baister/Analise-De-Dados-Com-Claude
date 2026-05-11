import { useState, useCallback } from 'react';
import { apiFetch } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import FilterBar from '../components/FilterBar';
import BarChart from '../charts/BarChart';
import PieChart from '../charts/PieChart';
import DataTable from '../components/DataTable';
import { brl, shortBrl, fmtDate } from '../utils/format';

const DETALHE_COLS = [
  { key: 'NrDoc', label: 'Nº Doc' },
  { key: 'DtVnd', label: 'Data', render: v => (v ? fmtDate(v) : '—') },
  { key: 'NomeProduto', label: 'Produto' },
  { key: 'DescrMarca', label: 'Marca' },
  { key: 'QtdVnd', label: 'Qtd', render: v => String(v ?? 0) },
  { key: 'VlrTotal', label: 'Valor', render: v => brl(v) },
  { key: 'Vendedor', label: 'Vendedor' },
];

export default function Cliente() {
  const [filters, setFilters] = useState({
    de: '',
    ate: '',
    vendedor: '',
    cliente: '',
    marca: '',
    produto: '',
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const filterDefs = [
    { key: 'de', label: 'Data', type: 'daterange' },
    { key: 'cliente', label: 'Cliente', type: 'text', placeholder: 'Nome ou código…' },
    { key: 'vendedor', label: 'Vendedor', type: 'text', placeholder: 'Nome…' },
    { key: 'marca', label: 'Marca', type: 'text', placeholder: 'Marca…' },
    { key: 'produto', label: 'Produto', type: 'text', placeholder: 'Produto…' },
  ];

  const buscar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        de: filters.de_de ?? '',
        ate: filters.de_ate ?? '',
        vendedor: filters.vendedor ?? '',
        cliente: filters.cliente ?? '',
        marca: filters.marca ?? '',
        produto: filters.produto ?? '',
      });
      const res = await apiFetch(`/dados/cliente?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  const topClientes = data?.top_clientes ?? [];
  const porMarca = data?.por_marca ?? [];
  const detalhe = data?.detalhe ?? [];

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold text-text_main">Análise por Cliente</h1>

      <div className="bg-sidebar border border-card_border rounded-lg px-4 py-3 space-y-3">
        <FilterBar filters={filterDefs} values={filters} onChange={setFilters} />
        <div className="flex items-center gap-3">
          <button
            onClick={buscar}
            disabled={loading}
            className="px-4 py-2 bg-accent text-white text-sm rounded-md hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Buscando…' : 'Aplicar Filtros'}
          </button>
          {error && <span className="text-accent_red text-xs">{error}</span>}
        </div>
      </div>

      {!data && !loading && (
        <div className="flex items-center justify-center h-48 text-subtext text-sm">
          Defina os filtros e clique em "Aplicar Filtros" para buscar dados.
        </div>
      )}

      {data && (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard label="Total Faturado" value={brl(data.kpis?.total_faturado ?? 0)} variant="default" />
            <KpiCard label="Qtd Documentos" value={String(data.kpis?.qtd_documentos ?? 0)} variant="default" />
            <KpiCard label="Ticket Médio" value={brl(data.kpis?.ticket_medio ?? 0)} variant="default" />
            <KpiCard label="Clientes" value={String(data.kpis?.qtd_clientes ?? 0)} variant="default" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Top clientes */}
            <div className="bg-card border border-card_border rounded-lg p-4">
              <h2 className="text-sm font-semibold text-text_main mb-3">Top Clientes</h2>
              <BarChart
                data={topClientes.slice(0, 10)}
                xKey="NomeCli"
                bars={[{ key: 'total_comprado', label: 'Total', formatter: shortBrl }]}
                horizontal
                showLabels
                height={220}
              />
            </div>

            {/* Por marca */}
            <div className="bg-card border border-card_border rounded-lg p-4">
              <h2 className="text-sm font-semibold text-text_main mb-3">Por Marca</h2>
              <PieChart
                data={porMarca.slice(0, 6)}
                nameKey="DescrMarca"
                valueKey="valor"
                showValue
                formatter={shortBrl}
                height={220}
              />
            </div>
          </div>

          {/* Detalhe de documentos */}
          <div className="bg-card border border-card_border rounded-lg p-4">
            <h2 className="text-sm font-semibold text-text_main mb-3">
              Detalhe ({detalhe.length} registros)
            </h2>
            <DataTable columns={DETALHE_COLS} rows={detalhe} />
          </div>
        </>
      )}
    </div>
  );
}
