import { useFilteredDados } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import PieChart from '../charts/PieChart';
import BarChart from '../charts/BarChart';
import { shortBrl, pct } from '../utils/format';

function fmtDelta(delta, unit = '') {
  if (delta === 0 || delta == null) return null;
  const abs = Math.abs(delta);
  return delta > 0 ? `↑ +${abs}${unit} vs mês ant.` : `↓ ${abs}${unit} vs mês ant.`;
}

export default function CRM({ refreshTrigger }) {
  const { data, loading, error, isEmpty } = useFilteredDados('crm', {}, refreshTrigger);

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64 text-subtext text-sm">
        Carregando dados de CRM…
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
          <p>Bot CRM está processando dados do banco…</p>
          <p className="text-xs opacity-60">A página atualiza automaticamente quando concluir.</p>
        </div>
      </div>
    );
  }

  const taxaConv    = data?.taxa_conversao_pct ?? 0;
  const pipeline    = data?.valor_orcado       ?? 0;
  const orcamentos  = data?.total_orcamentos   ?? 0;
  const convertidos = data?.total_convertidos  ?? 0;
  const fechado     = data?.valor_convertido   ?? 0;
  const ticket      = data?.ticket_medio       ?? 0;
  const deltaTaxa   = data?.delta_taxa_conv    ?? null;
  const deltaPipe   = data?.delta_valor_orcado ?? null;
  const distribuicao = data?.distribuicao      ?? [];
  const funilEtapas  = data?.funil_etapas      ?? [];

  const deltaTaxaLabel = fmtDelta(deltaTaxa, 'pp');
  const deltaPipeLabel = deltaPipe != null
    ? fmtDelta(Math.round(deltaPipe / 1000), 'k')
    : null;

  const taxaVariant = taxaConv >= 40 ? 'success' : taxaConv >= 25 ? 'warning' : 'error';

  return (
    <div className="p-6 space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text_main">Performance Comercial</h1>
        {data?.ultimo_update && (
          <span className="text-subtext text-xs">Atualizado: {data.ultimo_update}</span>
        )}
      </div>

      {/* 5 KPI cards */}
      <div className="grid grid-cols-5 gap-3">
        <KpiCard
          label="Taxa de Conversão"
          value={pct(taxaConv)}
          sub={deltaTaxaLabel}
          variant={taxaVariant}
          topBorder="#1f6feb"
        />
        <KpiCard
          label="Pipeline"
          value={shortBrl(pipeline)}
          sub={deltaPipeLabel}
          topBorder="#1f6feb"
        />
        <KpiCard
          label="Propostas Enviadas"
          value={String(orcamentos)}
          topBorder="#1f6feb"
        />
        <KpiCard
          label="Vendas Fechadas"
          value={String(convertidos)}
          sub={shortBrl(fechado)}
          variant="success"
          topBorder="#238636"
        />
        <KpiCard
          label="Ticket Médio"
          value={shortBrl(ticket)}
          topBorder="#d29922"
        />
      </div>

      {/* 2 gráficos */}
      <div className="flex gap-3 items-start">

        {/* Funil de Conversão — BarChart horizontal */}
        <div className="flex-1 bg-card border border-card_border rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold text-subtext uppercase tracking-widest">
              Funil de Conversão
            </span>
            <div className="flex-1 h-px bg-card_border" />
            <span className="text-[9px] text-subtext">mês atual</span>
          </div>
          <BarChart
            data={funilEtapas}
            xKey="etapa"
            bars={[{ key: 'qtd', label: 'Documentos' }]}
            horizontal={true}
            height={180}
          />
          <p className="text-center text-xs text-subtext mt-2">
            Taxa de conversão:{' '}
            <span className="font-semibold text-text_main">{pct(taxaConv)}</span>
          </p>
        </div>

        {/* Resultado do Período — PieChart */}
        <div className="w-[42%] bg-card border border-card_border rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold text-subtext uppercase tracking-widest">
              Resultado do Período
            </span>
            <div className="flex-1 h-px bg-card_border" />
          </div>
          <PieChart
            data={distribuicao}
            nameKey="status"
            valueKey="qtd"
            showValue={false}
            colors={['#238636', '#d29922', '#da3633']}
            height={180}
          />
        </div>

      </div>
    </div>
  );
}
