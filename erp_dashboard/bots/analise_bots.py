# bots/analise_bots.py
# Bots de análise — queries com os nomes reais do banco Blue.
# CodPlanoVnd = FORMA DE PAGAMENTO (não tipo de documento).
# Separação Orçamento × Venda usa Blue.dbo.TbOrcPedVnd.OrcPedVnd (1=Orc, 2=Venda).

import pandas as pd
import threading
import time
import logging
from datetime import datetime
from config.settings import BOT_INTERVALS, ALERTAS, FILIAL_EXCLUIR
from core.database import db

logger = logging.getLogger(__name__)

MAX             = ALERTAS.get("query_max_rows", 5000)
DIAS_RISCO      = ALERTAS.get("cliente_em_risco_dias", 60)
DIAS_INATIVO    = ALERTAS.get("cliente_inativo_dias", 90)
DIAS_CRITICO    = ALERTAS.get("estoque_critico_dias_sem_vnd", 90)
DIAS_LISTA_INAT = 30  # mostra inativos a partir de 30 dias
_MES_INI        = "DATEADD(month, DATEDIFF(month, 0, GETDATE()), 0)"
_MES_FIM        = "DATEADD(month, DATEDIFF(month, 0, GETDATE()) + 1, 0)"
_FILTRO_FILIAL  = f"AND v.CodFilial <> '{FILIAL_EXCLUIR}'" if FILIAL_EXCLUIR else ""


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
        self.erro_msg: str   = ""

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
                self.erro_msg = ""
            except Exception as e:
                logger.error("Bot [%s] erro: %s", self.name_label, e)
                self.status = "erro"
                self.erro_msg = str(e)
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
            WHERE v.DtVnd >= {_MES_INI}
              AND v.DtVnd <  {_MES_FIM}
              AND d.Cancelado    = ''
              AND d.Fat          = 1
              {_FILTRO_FILIAL}
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
            WHERE v.DtVnd >= {_MES_INI}
              AND v.DtVnd <  {_MES_FIM}
              AND d.Cancelado = ''
              AND d.Fat = 1
              {_FILTRO_FILIAL}
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
              {_FILTRO_FILIAL}
            GROUP BY CONVERT(date, v.DtVnd)
            ORDER BY dia
        """)

        df_marcas = db.query(f"""
            SELECT TOP 8
                i.DescrMarca,
                SUM(i.PrecoVndTotItem)                           AS faturamento,
                SUM(i.PrecoVndTotItem) - SUM(i.CustoRepTotItem) AS margem_bruta
            FROM Blue.dbo.vmVndItemDoc i
            WHERE i.DtVnd >= {_MES_INI}
              AND i.DtVnd <  {_MES_FIM}
              AND i.Fat = 1
              AND i.DescrMarca IS NOT NULL
            GROUP BY i.DescrMarca
            ORDER BY faturamento DESC
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
            "marcas_mes":         df_marcas.to_dict("records"),
        }


# ──────────────────────────────────────────────────────────────────
#  BOT VENDAS  — análise por marca, grupo, vendedor e devoluções
# ──────────────────────────────────────────────────────────────────
class BotVendas(BaseBot):
    def __init__(self):
        super().__init__("vendas")

    def analisar(self, filtro_data: str = "", planos_filter: list = None) -> dict:
        """filtro_data: fragmento SQL para WHERE de data. Vazio = mês atual.
        planos_filter: lista de CodPlanoVnd para filtrar (None = todos)."""
        if not filtro_data:
            filtro_data = (
                f"i.DtVnd >= {_MES_INI}"
                f" AND i.DtVnd < {_MES_FIM}"
            )
        filtro_v = filtro_data.replace("i.DtVnd", "v.DtVnd")
        filtro_d = filtro_data.replace("i.DtVnd", "dev.DtVnd")
        if planos_filter:
            _pl = ",".join(str(int(p)) for p in planos_filter)
            filtro_plano_v = f"AND v.CodPlanoVnd IN ({_pl})"
            filtro_plano_i = (
                f"AND EXISTS (SELECT 1 FROM Blue.dbo.vmVndDoc vv"
                f" WHERE vv.NrDoc = i.NrDoc AND vv.NSUDoc = i.NSUDoc"
                f" AND vv.CodPlanoVnd IN ({_pl}))"
            )
        else:
            filtro_plano_v = ""
            filtro_plano_i = ""

        df_kpi = db.query(f"""
            SELECT
                SUM(v.ValVndTotal)        AS faturamento_total,
                COUNT(DISTINCT v.NrDoc)   AS qtd_vendas,
                AVG(v.ValVndTotal)        AS ticket_medio
            FROM Blue.dbo.vmVndDoc v
            INNER JOIN Blue.dbo.vwVndDoc d ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE d.Cancelado = '' AND d.Fat = 1
              AND {filtro_v}
              {filtro_plano_v}
              {_FILTRO_FILIAL}
        """)

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
            WHERE d.Cancelado = '' AND i.Fat = 1
              AND {filtro_data}
              {filtro_plano_i}
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
            WHERE d.Cancelado = '' AND i.Fat = 1
              AND {filtro_data}
              {filtro_plano_i}
            GROUP BY i.CodGrpItem, i.DescrGrpItem
            ORDER BY faturamento DESC
        """)

        df_dev = db.query(f"""
            SELECT SUM(dev.ValTotItem) AS total_devolucoes
            FROM Blue.dbo.vmMetricasMotivoDevItem dev
            WHERE {filtro_d}
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
            WHERE d.Cancelado = '' AND d.Fat = 1
              AND {filtro_v}
              {filtro_plano_v}
            GROUP BY v.Vendedor, v.CodVend
            ORDER BY total_venda DESC
        """)

        margem = sum(float(r.get("margem_bruta", 0) or 0)
                     for r in df_marca.to_dict("records"))

        return {
            "faturamento_total": _safe_float(df_kpi, "faturamento_total"),
            "qtd_vendas":        _safe_int(df_kpi, "qtd_vendas"),
            "ticket_medio":      _safe_float(df_kpi, "ticket_medio"),
            "margem_total":      margem,
            "total_devolucoes":  _safe_float(df_dev, "total_devolucoes"),
            "por_marca":         df_marca.to_dict("records"),
            "por_grupo":         df_grupo.to_dict("records"),
            "por_vendedor":      df_vend.to_dict("records"),
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
                COUNT(*)  AS total_itens,
                SUM(VlrEstq)      AS valor_total_estoque,
                SUM(QtdEstq)      AS qtd_total,
                SUM(QtdEstqDisp)  AS qtd_disponivel,
                SUM(CASE WHEN QtdEstqDisp <= 0 THEN 1 ELSE 0 END) AS itens_zerados,
                SUM(CASE WHEN ISNULL(DATEDIFF(day, DtUltVnd, GETDATE()), 9999) > {DIAS_CRITICO}
                         THEN 1 ELSE 0 END) AS itens_sem_giro
            FROM Blue.dbo.vmAnaliseEstqVnd
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
                CASE WHEN ISNULL(DATEDIFF(day, e.DtUltVnd, GETDATE()), 9999) > 120
                     THEN 120
                     ELSE ISNULL(DATEDIFF(day, e.DtUltVnd, GETDATE()), 0)
                END AS DiasSemVnd,
                e.DtUltVnd,
                e.CustoRepProd,
                e.VlrEstq,
                e.QtdPendPedCmp,
                e.FornecUltCmp
            FROM Blue.dbo.vmAnaliseEstqVnd e
            WHERE ISNULL(DATEDIFF(day, e.DtUltVnd, GETDATE()), 9999) > {DIAS_CRITICO}
               OR e.QtdEstqDisp <= 0
            ORDER BY ISNULL(DATEDIFF(day, e.DtUltVnd, GETDATE()), 9999) DESC,
                     e.VlrEstq DESC
        """)

        df_marca = db.query(f"""
            SELECT TOP 30
                e.DescrMarca,
                COUNT(*)                                                       AS qtd_itens,
                SUM(e.VlrEstq)                                                 AS valor_estoque,
                AVG(CASE WHEN ISNULL(DATEDIFF(day, e.DtUltVnd, GETDATE()), 9999) > 120
                         THEN 120
                         ELSE ISNULL(DATEDIFF(day, e.DtUltVnd, GETDATE()), 0)
                    END)                                                           AS media_dias_sem_venda,
                SUM(e.QtdEstq)                                                 AS quantidade_total
            FROM Blue.dbo.vmAnaliseEstqVnd e
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

        # ── Venda × Estoque por item (90 dias) ───────────────────────
        df_venda_estq = db.query(f"""
            SELECT TOP 30
                e.CodItem,
                e.DescrItem,
                e.DescrMarca,
                e.QtdEstq,
                e.QtdEstqDisp,
                e.VlrEstq,
                ISNULL(v.qtd_vendida_90d, 0) AS qtd_vendida_90d,
                ISNULL(v.val_vendido_90d,  0) AS val_vendido_90d
            FROM Blue.dbo.vmAnaliseEstqVnd e
            LEFT JOIN (
                SELECT i.CodItem,
                       SUM(i.QtdItem)         AS qtd_vendida_90d,
                       SUM(i.PrecoVndTotItem) AS val_vendido_90d
                FROM Blue.dbo.vmVndItemDoc i
                INNER JOIN Blue.dbo.vwVndDoc d ON i.NrDoc = d.NrDoc AND i.NSUDoc = d.NSUDoc
                WHERE d.Cancelado = '' AND i.Fat = 1
                  AND i.DtVnd >= DATEADD(day, -90, GETDATE())
                GROUP BY i.CodItem
            ) v ON e.CodItem = v.CodItem
            WHERE e.QtdEstq > 0
            ORDER BY ISNULL(v.qtd_vendida_90d, 0) DESC
        """)

        # ── Orçamento × Estoque por item (mês atual) ─────────────────
        df_orc_estq = db.query(f"""
            SELECT TOP 30
                e.CodItem,
                e.DescrItem,
                e.DescrMarca,
                e.QtdEstqDisp,
                ISNULL(o.qtd_orcada, 0) AS qtd_orcada,
                ISNULL(o.val_orcado,  0) AS val_orcado
            FROM Blue.dbo.vmAnaliseEstqVnd e
            LEFT JOIN (
                SELECT i.CodItem,
                       SUM(i.QtdItem)         AS qtd_orcada,
                       SUM(i.PrecoVndTotItem) AS val_orcado
                FROM Blue.dbo.TbOrcPedVnd p
                INNER JOIN Blue.dbo.vmVndItemDoc i ON p.NrOrcPedVnd = i.NrDoc
                WHERE p.OrcPedVnd = 1
                  AND p.DtOrcPedVnd >= {_MES_INI}
                  AND p.DtOrcPedVnd <  {_MES_FIM}
                GROUP BY i.CodItem
            ) o ON e.CodItem = o.CodItem
            WHERE ISNULL(o.qtd_orcada, 0) > 0
            ORDER BY qtd_orcada DESC
        """)

        # ── Venda × Compra (30 dias, via movimentação) ───────────────
        df_venda_compra = db.query(f"""
            SELECT TOP 30
                m.CodItem,
                m.DescrItem,
                SUM(m.QtdSaida)   AS saidas,
                SUM(m.QtdEntrada) AS entradas
            FROM Blue.dbo.vmItemMovEstq m
            WHERE m.DtMovEstq >= DATEADD(day, -30, GETDATE())
            GROUP BY m.CodItem, m.DescrItem
            HAVING SUM(m.QtdSaida) > 0 OR SUM(m.QtdEntrada) > 0
            ORDER BY saidas DESC
        """)

        # ── Média venda semanal por item (90 dias) ───────────────────
        df_media_semanal = db.query(f"""
            SELECT TOP {MAX}
                i.CodItem,
                MAX(e.DescrItem)   AS DescrItem,
                MAX(e.DescrMarca)  AS DescrMarca,
                SUM(i.QtdItem)                                        AS total_90d,
                CAST(SUM(i.QtdItem) AS FLOAT) / (90.0 / 7.0)         AS media_semanal,
                MAX(ISNULL(e.QtdEstq, 0))                             AS QtdEstq,
                MAX(ISNULL(e.QtdEstqDisp, 0))                         AS QtdEstqDisp,
                CASE
                    WHEN SUM(i.QtdItem) > 0
                    THEN MAX(ISNULL(e.QtdEstqDisp, 0))
                         / (CAST(SUM(i.QtdItem) AS FLOAT) / (90.0 / 7.0))
                    ELSE 999
                END AS semanas_cobertura
            FROM Blue.dbo.vmVndItemDoc i
            INNER JOIN Blue.dbo.vwVndDoc d ON i.NrDoc = d.NrDoc AND i.NSUDoc = d.NSUDoc
            LEFT JOIN Blue.dbo.vmAnaliseEstqVnd e ON i.CodItem = e.CodItem
            WHERE d.Cancelado = '' AND i.Fat = 1
              AND i.DtVnd >= DATEADD(day, -90, GETDATE())
            GROUP BY i.CodItem
            ORDER BY media_semanal DESC
        """)

        df_sug = db.query(f"""
            SELECT TOP {MAX}
                CodItem,
                DescrItem,
                QtdEstq,
                QtdSugerida,
                FornecUltCmp,
                CustoRepProd
            FROM Blue.dbo.vmSugestaoCompra
            ORDER BY QtdSugerida DESC
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
            "venda_estoque":       df_venda_estq.to_dict("records"),
            "orc_estoque":         df_orc_estq.to_dict("records"),
            "venda_compra":        df_venda_compra.to_dict("records"),
            "media_semanal":       df_media_semanal.to_dict("records"),
            "sugestao_compra":     df_sug.to_dict("records"),
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
                r.CodCli,
                MAX(c.NomeFantCli)                     AS NomeFantCli,
                MAX(c.RzsCli)                          AS RzsCli,
                SUM(r.RcboLiquido)                     AS divida_total,
                COUNT(*)                               AS qtd_titulos,
                MAX(DATEDIFF(day, r.DtVcto, GETDATE())) AS max_dias_atraso
            FROM Blue.dbo.vmVendaXTipoRcbo r
            LEFT JOIN (
                SELECT DISTINCT CodCli, NomeFantCli, RzsCli
                FROM Blue.dbo.vmVndDoc
            ) c ON r.CodCli = c.CodCli
            WHERE r.DtQuitacao IS NULL
              AND r.DtVcto < GETDATE()
            GROUP BY r.CodCli
            ORDER BY divida_total DESC
        """)

        df_a_vencer = db.query("""
            SELECT TOP 30
                r.CodCli,
                MAX(c.NomeFantCli)                AS NomeFantCli,
                SUM(r.RcboLiquido)                AS a_vencer_total,
                COUNT(*)                          AS qtd_titulos,
                MIN(r.DtVcto)                     AS proximo_vencimento
            FROM Blue.dbo.vmVendaXTipoRcbo r
            LEFT JOIN (
                SELECT DISTINCT CodCli, NomeFantCli
                FROM Blue.dbo.vmVndDoc
            ) c ON r.CodCli = c.CodCli
            WHERE r.DtQuitacao IS NULL
              AND r.DtVcto >= GETDATE()
            GROUP BY r.CodCli
            ORDER BY proximo_vencimento ASC
        """)

        df_pmr = db.query("""
            SELECT
                AVG(CAST(DATEDIFF(day, DtLctoCtRec, DtQuitacao) AS float)) AS prazo_medio
            FROM Blue.dbo.vmVendaXTipoRcbo
            WHERE DtQuitacao IS NOT NULL
              AND DtQuitacao >= DATEADD(day, -90, GETDATE())
              AND DtLctoCtRec IS NOT NULL
        """)

        return {
            "recebido_mes":         _safe_float(df_resumo, "recebido"),
            "em_atraso":            _safe_float(df_resumo, "em_atraso"),
            "a_vencer":             _safe_float(df_resumo, "a_vencer"),
            "titulos_atrasados":    _safe_int(df_resumo, "titulos_atrasados"),
            "prazo_medio_receb":    round(_safe_float(df_pmr, "prazo_medio"), 1),
            "por_tipo_recebimento": df_tipo.to_dict("records"),
            "top_inadimplentes":    df_inad.to_dict("records"),
            "a_vencer_lista":       df_a_vencer.to_dict("records"),
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
            WHERE DtOrcPedVnd >= {_MES_INI}
              AND DtOrcPedVnd <  {_MES_FIM}
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
            WHERE o.DtOrcPedVnd >= {_MES_INI}
              AND o.DtOrcPedVnd <  {_MES_FIM}
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
            WHERE DtOrcPedVnd >= {_MES_INI}
              AND DtOrcPedVnd <  {_MES_FIM}
            GROUP BY OrcPedVnd
            ORDER BY OrcPedVnd
        """)

        # ── Meta vs Realizado por Vendedor ────────────────────────
        df_meta_vend = db.query(f"""
            SELECT TOP {MAX}
                Vendedor,
                ValMeta,
                ValRealizado
            FROM Blue.dbo.vmMetaRealizadoVnd
        """)
        if not df_meta_vend.empty and "ValMeta" in df_meta_vend.columns:
            def _cat(row):
                meta = float(row.get("ValMeta", 0) or 0)
                real = float(row.get("ValRealizado", 0) or 0)
                if meta <= 0:
                    return "Sem Meta"
                pct = real / meta * 100
                if pct >= 100:
                    return "Acima da Meta"
                if pct >= 80:
                    return "Próximo (80-99%)"
                return "Abaixo da Meta"
            df_meta_vend["categoria"] = df_meta_vend.apply(_cat, axis=1)
            meta_cats = df_meta_vend.groupby("categoria").size().reset_index(name="qtd").to_dict("records")
        else:
            meta_cats = []

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
            GROUP BY v.CodCli
            HAVING DATEDIFF(day, MAX(v.DtVnd), GETDATE()) >= {DIAS_LISTA_INAT}
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
            "meta_vendedor":      meta_cats,
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
            name: {
                "status":        b.status,
                "ultimo_update": b.ultimo_update,
                "erro_msg":      b.erro_msg,
            }
            for name, b in self.bots.items()
        }

    def get_resultado(self, bot_name: str) -> dict:
        return self.bots.get(bot_name, BaseBot("__null__")).resultado
