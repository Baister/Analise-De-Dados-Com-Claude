import { useFilteredDados } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import PieChart from '../charts/PieChart';
import DataTable from '../components/DataTable';
import { brl, shortBrl, fmtDate } from '../utils/format';

const INAD_COLS = [
  { key: 'CodCli', label: 'Cód.' },
  { key: 'NomeCli', label: 'Cliente' },
  { key: 'QtdTitulos', label: 'Títulos', render: v => String(v ?? 0) },
  { key: 'VlrTotal', label: 'Valor Total', render: v => brl(v) },
  { key: 'DtVenctoMaisAntigo', label: 'Vencto Mais Antigo', render: v => (v ? fmtDate(v) : '—') },
  { key: 'DiasAtraso', label: 'Dias Atraso', render: v => String(v ?? 0) },
];

export default function Financeiro({ refreshTrigger }) {
  const { data, loading, error, isEmpty } = useFilteredDados('financeiro', {}, refreshTrigger);

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64 text-subtext text-sm">
        Carregando dados financeiros…
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="flex items-center justify-center h-64 text-accent_red text-sm">
        Erro ao carregar dados: {error}
      </div>
    );
  }

  if (isEmpty) {
    return (
      <div className="flex items-center justify-center h-64 text-subtext text-sm">
        <div className="text-center space-y-1">
          <p>Bot Financeiro está processando dados do banco…</p>
          <p className="text-xs opacity-60">A página atualiza automaticamente quando concluir.</p>
        </div>
      </div>
    );
  }

  const inadimplentes = data?.top_inadimplentes ?? [];
  const porTipo = data?.por_tipo_recebimento ?? [];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text_main">Financeiro</h1>
        {data?.ultimo_update && (
          <span className="text-subtext text-xs">Atualizado: {data.ultimo_update}</span>
        )}
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Recebido no Mês" value={brl(data?.recebido_mes ?? 0)} variant="success" />
        <KpiCard label="A Receber" value={brl(data?.a_receber ?? 0)} variant="default" />
        <KpiCard
          label="Inadimplência"
          value={brl(data?.total_inadimplente ?? 0)}
          variant={data?.total_inadimplente > 0 ? 'error' : 'success'}
        />
        <KpiCard label="Qtd Inadimplentes" value={String(data?.qtd_inadimplentes ?? 0)} variant="default" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Por tipo de recebimento */}
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Por Tipo de Recebimento</h2>
          <PieChart
            data={porTipo.slice(0, 6)}
            nameKey="TipoRecebimento"
            valueKey="valor"
            showValue
            formatter={shortBrl}
            height={220}
          />
        </div>

        {/* Resumo adicional */}
        <div className="bg-card border border-card_border rounded-lg p-4 flex flex-col gap-4">
          <h2 className="text-sm font-semibold text-text_main">Resumo</h2>
          <div className="space-y-3 text-sm">
            {[
              { label: 'Maior inadimplente', value: inadimplentes[0]?.NomeCli ?? '—' },
              { label: 'Valor maior inadimplente', value: brl(inadimplentes[0]?.VlrTotal) },
              { label: 'Maior atraso (dias)', value: String(inadimplentes[0]?.DiasAtraso ?? 0) },
            ].map(item => (
              <div key={item.label} className="flex justify-between">
                <span className="text-subtext">{item.label}</span>
                <span className="text-text_main font-medium">{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Top inadimplentes */}
      <div className="bg-card border border-card_border rounded-lg p-4">
        <h2 className="text-sm font-semibold text-text_main mb-3">
          Top Inadimplentes ({inadimplentes.length})
        </h2>
        <DataTable columns={INAD_COLS} rows={inadimplentes} />
      </div>
    </div>
  );
}
