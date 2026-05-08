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

from config.settings import APP_TITLE, APP_VERSION, CORES, DB_CONFIG, ALERTAS, IS_HUB, HUB_URL, HUB_PORT
from core.database import db
from bots.analise_bots import BotManager
from core.exportador import exportar_excel

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = CORES  # alias curto


def _brl(val) -> str:
    """Formata valor como moeda Real brasileiro: R$ 1.234,56"""
    try:
        s = f"{float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {s}"
    except (TypeError, ValueError):
        return "—"


def _brl0(val) -> str:
    """Formata valor como Real sem casas decimais: R$ 1.234"""
    try:
        s = f"{float(val):,.0f}".replace(",", ".")
        return f"R$ {s}"
    except (TypeError, ValueError):
        return "—"


def _num(val) -> str:
    """Formata número inteiro com separador de milhar brasileiro: 1.234"""
    try:
        return f"{float(val):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


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
        self._mpl_canvas = None
        self._fig        = None

    def _clean(self):
        if self._mpl_canvas:
            self._mpl_canvas.get_tk_widget().destroy()
            self._mpl_canvas = None
        if self._fig:
            plt.close(self._fig)
            self._fig = None

    def _figsize(self, default_w=5.5, default_h=3.2):
        self.update_idletasks()
        px_w = self.winfo_width()
        px_h = self.winfo_height()
        if px_w > 50 and px_h > 60:
            return max((px_w - 12) / 100, default_w), max((px_h - 40) / 100, 2.0)
        return default_w, default_h

    def _on_configure(self, event):
        if not self._fig or not self._mpl_canvas or event.width < 20 or event.height < 20:
            return
        dpi = self._fig.get_dpi()
        self._fig.set_size_inches(event.width / dpi, event.height / dpi, forward=False)
        try:
            self._fig.tight_layout(pad=1.0)
        except Exception:
            pass
        self._mpl_canvas.draw_idle()

    def _attach_canvas(self, fig, canvas):
        self._fig = fig
        self._mpl_canvas = canvas
        self._mpl_canvas.draw_idle()
        w = self._mpl_canvas.get_tk_widget()
        w.pack(fill="both", expand=True, padx=6, pady=6)
        w.bind("<Configure>", self._on_configure, add="+")

    def barras(self, labels, valores, cor=C["accent_azul"], horizontal=False, fmt_val=None):
        self._clean()
        fw, fh = self._figsize()
        fig, ax = plt.subplots(figsize=(fw, fh))
        fig.patch.set_facecolor(C["card"])
        ax.set_facecolor(C["card"])
        _fmt = fmt_val if fmt_val else _num
        if horizontal:
            bars = ax.barh(labels[::-1], valores[::-1], color=cor, height=0.6)
            ax.tick_params(axis="y", labelsize=8, colors=C["subtext"])
            ax.tick_params(axis="x", labelsize=8, colors=C["subtext"])
            if valores:
                ax.set_xlim(0, max(valores) * 1.28)
            for bar, v in zip(bars, valores[::-1]):
                ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2,
                        f"  {_fmt(v)}", va="center", ha="left",
                        fontsize=7, color=C["subtext"])
        else:
            bars = ax.bar(labels, valores, color=cor, width=0.6, zorder=3)
            ax.tick_params(colors=C["subtext"], labelsize=8)
            ax.yaxis.grid(True, color=C["card_border"], zorder=0)
            ax.set_axisbelow(True)
            lbl_rot = 30 if len(labels) > 6 else 0
            ax.set_xticklabels(labels, rotation=lbl_rot, ha="right" if lbl_rot else "center")
            if valores:
                ax.set_ylim(0, max(valores) * 1.2)
            for bar, v in zip(bars, valores):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                        _fmt(v), va="bottom", ha="center",
                        fontsize=7, color=C["subtext"])
        ax.spines[:].set_visible(False)
        fig.tight_layout(pad=1.0)
        self._attach_canvas(fig, FigureCanvasTkAgg(fig, master=self))

    def linha(self, labels, valores, cor=C["accent_azul"], label_nome="Realizado"):
        self._clean()
        fw, fh = self._figsize()
        fig, ax = plt.subplots(figsize=(fw, fh))
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
        self._attach_canvas(fig, FigureCanvasTkAgg(fig, master=self))

    def donut(self, labels, valores, cores=None):
        self._clean()
        if not cores:
            cores = [C["accent_azul"], C["success"], C["warning"], C["accent_verm"], "#8b5cf6"]
        fw, fh = self._figsize(default_w=4.5, default_h=3.2)
        fig, ax = plt.subplots(figsize=(fw, fh))
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
        self._attach_canvas(fig, FigureCanvasTkAgg(fig, master=self))

    def barras_agrupadas(self, labels, series: dict):
        """series = {"Série A": [v1, v2, ...], "Série B": [v1, v2, ...]}"""
        self._clean()
        import numpy as np
        n_grupos = len(labels)
        n_series = len(series)
        if n_grupos == 0 or n_series == 0:
            return
        fw, fh = self._figsize(default_w=min(max(6.0, n_grupos * 0.5), 9.0), default_h=3.5)
        fig, ax = plt.subplots(figsize=(fw, fh))
        fig.patch.set_facecolor(C["card"])
        ax.set_facecolor(C["card"])
        x       = np.arange(n_grupos)
        largura = 0.8 / n_series
        paleta  = [C["accent_azul"], C["success"], C["warning"], C["accent_verm"], "#8b5cf6"]
        for idx, (nome, vals) in enumerate(series.items()):
            offset = (idx - (n_series - 1) / 2) * largura
            bars   = ax.bar(x + offset, vals, largura * 0.9,
                            label=nome, color=paleta[idx % len(paleta)], zorder=3)
            for bar, v in zip(bars, vals):
                if v and v > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                            _num(v), va="bottom", ha="center",
                            fontsize=6, color=C["subtext"])
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=7)
        ax.tick_params(colors=C["subtext"], labelsize=8)
        ax.yaxis.grid(True, color=C["card_border"], zorder=0)
        ax.set_axisbelow(True)
        ax.spines[:].set_visible(False)
        ax.legend(fontsize=8, facecolor=C["card"], labelcolor=C["text"], loc="upper right")
        fig.tight_layout(pad=1.0)
        self._attach_canvas(fig, FigureCanvasTkAgg(fig, master=self))


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
            if any(x in kw for x in ("fat", "valor", "total", "divida", "ticket", "custo", "rcbo", "vlr", "val_")):
                return _brl(val)
            return f"{val:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if isinstance(val, int):
            return f"{val:,}".replace(",", ".")
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


class TabelaVendMeta(ctk.CTkScrollableFrame):
    """Tabela de vendedores com coluna de meta individual editável por linha."""

    _HDRS = ["Vendedor", "Faturamento", "Pedidos", "Ticket Médio",
             "Meta Individual", "% Meta", "Devoluções"]

    def __init__(self, master, on_meta_change, **kw):
        super().__init__(master, fg_color=C["card"], corner_radius=10,
                         border_width=1, border_color=C["card_border"], **kw)
        self._on_meta_change = on_meta_change
        self._rows: list = []
        for j, col in enumerate(self._HDRS):
            ctk.CTkLabel(self, text=col.upper(),
                         font=ctk.CTkFont(size=9, weight="bold"),
                         text_color=C["subtext"]).grid(row=0, column=j, padx=8, pady=(8, 4), sticky="w")

    def populate(self, vendedores: list, meta_tot: float, metas_ind: dict):
        for row_ws in self._rows:
            for w in row_ws:
                w.destroy()
        self._rows.clear()
        n = len(vendedores)
        default = meta_tot / n if n else 0
        for i, r in enumerate(vendedores, start=1):
            cod  = str(r.get("CodVend", ""))
            fat  = float(r.get("total_venda", 0) or 0)
            meta = metas_ind.get(cod, default)
            pct  = round(fat / meta * 100, 1) if meta else 0
            cor_pct = C["success"] if pct >= 100 else C["warning"] if pct >= 80 else C["accent_verm"]
            qtd_dev = int(r.get("qtd_devolucoes", 0) or 0)
            rw = []

            for j, (txt, tc) in enumerate([
                (str(r.get("Vendedor", ""))[:20], C["text"]),
                (_brl(fat),                        C["accent_azul"]),
                (_num(r.get("qtd_pedidos", 0)),    C["text"]),
                (_brl(r.get("ticket_medio", 0)),   C["text"]),
            ]):
                lbl = ctk.CTkLabel(self, text=txt, font=ctk.CTkFont(size=10), text_color=tc)
                lbl.grid(row=i, column=j, padx=8, pady=2, sticky="w")
                rw.append(lbl)

            # Meta editável
            mv = ctk.StringVar(value=f"{meta:,.0f}".replace(",", "."))
            ent = ctk.CTkEntry(self, textvariable=mv, width=110, height=24,
                                fg_color=C["progress_bg"], border_color=C["card_border"],
                                text_color=C["text"], font=ctk.CTkFont(size=10))
            ent.grid(row=i, column=4, padx=8, pady=2, sticky="w")

            def _confirm(event=None, c=cod, v=mv, mt=meta_tot):
                raw = v.get().replace(".", "").replace(",", ".")
                try:
                    val = min(max(float(raw), 0.0), mt)
                    v.set(f"{val:,.0f}".replace(",", "."))
                    self._on_meta_change(c, val)
                except ValueError:
                    pass

            ent.bind("<Return>", _confirm)
            ent.bind("<FocusOut>", _confirm)
            rw.append(ent)

            # % meta
            pl = ctk.CTkLabel(self, text=f"{pct}%", font=ctk.CTkFont(size=10), text_color=cor_pct)
            pl.grid(row=i, column=5, padx=8, pady=2, sticky="w")
            rw.append(pl)

            # Devoluções
            dl = ctk.CTkLabel(self, text=str(qtd_dev), font=ctk.CTkFont(size=10),
                               text_color=C["accent_verm"] if qtd_dev > 0 else C["subtext"])
            dl.grid(row=i, column=6, padx=8, pady=2, sticky="w")
            rw.append(dl)
            self._rows.append(rw)


def _secao(master, texto: str):
    ctk.CTkLabel(master, text=texto,
                 font=ctk.CTkFont(size=12, weight="bold"),
                 text_color=C["subtext"]).pack(anchor="w", pady=(10, 4))


# ──────────────────────────────────────────────────────────────────
#  PLANO DROPDOWN  — seletor multi-plano estilo Power BI
# ──────────────────────────────────────────────────────────────────
class PlanoDropdown(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._vars: dict  = {}
        self._nomes: dict = {}
        self._popup       = None
        self._btn = ctk.CTkButton(
            self, text="Plano de Venda  ▼", width=220, height=30,
            fg_color=C["progress_bg"], border_color=C["card_border"], border_width=1,
            hover_color=C["card"], text_color=C["subtext"], font=ctk.CTkFont(size=10),
            anchor="w", command=self._toggle,
        )
        self._btn.pack(side="left")

    def carregar(self, df):
        for _, r in df.iterrows():
            cod = r["CodPlanoVnd"]
            self._nomes[cod] = str(r.get("NomePlanoVnd", ""))
            self._vars[cod]  = ctk.BooleanVar(value=False)

    def selecionados(self) -> list:
        return [c for c, v in self._vars.items() if v.get()]

    def _refresh_label(self):
        sel = self.selecionados()
        if not sel:
            self._btn.configure(text="Plano de Venda  ▼", text_color=C["subtext"])
        else:
            self._btn.configure(text=f"{len(sel)} plano(s)  ▼", text_color=C["text"])

    def _toggle(self):
        if self._popup and self._popup.winfo_exists():
            self._fechar()
        else:
            self._abrir()

    def _fechar(self):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
        self._popup = None

    def _abrir(self):
        self._btn.update_idletasks()
        x = self._btn.winfo_rootx()
        y = self._btn.winfo_rooty() + self._btn.winfo_height() + 2
        pop = ctk.CTkToplevel(self.winfo_toplevel())
        pop.wm_overrideredirect(True)
        pop.configure(fg_color=C["card"])
        pop.geometry(f"280x300+{x}+{y}")
        pop.attributes("-topmost", True)
        pop.lift()
        hdr = ctk.CTkFrame(pop, fg_color=C["sidebar"], corner_radius=0)
        hdr.pack(fill="x")
        var_all = ctk.BooleanVar(value=False)

        def _toggle_all():
            for v in self._vars.values():
                v.set(var_all.get())

        ctk.CTkCheckBox(
            hdr, text="Selecionar Todos", variable=var_all, command=_toggle_all,
            text_color=C["text"], font=ctk.CTkFont(size=10, weight="bold"),
            checkbox_height=16, checkbox_width=16,
        ).pack(anchor="w", padx=10, pady=8)
        ctk.CTkFrame(pop, fg_color=C["card_border"], height=1).pack(fill="x")
        scroll = ctk.CTkScrollableFrame(pop, fg_color=C["card"])
        scroll.pack(fill="both", expand=True)
        for cod, var in self._vars.items():
            nome = self._nomes.get(cod, "")[:28]
            ctk.CTkCheckBox(
                scroll, text=f"{cod}  ·  {nome}", variable=var,
                text_color=C["text"], font=ctk.CTkFont(size=10),
                checkbox_height=15, checkbox_width=15,
            ).pack(anchor="w", padx=8, pady=2)
        ctk.CTkFrame(pop, fg_color=C["card_border"], height=1).pack(fill="x")
        btns = ctk.CTkFrame(pop, fg_color=C["sidebar"], corner_radius=0)
        btns.pack(fill="x")

        def _aplicar():
            self._refresh_label()
            self._fechar()

        def _limpar():
            for v in self._vars.values():
                v.set(False)
            var_all.set(False)

        ctk.CTkButton(
            btns, text="Limpar", width=90, height=28,
            fg_color="transparent", text_color=C["subtext"],
            hover_color=C["card"], command=_limpar,
        ).pack(side="left", padx=8, pady=6)
        ctk.CTkButton(
            btns, text="Aplicar", width=90, height=28,
            fg_color=C["accent_azul"], command=_aplicar,
        ).pack(side="right", padx=8, pady=6)
        self._popup = pop


# ──────────────────────────────────────────────────────────────────
#  TELA DASHBOARD
# ──────────────────────────────────────────────────────────────────
class TelaDashboard(ctk.CTkFrame):
    def __init__(self, master, bot_manager):
        super().__init__(master, fg_color="transparent")
        self._bot_manager = bot_manager
        self._bot_status_labels: dict[str, ctk.CTkLabel] = {}
        self._ultimo_fat: float = 0.0
        self._build()
        self._tick_countdown()

    def _build(self):
        # KPIs
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 6))
        self.k_fat    = KpiCard(row1, "Faturamento do Mês", cor=C["accent_azul"])
        self.k_docs   = KpiCard(row1, "Documentos")
        self.k_cli    = KpiCard(row1, "Clientes Ativos", cor=C["success"])
        self.k_ticket = KpiCard(row1, "Ticket Médio")
        self.k_meta   = KpiCard(row1, "% da Meta")
        for k in (self.k_fat, self.k_docs, self.k_cli, self.k_ticket, self.k_meta):
            k.pack(side="left", fill="both", expand=True, padx=4)

        # Barra de configuração de meta
        meta_bar = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=8,
                                 border_width=1, border_color=C["card_border"])
        meta_bar.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(meta_bar, text="META MENSAL:",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=C["subtext"]).pack(side="left", padx=14, pady=8)
        self._meta_entry = ctk.CTkEntry(
            meta_bar, width=160, height=28,
            fg_color=C["progress_bg"], border_color=C["card_border"],
            text_color=C["text"], placeholder_text="Ex: 400000",
        )
        self._meta_entry.pack(side="left", padx=6, pady=8)
        self._meta_entry.insert(0, str(int(ALERTAS.get("meta_faturamento_mensal", 400000))))
        ctk.CTkButton(
            meta_bar, text="Aplicar", width=80, height=28,
            fg_color=C["accent_azul"],
            command=self._aplicar_meta,
        ).pack(side="left", padx=6, pady=8)
        self._lbl_meta_status = ctk.CTkLabel(
            meta_bar, text="", font=ctk.CTkFont(size=10),
            text_color=C["subtext"],
        )
        self._lbl_meta_status.pack(side="left", padx=10, pady=8)

        # Gráficos
        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="both", expand=True, pady=(0, 6))
        self.g_diario = Grafico(row2, "Faturamento Diário (30 dias)")
        self.g_diario.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.g_marcas = Grafico(row2, "Marcas Mais Vendidas — Mês (com Margem)")
        self.g_marcas.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.g_vend = Grafico(row2, "Top Vendedores do Mês")
        self.g_vend.pack(side="left", fill="both", expand=True)

        self._build_status_bar()

    def _build_status_bar(self):
        bar = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=8,
                           border_width=1, border_color=C["card_border"])
        bar.pack(fill="x", pady=(6, 0))

        ctk.CTkLabel(bar, text="📡 Bots:", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=C["subtext"]).pack(side="left", padx=(12, 6), pady=6)

        _nomes = {
            "dashboard":  "Dashboard",
            "vendas":     "Vendas",
            "estoque":    "Estoque",
            "financeiro": "Financeiro",
            "crm":        "CRM",
        }
        for key, nome in _nomes.items():
            lbl = ctk.CTkLabel(bar, text=f"{nome}  —",
                               font=ctk.CTkFont(size=10),
                               text_color=C["subtext"])
            lbl.pack(side="left", padx=14, pady=6)
            self._bot_status_labels[key] = lbl

    def _tick_countdown(self):
        for key, lbl in self._bot_status_labels.items():
            bot = self._bot_manager.bots.get(key)
            if bot is None:
                continue
            secs = bot.seconds_until_next()
            nome = key.capitalize()
            if bot.status == "executando" or secs == 0:
                text = f"{nome}  ⟳ atualizando"
                cor  = C["warning"]
            elif secs is None:
                text = f"{nome}  aguardando"
                cor  = C["subtext"]
            else:
                m, s = divmod(secs, 60)
                text = f"{nome}  ✓ {m}:{s:02d}"
                cor  = C["success"] if bot.status == "ok" else C["subtext"]
            lbl.configure(text=text, text_color=cor)
        self.after(1000, self._tick_countdown)

    def _aplicar_meta(self):
        raw = self._meta_entry.get().strip().replace(".", "").replace(",", ".")
        try:
            nova = float(raw)
            if nova <= 0:
                raise ValueError
        except ValueError:
            self._lbl_meta_status.configure(text="✗ Valor inválido", text_color=C["accent_verm"])
            return
        ALERTAS["meta_faturamento_mensal"] = nova
        pct = round(self._ultimo_fat / nova * 100, 1) if nova else 0
        cor = C["success"] if pct >= 100 else C["warning"] if pct >= 70 else C["accent_verm"]
        self.k_meta.update(f"{pct}%", f"Meta: {_brl0(nova)}", cor=cor)
        self.k_fat.update(_brl(self._ultimo_fat), f"{pct}% da meta")
        self._lbl_meta_status.configure(
            text=f"✓ Meta: {_brl0(nova)}", text_color=C["success"])

    def refresh(self, dados: dict):
        fat  = dados.get("faturamento_atual", 0)
        meta = ALERTAS.get("meta_faturamento_mensal", 400000)
        pct  = round(fat / meta * 100, 1) if meta else 0
        self._ultimo_fat = fat
        cor_meta = C["success"] if pct >= 100 else C["warning"] if pct >= 70 else C["accent_verm"]
        self.k_fat.update(_brl(fat), f"{pct}% da meta")
        self.k_docs.update(_num(dados.get("qtd_documentos", 0)))
        self.k_cli.update(_num(dados.get("clientes_ativos", 0)))
        self.k_ticket.update(_brl(dados.get("ticket_medio", 0)))
        self.k_meta.update(f"{pct}%", f"Meta: {_brl0(meta)}", cor=cor_meta)

        diario = dados.get("faturamento_diario", [])
        if diario:
            lbs = [str(r.get("dia", ""))[-5:] for r in diario]
            vs  = [float(r.get("faturamento", 0) or 0) for r in diario]
            self.g_diario.linha(lbs, vs)

        marcas = dados.get("marcas_mes", [])
        if marcas:
            lbs  = [str(r.get("DescrMarca", "?"))[:14] for r in marcas]
            vs   = [float(r.get("faturamento", 0) or 0) for r in marcas]
            mgns = [float(r.get("margem_bruta", 0) or 0) for r in marcas]
            lbs_fmt = [f"{l} | Mg {_brl0(m)}" for l, m in zip(lbs, mgns)]
            self.g_marcas.donut(lbs_fmt, vs)

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
        self._metas_ind: dict[str, float] = {}
        self._ultimo_vend_dados: list = []
        self._build()
        threading.Thread(target=self._carregar_planos, daemon=True).start()

    def _build(self):
        from datetime import date
        hoje     = date.today()
        primeiro = hoje.replace(day=1)

        # ── KPIs (5 cards) ────────────────────────────────────────────
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 6))
        self.k_fat    = KpiCard(row1, "Faturamento Total",    cor=C["accent_azul"])
        self.k_qtd    = KpiCard(row1, "Qtde de Vendas")
        self.k_ticket = KpiCard(row1, "Ticket Médio")
        self.k_dev    = KpiCard(row1, "Total Devoluções",     cor=C["accent_verm"])
        self.k_mar    = KpiCard(row1, "Margem Bruta",         cor=C["success"])
        for k in (self.k_fat, self.k_qtd, self.k_ticket, self.k_dev, self.k_mar):
            k.pack(side="left", fill="both", expand=True, padx=4)

        # ── Filtro por período ─────────────────────────────────────────
        filtro_bar = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=8,
                                   border_width=1, border_color=C["card_border"])
        filtro_bar.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(filtro_bar, text="PERÍODO:",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=C["subtext"]).pack(side="left", padx=14, pady=8)
        ctk.CTkLabel(filtro_bar, text="De:", text_color=C["subtext"],
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 4), pady=8)
        self._de_entry = ctk.CTkEntry(
            filtro_bar, width=100, height=28,
            fg_color=C["progress_bg"], border_color=C["card_border"],
            text_color=C["text"], placeholder_text="DD/MM/AAAA",
        )
        self._de_entry.pack(side="left", padx=(0, 8), pady=8)
        self._de_entry.insert(0, primeiro.strftime("%d/%m/%Y"))
        ctk.CTkLabel(filtro_bar, text="Até:", text_color=C["subtext"],
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 4), pady=8)
        self._ate_entry = ctk.CTkEntry(
            filtro_bar, width=100, height=28,
            fg_color=C["progress_bg"], border_color=C["card_border"],
            text_color=C["text"], placeholder_text="DD/MM/AAAA",
        )
        self._ate_entry.pack(side="left", padx=(0, 8), pady=8)
        self._ate_entry.insert(0, hoje.strftime("%d/%m/%Y"))
        ctk.CTkButton(
            filtro_bar, text="Buscar", width=80, height=28,
            fg_color=C["accent_azul"],
            command=self._buscar_periodo,
        ).pack(side="left", padx=4, pady=8)
        self._lbl_periodo = ctk.CTkLabel(
            filtro_bar, text="Exibindo: este mês (bot automático)",
            font=ctk.CTkFont(size=10), text_color=C["subtext"],
        )
        self._lbl_periodo.pack(side="left", padx=12, pady=8)

        # ── Filtro por plano de venda ──────────────────────────────────
        plano_bar = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=8,
                                  border_width=1, border_color=C["card_border"])
        plano_bar.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(plano_bar, text="PLANO DE VENDA:",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=C["subtext"]).pack(side="left", padx=14, pady=8)
        self._plano_drop = PlanoDropdown(plano_bar)
        self._plano_drop.pack(side="left", padx=6, pady=8)

        # ── Gráficos ──────────────────────────────────────────────────
        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="both", expand=True, pady=(0, 8))
        self.g_marca = Grafico(row2, "Faturamento por Marca (R$)")
        self.g_marca.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.g_grupo = Grafico(row2, "Faturamento por Grupo (R$)")
        self.g_grupo.pack(side="left", fill="both", expand=True)

        # ── Tabela de vendedores ───────────────────────────────────────
        _secao(self, "TOP VENDEDORES — clique em Meta Individual para editar (máx = meta do Dashboard)")
        self.tab_vend = TabelaVendMeta(
            self, on_meta_change=self._on_meta_change, height=220,
        )
        self.tab_vend.pack(fill="x")

    def _on_meta_change(self, cod_vend: str, nova_meta: float):
        self._metas_ind[cod_vend] = nova_meta
        if self._ultimo_vend_dados:
            meta_tot = ALERTAS.get("meta_faturamento_mensal", 400000)
            self.tab_vend.populate(self._ultimo_vend_dados, meta_tot, self._metas_ind)

    def _carregar_planos(self):
        from config.settings import IS_HUB, HUB_URL
        if HUB_URL and not IS_HUB:
            return  # client mode — no direct DB access
        import time as _t
        _t.sleep(0.5)  # ensure mainloop has started before calling self.after()
        df = None
        for _ in range(15):
            df = db.mapear_planos()
            if not df.empty:
                break
            _t.sleep(2)
        if df is None or df.empty:
            return
        self.after(0, lambda: self._plano_drop.carregar(df))

    def _buscar_periodo(self):
        from datetime import datetime as dt2
        def _parse(s):
            return dt2.strptime(s.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
        try:
            ini = _parse(self._de_entry.get())
            fim = _parse(self._ate_entry.get())
        except ValueError:
            self._lbl_periodo.configure(
                text="✗ Data inválida. Use DD/MM/AAAA", text_color=C["accent_verm"])
            return
        self._lbl_periodo.configure(
            text=f"⟳ Buscando {ini} → {fim}...", text_color=C["warning"])
        planos = self._plano_drop.selecionados()
        filtro = f"i.DtVnd BETWEEN '{ini}' AND '{fim}'"
        def task():
            from bots.analise_bots import BotVendas
            _bot = BotVendas()
            dados = _bot.analisar(
                filtro_data=filtro,
                planos_filter=planos if planos else None,
            )
            de_fmt  = self._de_entry.get().strip()
            ate_fmt = self._ate_entry.get().strip()
            self.after(0, lambda: self._lbl_periodo.configure(
                text=f"Exibindo: {de_fmt} → {ate_fmt}", text_color=C["success"]))
            self.after(0, lambda: self.refresh(dados))
        threading.Thread(target=task, daemon=True).start()

    def refresh(self, dados: dict):
        self.k_fat.update(_brl(dados.get("faturamento_total", 0)))
        self.k_qtd.update(_num(dados.get("qtd_vendas", 0)))
        self.k_ticket.update(_brl(dados.get("ticket_medio", 0)))
        self.k_dev.update(_brl(dados.get("total_devolucoes", 0)))
        self.k_mar.update(_brl(dados.get("margem_total", 0)))

        marcas = dados.get("por_marca", [])
        if marcas:
            lbs = [str(r.get("DescrMarca", "?"))[:14] for r in marcas[:10]]
            vs  = [float(r.get("faturamento", 0) or 0) for r in marcas[:10]]
            self.g_marca.barras(lbs, vs, fmt_val=_brl)

        grupos = dados.get("por_grupo", [])
        if grupos:
            lbs = [str(r.get("DescrGrpItem", "?"))[:14] for r in grupos[:10]]
            vs  = [float(r.get("faturamento", 0) or 0) for r in grupos[:10]]
            self.g_grupo.barras(lbs, vs, cor=C["warning"], fmt_val=_brl)

        vendedores = dados.get("por_vendedor", [])
        if vendedores:
            self._ultimo_vend_dados = vendedores
            meta_tot = ALERTAS.get("meta_faturamento_mensal", 400000)
            n = len(vendedores)
            default = meta_tot / n if n else 0
            for r in vendedores:
                cod = str(r.get("CodVend", ""))
                if cod not in self._metas_ind:
                    self._metas_ind[cod] = default
            self.tab_vend.populate(vendedores, meta_tot, self._metas_ind)


# ──────────────────────────────────────────────────────────────────
#  TELA ESTOQUE
# ──────────────────────────────────────────────────────────────────
class TelaEstoque(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._criticos_dados: list = []
        self._ultimo_dados: dict = {}
        self._build()

    def _build(self):
        # ── KPIs ──────────────────────────────────────────────────────
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 8))
        self.k_itens = KpiCard(row1, "Total Itens")
        self.k_valor = KpiCard(row1, "Valor em Estoque", cor=C["accent_azul"])
        self.k_zero  = KpiCard(row1, "Itens Zerados",    cor=C["accent_verm"])
        self.k_giro  = KpiCard(row1, "Sem Giro +90d",    cor=C["warning"])
        for k in (self.k_itens, self.k_valor, self.k_zero, self.k_giro):
            k.pack(side="left", fill="both", expand=True, padx=4)

        # ── Abas de análise ───────────────────────────────────────────
        self._tabs = ctk.CTkTabview(
            self,
            fg_color=C["bg"],
            segmented_button_fg_color=C["sidebar"],
            segmented_button_selected_color=C["accent_azul"],
            segmented_button_unselected_color=C["sidebar"],
            segmented_button_selected_hover_color=C["accent_azul"],
            text_color=C["text"],
        )
        self._tabs.pack(fill="both", expand=True, pady=(0, 8))

        # Aba 1 — Visão Geral
        t1 = self._tabs.add("Visão Geral")
        row_t1 = ctk.CTkFrame(t1, fg_color="transparent")
        row_t1.pack(fill="both", expand=True)
        self.g_marca = Grafico(row_t1, "Valor em Estoque por Marca (R$)")
        self.g_marca.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.g_mov   = Grafico(row_t1, "Saídas por Item — 30 dias (qtd)")
        self.g_mov.pack(side="left", fill="both", expand=True)

        # Aba 2 — Venda × Estoque
        t2 = self._tabs.add("Venda × Estoque")
        self.g_venda_estq = Grafico(t2, "Qtd Vendida (90d) vs Estoque Disponível — Top 15")
        self.g_venda_estq.pack(fill="both", expand=True)

        # Aba 3 — Orç × Estoque
        t3 = self._tabs.add("Orc × Estoque")
        self.g_orc_estq = Grafico(t3, "Qtd Orçada (últimos 30 dias) vs Estoque Disponível — Top 15")
        self.g_orc_estq.pack(fill="both", expand=True)

        # Aba 4 — Venda × Compra
        t4 = self._tabs.add("Venda × Compra")
        self.g_venda_compra = Grafico(t4, "Saídas (vendas) vs Entradas (compras) — 30 dias")
        self.g_venda_compra.pack(fill="both", expand=True)

        # Aba 5 — Média Semanal
        t5 = self._tabs.add("Média Semanal")
        self.tab_media = Tabela(
            t5,
            ["CodItem", "DescrItem", "DescrMarca", "media_semanal", "QtdEstqDisp", "semanas_cobertura"],
            height=360,
        )
        self.tab_media.pack(fill="both", expand=True, padx=4, pady=4)

        # Aba 6 — Sugestão de Transferência
        t6 = self._tabs.add("Sugestão Transf.")
        _secao(t6, "Sugestão de transferência de estoque")
        self._frm_sug = ctk.CTkFrame(t6, fg_color="transparent")
        self._frm_sug.pack(fill="both", expand=True)

        # Aba 7 — OS Pendentes
        t7 = self._tabs.add("OS Pendentes")
        _secao(t7, "Ordens de serviço com estoque temporário")
        self._frm_os = ctk.CTkFrame(t7, fg_color="transparent")
        self._frm_os.pack(fill="both", expand=True)

        # ── Itens críticos com filtro ─────────────────────────────────
        _secao(self, "ITENS CRÍTICOS (sem giro ou zerados)")

        filtro_row = ctk.CTkFrame(self, fg_color="transparent")
        filtro_row.pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(filtro_row, text="Filtrar:",
                     text_color=C["subtext"],
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
        self._filtro_var = ctk.StringVar()
        self._filtro_var.trace_add("write", lambda *_: self._aplicar_filtro())
        ctk.CTkEntry(
            filtro_row,
            textvariable=self._filtro_var,
            placeholder_text="Pesquisar por descrição, marca ou código...",
            width=340, height=28,
            fg_color=C["card"],
            border_color=C["card_border"],
            text_color=C["text"],
        ).pack(side="left")

        self.tab_crit = Tabela(
            self,
            ["CodItem", "DescrItem", "DescrMarca", "QtdEstq", "QtdEstqDisp",
             "DiasSemVnd", "VlrEstq", "FornecUltCmp"],
            height=200,
        )
        self.tab_crit.pack(fill="x")

    def _render_dyn_tab(self, frame, dados: list, attr: str):
        old = getattr(self, attr, None)
        if old is not None:
            old.destroy()
            setattr(self, attr, None)
        if not dados:
            return
        cols = list(dados[0].keys())
        tab = Tabela(frame, cols, height=300)
        tab.pack(fill="both", expand=True)
        tab.populate(dados[:200])
        setattr(self, attr, tab)

    def _aplicar_filtro(self):
        termo = self._filtro_var.get().strip().lower()
        dados = self._criticos_dados
        if termo:
            dados = [
                r for r in dados
                if termo in str(r.get("DescrItem",  "")).lower()
                or termo in str(r.get("DescrMarca", "")).lower()
                or termo in str(r.get("CodItem",    "")).lower()
            ]
        self.tab_crit.populate(dados[:100])

    def refresh(self, dados: dict):
        self._ultimo_dados = dados

        # KPIs — imediato
        self.k_itens.update(str(dados.get("total_itens", 0)))
        self.k_valor.update(_brl(dados.get("valor_total_estoque", 0)))
        self.k_zero.update(str(dados.get("itens_zerados", 0)))
        self.k_giro.update(str(dados.get("itens_sem_giro", 0)))

        # Aba 1 — Visão Geral (marcas + movimentação + críticos) — imediato
        marcas = dados.get("por_marca", [])
        if marcas:
            lbs = [str(r.get("DescrMarca", "?"))[:14] for r in marcas[:10]]
            vs  = [float(r.get("valor_estoque", 0) or 0) for r in marcas[:10]]
            self.g_marca.barras(lbs, vs, cor=C["accent_azul"], horizontal=True, fmt_val=_brl)

        mov = dados.get("movimentacao", [])
        if mov:
            lbs = [str(r.get("DescrItem", "?"))[:12] for r in mov[:10]]
            vs  = [float(r.get("saidas", 0) or 0) for r in mov[:10]]
            self.g_mov.barras(lbs, vs, cor=C["success"])

        self._criticos_dados = dados.get("criticos", [])
        self._aplicar_filtro()

        # Abas 2–7 — diferidas 10ms para não travar o frame atual
        self.after(10, lambda d=dados: self._refresh_secondary(d))

    def _refresh_secondary(self, dados: dict):
        """Renderiza abas 2–7 no próximo ciclo do event loop, evitando freeze."""
        # Aba 2 — Venda × Estoque
        ve = dados.get("venda_estoque", [])
        if ve:
            lbs   = [str(r.get("DescrItem", r.get("CodItem", "?")))[:14] for r in ve[:15]]
            vs_vd = [float(r.get("qtd_vendida_90d", 0) or 0) for r in ve[:15]]
            vs_eq = [float(r.get("QtdEstqDisp",     0) or 0) for r in ve[:15]]
            self.g_venda_estq.barras_agrupadas(lbs, {"Vendido 90d": vs_vd, "Estq Disp": vs_eq})

        # Aba 3 — Orç × Estoque
        oe = dados.get("orc_estoque", [])
        if oe:
            lbs   = [str(r.get("DescrItem", r.get("CodItem", "?")))[:14] for r in oe[:15]]
            vs_oc = [float(r.get("qtd_orcada",  0) or 0) for r in oe[:15]]
            vs_eq = [float(r.get("QtdEstqDisp", 0) or 0) for r in oe[:15]]
            self.g_orc_estq.barras_agrupadas(lbs, {"Orçado (mês)": vs_oc, "Estq Disp": vs_eq})

        # Aba 4 — Venda × Compra
        vc = dados.get("venda_compra", [])
        if vc:
            lbs   = [str(r.get("DescrItem", "?"))[:14] for r in vc[:15]]
            vs_sa = [float(r.get("saidas",   0) or 0) for r in vc[:15]]
            vs_en = [float(r.get("entradas", 0) or 0) for r in vc[:15]]
            self.g_venda_compra.barras_agrupadas(lbs, {"Saídas": vs_sa, "Entradas": vs_en})

        # Aba 5 — Média Semanal
        ms = dados.get("media_semanal", [])
        if ms:
            self.tab_media.populate(ms[:100])

        # Aba 6 — Sugestão Transf. / Aba 7 — OS Pendentes
        self._render_dyn_tab(self._frm_sug, dados.get("sugestao_transferencia", []), "_tab_sug_inst")
        self._render_dyn_tab(self._frm_os,  dados.get("estq_os", []),               "_tab_os_inst")


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

        self._tabs_fin = ctk.CTkTabview(
            col_r,
            fg_color=C["bg"],
            segmented_button_fg_color=C["sidebar"],
            segmented_button_selected_color=C["accent_azul"],
            segmented_button_unselected_color=C["sidebar"],
            segmented_button_selected_hover_color=C["accent_azul"],
            text_color=C["text"],
        )
        self._tabs_fin.pack(fill="both", expand=True)

        tab_in = self._tabs_fin.add("Inadimplentes")
        self.tab_inad = Tabela(
            tab_in,
            ["NomeFantCli", "divida_total", "qtd_titulos", "max_dias_atraso"],
            height=380,
        )
        self.tab_inad.pack(fill="both", expand=True)

        tab_av = self._tabs_fin.add("A Vencer")
        self.tab_a_vencer = Tabela(
            tab_av,
            ["NomeFantCli", "a_vencer_total", "qtd_titulos", "proximo_vencimento"],
            height=380,
        )
        self.tab_a_vencer.pack(fill="both", expand=True)

    def refresh(self, dados: dict):
        self.k_rec.update(_brl(dados.get("recebido_mes", 0)))
        self.k_atra.update(_brl(dados.get("em_atraso", 0)),
                           f"{_num(dados.get('titulos_atrasados', 0))} títulos")
        self.k_venc.update(_brl(dados.get("a_vencer", 0)))
        self.k_pmr.update(f"{dados.get('prazo_medio_receb', 0)} dias")
        self.k_inad.update(_brl(dados.get("total_inadimplencia", 0)),
                           f"{_num(dados.get('qtd_inadimplentes', 0))} clientes")

        tipos = dados.get("por_tipo_recebimento", [])
        if tipos:
            lbs = [str(r.get("TipoRcbo", "?")) for r in tipos]
            vs  = [float(r.get("total", 0) or 0) for r in tipos]
            self.g_tipo.donut(lbs, vs)

        self.tab_inad.populate(dados.get("top_inadimplentes", [])[:50])
        self.tab_a_vencer.populate(dados.get("a_vencer_lista", [])[:30])


# ──────────────────────────────────────────────────────────────────
#  TELA CRM
# ──────────────────────────────────────────────────────────────────
class TelaCRM(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._inativos_dados: list = []
        self._sort_desc: bool = True
        self._build()

    def _build(self):
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 10))
        self.k_vorc  = KpiCard(row1, "Valor Orçado (mês)",     cor=C["warning"])
        self.k_vcvt  = KpiCard(row1, "Valor Convertido (mês)", cor=C["success"])
        self.k_conv  = KpiCard(row1, "Taxa de Conversão",      cor=C["accent_azul"])
        self.k_risco = KpiCard(row1, "Clientes em Risco",      cor=C["warning"])
        self.k_inat  = KpiCard(row1, "Inativos",               cor=C["accent_verm"])
        for k in (self.k_vorc, self.k_vcvt, self.k_conv, self.k_risco, self.k_inat):
            k.pack(side="left", fill="both", expand=True, padx=4)

        _tabs_crm_g = ctk.CTkTabview(
            self,
            fg_color=C["bg"],
            segmented_button_fg_color=C["sidebar"],
            segmented_button_selected_color=C["accent_azul"],
            segmented_button_unselected_color=C["sidebar"],
            segmented_button_selected_hover_color=C["accent_azul"],
            text_color=C["text"],
        )
        _tabs_crm_g.pack(fill="both", expand=True, pady=(0, 8))
        tg1 = _tabs_crm_g.add("Funil de Conversão")
        self.g_funil = Grafico(tg1, "Funil de Conversão (mês)")
        self.g_funil.pack(fill="both", expand=True)
        tg2 = _tabs_crm_g.add("Faixas de Inatividade")
        self.g_faixas = Grafico(tg2, "Clientes por Faixa de Inatividade")
        self.g_faixas.pack(fill="both", expand=True)
        tg3 = _tabs_crm_g.add("Status Vendedores")
        self.g_vend_status = Grafico(tg3, "Status dos Vendedores — Meta vs Realizado")
        self.g_vend_status.pack(fill="both", expand=True)

        _secao(self, "CLIENTES INATIVOS / EM RISCO (30-60-90-120+ dias)")
        sort_bar = ctk.CTkFrame(self, fg_color="transparent")
        sort_bar.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(sort_bar, text="Ordenar por dias sem compra:",
                     text_color=C["subtext"], font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            sort_bar, text="↓ Mais inativos primeiro", width=160, height=26,
            fg_color=C["accent_verm"], text_color=C["text"], font=ctk.CTkFont(size=10),
            command=lambda: self._aplicar_sort(True),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            sort_bar, text="↑ Mais recentes primeiro", width=160, height=26,
            fg_color=C["progress_bg"], text_color=C["subtext"], font=ctk.CTkFont(size=10),
            border_width=1, border_color=C["card_border"],
            command=lambda: self._aplicar_sort(False),
        ).pack(side="left", padx=4)
        self.tab_inat = Tabela(
            self,
            ["nome_cliente", "razao_social", "ultima_compra", "dias_sem_compra",
             "total_pedidos", "ticket_medio"],
            height=200,
        )
        self.tab_inat.pack(fill="x")

    def _aplicar_sort(self, desc: bool):
        self._sort_desc = desc
        self._repopular_inat()

    def _repopular_inat(self):
        dados = sorted(
            self._inativos_dados,
            key=lambda r: float(r.get("dias_sem_compra", 0) or 0),
            reverse=self._sort_desc,
        )
        self.tab_inat.populate(dados[:150])

    def refresh(self, dados: dict):
        self.k_vorc.update(_brl(dados.get("valor_orcado", 0)))
        self.k_vcvt.update(_brl(dados.get("valor_convertido", 0)))
        pct = dados.get("taxa_conversao_pct", 0)
        cor = C["success"] if pct >= 50 else C["warning"] if pct >= 25 else C["accent_verm"]
        orc = dados.get("total_orcamentos", 0)
        cvt = dados.get("total_convertidos", 0)
        self.k_conv.update(f"{pct}%", subtitulo=f"{_num(cvt)} de {_num(orc)} orçamentos", cor=cor)
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

        mv = dados.get("meta_vendedor", [])
        if mv:
            lbs = [str(r.get("categoria", "?")) for r in mv]
            vs  = [int(r.get("qtd", 0)) for r in mv]
            _cor_map = {
                "Acima da Meta":    C["success"],
                "Próximo (80-99%)": C["warning"],
                "Abaixo da Meta":   C["accent_verm"],
                "Sem Meta":         C["subtext"],
            }
            cores = [_cor_map.get(l, C["accent_azul"]) for l in lbs]
            self.g_vend_status.donut(lbs, vs, cores=cores)

        self._inativos_dados = dados.get("inativos_lista", [])
        self._repopular_inat()


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
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # use_hub=True only when this machine is NOT the hub AND a hub URL is configured
        self.bot_manager = BotManager(use_hub=(not IS_HUB and bool(HUB_URL)))
        self._telas: dict[str, ctk.CTkFrame] = {}
        self._sidebar_btns: dict[str, ctk.CTkButton] = {}
        self._tela_atual = ""

        self._build_layout()
        self.after(150, self._connect_and_start)

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

        ctk.CTkFrame(self._sidebar, fg_color="transparent").pack(fill="y", expand=True)
        ctk.CTkButton(
            self._sidebar,
            text="  ✕  Sair",
            anchor="w",
            width=180, height=38,
            fg_color=C["accent_verm"],
            hover_color="#b91c1c",
            text_color=C["text"],
            font=ctk.CTkFont(size=13),
            command=self.on_close,
        ).pack(padx=10, pady=(2, 16))

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
        footer = ctk.CTkFrame(content_wrap, fg_color=C["card"], height=52, corner_radius=0)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self._lbl_bots = ctk.CTkLabel(footer, text="Bots: aguardando conexão...",
                                       font=ctk.CTkFont(size=10),
                                       text_color=C["subtext"])
        self._lbl_bots.pack(side="left", padx=16, pady=(6, 0))
        self._lbl_erros = ctk.CTkLabel(footer, text="",
                                        font=ctk.CTkFont(size=10),
                                        text_color=C["accent_verm"])
        self._lbl_erros.pack(side="left", padx=16, pady=(0, 6))

        # Cria telas (não visíveis ainda)
        self._telas = {
            "Dashboard":  TelaDashboard(self._frame_telas, self.bot_manager),
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
        self._register_callbacks()          # register UI callbacks on main thread
        self.bot_manager.load_from_cache()  # now callbacks exist, instant display works

        if IS_HUB:
            # Hub mode: start real bots + REST server in background thread
            def hub_task():
                import uvicorn
                import hub.server as _hs
                _hs._manager = self.bot_manager
                self.bot_manager.start_all()
                uvicorn.run(_hs.app, host="0.0.0.0", port=HUB_PORT, log_level="warning")
            t = threading.Thread(target=hub_task, daemon=True)
            t.start()
            self.after(0, lambda: self._lbl_status.configure(
                text=f"● Hub ativo — porta {HUB_PORT}", text_color=C["success"]))

        elif HUB_URL:
            # Client mode: HubPollerBots poll hub; no direct DB connection needed
            self.bot_manager.start_all()
            self.after(0, lambda: self._lbl_status.configure(
                text=f"● Cliente conectado ao hub {HUB_URL}", text_color=C["success"]))

        else:
            # Standalone mode: original behavior — connect to DB + start real bots
            def task():
                ok = db.connect()
                if not ok:
                    self.after(0, lambda: self._lbl_status.configure(
                        text=f"● Erro — DSN: {DB_CONFIG['dsn']}", text_color=C["accent_verm"]))
                    self.after(0, lambda: messagebox.showerror(
                        "Erro de Conexão",
                        f"Não foi possível conectar via DSN '{DB_CONFIG['dsn']}'.\n"
                        "Verifique usuário/senha em config/settings.py",
                    ))
                    return

                # Testa acesso real ao banco Blue antes de iniciar os bots
                df_test = db.query("SELECT TOP 1 NrDoc FROM Blue.dbo.vmVndDoc")
                if df_test.empty and db.last_error:
                    msg = f"● Conectado | Blue inacessível: {db.last_error[:60]}"
                    self.after(0, lambda m=msg: self._lbl_status.configure(
                        text=m, text_color=C["warning"]))
                    self.after(0, lambda: messagebox.showwarning(
                        "Aviso de Acesso",
                        f"Conexão estabelecida, mas a query de teste falhou:\n\n{db.last_error}\n\n"
                        "Verifique se o DSN aponta para o banco correto e se o usuário tem permissão.",
                    ))
                else:
                    self.after(0, lambda: self._lbl_status.configure(
                        text="● Conectado ao Blue", text_color=C["success"]))

                # self._register_callbacks() — moved to main thread before load_from_cache()
                self.bot_manager.start_all()

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
        erros = []
        for nome, s in status.items():
            ico = "✓" if s["status"] == "ok" else "⟳" if s["status"] == "executando" else "✗"
            partes.append(f"{ico} {nome.capitalize()} {s['ultimo_update']}")
            if s.get("erro_msg"):
                erros.append(f"[{nome}] {s['erro_msg'][:70]}")
        self._lbl_bots.configure(text="  |  ".join(partes))
        self._lbl_erros.configure(text=erros[0] if erros else "")

    def _tick_hora(self):
        self._lbl_hora.configure(text=datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))
        self.after(1000, self._tick_hora)

    def on_close(self):
        self.bot_manager.stop_all()
        db.disconnect()
        for after_id in self.tk.eval("after info").split():
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        self.destroy()
