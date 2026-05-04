# bots/analise_bots.py
# Bots de análise — queries com os nomes reais do banco Blue.
# CodPlanoVnd = FORMA DE PAGAMENTO (não tipo de documento).
# Separação Orçamento × Venda usa Blue.dbo.TbOrcPedVnd.OrcPedVnd (1=Orc, 2=Venda).

import pandas as pd
import threading
import time
import logging
from datetime import datetime
from config.settings import BOT_INTERVALS, ALERTAS
from core.database import db

logger = logging.getLogger(__name__)

MAX          = ALERTAS.get("query_max_rows", 5000)
DIAS_RISCO   = ALERTAS.get("cliente_em_risco_dias", 60)
DIAS_INATIVO = ALERTAS.get("cliente_inativo_dias", 90)
DIAS_CRITICO = ALERTAS.get("estoque_critico_dias_sem_vnd", 90)


def _safe_float(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    v = df[col].iloc[0]
    return float(v) if v is not None else 0.0


def _safe_int(df: pd.DataFrame, col: str) -> int:
    return int(_safe_float(df, col))


# ──────────────────────────────────────────────────────────────────
class BaseBot(threading.Thread):
    def __init__(self, name: str):
        super().__init__(daemon=True, name=name)
        self.name_label  = name
        self.interval    = BOT_INTERVALS.get(name, 600)
        self.resultado: dict = {}
        self.ultimo_update   = "—"
        self.status          = "aguardando"
        self._stop           = threading.Event()
        self.callbacks: list = []

    def stop(self):
        self._stop.set()

    def add_callback(self, fn):
        self.callbacks.append(fn)

    def _notify(self):
        self.ultimo_update = datetime.now().strftime("%H:%M:%S")
        for cb in self.callbacks:
            try:
                cb(self.name_label, self.resultado)
            except Exception as e:
                logger.warning("Callback error [%s]: %s", self.name_label, e)

    def run(self):
        logger.info("Bot [%s] iniciado. Intervalo: %ds", self.name_label, self.interval)
        while not self._stop.is_set():
            self.status = "executando"
            try:
                self.resultado = self.analisar()
                self.status = "ok"
            except Exception as e:
                logger.error("Bot [%s] erro: %s", self.name_label, e)
                self.status = "erro"
            self._notify()
            for _ in range(max(1, self.interval // 5)):
                if self._stop.is_set():
                    break
                time.sleep(5)

    def analisar(self) -> dict:
        raise NotImplementedError


# ──────────────────────────────────────────────────────────────────
#  BOT DASHBOARD  — KPIs gerais do mês (somente vendas faturadas)
# ──────────────────────────────────────────────────────────────────
class BotDashboard(BaseBot):
    def __init__(self):
        super().__init__("dashboard")

    def analisar(self) -> dict:
        df_kpi = db.query(f"""
            SELECT
                SUM(v.ValVndTotal)        AS faturamento_atual,
                COUNT(DISTINCT v.NrDoc)   AS qtd_documentos,
                COUNT(DISTINCT v.CodCli)  AS clientes_ativos,
                AVG(v.ValVndTotal)        AS ticket_medio
            FROM Blue.dbo.vmVndDoc v
            INNER JOIN Blue.dbo.vwVndDoc d ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE MONTH(v.DtVnd) = MONTH(GETDATE())
              AND YEAR(v.DtVnd)  = YEAR(GETDATE())
              AND d.Cancelado    = ''
              AND d.Fat          = 1
        """)

        df_vend = db.query(f"""
            SELECT TOP 10
                v.Vendedor,
                v.CodVend,
                SUM(v.ValVndTotal)      AS total_venda,
                COUNT(DISTINCT v.NrDoc) AS qtd_pedidos,
                AVG(v.ValVndTotal)      AS ticket_medio
            FROM Blue.dbo.vmVndDoc v
            INNER JOIN Blue.dbo.vwVndDoc d ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE MONTH(v.DtVnd) = MONTH(GETDATE())
              AND YEAR(v.DtVnd)  = YEAR(GETDATE())
              AND d.Cancelado = ''
              AND d.Fat = 1
            GROUP BY v.Vendedor, v.CodVend
            ORDER BY total_venda DESC
        """)

        df_diario = db.query(f"""
            SELECT TOP 30
                CONVERT(date, v.DtVnd) AS dia,
                SUM(v.ValVndTotal)      AS faturamento
            FROM Blue.dbo.vmVndDoc v
            INNER JOIN Blue.dbo.vwVndDoc d ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE v.DtVnd >= DATEADD(day, -30, GETDATE())
              AND d.Cancelado = ''
              AND d.Fat = 1
            GROUP BY CONVERT(date, v.DtVnd)
            ORDER BY dia
        """)

        fat  = _safe_float(df_kpi, "faturamento_atual")
        meta = ALERTAS.get("meta_faturamento_mensal", 400000)
        pct  = round(fat / meta * 100, 1) if meta else 0

        return {
            "faturamento_atual":  fat,
            "qtd_documentos":     _safe_int(df_kpi, "qtd_documentos"),
            "clientes_ativos":    _safe_int(df_kpi, "clientes_ativos"),
            "ticket_medio":       _safe_float(df_kpi, "ticket_medio"),
            "pct_meta":           pct,
            "meta_mensal":        meta,
            "top_vendedores":     df_vend.to_dict("records"),
            "faturamento_diario": df_diario.to_dict("records"),
        }


# ──────────────────────────────────────────────────────────────────
#  BOT VENDAS  — análise por marca, grupo, vendedor e devoluções
# ──────────────────────────────────────────────────────────────────
class BotVendas(BaseBot):
    def __init__(self):
        super().__init__("vendas")

    def analisar(self) -> dict:
        df_marca = db.query(f"""
            SELECT TOP 20
                i.CodMarca,
                i.DescrMarca,
                SUM(i.PrecoVndTotItem)                           AS faturamento,
                SUM(i.QtdItem)                                   AS quantidade,
                SUM(i.CustoRepTotItem)                           AS custo_total,
                SUM(i.PrecoVndTotItem) - SUM(i.CustoRepTotItem)  AS margem_bruta
            FROM Blue.dbo.vmVndItemDoc i
            INNER JOIN Blue.dbo.vwVndDoc d ON i.NrDoc = d.NrDoc AND i.NSUDoc = d.NSUDoc
            WHERE MONTH(i.DtVnd) = MONTH(GETDATE())
              AND YEAR(i.DtVnd)  = YEAR(GETDATE())
              AND d.Cancelado = ''
              AND i.Fat = 1
            GROUP BY i.CodMarca, i.DescrMarca
            ORDER BY faturamento DESC
        """)

        df_grupo = db.query(f"""
            SELECT TOP 20
                i.CodGrpItem,
                i.DescrGrpItem,
                SUM(i.PrecoVndTotItem) AS faturamento,
                SUM(i.QtdItem)         AS quantidade
            FROM Blue.dbo.vmVndItemDoc i
            INNER JOIN Blue.dbo.vwVndDoc d ON i.NrDoc = d.NrDoc AND i.NSUDoc = d.NSUDoc
            WHERE MONTH(i.DtVnd) = MONTH(GETDATE())
              AND YEAR(i.DtVnd)  = YEAR(GETDATE())
              AND d.Cancelado = ''
              AND i.Fat = 1
            GROUP BY i.CodGrpItem, i.DescrGrpItem
            ORDER BY faturamento DESC
        """)

        df_dev = db.query(f"""
            SELECT TOP {MAX}
                dev.MotivoDevolucao,
                dev.Vendedor,
                dev.DescrItem,
                SUM(dev.QtdeItemDev) AS qtd_devolvida,
                SUM(dev.ValTotItem)  AS valor_devolvido,
                COUNT(*)             AS ocorrencias
            FROM Blue.dbo.vmMetricasMotivoDevItem dev
            WHERE MONTH(dev.DtVnd) = MONTH(GETDATE())
              AND YEAR(dev.DtVnd)  = YEAR(GETDATE())
            GROUP BY dev.MotivoDevolucao, dev.Vendedor, dev.DescrItem
            ORDER BY valor_devolvido DESC
        """)

        df_vend = db.query(f"""
            SELECT TOP 10
                v.Vendedor,
                v.CodVend,
                SUM(v.ValVndTotal)      AS total_venda,
                COUNT(DISTINCT v.NrDoc) AS qtd_pedidos,
                AVG(v.ValVndTotal)      AS ticket_medio,
                SUM(v.CustoRepTotal)    AS custo_total
            FROM Blue.dbo.vmVndDoc v
            INNER JOIN Blue.dbo.vwVndDoc d ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE MONTH(v.DtVnd) = MONTH(GETDATE())
              AND YEAR(v.DtVnd)  = YEAR(GETDATE())
              AND d.Cancelado = ''
              AND d.Fat = 1
            GROUP BY v.Vendedor, v.CodVend
            ORDER BY total_venda DESC
        """)

        total_dev = float(df_dev["valor_devolvido"].sum()) if not df_dev.empty else 0.0

        return {
            "por_marca":        df_marca.to_dict("records"),
            "por_grupo":        df_grupo.to_dict("records"),
            "devolucoes":       df_dev.head(20).to_dict("records"),
            "total_devolucoes": total_dev,
            "por_vendedor":     df_vend.to_dict("records"),
        }


# ──────────────────────────────────────────────────────────────────
#  BOT ESTOQUE
# ──────────────────────────────────────────────────────────────────
class BotEstoque(BaseBot):
    def __init__(self):
        super().__init__("estoque")

    def analisar(self) -> dict:
        df_resumo = db.query(f"""
            SELECT
                COUNT(*)                     AS total_itens,
                SUM(VlrEstq)                 AS valor_total_estoque,
                SUM(QtdEstq)                AS qtd_total,
                SUM(QtdEstqDisp)            AS qtd_disponivel,
                SUM(CASE WHEN QtdEstqDisp <= 0 THEN 1 ELSE 0 END)        AS itens_zerados,
                SUM(CASE WHEN DiasSemVnd > {DIAS_CRITICO} THEN 1 ELSE 0 END) AS itens_sem_giro
            FROM Blue.dbo.vmAnaliseEstqItem
            WHERE QtdEstq > 0
        """)

        df_criticos = db.query(f"""
            SELECT TOP {MAX}
                e.CodItem,
                e.DescrItem,
                e.DescrMarca,
                e.CodGrpItem,
                e.QtdEstq,
                e.QtdEstqDisp,
                e.DiasSemVnd,
                e.DtUltVnd,
                e.CustoRepProd,
                e.VlrEstq,
                e.QtdPendPedCmp,
                e.FornecUltCmp
            FROM Blue.dbo.vmAnaliseEstqItem e
            WHERE e.DiasSemVnd > {DIAS_CRITICO}
               OR e.QtdEstqDisp <= 0
            ORDER BY e.DiasSemVnd DESC, e.VlrEstq DESC
        """)

        df_marca = db.query(f"""
            SELECT TOP 30
                e.DescrMarca,
                COUNT(*)           AS qtd_itens,
                SUM(e.VlrEstq)     AS valor_estoque,
                AVG(e.DiasSemVnd)  AS media_dias_sem_venda,
                SUM(e.QtdEstq)    AS quantidade_total
            FROM Blue.dbo.vmAnaliseEstqItem e
            GROUP BY e.DescrMarca
            ORDER BY valor_estoque DESC
        """)

        df_mov = db.query(f"""
            SELECT TOP 2000
                m.CodItem,
                m.DescrItem,
                SUM(m.QtdEntrada)   AS entradas,
                SUM(m.QtdSaida)     AS saidas,
                SUM(m.QtdLiqVendas) AS vendas_liquidas
            FROM Blue.dbo.vmItemMovEstq m
            WHERE m.DtMovEstq >= DATEADD(day, -30, GETDATE())
            GROUP BY m.CodItem, m.DescrItem
            ORDER BY saidas DESC
        """)

        return {
            "total_itens":         _safe_int(df_resumo, "total_itens"),
            "valor_total_estoque": _safe_float(df_resumo, "valor_total_estoque"),
            "qtd_disponivel":      _safe_int(df_resumo, "qtd_disponivel"),
            "itens_zerados":       _safe_int(df_resumo, "itens_zerados"),
            "itens_sem_giro":      _safe_int(df_resumo, "itens_sem_giro"),
            "criticos":            df_criticos.to_dict("records"),
            "por_marca":           df_marca.to_dict("records"),
            "movimentacao":        df_mov.head(50).to_dict("records"),
        }


# ──────────────────────────────────────────────────────────────────
#  BOT FINANCEIRO
# ──────────────────────────────────────────────────────────────────
class BotFinanceiro(BaseBot):
    def __init__(self):
        super().__init__("financeiro")

    def analisar(self) -> dict:
        df_resumo = db.query("""
            SELECT
                SUM(CASE WHEN DtQuitacao IS NOT NULL THEN RcboLiquido ELSE 0 END)                    AS recebido,
                SUM(CASE WHEN DtQuitacao IS NULL AND DtVcto < GETDATE() THEN RcboLiquido ELSE 0 END) AS em_atraso,
                SUM(CASE WHEN DtQuitacao IS NULL AND DtVcto >= GETDATE() THEN RcboLiquido ELSE 0 END) AS a_vencer,
                COUNT(CASE WHEN DtQuitacao IS NULL AND DtVcto < GETDATE() THEN 1 END)                AS titulos_atrasados
            FROM Blue.dbo.vmVendaXTipoRcbo
            WHERE DtLctoCtRec >= DATEADD(month, DATEDIFF(month, 0, GETDATE()), 0)
              AND DtLctoCtRec <  DATEADD(month, DATEDIFF(month, 0, GETDATE()) + 1, 0)
        """)

        df_tipo = db.query("""
            SELECT TOP 20
                TipoRcbo,
                SUM(RcboLiquido)  AS total,
                COUNT(*)          AS qtd_lancamentos,
                AVG(RcboLiquido)  AS media_valor
            FROM Blue.dbo.vmVendaXTipoRcbo
            WHERE DtLctoCtRec >= DATEADD(month, DATEDIFF(month, 0, GETDATE()), 0)
              AND DtLctoCtRec <  DATEADD(month, DATEDIFF(month, 0, GETDATE()) + 1, 0)
              AND DtQuitacao IS NOT NULL
            GROUP BY TipoRcbo
            ORDER BY total DESC
        """)

        df_inad = db.query("""
            SELECT TOP 50
                CodigoCli,
                NomeFantCli,
                RzsCli,
                SUM(RcboLiquido)                       AS divida_total,
                COUNT(*)                               AS qtd_titulos,
                MAX(DATEDIFF(day, DtVcto, GETDATE()))  AS max_dias_atraso
            FROM Blue.dbo.vmVendaXTipoRcbo
            WHERE DtQuitacao IS NULL
              AND DtVcto < GETDATE()
            GROUP BY CodigoCli, NomeFantCli, RzsCli
            ORDER BY divida_total DESC
        """)

        df_pmr = db.query("""
            SELECT
                AVG(CAST(DATEDIFF(day, v.DtVnd, r.DtQuitacao) AS float)) AS prazo_medio
            FROM Blue.dbo.vmVendaXTipoRcbo r
            INNER JOIN Blue.dbo.vmVndDoc v ON r.Documento = v.Documento
            WHERE r.DtQuitacao IS NOT NULL
              AND r.DtQuitacao >= DATEADD(day, -90, GETDATE())
        """)

        return {
            "recebido_mes":         _safe_float(df_resumo, "recebido"),
            "em_atraso":            _safe_float(df_resumo, "em_atraso"),
            "a_vencer":             _safe_float(df_resumo, "a_vencer"),
            "titulos_atrasados":    _safe_int(df_resumo, "titulos_atrasados"),
            "prazo_medio_receb":    round(_safe_float(df_pmr, "prazo_medio"), 1),
            "por_tipo_recebimento": df_tipo.to_dict("records"),
            "top_inadimplentes":    df_inad.to_dict("records"),
            "total_inadimplencia":  float(df_inad["divida_total"].sum()) if not df_inad.empty else 0.0,
            "qtd_inadimplentes":    len(df_inad),
        }


# ──────────────────────────────────────────────────────────────────
#  BOT CRM  — Funil de conversão usando TbOrcPedVnd (OrcPedVnd 1/2)
# ──────────────────────────────────────────────────────────────────
class BotCRM(BaseBot):
    def __init__(self):
        super().__init__("crm")

    def analisar(self) -> dict:
        # ── KPIs de conversão do mês ──────────────────────────────
        df_conv = db.query(f"""
            SELECT
                COUNT(CASE WHEN OrcPedVnd = 1 THEN 1 END)  AS total_orcamentos,
                COUNT(CASE WHEN OrcPedVnd = 2 THEN 1 END)  AS total_convertidos,
                CAST(COUNT(CASE WHEN OrcPedVnd = 2 THEN 1 END) AS FLOAT) /
                    NULLIF(COUNT(CASE WHEN OrcPedVnd = 1 THEN 1 END), 0) * 100
                                                             AS taxa_conversao_pct,
                SUM(CASE WHEN OrcPedVnd = 1 THEN ValTotalOrcPedVnd ELSE 0 END) AS valor_orcado,
                SUM(CASE WHEN OrcPedVnd = 2 THEN ValTotalOrcPedVnd ELSE 0 END) AS valor_convertido
            FROM Blue.dbo.TbOrcPedVnd
            WHERE MONTH(DtOrcPedVnd) = MONTH(GETDATE())
              AND YEAR(DtOrcPedVnd)  = YEAR(GETDATE())
        """)

        # ── Funil por Vendedor e Marca ────────────────────────────
        df_conv_vend = db.query(f"""
            SELECT TOP 20
                v.Vendedor,
                i.DescrMarca,
                COUNT(CASE WHEN o.OrcPedVnd = 1 THEN 1 END)                              AS orcamentos,
                COUNT(CASE WHEN o.OrcPedVnd = 2 THEN 1 END)                              AS convertidos,
                SUM(CASE WHEN o.OrcPedVnd = 1 THEN i.PrecoVndTotItem ELSE 0 END)         AS valor_orcado,
                SUM(CASE WHEN o.OrcPedVnd = 2 THEN i.PrecoVndTotItem ELSE 0 END)         AS valor_convertido
            FROM Blue.dbo.TbOrcPedVnd o
            INNER JOIN Blue.dbo.vmVndDoc v     ON o.NrOrcPedVnd = v.NrDoc
            INNER JOIN Blue.dbo.vmVndItemDoc i ON o.NrOrcPedVnd = i.NrDoc
            WHERE MONTH(o.DtOrcPedVnd) = MONTH(GETDATE())
              AND YEAR(o.DtOrcPedVnd)  = YEAR(GETDATE())
            GROUP BY v.Vendedor, i.DescrMarca
            ORDER BY valor_orcado DESC
        """)

        # ── Funil resumido por tipo (para gráfico de barras) ──────
        df_funil = db.query(f"""
            SELECT
                CASE OrcPedVnd WHEN 1 THEN 'Orcamento' WHEN 2 THEN 'Venda Convertida' ELSE 'Outro' END
                    AS tipo,
                COUNT(*)                   AS qtd_documentos,
                SUM(ValTotalOrcPedVnd)     AS valor_total
            FROM Blue.dbo.TbOrcPedVnd
            WHERE MONTH(DtOrcPedVnd) = MONTH(GETDATE())
              AND YEAR(DtOrcPedVnd)  = YEAR(GETDATE())
            GROUP BY OrcPedVnd
            ORDER BY OrcPedVnd
        """)

        # ── Clientes inativos / em risco ──────────────────────────
        df_inativos = db.query(f"""
            SELECT TOP {MAX}
                v.CodCli,
                MAX(v.NomeFantCli)                     AS nome_cliente,
                MAX(v.RzsCli)                          AS razao_social,
                MAX(v.UF)                              AS uf,
                MAX(v.Munic)                           AS municipio,
                MAX(v.CodSegCli)                       AS segmento,
                MAX(v.DtVnd)                           AS ultima_compra,
                DATEDIFF(day, MAX(v.DtVnd), GETDATE()) AS dias_sem_compra,
                COUNT(DISTINCT v.NrDoc)                AS total_pedidos,
                SUM(v.ValVndTotal)                     AS faturamento_historico,
                AVG(v.ValVndTotal)                     AS ticket_medio
            FROM Blue.dbo.vmVndDoc v
            INNER JOIN Blue.dbo.vwVndDoc d ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE d.Cancelado = ''
              AND d.Fat = 1
            GROUP BY v.CodCli
            HAVING DATEDIFF(day, MAX(v.DtVnd), GETDATE()) >= {DIAS_RISCO}
            ORDER BY dias_sem_compra DESC
        """)

        # ── Distribuição por faixa de inatividade ─────────────────
        df_faixas = db.query(f"""
            SELECT
                CASE
                    WHEN dias BETWEEN {DIAS_RISCO} AND {DIAS_INATIVO - 1} THEN 'Em Risco ({DIAS_RISCO}-{DIAS_INATIVO - 1}d)'
                    WHEN dias BETWEEN {DIAS_INATIVO} AND 179              THEN 'Inativo ({DIAS_INATIVO}-179d)'
                    WHEN dias BETWEEN 180 AND 364                         THEN 'Critico (180-364d)'
                    ELSE 'Perdido (365d+)'
                END AS faixa,
                COUNT(*)  AS qtd_clientes,
                SUM(fat)  AS faturamento_historico
            FROM (
                SELECT
                    v.CodCli,
                    DATEDIFF(day, MAX(v.DtVnd), GETDATE()) AS dias,
                    SUM(v.ValVndTotal)                     AS fat
                FROM Blue.dbo.vmVndDoc v
                INNER JOIN Blue.dbo.vwVndDoc d ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
                WHERE d.Cancelado = '' AND d.Fat = 1
                GROUP BY v.CodCli
                HAVING DATEDIFF(day, MAX(v.DtVnd), GETDATE()) >= {DIAS_RISCO}
            ) sub
            GROUP BY
                CASE
                    WHEN dias BETWEEN {DIAS_RISCO} AND {DIAS_INATIVO - 1} THEN 'Em Risco ({DIAS_RISCO}-{DIAS_INATIVO - 1}d)'
                    WHEN dias BETWEEN {DIAS_INATIVO} AND 179              THEN 'Inativo ({DIAS_INATIVO}-179d)'
                    WHEN dias BETWEEN 180 AND 364                         THEN 'Critico (180-364d)'
                    ELSE 'Perdido (365d+)'
                END
            ORDER BY faixa
        """)

        # ── Clientes novos vs recorrentes (30 dias) ───────────────
        df_tipo_cli = db.query(f"""
            SELECT
                CASE WHEN primeira_compra >= DATEADD(day,-30,GETDATE()) THEN 'Novo' ELSE 'Recorrente' END AS tipo,
                COUNT(*) AS qtd_clientes,
                SUM(fat_mes) AS faturamento
            FROM (
                SELECT
                    v.CodCli,
                    MIN(v.DtVnd) AS primeira_compra,
                    SUM(CASE WHEN v.DtVnd >= DATEADD(day,-30,GETDATE()) THEN v.ValVndTotal ELSE 0 END) AS fat_mes
                FROM Blue.dbo.vmVndDoc v
                INNER JOIN Blue.dbo.vwVndDoc d ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
                WHERE d.Cancelado = '' AND d.Fat = 1
                GROUP BY v.CodCli
                HAVING SUM(CASE WHEN v.DtVnd >= DATEADD(day,-30,GETDATE()) THEN 1 ELSE 0 END) > 0
            ) sub
            GROUP BY
                CASE WHEN primeira_compra >= DATEADD(day,-30,GETDATE()) THEN 'Novo' ELSE 'Recorrente' END
        """)

        em_risco = df_inativos[df_inativos["dias_sem_compra"].between(DIAS_RISCO, DIAS_INATIVO - 1)] if not df_inativos.empty else pd.DataFrame()
        inativos = df_inativos[df_inativos["dias_sem_compra"] >= DIAS_INATIVO] if not df_inativos.empty else pd.DataFrame()

        return {
            "total_orcamentos":   _safe_int(df_conv, "total_orcamentos"),
            "total_convertidos":  _safe_int(df_conv, "total_convertidos"),
            "taxa_conversao_pct": round(_safe_float(df_conv, "taxa_conversao_pct"), 1),
            "valor_orcado":       _safe_float(df_conv, "valor_orcado"),
            "valor_convertido":   _safe_float(df_conv, "valor_convertido"),
            "funil":              df_funil.to_dict("records"),
            "conv_por_vendedor":  df_conv_vend.to_dict("records"),
            "inativos_lista":     df_inativos.to_dict("records"),
            "faixas_inatividade": df_faixas.to_dict("records"),
            "qtd_em_risco":       len(em_risco),
            "qtd_inativos":       len(inativos),
            "tipo_clientes_30d":  df_tipo_cli.to_dict("records"),
        }


# ──────────────────────────────────────────────────────────────────
#  GERENCIADOR
# ──────────────────────────────────────────────────────────────────
class BotManager:
    def __init__(self):
        self.bots: dict[str, BaseBot] = {
            "dashboard":  BotDashboard(),
            "vendas":     BotVendas(),
            "estoque":    BotEstoque(),
            "financeiro": BotFinanceiro(),
            "crm":        BotCRM(),
        }

    def start_all(self):
        for bot in self.bots.values():
            bot.start()
        logger.info("Todos os bots iniciados.")

    def stop_all(self):
        for bot in self.bots.values():
            bot.stop()

    def add_callback(self, bot_name: str, fn):
        if bot_name in self.bots:
            self.bots[bot_name].add_callback(fn)

    def get_status(self) -> dict:
        return {
            name: {"status": b.status, "ultimo_update": b.ultimo_update}
            for name, b in self.bots.items()
        }

    def get_resultado(self, bot_name: str) -> dict:
        return self.bots.get(bot_name, BaseBot("__null__")).resultado
