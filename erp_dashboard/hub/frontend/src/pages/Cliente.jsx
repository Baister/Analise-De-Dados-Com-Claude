import { useState, useCallback } from 'react';
import { apiFetch } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import BarChart from '../charts/BarChart';
import PieChart from '../charts/PieChart';
import DataTable from '../components/DataTable';
import { brl, shortBrl, fmtDate } from '../utils/format';

const AZUL = '#1f6feb', VERDE = '#238636', AMBAR = '#d29922', VERM = '#da3633', ROXO = '#a371f7';

const fmtInt = v => (v == null ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 0 }));
const fmtQtd = v => (v == null ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 1 }));

function SectionLabel({ children, first }) {
  return (
    <p className="text-[10px] text-subtext uppercase mb-[7px]"
      style={{ letterSpacing: '1px', marginTop: first ? 0 : 18 }}>
      {children}
    </p>
  );
}

function Card({ children, className = '' }) {
  return (
    <div className={`bg-card border border-card_border rounded-lg p-4 ${className}`}>
      {children}
    </div>
  );
}

function CardTitle({ children, right }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <p className="text-[11px] text-subtext uppercase" style={{ letterSpacing: '0.8px' }}>{children}</p>
      {right && <span className="text-[9px] text-subtext opacity-70">{right}</span>}
    </div>
  );
}

function Chip({ text, color, bg }) {
  return (
    <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 9px', borderRadius: 9999, background: bg, color, whiteSpace: 'nowrap' }}>
      {text}
    </span>
  );
}

// Situação do cliente pela recência da última compra
function situacao(dias) {
  if (dias == null) return { label: 'Sem compras', color: '#94a3b8', bg: 'rgba(148,163,184,0.15)' };
  if (dias <= 30)  return { label: `Ativo · ${dias}d`,     color: '#4ade80', bg: 'rgba(35,134,54,0.18)' };
  if (dias <= 60)  return { label: `Atenção · ${dias}d`,   color: '#fbbf24', bg: 'rgba(210,153,34,0.18)' };
  if (dias <= 90)  return { label: `Em risco · ${dias}d`,  color: '#fb923c', bg: 'rgba(249,115,22,0.18)' };
  return { label: `Inativo · ${dias}d`, color: '#f87171', bg: 'rgba(218,54,51,0.18)' };
}

const mono = v => <span className="text-subtext" style={{ fontFamily: 'monospace' }}>{v ?? '—'}</span>;

const PROD_COLS = [
  { key: 'cod_item', label: 'Cód.', render: mono },
  { key: 'produto',  label: 'Produto' },
  { key: 'marca',    label: 'Marca' },
  { key: 'qtd',      label: 'Qtd',   align: 'right', render: fmtQtd },
  { key: 'valor',    label: 'Valor', align: 'right', render: brl },
];

const VEND_COLS = [
  { key: 'vendedor', label: 'Vendedor', render: (v, r) => (
      <span className="text-text_main">
        {v}{' '}
        {r.atual && <Chip text="ATUAL" color="#4ade80" bg="rgba(35,134,54,0.18)" />}
      </span>
    ) },
  { key: 'pedidos',  label: 'Pedidos',       align: 'right', render: fmtInt },
  { key: 'valor',    label: 'Valor',         align: 'right', render: brl },
  { key: 'primeira', label: 'Primeiro atend.', render: v => fmtDate(v) },
  { key: 'ultima',   label: 'Último atend.',   render: v => fmtDate(v) },
];

const COMPRAS_COLS = [
  { key: 'nr_doc',   label: 'Doc', render: mono },
  { key: 'data',     label: 'Data', render: v => fmtDate(v) },
  { key: 'vendedor', label: 'Vendedor' },
  { key: 'valor',    label: 'Valor', align: 'right', render: (v, r) => (
      <span style={{ color: r.devolucao ? '#f87171' : undefined, fontWeight: r.devolucao ? 600 : 400 }}>
        {brl(v)}{r.devolucao ? ' (dev.)' : ''}
      </span>
    ) },
];

const ORC_COLS = [
  { key: 'nr',   label: 'Orçamento', render: mono },
  { key: 'data', label: 'Data', render: v => fmtDate(v) },
  { key: 'dias_aberto', label: 'Aberto há', render: v => {
      const n = v ?? 0;
      const [color, bg] = n <= 7 ? ['#4ade80', 'rgba(35,134,54,0.15)']
        : n <= 30 ? ['#fbbf24', 'rgba(210,153,34,0.15)'] : ['#f87171', 'rgba(218,54,51,0.15)'];
      return <Chip text={`${n} dias`} color={color} bg={bg} />;
    } },
  { key: 'valor', label: 'Valor', align: 'right', render: brl },
];

const TIT_COLS = [
  { key: 'documento',  label: 'Documento', render: mono },
  { key: 'receita',    label: 'Tipo' },
  { key: 'vencimento', label: 'Vencimento', render: (v, r) => {
      const hoje = new Date().toISOString().slice(0, 10);
      const venc = v && v < hoje;
      return <span style={{ color: venc ? '#f87171' : undefined, fontWeight: venc ? 600 : 400 }}>{fmtDate(v)}</span>;
    } },
  { key: 'valor', label: 'Valor', align: 'right', render: brl },
];

export default function Cliente() {
  const [termo, setTermo]         = useState('');
  const [resultados, setResultados] = useState(null);   // lista da busca
  const [perfil, setPerfil]       = useState(null);     // perfil 360 carregado
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState(null);

  const buscar = useCallback(async () => {
    if (!termo.trim()) return;
    setLoading(true); setError(null); setPerfil(null);
    try {
      const res = await apiFetch(`/dados/cliente?busca=${encodeURIComponent(termo.trim())}`);
      const lista = res?.resultados ?? [];
      setResultados(lista);
      if (lista.length === 1) await abrirPerfil(lista[0].cod);   // único resultado → abre direto
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [termo]); // eslint-disable-line react-hooks/exhaustive-deps

  const abrirPerfil = useCallback(async (cod) => {
    setLoading(true); setError(null);
    try {
      const res = await apiFetch(`/dados/cliente?cod=${encodeURIComponent(cod)}`);
      if (res?.erro) { setError(res.erro); setPerfil(null); }
      else setPerfil(res);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  const cad  = perfil?.cadastro ?? {};
  const kpis = perfil?.kpis ?? {};
  const sit  = situacao(kpis.dias_sem_compra);
  const titulos = perfil?.titulos ?? {};

  return (
    <div className="p-4">
      {/* ── Cabeçalho + busca ── */}
      <div className="flex items-end justify-between flex-wrap gap-2 mb-1">
        <div>
          <h1 className="text-text_main text-lg font-bold leading-tight">Cliente 360º</h1>
          <p className="text-subtext text-[11px]">
            Perfil completo: compras, produtos, vendedores, orçamentos e títulos
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text" value={termo} autoFocus
            onChange={e => setTermo(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') buscar(); }}
            placeholder="Nome, razão social, código ou CNPJ…"
            className="w-72 px-3 py-2 text-sm bg-card border border-card_border rounded-lg text-text_main placeholder-subtext focus:outline-none focus:border-accent"
          />
          <button onClick={buscar} disabled={loading || !termo.trim()}
            className="px-4 py-2 bg-accent text-white text-sm rounded-lg hover:opacity-90 disabled:opacity-40 transition-opacity">
            {loading ? 'Buscando…' : 'Buscar'}
          </button>
        </div>
      </div>
      {error && <p className="text-accent_red text-xs mt-2">{error}</p>}

      {/* ── Estado inicial ── */}
      {!perfil && resultados === null && !loading && (
        <div className="flex items-center justify-center h-56 text-subtext text-sm">
          <div className="text-center space-y-1">
            <p className="text-2xl">🔎</p>
            <p>Busque um cliente por nome, razão social, código ou CNPJ.</p>
          </div>
        </div>
      )}

      {/* ── Resultados da busca ── */}
      {!perfil && resultados !== null && (
        <>
          <SectionLabel>Resultados da Busca — {resultados.length} cliente{resultados.length !== 1 ? 's' : ''}</SectionLabel>
          {resultados.length === 0 ? (
            <Card><p className="text-subtext text-sm text-center py-6">Nenhum cliente encontrado para "{termo}".</p></Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {resultados.map(r => (
                <button key={r.cod} onClick={() => abrirPerfil(r.cod)}
                  className="bg-card border border-card_border rounded-lg p-3 text-left hover:border-accent transition-colors">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-text_main text-sm font-semibold truncate">{r.nome}</span>
                    <span className="text-subtext text-[10px]" style={{ fontFamily: 'monospace' }}>{r.cod}</span>
                  </div>
                  <div className="text-subtext text-[11px] mt-1 flex gap-3 flex-wrap">
                    {r.doc && <span>{r.doc}</span>}
                    {r.uf && <span>{r.uf}</span>}
                    <span>Últ. compra: {r.ultima_compra ? fmtDate(r.ultima_compra) : '—'}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </>
      )}

      {/* ── Perfil 360 ── */}
      {perfil && (
        <>
          {/* Identidade */}
          <SectionLabel first={false}>Perfil do Cliente</SectionLabel>
          <Card>
            <div className="flex items-start justify-between flex-wrap gap-3">
              <div>
                <div className="flex items-center gap-3 flex-wrap">
                  <h2 className="text-text_main text-xl font-bold">{cad.nome}</h2>
                  <Chip text={sit.label} color={sit.color} bg={sit.bg} />
                </div>
                {cad.razao && cad.razao !== cad.nome && (
                  <p className="text-subtext text-[11px] mt-0.5">{cad.razao}</p>
                )}
                <div className="flex gap-4 flex-wrap mt-2 text-[11px] text-subtext">
                  <span>Cód. <b className="text-text_main" style={{ fontFamily: 'monospace' }}>{cad.cod}</b></span>
                  {cad.doc && <span>CNPJ/CPF <b className="text-text_main">{cad.doc}</b></span>}
                  {cad.uf && <span>UF <b className="text-text_main">{cad.uf}</b></span>}
                  {cad.fone && <span>Fone <b className="text-text_main">{cad.fone}</b></span>}
                  {cad.plano_padrao && <span>Plano padrão <b className="text-text_main">{cad.plano_padrao}</b></span>}
                  <span>Cadastro <b className="text-text_main">{fmtDate(cad.cadastro)}</b></span>
                  {perfil.cliente_desde && <span>1ª compra <b className="text-text_main">{fmtDate(perfil.cliente_desde)}</b></span>}
                  {cad.limite_credito != null && <span>Limite crédito <b className="text-text_main">{brl(cad.limite_credito)}</b></span>}
                </div>
              </div>
              <button onClick={() => { setPerfil(null); }}
                className="text-[11px] px-3 py-1.5 rounded-lg border border-card_border text-subtext hover:text-text_main">
                ← Voltar à busca
              </button>
            </div>
          </Card>

          {/* KPIs 12m */}
          <SectionLabel>Últimos 12 Meses</SectionLabel>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2.5">
            <KpiCard label="Total Comprado" value={brl(kpis.comprado_12m)}
              sub="vendas líquidas 12m" topBorder={AZUL} gradient="rgba(31,111,235,0.10)" />
            <KpiCard label="Pedidos" value={fmtInt(kpis.pedidos_12m)}
              sub="documentos de venda" topBorder={AZUL} />
            <KpiCard label="Ticket Médio" value={brl(kpis.ticket_medio)}
              sub="por pedido" topBorder={VERDE} />
            <KpiCard label="Devoluções" value={brl(Math.abs(kpis.devolucoes_12m ?? 0))}
              sub="últimos 12 meses" variant={Math.abs(kpis.devolucoes_12m ?? 0) > 0 ? 'error' : 'default'} topBorder={VERM} />
            <KpiCard label="Última Compra" value={kpis.ultima_compra ? fmtDate(kpis.ultima_compra) : '—'}
              sub={kpis.dias_sem_compra != null ? `há ${kpis.dias_sem_compra} dias` : '—'}
              valueColor={sit.color} topBorder={sit.color} />
            <KpiCard label="Frequência de Compra" value={kpis.freq_media_dias != null ? `a cada ${kpis.freq_media_dias}d` : '—'}
              sub="média entre pedidos" topBorder={ROXO} valueColor="#c084fc" />
          </div>

          {/* Evolução */}
          <SectionLabel>Evolução de Compras (12 meses)</SectionLabel>
          <Card>
            <BarChart
              data={perfil.evolucao ?? []} xKey="mes" height={210}
              bars={[{ key: 'valor', label: 'Comprado', formatter: shortBrl }]}
              colors={[AZUL]}
              tooltipExtra={[{ key: 'pedidos', label: 'Pedidos', formatter: fmtInt }]}
            />
          </Card>

          {/* O que mais compra */}
          <SectionLabel>O Que Mais Compra (12 meses)</SectionLabel>
          <div className="grid gap-2.5" style={{ gridTemplateColumns: '1.6fr 1fr' }}>
            <Card>
              <CardTitle right="top 10 por valor">Top Produtos</CardTitle>
              <DataTable columns={PROD_COLS} rows={perfil.top_produtos ?? []} />
            </Card>
            <Card>
              <CardTitle>Marcas Preferidas</CardTitle>
              <PieChart
                data={perfil.top_marcas ?? []} nameKey="marca" valueKey="valor"
                showValue formatter={brl} height={230}
                tooltipContext={{
                  title: 'Comprado 12m',
                  extra: [{ key: 'qtd', label: 'Unidades', formatter: fmtInt }],
                }}
              />
            </Card>
          </div>

          {/* Vendedores + últimas compras */}
          <SectionLabel>Atendimento</SectionLabel>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
            <Card>
              <CardTitle right="últimos 24 meses">Histórico de Vendedores</CardTitle>
              <DataTable columns={VEND_COLS} rows={perfil.vendedores ?? []} />
            </Card>
            <Card>
              <CardTitle right="15 mais recentes">Últimas Compras</CardTitle>
              <DataTable columns={COMPRAS_COLS} rows={perfil.ultimas_compras ?? []} />
            </Card>
          </div>

          {/* Oportunidades e financeiro */}
          <SectionLabel>Oportunidades e Financeiro</SectionLabel>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
            <Card>
              <CardTitle right="não convertidos · 180 dias">Orçamentos Abertos</CardTitle>
              {(perfil.orcamentos_abertos ?? []).length === 0 ? (
                <p className="text-subtext text-xs text-center py-6">Nenhum orçamento aberto nos últimos 180 dias.</p>
              ) : (
                <DataTable columns={ORC_COLS} rows={perfil.orcamentos_abertos} />
              )}
            </Card>
            <Card>
              <CardTitle
                right={titulos.qtd > 0 ? `${fmtInt(titulos.qtd)} títulos · ${brl(titulos.valor)}` : undefined}>
                Títulos em Aberto
              </CardTitle>
              {titulos.vencidos_qtd > 0 && (
                <p className="text-[11px] mb-2" style={{ color: '#f87171' }}>
                  ⚠ {titulos.vencidos_qtd} vencido{titulos.vencidos_qtd !== 1 ? 's' : ''} · {brl(titulos.vencidos_valor)}
                </p>
              )}
              {(titulos.lista ?? []).length === 0 ? (
                <p className="text-subtext text-xs text-center py-6">Nenhum título em aberto. ✅</p>
              ) : (
                <DataTable columns={TIT_COLS} rows={titulos.lista} />
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
