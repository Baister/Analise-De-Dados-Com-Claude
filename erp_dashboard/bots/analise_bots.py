# bots/analise_bots.py
# Bots de análise — queries com os nomes reais do banco Blue.
# CodPlanoVnd = FORMA DE PAGAMENTO (não tipo de documento).
# Separação Orçamento × Venda usa Blue.dbo.TbOrcPedVnd.OrcPedVnd (1=Orc, 2=Venda).

import pandas as pd
import threading
import time
import logging
from datetime import datetime
from config.settings import BOT_INTERVALS, ALERTAS, PLANO_EXCLUIR_FAT
from core.database import db
from core.cache import cache as _cache

logger = logging.getLogger(__name__)

MAX             = ALERTAS.get("query_max_rows", 5000)
DIAS_RISCO      = ALERTAS.get("cliente_em_risco_dias", 60)
DIAS_INATIVO    = ALERTAS.get("cliente_inativo_dias", 90)
DIAS_CRITICO    = ALERTAS.get("estoque_critico_dias_sem_vnd", 90)
DIAS_LISTA_INAT = 30  # mostra inativos a partir de 30 dias
_MES_INI        = "DATEADD(month, DATEDIFF(month, 0, GETDATE()), 0)"
_MES_FIM        = "DATEADD(month, DATEDIFF(month, 0, GETDATE()) + 1, 0)"
_EXCLUIR_PLANO  = f"AND v.CodPlanoVnd <> {PLANO_EXCLUIR_FAT}"  # exclui plano 25 dos totais


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
        try:
            _cache.save(self.name_label, self.resultado)
        except Exception as e:
            logger.warning("cache.save error for %s: %s", self.name_label, e)

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
              {_EXCLUIR_PLANO}
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
              {_EXCLUIR_PLANO}
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
              {_EXCLUIR_PLANO}
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
              {_EXCLUIR_PLANO}
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

        df_dev_vend = db.query(f"""
            SELECT
                v.CodVend,
                COUNT(DISTINCT dev.NrDoc) AS qtd_devolucoes
            FROM Blue.dbo.vmMetricasMotivoDevItem dev
            INNER JOIN Blue.dbo.vmVndDoc v ON dev.NrDoc = v.NrDoc
            WHERE {filtro_d}
            GROUP BY v.CodVend
        """)
        if not df_dev_vend.empty and not df_vend.empty:
            dev_dict = df_dev_vend.set_index("CodVend")["qtd_devolucoes"].to_dict()
            df_vend["qtd_devolucoes"] = df_vend["CodVend"].map(dev_dict).fillna(0).astype(int)
        elif not df_vend.empty:
            df_vend["qtd_devolucoes"] = 0

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
    """Detecta colunas em runtime via SELECT TOP 0 * para tolerar variações de schema.
    Views usadas (somente SELECT): vmAnaliseEstqItem, vmAnaliseEstqVnd,
    vmItemMovEstq, vmSugestaoTransfEstq, vwEstqTempOs, vwFuncRespEstq."""

    _VIEWS = {
        "item": "Blue.dbo.vmAnaliseEstqItem",
        "vnd":  "Blue.dbo.vmAnaliseEstqVnd",
        "mov":  "Blue.dbo.vmItemMovEstq",
        "sug":  "Blue.dbo.vmSugestaoTransfEstq",
        "os":   "Blue.dbo.vwEstqTempOs",
        "func": "Blue.dbo.vwFuncRespEstq",
    }

    def __init__(self):
        super().__init__("estoque")
        self._s: dict[str, list] = {}
        self._loaded = False

    def _load_schemas(self):
        if self._loaded:
            return
        for tag, view in self._VIEWS.items():
            df = db.query(f"SELECT TOP 0 * FROM {view}")
            if len(df.columns) > 0:
                self._s[tag] = list(df.columns)
            else:
                # TOP 0 pode falhar em views com erros de compilação — tenta TOP 1 como fallback
                df1 = db.query(f"SELECT TOP 1 * FROM {view}")
                self._s[tag] = list(df1.columns) if len(df1.columns) > 0 else []
            logger.info("[Estq] %-4s %-32s → %s",
                        tag, view.split(".")[-1],
                        self._s[tag] if self._s[tag] else "(INACESSÍVEL)")
        self._loaded = True

    def _c(self, tag: str, *cands: str) -> str:
        """Retorna o primeiro candidato encontrado no schema (insensível a maiúsculas)."""
        lc = {c.lower(): c for c in self._s.get(tag, [])}
        for cand in cands:
            if cand.lower() in lc:
                return lc[cand.lower()]
        return ""

    def _best(self, *tags: str) -> tuple:
        """(view_path, tag) para o primeiro tag com schema disponível."""
        for t in tags:
            if self._s.get(t):
                return self._VIEWS[t], t
        return self._VIEWS[tags[0]], tags[0]

    def analisar(self) -> dict:
        self._load_schemas()
        ev,  et  = self._best("item", "vnd")
        evv, evt = self._best("vnd",  "item")

        col_cod  = self._c(et,  "CodItem",       "Codigo",         "CodigoItem",      "CodProduto")
        col_dsc  = self._c(et,  "DescrItem",     "Descricao",      "NomeItem",        "DescrProduto",
                                "NomeProduto",   "DescrProd")
        col_mrc  = self._c(et,  "DescrMarca",    "Marca",          "DescrMarcaItem",  "NomeMarca",
                                "DescrMarcaProd","MarcaItem")
        col_qtd  = self._c(et,  "QtdEstq",       "SaldoEstq",      "QtdSaldo",        "Qtd",
                                "QtdEstoque",    "QtdTotEstq",     "QtdTotalEstq",    "SaldoQtd",
                                "QtdSaldoEstq",  "QuantidadeEstq", "Quantidade")
        col_disp = self._c(et,  "QtdEstqDisp",   "SaldoDisp",      "QtdDisp",         "QtdSaldoDisp",
                                "QtdEstqDisponiveis","QtdDisponivel","QtdEstoqueDisp",  "QtdSaldoDisponivel",
                                "SaldoDisponivel","QtdDispEstq")
        col_vlr  = self._c(et,  "VlrEstq",       "ValEstq",        "VlrTotEstq",      "SaldoVlr",
                                "ValorEstoque",  "VlrTotalEstq",   "ValTotEstq",      "VlrTotal",
                                "ValorTotal",    "TotVlrEstq",     "VlrEstoque",      "VlrSaldoEstq",
                                "ValSaldoEstq",  "VlrTotItem",     "ValTotItem")
        col_cst  = self._c(et,  "CustoRepProd",  "CustoRep",       "ValCustoRep",     "CustoReposicao",
                                "CustoRepItem",  "VlrCustoRep")
        col_forn = self._c(et,  "FornecUltCmp",  "FornecUltima",   "CodFornecUlt",    "Fornecedor",
                                "NomeFornec",    "FornecedorUlt")
        col_pend = self._c(et,  "QtdPendPedCmp", "PendPed",        "QtdPedCmp",       "QtdPendCmp",
                                "QtdPendentePed","QtdPendCompra")
        col_dtv  = (self._c(et,  "DtUltVnd",      "DtUltimaVenda",  "DtVnd",           "UltDtVnd",
                                "DtUltVenda",    "DataUltVnd",     "DataUltimaVenda", "DtUltimaVnd")
                    or self._c(evt,"DtUltVnd",   "DtUltimaVenda",  "DtVnd",           "UltDtVnd",
                                "DtUltVenda",    "DataUltVnd",     "DataUltimaVenda", "DtUltimaVnd"))

        logger.info("[Estq] Cols detectadas: ev=%s | cod='%s' qtd='%s' vlr='%s' disp='%s' dtv='%s'",
                    ev.split(".")[-1], col_cod, col_qtd, col_vlr, col_disp, col_dtv)
        if not col_qtd and not col_vlr and not col_disp:
            logger.warning("[Estq] NENHUMA coluna-chave detectada! Colunas brutas de [%s]: %s",
                           et, self._s.get(et, []))

        smov     = self._s.get("mov", [])
        col_mcod = self._c("mov", "CodItem",      "Codigo",      "CodProduto",    "CodigoItem",  "CodItm")
        col_mdsc = self._c("mov", "DescrItem",    "Descricao",  "NomeItem",      "DescrProduto","NomeProduto", "DescrProd")
        col_ment = self._c("mov", "QtdEntrada",   "Entrada",    "Qtd_Entrada",   "QtdEntradas", "TotEntrada",  "EntradaQtd",  "SaldoEntrada", "QtdEnt")
        col_msai = self._c("mov", "QtdSaida",     "Saida",      "Qtd_Saida",     "QtdSaidas",   "TotSaida",    "SaidaQtd",    "SaldoSaida",   "QtdSai", "QtdLiqVendas", "QtdLiq")
        col_mliq = self._c("mov", "QtdLiqVendas", "QtdLiq",     "Liquido",       "QtdLiquido",  "LiqVnd")
        col_mdt  = self._c("mov", "DtMovEstq",    "DtMov",      "Data",          "DtMovimento", "DtMov",       "DataMov")

        def _sum(col, alias):
            return f"SUM(ISNULL({col},0)) AS {alias}" if col else f"0 AS {alias}"

        wh_q    = f"WHERE ISNULL({col_qtd},0)>0" if col_qtd else ""
        zero_ex = (f"SUM(CASE WHEN ISNULL({col_disp},0)<=0 THEN 1 ELSE 0 END) AS itens_zerados"
                   if col_disp else "0 AS itens_zerados")
        giro_ex = (f"SUM(CASE WHEN ISNULL(DATEDIFF(day,{col_dtv},GETDATE()),9999)"
                   f">{DIAS_CRITICO} THEN 1 ELSE 0 END) AS itens_sem_giro"
                   if col_dtv else "0 AS itens_sem_giro")

        df_resumo = db.query(f"""
            SELECT COUNT(*) AS total_itens,
                   {_sum(col_vlr, 'valor_total_estoque')},
                   {_sum(col_qtd, 'qtd_total')},
                   {_sum(col_disp,'qtd_disponivel')},
                   {zero_ex}, {giro_ex}
            FROM {ev} {wh_q}
        """)

        _cp = list(filter(None, [
            f"e.{col_cod}  AS CodItem"       if col_cod  else None,
            f"e.{col_dsc}  AS DescrItem"     if col_dsc  else None,
            f"e.{col_mrc}  AS DescrMarca"    if col_mrc  else None,
            f"e.{col_qtd}  AS QtdEstq"       if col_qtd  else None,
            f"e.{col_disp} AS QtdEstqDisp"   if col_disp else None,
            (f"CASE WHEN ISNULL(DATEDIFF(day,e.{col_dtv},GETDATE()),9999)>120 THEN 120"
             f" ELSE ISNULL(DATEDIFF(day,e.{col_dtv},GETDATE()),0) END AS DiasSemVnd"
             if col_dtv else None),
            f"e.{col_dtv}  AS DtUltVnd"      if col_dtv  else None,
            f"e.{col_cst}  AS CustoRepProd"  if col_cst  else None,
            f"e.{col_vlr}  AS VlrEstq"       if col_vlr  else None,
            f"e.{col_pend} AS QtdPendPedCmp" if col_pend else None,
            f"e.{col_forn} AS FornecUltCmp"  if col_forn else None,
        ]))
        _wd = (f"ISNULL(DATEDIFF(day,e.{col_dtv},GETDATE()),9999)>{DIAS_CRITICO}"
               if col_dtv else "")
        _wz = f"e.{col_disp}<=0" if col_disp else ""
        _od = f"ISNULL(DATEDIFF(day,e.{col_dtv},GETDATE()),9999) DESC," if col_dtv else ""
        _ov = f"e.{col_vlr} DESC" if col_vlr else "1"
        _where_crit = " OR ".join(filter(None, [_wd, _wz])) or "1=1"
        df_criticos = db.query(f"""
            SELECT TOP {MAX} {", ".join(_cp) if _cp else "e.*"}
            FROM {ev} e WHERE {_where_crit}
            ORDER BY {_od} {_ov}
        """)

        df_marca = db.query(f"""
            SELECT TOP 30 e.{col_mrc} AS DescrMarca,
                COUNT(*) AS qtd_itens,
                {_sum(col_vlr, 'valor_estoque')},
                {_sum(col_qtd, 'quantidade_total')}
            FROM {ev} e GROUP BY e.{col_mrc} ORDER BY valor_estoque DESC
        """) if col_mrc else pd.DataFrame()

        _wm = f"m.{col_mdt}>=DATEADD(day,-30,GETDATE())" if col_mdt else "1=1"
        df_mov = pd.DataFrame()
        if smov and col_mcod:
            _mp = [f"m.{col_mcod} AS CodItem"]
            if col_mdsc: _mp.append(f"m.{col_mdsc} AS DescrItem")
            _mp.append(f"SUM(m.{col_ment}) AS entradas" if col_ment else "0 AS entradas")
            _mp.append(f"SUM(m.{col_msai}) AS saidas"   if col_msai else "0 AS saidas")
            if col_mliq: _mp.append(f"SUM(m.{col_mliq}) AS vendas_liquidas")
            _grp = f"m.{col_mcod}" + (f", m.{col_mdsc}" if col_mdsc else "")
            df_mov = db.query(f"""
                SELECT TOP 2000 {", ".join(_mp)}
                FROM Blue.dbo.vmItemMovEstq m WHERE {_wm}
                GROUP BY {_grp} ORDER BY saidas DESC
            """)

        df_venda_estq = pd.DataFrame()
        if col_cod:
            _vep = [f"e.{col_cod} AS CodItem"]
            for _cx, _ax in [(col_dsc,"DescrItem"),(col_mrc,"DescrMarca"),
                              (col_qtd,"QtdEstq"),  (col_vlr,"VlrEstq")]:
                if _cx:
                    _vep.append(f"e.{_cx} AS {_ax}")
            _col_disp_ve = col_disp or col_qtd
            _vep += [
                f"ISNULL(e.{_col_disp_ve},0) AS QtdEstqDisp" if _col_disp_ve else "0 AS QtdEstqDisp",
                "ISNULL(v.qtd_vendida_90d,0) AS qtd_vendida_90d",
                "ISNULL(v.val_vendido_90d, 0) AS val_vendido_90d",
            ]
            _where_ve = f"WHERE ISNULL(e.{col_disp},0)>=0" if col_disp else ""
            df_venda_estq = db.query(f"""
                SELECT TOP 30 {", ".join(_vep)}
                FROM {ev} e
                LEFT JOIN (
                    SELECT i.CodItem,
                           SUM(i.QtdItem)         AS qtd_vendida_90d,
                           SUM(i.PrecoVndTotItem) AS val_vendido_90d
                    FROM Blue.dbo.vmVndItemDoc i
                    INNER JOIN Blue.dbo.vwVndDoc d ON i.NrDoc=d.NrDoc AND i.NSUDoc=d.NSUDoc
                    WHERE d.Cancelado='' AND i.Fat=1
                      AND i.DtVnd>=DATEADD(day,-90,GETDATE())
                    GROUP BY i.CodItem
                ) v ON e.{col_cod}=v.CodItem
                {_where_ve}
                ORDER BY ISNULL(v.qtd_vendida_90d,0) DESC
            """)

        df_orc_estq = pd.DataFrame()
        if col_cod:
            _oep = [f"e.{col_cod} AS CodItem"]
            if col_dsc: _oep.append(f"e.{col_dsc} AS DescrItem")
            if col_mrc: _oep.append(f"e.{col_mrc} AS DescrMarca")
            _col_disp_oe = col_disp or col_qtd
            _oep += [
                f"ISNULL(e.{_col_disp_oe},0) AS QtdEstqDisp" if _col_disp_oe else "0 AS QtdEstqDisp",
                "ISNULL(o.qtd_orcada,0) AS qtd_orcada",
                "ISNULL(o.val_orcado, 0) AS val_orcado",
            ]
            df_orc_estq = db.query(f"""
                SELECT TOP 30 {", ".join(_oep)}
                FROM {ev} e
                LEFT JOIN (
                    SELECT i.CodItem,
                           SUM(i.QtdItem)         AS qtd_orcada,
                           SUM(i.PrecoVndTotItem) AS val_orcado
                    FROM Blue.dbo.vmVndItemDoc i
                    INNER JOIN Blue.dbo.TbOrcPedVnd p ON i.NrDoc=p.NrOrcPedVnd
                    WHERE p.OrcPedVnd=1
                      AND i.DtVnd>=DATEADD(day,-30,GETDATE())
                    GROUP BY i.CodItem
                ) o ON e.{col_cod}=o.CodItem
                WHERE ISNULL(o.qtd_orcada,0)>0
                ORDER BY qtd_orcada DESC
            """)

        df_venda_compra = pd.DataFrame()
        if smov and col_mcod:
            _vcp = [f"m.{col_mcod} AS CodItem"]
            if col_mdsc: _vcp.append(f"m.{col_mdsc} AS DescrItem")
            _vcp.append(f"SUM(m.{col_msai}) AS saidas"   if col_msai else "0 AS saidas")
            _vcp.append(f"SUM(m.{col_ment}) AS entradas" if col_ment else "0 AS entradas")
            _grpvc = f"m.{col_mcod}" + (f", m.{col_mdsc}" if col_mdsc else "")
            _hvc = (f"SUM(m.{col_msai})>0 OR SUM(m.{col_ment})>0"
                    if col_msai and col_ment else "1=1")
            df_venda_compra = db.query(f"""
                SELECT TOP 30 {", ".join(_vcp)}
                FROM Blue.dbo.vmItemMovEstq m
                WHERE {_wm} GROUP BY {_grpvc}
                HAVING {_hvc} ORDER BY saidas DESC
            """)

        df_media_semanal = pd.DataFrame()
        if col_cod:
            _msp = ["i.CodItem"]
            if col_dsc: _msp.append(f"MAX(e.{col_dsc}) AS DescrItem")
            if col_mrc: _msp.append(f"MAX(e.{col_mrc}) AS DescrMarca")
            _msp += ["SUM(i.QtdItem) AS total_90d",
                     "CAST(SUM(i.QtdItem) AS FLOAT)/(90.0/7.0) AS media_semanal"]
            if col_qtd:  _msp.append(f"MAX(ISNULL(e.{col_qtd},0)) AS QtdEstq")
            if col_disp: _msp.append(f"MAX(ISNULL(e.{col_disp},0)) AS QtdEstqDisp")
            _cov = (f"MAX(ISNULL(e.{col_disp},0))/(CAST(SUM(i.QtdItem) AS FLOAT)/(90.0/7.0))"
                    if col_disp else "999")
            _msp.append(
                f"CASE WHEN SUM(i.QtdItem)>0 THEN {_cov} ELSE 999 END AS semanas_cobertura")
            # JOIN com estoque só quando há colunas úteis a buscar — evita fan-out quando
            # ev = vmAnaliseEstqVnd (N linhas por item → distorce SUM(i.QtdItem))
            _need_join_e = any([col_dsc, col_mrc, col_qtd, col_disp])
            _join_e_ms   = f"LEFT JOIN {ev} e ON i.CodItem=e.{col_cod}" if _need_join_e else ""
            df_media_semanal = db.query(f"""
                SELECT TOP {MAX} {", ".join(_msp)}
                FROM Blue.dbo.vmVndItemDoc i
                INNER JOIN Blue.dbo.vwVndDoc d ON i.NrDoc=d.NrDoc AND i.NSUDoc=d.NSUDoc
                {_join_e_ms}
                WHERE d.Cancelado='' AND i.Fat=1
                  AND i.DtVnd>=DATEADD(day,-90,GETDATE())
                GROUP BY i.CodItem ORDER BY media_semanal DESC
            """)

        df_sug = db.query(f"SELECT TOP {MAX} * FROM Blue.dbo.vmSugestaoTransfEstq")
        df_os  = db.query("SELECT TOP 200 * FROM Blue.dbo.vwEstqTempOs")

        def _recs(df):
            return df.to_dict("records") if not df.empty else []

        return {
            "total_itens":            _safe_int(df_resumo,  "total_itens"),
            "valor_total_estoque":    _safe_float(df_resumo,"valor_total_estoque"),
            "qtd_disponivel":         _safe_int(df_resumo,  "qtd_disponivel"),
            "itens_zerados":          _safe_int(df_resumo,  "itens_zerados"),
            "itens_sem_giro":         _safe_int(df_resumo,  "itens_sem_giro"),
            "criticos":               _recs(df_criticos),
            "por_marca":              _recs(df_marca),
            "movimentacao":           df_mov.head(50).to_dict("records") if not df_mov.empty else [],
            "venda_estoque":          _recs(df_venda_estq),
            "orc_estoque":            _recs(df_orc_estq),
            "venda_compra":           _recs(df_venda_compra),
            "media_semanal":          _recs(df_media_semanal),
            "sugestao_transferencia": _recs(df_sug),
            "estq_os":                _recs(df_os),
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

        # inadimplentes: query simples sem JOIN (mais robusta)
        df_inad = db.query("""
            SELECT TOP 50
                CodCli,
                SUM(RcboLiquido)                      AS divida_total,
                COUNT(*)                               AS qtd_titulos,
                MAX(DATEDIFF(day, DtVcto, GETDATE()))  AS max_dias_atraso
            FROM Blue.dbo.vmVendaXTipoRcbo
            WHERE DtQuitacao IS NULL
              AND DtVcto < GETDATE()
            GROUP BY CodCli
            ORDER BY divida_total DESC
        """)
        if not df_inad.empty:
            _df_cli = db.query("""
                SELECT DISTINCT CodCli, NomeFantCli, RzsCli
                FROM Blue.dbo.vmVndDoc WHERE CodCli IS NOT NULL
            """)
            if not _df_cli.empty:
                _idx = _df_cli.set_index("CodCli").to_dict("index")
                df_inad["NomeFantCli"] = df_inad["CodCli"].map(
                    lambda c: _idx.get(c, {}).get("NomeFantCli", str(c)))
                df_inad["RzsCli"] = df_inad["CodCli"].map(
                    lambda c: _idx.get(c, {}).get("RzsCli", ""))
            else:
                df_inad["NomeFantCli"] = df_inad["CodCli"].astype(str)
                df_inad["RzsCli"] = ""

        df_a_vencer = db.query("""
            SELECT TOP 30
                CodCli,
                SUM(RcboLiquido)   AS a_vencer_total,
                COUNT(*)           AS qtd_titulos,
                MIN(DtVcto)        AS proximo_vencimento
            FROM Blue.dbo.vmVendaXTipoRcbo
            WHERE DtQuitacao IS NULL
              AND DtVcto >= GETDATE()
            GROUP BY CodCli
            ORDER BY proximo_vencimento ASC
        """)
        if not df_a_vencer.empty:
            _df_cli2 = db.query("""
                SELECT DISTINCT CodCli, NomeFantCli
                FROM Blue.dbo.vmVndDoc WHERE CodCli IS NOT NULL
            """)
            if not _df_cli2.empty:
                _idx2 = _df_cli2.set_index("CodCli")["NomeFantCli"].to_dict()
                df_a_vencer["NomeFantCli"] = df_a_vencer["CodCli"].map(
                    lambda c: _idx2.get(c, str(c)))
            else:
                df_a_vencer["NomeFantCli"] = df_a_vencer["CodCli"].astype(str)

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
