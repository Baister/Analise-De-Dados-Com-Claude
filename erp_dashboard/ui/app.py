# ui/app.py
# Interface principal — sidebar fixa + troca de telas

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading
from datetime import datetime

from config.settings import APP_TITLE, APP_VERSION, CORES, DB_CONFIG
from core.database import db
from bots.analise_bots import BotManager
from core.exportador import exportar_excel

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = CORES  # alias curto


# ──────────────────────────────────────────────────────────────────
#  COMPONENTES BASE
# ──────────────────────────────────────────────────────────────────
class KpiCard(ctk.CTkFrame):
    def __init__(self, master, titulo: str, valor: str = "—",
                 subtitulo: str = "", cor: str = C["accent_azul"], **kw):
        super().__init__(master, fg_color=C["card"], corner_radius=10,
                         border_width=1, border_color=C["card_border"], **kw)
        ctk.CTkLabel(self, text=titulo.upper(),
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=C["subtext"]).pack(anchor="w", padx=14, pady=(12, 0))
        self._val = ctk.CTkLabel(self, text=valor,
                                  font=ctk.CTkFont(size=24, weight="bold"),
                                  text_color=cor)
        self._val.pack(anchor="w", padx=14, pady=2)
        self._sub = ctk.CTkLabel(self, text=subtitulo,
                                  font=ctk.CTkFont(size=10),
                                  text_color=C["subtext"])
        self._sub.pack(anchor="w", padx=14, pady=(0, 12))

    def update(self, valor: str, subtitulo: str = "", cor: str = None):
        self._val.configure(text=valor)
        if subtitulo:
            self._sub.configure(text=subtitulo)
        if cor:
            self._val.configure(text_color=cor)


class Grafico(ctk.CTkFrame):
    def __init__(self, master, titulo: str, **kw):
        super().__init__(master, fg_color=C["card"], corner_radius=10,
                         border_width=1, border_color=C["card_border"], **kw)
        ctk.CTkLabel(self, text=titulo,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=14, pady=(10, 0))
        self._canvas = None
        self._fig    = None

    def _clean(self):
        if self._canvas:
            self._canvas.get_tk_widget().destroy()
            self._canvas = None
        if self._fig:
            plt.close(self._fig)
            self._fig = None

    def barras(self, labels, valores, cor=C["accent_azul"], horizontal=False):
        self._clean()
        fig, ax = plt.subplots(figsize=(5, 3))
        fig.patch.set_facecolor(C["card"])
        ax.set_facecolor(C["card"])
        if horizontal:
            bars = ax.barh(labels[::-1], valores[::-1], color=cor, height=0.6)
            ax.tick_params(axis="y", labelsize=8, colors=C["subtext"])
            ax.tick_params(axis="x", labelsize=8, colors=C["subtext"])
        else:
            bars = ax.bar(labels, valores, color=cor, width=0.6, zorder=3)
            ax.tick_params(colors=C["subtext"], labelsize=8)
            ax.yaxis.grid(True, color=C["card_border"], zorder=0)
            ax.set_axisbelow(True)
            lbl_rot = 30 if len(labels) > 6 else 0
            ax.set_xticklabels(labels, rotation=lbl_rot, ha="right" if lbl_rot else "center")
        ax.spines[:].set_visible(False)
        fig.tight_layout(pad=1.0)
        self._fig = fig
        self._canvas = FigureCanvasTkAgg(fig, master=self)
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=6)

    def linha(self, labels, valores, cor=C["accent_azul"], label_nome="Realizado"):
        self._clean()
        fig, ax = plt.subplots(figsize=(5, 3))
        fig.patch.set_facecolor(C["card"])
        ax.set_facecolor(C["card"])
        ax.plot(labels, valores, color=cor, linewidth=2, marker="o", markersize=3, label=label_nome)
        ax.fill_between(labels, valores, alpha=0.15, color=cor)
        ax.tick_params(colors=C["subtext"], labelsize=8)
        ax.spines[:].set_visible(False)
        ax.yaxis.grid(True, color=C["card_border"])
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=7)
        ax.legend(fontsize=8, facecolor=C["card"], labelcolor=C["text"])
        fig.tight_layout(pad=1.0)
        self._fig = fig
        self._canvas = FigureCanvasTkAgg(fig, master=self)
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=6)

    def donut(self, labels, valores, cores=None):
        self._clean()
        if not cores:
            cores = [C["accent_azul"], C["success"], C["warning"], C["accent_verm"], "#8b5cf6"]
        fig, ax = plt.subplots(figsize=(4, 3))
        fig.patch.set_facecolor(C["card"])
        ax.set_facecolor(C["card"])
        wedges, texts, autotexts = ax.pie(
            valores, labels=None, colors=cores[:len(valores)],
            autopct="%1.0f%%", pctdistance=0.75,
            wedgeprops={"width": 0.5, "edgecolor": C["card"]},
        )
        for at in autotexts:
            at.set_color(C["text"])
            at.set_fontsize(8)
        ax.legend(labels, loc="lower center", bbox_to_anchor=(0.5, -0.15),
                  ncol=2, fontsize=7, facecolor=C["card"], labelcolor=C["text"],
                  framealpha=0)
        fig.tight_layout(pad=0.5)
        self._fig = fig
        self._canvas = FigureCanvasTkAgg(fig, master=self)
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=6)


class Tabela(ctk.CTkScrollableFrame):
    def __init__(self, master, colunas: list[str], **kw):
        super().__init__(master, fg_color=C["card"], corner_radius=10,
                         border_width=1, border_color=C["card_border"], **kw)
        self._cols = colunas
        self._rows: list = []
        for j, col in enumerate(colunas):
            ctk.CTkLabel(self, text=col.upper(),
                         font=ctk.CTkFont(size=9, weight="bold"),
                         text_color=C["subtext"]).grid(row=0, column=j, padx=10, pady=(8, 4), sticky="w")

    def _fmt(self, col: str, val) -> str:
        if val is None:
            return "—"
        if isinstance(val, float):
            kw = col.lower()
            if any(x in kw for x in ("fat", "valor", "total", "divida", "ticket", "med", "margen", "custo", "rcbo")):
                return f"R$ {val:,.2f}"
            return f"{val:,.1f}"
        return str(val)

    def populate(self, dados: list[dict]):
        for wrow in self._rows:
            for w in wrow:
                w.destroy()
        self._rows.clear()
        for i, row in enumerate(dados, start=1):
            bg = C["card"] if i % 2 == 0 else C["progress_bg"]
            rw = []
            for j, col in enumerate(self._cols):
                val = row.get(col, row.get(col.lower(), "—"))
                lbl = ctk.CTkLabel(self, text=self._fmt(col, val),
                                   font=ctk.CTkFont(size=10),
                                   text_color=C["text"])
                lbl.grid(row=i, column=j, padx=10, pady=2, sticky="w")
                rw.append(lbl)
            self._rows.append(rw)


def _secao(master, texto: str):
    ctk.CTkLabel(master, text=texto,
                 font=ctk.CTkFont(size=12, weight="bold"),
                 text_color=C["subtext"]).pack(anchor="w", pady=(10, 4))


# ──────────────────────────────────────────────────────────────────
#  TELA DASHBOARD
# ──────────────────────────────────────────────────────────────────
class TelaDashboard(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._build()

    def _build(self):
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 10))
        self.k_fat    = KpiCard(row1, "Faturamento do Mês", cor=C["accent_azul"])
        self.k_docs   = KpiCard(row1, "Documentos")
        self.k_cli    = KpiCard(row1, "Clientes Ativos", cor=C["success"])
        self.k_ticket = KpiCard(row1, "Ticket Médio")
        self.k_meta   = KpiCard(row1, "% da Meta")
        for k in (self.k_fat, self.k_docs, self.k_cli, self.k_ticket, self.k_meta):
            k.pack(side="left", fill="both", expand=True, padx=4)

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="both", expand=True, pady=(0, 10))
        self.g_diario = Grafico(row2, "Faturamento Diário (30 dias)")
        self.g_diario.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.g_vend = Grafico(row2, "Top Vendedores do Mês")
        self.g_vend.pack(side="left", fill="both", expand=True)

    def refresh(self, dados: dict):
        fat  = dados.get("faturamento_atual", 0)
        meta = dados.get("meta_mensal", 400000)
        pct  = dados.get("pct_meta", 0)
        cor_meta = C["success"] if pct >= 100 else C["warning"] if pct >= 70 else C["accent_verm"]
        self.k_fat.update(f"R$ {fat:,.2f}", f"{pct}% da meta")
        self.k_docs.update(str(dados.get("qtd_documentos", 0)))
        self.k_cli.update(str(dados.get("clientes_ativos", 0)))
        self.k_ticket.update(f"R$ {dados.get('ticket_medio', 0):,.2f}")
        self.k_meta.update(f"{pct}%", f"Meta: R$ {meta:,.0f}", cor=cor_meta)

        diario = dados.get("faturamento_diario", [])
        if diario:
            lbs = [str(r.get("dia", ""))[-5:] for r in diario]
            vs  = [float(r.get("faturamento", 0) or 0) for r in diario]
            self.g_diario.linha(lbs, vs)

        vend = dados.get("top_vendedores", [])
        if vend:
            lbs = [str(r.get("Vendedor", r.get("CodVend", "?")))[:15] for r in vend[:8]]
            vs  = [float(r.get("total_venda", 0) or 0) for r in vend[:8]]
            self.g_vend.barras(lbs, vs, horizontal=True)


# ──────────────────────────────────────────────────────────────────
#  TELA VENDAS
# ──────────────────────────────────────────────────────────────────
class TelaVendas(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._build()

    def _build(self):
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 10))
        self.k_dev = KpiCard(row1, "Total Devoluções", cor=C["accent_verm"])
        self.k_mar = KpiCard(row1, "Margem Bruta (estimada)", cor=C["success"])
        for k in (self.k_dev, self.k_mar):
            k.pack(side="left", fill="both", expand=True, padx=4)

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="both", expand=True, pady=(0, 10))
        self.g_marca = Grafico(row2, "Faturamento por Marca")
        self.g_marca.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.g_grupo = Grafico(row2, "Faturamento por Grupo")
        self.g_grupo.pack(side="left", fill="both", expand=True)

        _secao(self, "TOP VENDEDORES (MÊS)")
        self.tab_vend = Tabela(self, ["Vendedor", "total_venda", "qtd_pedidos", "ticket_medio"], height=180)
        self.tab_vend.pack(fill="x", pady=(0, 10))

        _secao(self, "DEVOLUÇÕES POR MOTIVO")
        self.tab_dev = Tabela(self, ["MotivoDevolucao", "Vendedor", "DescrItem", "valor_devolvido", "qtd_devolvida"], height=180)
        self.tab_dev.pack(fill="x")

    def refresh(self, dados: dict):
        self.k_dev.update(f"R$ {dados.get('total_devolucoes', 0):,.2f}")
        marcas = dados.get("por_marca", [])
        margem = sum(float(r.get("margem_bruta", 0) or 0) for r in marcas)
        self.k_mar.update(f"R$ {margem:,.2f}")

        if marcas:
            lbs = [str(r.get("DescrMarca", "?"))[:12] for r in marcas[:10]]
            vs  = [float(r.get("faturamento", 0) or 0) for r in marcas[:10]]
            self.g_marca.barras(lbs, vs)

        grupos = dados.get("por_grupo", [])
        if grupos:
            lbs = [str(r.get("DescrGrpItem", "?"))[:12] for r in grupos[:10]]
            vs  = [float(r.get("faturamento", 0) or 0) for r in grupos[:10]]
            self.g_grupo.barras(lbs, vs, cor=C["warning"])

        self.tab_vend.populate(dados.get("por_vendedor", []))
        self.tab_dev.populate(dados.get("devolucoes", [])[:20])


# ──────────────────────────────────────────────────────────────────
#  TELA ESTOQUE
# ──────────────────────────────────────────────────────────────────
class TelaEstoque(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._build()

    def _build(self):
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 10))
        self.k_itens = KpiCard(row1, "Total Itens")
        self.k_valor = KpiCard(row1, "Valor em Estoque", cor=C["accent_azul"])
        self.k_zero  = KpiCard(row1, "Itens Zerados", cor=C["accent_verm"])
        self.k_giro  = KpiCard(row1, f"Sem Giro +90d", cor=C["warning"])
        for k in (self.k_itens, self.k_valor, self.k_zero, self.k_giro):
            k.pack(side="left", fill="both", expand=True, padx=4)

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="both", expand=True, pady=(0, 10))
        self.g_marca = Grafico(row2, "Valor em Estoque por Marca")
        self.g_marca.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.g_mov   = Grafico(row2, "Movimentação (30 dias)")
        self.g_mov.pack(side="left", fill="both", expand=True)

        _secao(self, "ITENS CRÍTICOS (sem giro ou zerados)")
        self.tab_crit = Tabela(self, ["DescrItem", "DescrMarca", "QtdeEstqDisp", "DiasSemVnd", "VlrEstq", "FornecUltCmp"], height=220)
        self.tab_crit.pack(fill="x")

    def refresh(self, dados: dict):
        self.k_itens.update(str(dados.get("total_itens", 0)))
        self.k_valor.update(f"R$ {dados.get('valor_total_estoque', 0):,.2f}")
        self.k_zero.update(str(dados.get("itens_zerados", 0)))
        self.k_giro.update(str(dados.get("itens_sem_giro", 0)))

        marcas = dados.get("por_marca", [])
        if marcas:
            lbs = [str(r.get("DescrMarca", "?"))[:12] for r in marcas[:10]]
            vs  = [float(r.get("valor_estoque", 0) or 0) for r in marcas[:10]]
            self.g_marca.barras(lbs, vs, cor=C["accent_azul"], horizontal=True)

        mov = dados.get("movimentacao", [])
        if mov:
            lbs = [str(r.get("DescrItem", "?"))[:10] for r in mov[:10]]
            vs  = [float(r.get("saidas", 0) or 0) for r in mov[:10]]
            self.g_mov.barras(lbs, vs, cor=C["success"])

        self.tab_crit.populate(dados.get("criticos", [])[:50])


# ──────────────────────────────────────────────────────────────────
#  TELA FINANCEIRO
# ──────────────────────────────────────────────────────────────────
class TelaFinanceiro(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._build()

    def _build(self):
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 10))
        self.k_rec   = KpiCard(row1, "Recebido (mês)", cor=C["success"])
        self.k_atra  = KpiCard(row1, "Em Atraso",      cor=C["accent_verm"])
        self.k_venc  = KpiCard(row1, "A Vencer",       cor=C["warning"])
        self.k_pmr   = KpiCard(row1, "Prazo Médio (dias)")
        self.k_inad  = KpiCard(row1, "Total Inadimpl.", cor=C["accent_verm"])
        for k in (self.k_rec, self.k_atra, self.k_venc, self.k_pmr, self.k_inad):
            k.pack(side="left", fill="both", expand=True, padx=4)

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="both", expand=True, pady=(0, 10))
        self.g_tipo = Grafico(row2, "Recebimentos por Tipo")
        self.g_tipo.pack(side="left", fill="both", expand=True, padx=(0, 6))

        col_r = ctk.CTkFrame(row2, fg_color="transparent")
        col_r.pack(side="left", fill="both", expand=True)
        _secao(col_r, "TOP INADIMPLENTES")
        self.tab_inad = Tabela(col_r, ["NomeFantCli", "divida_total", "qtd_titulos", "max_dias_atraso"], height=260)
        self.tab_inad.pack(fill="both", expand=True)

    def refresh(self, dados: dict):
        self.k_rec.update(f"R$ {dados.get('recebido_mes', 0):,.2f}")
        self.k_atra.update(f"R$ {dados.get('em_atraso', 0):,.2f}",
                           f"{dados.get('titulos_atrasados', 0)} títulos")
        self.k_venc.update(f"R$ {dados.get('a_vencer', 0):,.2f}")
        self.k_pmr.update(f"{dados.get('prazo_medio_receb', 0)} dias")
        self.k_inad.update(f"R$ {dados.get('total_inadimplencia', 0):,.2f}",
                           f"{dados.get('qtd_inadimplentes', 0)} clientes")

        tipos = dados.get("por_tipo_recebimento", [])
        if tipos:
            lbs = [str(r.get("TipoRcbo", "?")) for r in tipos]
            vs  = [float(r.get("total", 0) or 0) for r in tipos]
            self.g_tipo.donut(lbs, vs)

        self.tab_inad.populate(dados.get("top_inadimplentes", [])[:20])


# ──────────────────────────────────────────────────────────────────
#  TELA CRM
# ──────────────────────────────────────────────────────────────────
class TelaCRM(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._build()

    def _build(self):
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 10))
        self.k_conv  = KpiCard(row1, "Taxa de Conversão", cor=C["success"])
        self.k_risco = KpiCard(row1, "Clientes em Risco",  cor=C["warning"])
        self.k_inat  = KpiCard(row1, "Inativos",           cor=C["accent_verm"])
        for k in (self.k_conv, self.k_risco, self.k_inat):
            k.pack(side="left", fill="both", expand=True, padx=4)

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="both", expand=True, pady=(0, 10))
        self.g_funil  = Grafico(row2, "Funil de Conversão (mês)")
        self.g_funil.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.g_faixas = Grafico(row2, "Clientes por Faixa de Inatividade")
        self.g_faixas.pack(side="left", fill="both", expand=True)

        _secao(self, "CLIENTES INATIVOS / EM RISCO (lista exportável)")
        self.tab_inat = Tabela(
            self,
            ["nome_cliente", "uf", "municipio", "ultima_compra", "dias_sem_compra", "ticket_medio"],
            height=250,
        )
        self.tab_inat.pack(fill="x")

    def refresh(self, dados: dict):
        pct = dados.get("taxa_conversao_pct", 0)
        cor = C["success"] if pct >= 50 else C["warning"] if pct >= 25 else C["accent_verm"]
        orc = dados.get("total_orcamentos", 0)
        cvt = dados.get("total_convertidos", 0)
        self.k_conv.update(f"{pct}%", subtitulo=f"{cvt} de {orc} orçamentos", cor=cor)
        self.k_risco.update(str(dados.get("qtd_em_risco", 0)))
        self.k_inat.update(str(dados.get("qtd_inativos", 0)))

        funil = dados.get("funil", [])
        if funil:
            lbs = [str(r.get("tipo", "?"))[:18] for r in funil]
            vs  = [float(r.get("qtd_documentos", 0) or 0) for r in funil]
            self.g_funil.barras(lbs, vs)

        faixas = dados.get("faixas_inatividade", [])
        if faixas:
            lbs = [str(r.get("faixa", "?")) for r in faixas]
            vs  = [float(r.get("qtd_clientes", 0) or 0) for r in faixas]
            self.g_faixas.barras(lbs, vs, cor=C["warning"])

        self.tab_inat.populate(dados.get("inativos_lista", [])[:100])


# ──────────────────────────────────────────────────────────────────
#  TELA RELATÓRIOS (placeholder)
# ──────────────────────────────────────────────────────────────────
class TelaRelatorios(ctk.CTkFrame):
    def __init__(self, master, bot_manager: "BotManager"):
        super().__init__(master, fg_color="transparent")
        self._bm = bot_manager
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Exportar Relatórios",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=C["text"]).pack(pady=(30, 10))
        ctk.CTkLabel(self, text="Selecione o módulo e clique em Exportar Excel",
                     text_color=C["subtext"]).pack(pady=(0, 20))

        for nome, bot_key in [
            ("Dashboard",  "dashboard"),
            ("Vendas",     "vendas"),
            ("Estoque",    "estoque"),
            ("Financeiro", "financeiro"),
            ("CRM",        "crm"),
        ]:
            ctk.CTkButton(
                self, text=f"  Exportar {nome}",
                width=280, height=40,
                fg_color=C["accent_azul"],
                command=lambda k=bot_key: self._exportar(k),
            ).pack(pady=4)

    def _exportar(self, bot_key: str):
        dados = self._bm.get_resultado(bot_key)
        if not dados:
            messagebox.showwarning("Exportar", "Sem dados ainda. Aguarde o próximo ciclo.")
            return
        path = exportar_excel(dados, bot_key)
        messagebox.showinfo("Exportado!", f"Salvo em:\n{path}")

    def refresh(self, dados: dict):
        pass


# ──────────────────────────────────────────────────────────────────
#  SIDEBAR
# ──────────────────────────────────────────────────────────────────
_SIDEBAR_ITEMS = [
    ("Dashboard",   "■"),
    ("Vendas",      "▶"),
    ("Estoque",     "▣"),
    ("Financeiro",  "Ⓜ"),
    ("CRM",         "☺"),
    ("Relatórios",  "⤓"),
]


class ERPDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE}  v{APP_VERSION}")
        self.geometry("1380x860")
        self.minsize(1100, 700)
        self.configure(fg_color=C["bg"])

        self.bot_manager = BotManager()
        self._telas: dict[str, ctk.CTkFrame] = {}
        self._sidebar_btns: dict[str, ctk.CTkButton] = {}
        self._tela_atual = ""

        self._build_layout()
        self._connect_and_start()

    # ── Layout ──────────────────────────────────────────────────────
    def _build_layout(self):
        # Sidebar
        self._sidebar = ctk.CTkFrame(self, fg_color=C["sidebar"], width=200, corner_radius=0)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        ctk.CTkLabel(
            self._sidebar, text="ERP\nANALYTICS",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=C["accent_azul"],
        ).pack(pady=(24, 20))

        for nome, icone in _SIDEBAR_ITEMS:
            btn = ctk.CTkButton(
                self._sidebar,
                text=f"  {icone}  {nome}",
                anchor="w",
                width=180, height=38,
                fg_color="transparent",
                hover_color=C["card"],
                text_color=C["subtext"],
                font=ctk.CTkFont(size=13),
                command=lambda n=nome: self._navegar(n),
            )
            btn.pack(padx=10, pady=2)
            self._sidebar_btns[nome] = btn

        # Área de conteúdo
        content_wrap = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        content_wrap.pack(side="left", fill="both", expand=True)

        # Header
        header = ctk.CTkFrame(content_wrap, fg_color=C["card"], height=50, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        self._lbl_pagina = ctk.CTkLabel(header, text="Dashboard",
                                         font=ctk.CTkFont(size=14, weight="bold"),
                                         text_color=C["text"])
        self._lbl_pagina.pack(side="left", padx=20)

        self._lbl_status = ctk.CTkLabel(header, text="● Conectando...",
                                         font=ctk.CTkFont(size=11),
                                         text_color=C["warning"])
        self._lbl_status.pack(side="left", padx=16)

        self._lbl_hora = ctk.CTkLabel(header, text="",
                                       font=ctk.CTkFont(size=11),
                                       text_color=C["subtext"])
        self._lbl_hora.pack(side="right", padx=20)

        # Container de telas
        self._frame_telas = ctk.CTkFrame(content_wrap, fg_color=C["bg"], corner_radius=0)
        self._frame_telas.pack(fill="both", expand=True, padx=12, pady=10)

        # Footer
        footer = ctk.CTkFrame(content_wrap, fg_color=C["card"], height=36, corner_radius=0)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self._lbl_bots = ctk.CTkLabel(footer, text="Bots: aguardando conexão...",
                                       font=ctk.CTkFont(size=10),
                                       text_color=C["subtext"])
        self._lbl_bots.pack(side="left", padx=16, pady=8)

        # Cria telas (não visíveis ainda)
        self._telas = {
            "Dashboard":  TelaDashboard(self._frame_telas),
            "Vendas":     TelaVendas(self._frame_telas),
            "Estoque":    TelaEstoque(self._frame_telas),
            "Financeiro": TelaFinanceiro(self._frame_telas),
            "CRM":        TelaCRM(self._frame_telas),
            "Relatórios": TelaRelatorios(self._frame_telas, self.bot_manager),
        }

        self._navegar("Dashboard")
        self._tick_hora()

    def _navegar(self, nome: str):
        for n, t in self._telas.items():
            if n == nome:
                t.pack(fill="both", expand=True)
            else:
                t.pack_forget()

        for n, btn in self._sidebar_btns.items():
            if n == nome:
                btn.configure(fg_color=C["accent_azul"], text_color=C["text"])
            else:
                btn.configure(fg_color="transparent", text_color=C["subtext"])

        self._lbl_pagina.configure(text=nome)
        self._tela_atual = nome

    # ── Conexão ─────────────────────────────────────────────────────
    def _connect_and_start(self):
        def task():
            ok = db.connect()
            if ok:
                self._lbl_status.configure(text="● Conectado", text_color=C["success"])
                self._register_callbacks()
                self.bot_manager.start_all()
            else:
                self._lbl_status.configure(
                    text=f"● Erro — DSN: {DB_CONFIG['dsn']}", text_color=C["accent_verm"])
                self.after(0, lambda: messagebox.showerror(
                    "Erro de Conexão",
                    f"Não foi possível conectar via DSN '{DB_CONFIG['dsn']}'.\n"
                    "Verifique usuário/senha em config/settings.py",
                ))

        threading.Thread(target=task, daemon=True).start()

    def _register_callbacks(self):
        mapa = {
            "dashboard":  "Dashboard",
            "vendas":     "Vendas",
            "estoque":    "Estoque",
            "financeiro": "Financeiro",
            "crm":        "CRM",
        }
        for bot_key, tela_nome in mapa.items():
            tela = self._telas[tela_nome]

            def make_cb(t):
                def cb(_, dados):
                    self.after(0, lambda: t.refresh(dados))
                    self.after(0, self._update_status)
                return cb

            self.bot_manager.add_callback(bot_key, make_cb(tela))

    def _update_status(self):
        status = self.bot_manager.get_status()
        partes = []
        for nome, s in status.items():
            ico = "✓" if s["status"] == "ok" else "⟳" if s["status"] == "executando" else "✗"
            partes.append(f"{ico} {nome.capitalize()} {s['ultimo_update']}")
        self._lbl_bots.configure(text="  |  ".join(partes))

    def _tick_hora(self):
        self._lbl_hora.configure(text=datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))
        self.after(1000, self._tick_hora)

    def on_close(self):
        self.bot_manager.stop_all()
        db.disconnect()
        self.destroy()
