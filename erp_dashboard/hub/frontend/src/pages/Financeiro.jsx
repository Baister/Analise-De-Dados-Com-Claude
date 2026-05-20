import { useMemo } from 'react';
import { useFilteredDados } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import PieChart from '../charts/PieChart';
import BarChart from '../charts/BarChart';
import { brl, shortBrl, fmtDate } from '../utils/format';

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------
const STATUS_STYLE = {
  Vencido:  'bg-red-900/40 text-red-400 border border-red-800',
  Pendente: 'bg-blue-900/40 text-blue-400 border border-blue-800',
  Pago:     'bg-green-900/40 text-green-400 border border-green-800',
};

const StatusBadge = ({ status }) => (
  <span
    className={`px-2 py-0.5 rounded text-[10px] font-medium ${STATUS_STYLE[status] ?? 'bg-gray-800 text-subtext'}`}
  >
    {status ?? '—'}
  </span>
);

// ---------------------------------------------------------------------------
// Column definitions
// ---------------------------------------------------------------------------
const TITULOS_CR_COLS = [
  { key: 'NrDoc', label: 'Doc' },
  { key: 'NomeCli', label: 'Cliente' },
  { key: 'DtVcto', label: 'Vencimento', render: v => fmtDate(v) },
  { key: 'Parcela', label: 'Parcela' },
  { key: 'VlrTitulo', label: 'Valor', render: v => brl(v) },
  { key: 'TipoRecebimento', label: 'Tipo' },
  { key: 'DiasAtraso', label: 'Atraso', render: v => String(v ?? 0) },
  { key: 'Status', label: 'Status', render: v => <StatusBadge status={v} /> },
];

const INAD_COLS = [
  { key: 'CodCli', label: 'Cód.' },
  { key: 'NomeCli', label: 'Cliente' },
  { key: 'QtdTitulos', label: 'Títulos', render: v => String(v ?? 0) },
  { key: 'VlrTotal', label: 'Valor Total', render: v => brl(v) },
  { key: 'DtVenctoMaisAntigo', label: 'Vencto Mais Antigo', render: v => fmtDate(v) },
  { key: 'DiasAtraso', label: 'Dias Atraso', render: v => String(v ?? 0) },
];

const TITULOS_CP_COLS = [
  { key: 'NrDoc', label: 'Doc' },
  { key: 'NomeForn', label: 'Fornecedor' },
  { key: 'DtVcto', label: 'Vencimento', render: v => fmtDate(v) },
  { key: 'Parcela', label: 'Parcela' },
  { key: 'VlrTitulo', label: 'Valor', render: v => brl(v) },
  { key: 'TipoPagto', label: 'Tipo' },
  { key: 'DiasAtraso', label: 'Atraso', render: v => String(v ?? 0) },
  { key: 'Status', label: 'Status', render: v => <StatusBadge status={v} /> },
];

const NFE_COLS = [
  { key: 'NrNFE', label: 'NF-e' },
  { key: 'DtEmissao', label: 'Emissão', render: v => fmtDate(v) },
  { key: 'NomeDest', label: 'Destinatário' },
  { key: 'ValNFE', label: 'Valor', render: v => brl(v) },
  { key: 'Status', label: 'Status', render: v => <StatusBadge status={v} /> },
];

const PEDIDOS_COLS = [
  { key: 'NrPed', label: 'Pedido' },
  { key: 'NomeCli', label: 'Cliente' },
  { key: 'DtPed', label: 'Data', render: v => fmtDate(v) },
  { key: 'Status', label: 'Status', render: v => <StatusBadge status={v} /> },
];

const MOV_CC_COLS = [
  { key: 'CentroCusto', label: 'Centro de Custo' },
  { key: 'ValEntrada', label: 'Entrada', render: v => brl(v) },
  { key: 'ValSaida', label: 'Saída', render: v => brl(v) },
];

// ---------------------------------------------------------------------------
// Helper — aggregate mov_financeiro into Entrada/Saída per date (last 14 days)
// ---------------------------------------------------------------------------
function buildMovChart(movFinanceiro) {
  const byDate = {};
  for (const m of movFinanceiro) {
    const dt = m.DtMov ? String(m.DtMov).slice(0, 10) : null;
    if (!dt || dt === 'null') continue;
    if (!byDate[dt]) byDate[dt] = { data: dt, Entrada: 0, Saída: 0 };
    const val = Number(m.ValMov) || 0;
    const tipo = String(m.TipoMov ?? '').toLowerCase();
    if (tipo.includes('entrada') || tipo.includes('receb') || tipo === 'e' || tipo === 'r') {
      byDate[dt].Entrada += val;
    } else if (tipo.includes('saida') || tipo.includes('saída') || tipo.includes('pag') || tipo.includes('desp') || tipo === 's' || tipo === 'p') {
      byDate[dt].Saída += val;
    }
    // unknown types are silently skipped — no mislabelling
  }
  return Object.values(byDate).sort((a, b) => a.data.localeCompare(b.data)).slice(-14);
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function Financeiro({ refreshTrigger }) {
  const { data, loading, error, isEmpty } = useFilteredDados('financeiro', {}, refreshTrigger);

  // Destructure data with safe defaults — ALL hooks and derived state before early returns
  const fat_dia              = data?.fat_dia              ?? 0;
  const ticket_medio         = data?.ticket_medio         ?? 0;
  const total_a_receber      = data?.total_a_receber      ?? 0;
  const total_a_pagar        = data?.total_a_pagar        ?? 0;
  const fluxo_caixa          = data?.fluxo_caixa          ?? 0;
  const recebido_mes         = data?.recebido_mes         ?? 0;
  const total_inadimplente   = data?.total_inadimplente   ?? 0;
  const qtd_inadimplentes    = data?.qtd_inadimplentes    ?? 0;
  const indice_inadimplencia = data?.indice_inadimplencia ?? 0;

  const inadimplentes      = data?.top_inadimplentes    ?? [];
  const porTipo            = data?.por_tipo_recebimento ?? [];
  const rec_hoje           = data?.rec_hoje             ?? 0;
  const rec_semana         = data?.rec_semana           ?? 0;
  const a_vencer_20d       = data?.a_vencer_20d         ?? 0;
  const a_vencer_30d       = data?.a_vencer_30d         ?? 0;
  const titulosCR          = data?.titulos_lista        ?? [];

  const vencido_pagar      = data?.vencido_pagar        ?? 0;
  const a_vencer_pagar_20d = data?.a_vencer_pagar_20d   ?? 0;
  const titulosCP          = data?.titulos_pagar_lista  ?? [];

  const movFinanceiro = data?.mov_financeiro   ?? [];
  const movCC         = data?.mov_centro_custo ?? [];
  const nfeList       = data?.nfe_monitor      ?? [];
  const pedidosList   = data?.pedidos_conf     ?? [];

  const movChartData = useMemo(() => buildMovChart(movFinanceiro), [movFinanceiro]);

  const topInad = inadimplentes[0] ?? null;

  // Loading / error / empty guards
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
          <p>Bot Financeiro está processando dados…</p>
          <p className="text-xs opacity-60">A página atualiza automaticamente quando concluir.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* ------------------------------------------------------------------ */}
      {/* A. Header                                                            */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text_main">Financeiro</h1>
        {data?.ultimo_update && (
          <span className="text-subtext text-xs">Atualizado: {data.ultimo_update}</span>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* B. 8 KPI cards — 2 rows of 4                                        */}
      {/* ------------------------------------------------------------------ */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard label="Faturamento Hoje" value={shortBrl(fat_dia)} variant="default" />
        <KpiCard label="A Receber" value={brl(total_a_receber)} variant="default" />
        <KpiCard label="A Pagar" value={brl(total_a_pagar)} variant="warning" />
        <KpiCard
          label="Fluxo de Caixa"
          value={brl(fluxo_caixa)}
          variant={fluxo_caixa >= 0 ? 'success' : 'error'}
        />
        <KpiCard label="Recebido no Mês" value={brl(recebido_mes)} variant="success" />
        <KpiCard
          label="Inadimplência"
          value={brl(total_inadimplente)}
          variant={total_inadimplente > 0 ? 'error' : 'success'}
        />
        <KpiCard
          label="% Inadimplência"
          value={`${indice_inadimplencia.toFixed(1)}%`}
          variant={indice_inadimplencia > 5 ? 'warning' : 'default'}
        />
        <KpiCard label="Ticket Médio" value={brl(ticket_medio)} variant="default" />
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* C. Contas a Receber                                                  */}
      {/* ------------------------------------------------------------------ */}
      <div className="bg-card border border-card_border rounded-lg p-4 space-y-4">
        <h2 className="text-base font-semibold text-text_main border-b border-card_border pb-2">
          Contas a Receber
        </h2>

        {/* Mini-KPIs */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <KpiCard label="Recebido Hoje" value={shortBrl(rec_hoje)} variant="success" />
          <KpiCard label="Recebido na Semana" value={shortBrl(rec_semana)} variant="success" />
          <KpiCard label="A Vencer 20d" value={shortBrl(a_vencer_20d)} variant="default" />
          <KpiCard label="A Vencer 30d" value={shortBrl(a_vencer_30d)} variant="default" />
          <KpiCard
            label="QTD Inadimplentes"
            value={String(qtd_inadimplentes)}
            variant="warning"
          />
        </div>

        {/* Pie chart + Maior inadimplente */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-card border border-card_border rounded-lg p-4">
            <h3 className="text-sm font-semibold text-text_main mb-3">
              Por Tipo de Recebimento
            </h3>
            <PieChart
              data={porTipo.slice(0, 6)}
              nameKey="TipoRecebimento"
              valueKey="valor"
              showValue
              formatter={shortBrl}
              height={200}
            />
          </div>

          <div className="bg-card border border-card_border rounded-lg p-4">
            <h3 className="text-sm font-semibold text-text_main mb-3">
              Maior Inadimplente
            </h3>
            {topInad ? (
              <div className="space-y-3 text-sm mt-2">
                <div>
                  <p className="text-subtext text-[10px] uppercase tracking-wider mb-0.5">Cliente</p>
                  <p className="text-text_main font-semibold truncate">{topInad.NomeCli}</p>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <p className="text-subtext text-[10px] uppercase tracking-wider mb-0.5">Valor</p>
                    <p className="text-red-400 font-bold">{brl(topInad.VlrTotal)}</p>
                  </div>
                  <div>
                    <p className="text-subtext text-[10px] uppercase tracking-wider mb-0.5">Dias</p>
                    <p className="text-red-400 font-bold">{topInad.DiasAtraso ?? 0}d</p>
                  </div>
                  <div>
                    <p className="text-subtext text-[10px] uppercase tracking-wider mb-0.5">Vencto</p>
                    <p className="text-text_main font-medium">{fmtDate(topInad.DtVenctoMaisAntigo)}</p>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-subtext text-sm mt-4">Sem inadimplentes</p>
            )}
          </div>
        </div>

        {/* Titles table */}
        <div>
          <h3 className="text-sm font-semibold text-text_main mb-2">
            Títulos em Aberto ({titulosCR.length})
          </h3>
          <DataTable columns={TITULOS_CR_COLS} rows={titulosCR} />
        </div>

        {/* Top inadimplentes table */}
        <div>
          <h3 className="text-sm font-semibold text-text_main mb-2">
            Top Clientes Inadimplentes ({inadimplentes.length})
          </h3>
          <DataTable columns={INAD_COLS} rows={inadimplentes} />
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* D. Contas a Pagar                                                    */}
      {/* ------------------------------------------------------------------ */}
      <div className="bg-card border border-card_border rounded-lg p-4 space-y-4">
        <h2 className="text-base font-semibold text-text_main border-b border-card_border pb-2">
          Contas a Pagar
        </h2>

        {/* Mini-KPIs */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <KpiCard label="Total a Pagar" value={shortBrl(total_a_pagar)} variant="warning" />
          <KpiCard
            label="Vencidos"
            value={shortBrl(vencido_pagar)}
            variant={vencido_pagar > 0 ? 'error' : 'default'}
          />
          <KpiCard label="A Vencer 20d" value={shortBrl(a_vencer_pagar_20d)} variant="default" />
          <KpiCard
            label="Títulos CP"
            value={String(titulosCP.length)}
            variant="default"
          />
        </div>

        <div>
          <h3 className="text-sm font-semibold text-text_main mb-2">
            Títulos a Pagar ({titulosCP.length})
          </h3>
          <DataTable columns={TITULOS_CP_COLS} rows={titulosCP} />
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* E. Movimento Financeiro                                              */}
      {/* ------------------------------------------------------------------ */}
      <div className="bg-card border border-card_border rounded-lg p-4 space-y-4">
        <h2 className="text-base font-semibold text-text_main border-b border-card_border pb-2">
          Movimento Financeiro
        </h2>

        {/* Bar chart Entrada vs Saída per date */}
        <BarChart
          data={movChartData}
          xKey="data"
          bars={[
            { key: 'Entrada', label: 'Entrada', formatter: shortBrl },
            { key: 'Saída', label: 'Saída', formatter: shortBrl },
          ]}
          colors={['#238636', '#da3633']}
          height={220}
        />

        {/* Centro de custo + Monitor NF-e */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <h3 className="text-sm font-semibold text-text_main mb-2">
              Centro de Custo ({movCC.length})
            </h3>
            <DataTable columns={MOV_CC_COLS} rows={movCC} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text_main mb-2">
              Monitor NF-e ({nfeList.length})
            </h3>
            <DataTable columns={NFE_COLS} rows={nfeList} />
          </div>
        </div>

        {/* Pedidos confirmados — only when data is present */}
        {pedidosList.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-text_main mb-2">
              Pedidos Confirmados ({pedidosList.length})
            </h3>
            <DataTable columns={PEDIDOS_COLS} rows={pedidosList} />
          </div>
        )}
      </div>
    </div>
  );
}
